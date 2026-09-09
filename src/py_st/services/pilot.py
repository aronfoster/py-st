"""Foreground earning decisions under one session's unchanged budgets."""

from __future__ import annotations

import logging
import math
import shlex
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from py_st.services.automation import SafetyStop, Session
from py_st.services.earning import earn_run


def pilot_run(
    run: Session,
    system: str,
    steps: int = 10,
    max_age: int = 900,
    *,
    reposition: bool = False,
) -> dict[str, Any]:
    """Count returned earn decisions, not trades; exceptions never retry.

    Dry runs inspect one decision. A fresh invocation recovers positions via
    earn_run, never by replaying this run's recorded decisions.
    """
    if not 1 <= steps <= 100 or not 1 <= max_age <= 86400:
        raise ValueError("Bounds: 1..100 steps, 1..86400 max-age seconds")
    initial_actions = run.remaining
    seconds = max(1, min(7200, math.ceil(run.deadline - time.monotonic())))
    command = [
        "python",
        "-m",
        "py_st",
        "auto",
        "pilot",
        system,
        "--steps",
        str(steps),
        "--seconds",
        str(seconds),
        "--actions",
        str(max(1, initial_actions)),
        "--max-age",
        str(max_age),
    ]
    if run.execute:
        command.append("--execute")
    if reposition:
        command.append("--reposition")
    record: dict[str, Any] = {
        "id": str(uuid4()),
        "system": system,
        "execute": run.execute,
        "reposition": reposition,
        "steps": steps,
        "max_age": max_age,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "completed_steps": 0,
        "outcome": "starting",
        "last_decision": None,
        "action_limit": initial_actions,
        "resume_command": shlex.join(command),
        "resume_instructions": (
            "Start a new bounded run from fresh state with resume_command. "
            "Review blockers and deliberately remove STOP only when ready; "
            "reconcile pending actions first. Never replay recorded decisions."
        ),
    }

    def persist() -> None:
        record.update(
            updated_at=datetime.now(UTC).isoformat(),
            actions_used=initial_actions - run.remaining,
            remaining_actions=run.remaining,
            remaining_seconds=max(0, run.deadline - time.monotonic()),
        )
        # Authentication may fail before a valid reset/agent scope exists.
        if run.scope:
            run.store.observe(
                run.scope, "automation_run", record["id"], record, "pilot"
            )

    unwinding = False
    try:
        run.check()
        if not run.scope:
            run.refresh()
        persist()
        for _ in range(steps if run.execute else 1):
            run.check()
            if run.execute and run.remaining <= 0:
                raise SafetyStop(
                    "Action budget exhausted; resume from live state"
                )
            decision = earn_run(
                run, system, cycles=1, max_age=max_age, reposition=reposition
            )
            record.update(
                completed_steps=record["completed_steps"] + 1,
                last_decision=decision,
                outcome=decision["status"],
            )
            persist()
            run.check()
            if not run.execute:
                record.update(status="completed", outcome="dry run")
                break
            if decision["status"] in (
                "no ready routes or scout targets",
                "reposition blocked",
            ):
                record["status"] = "stopped"
                break
            if decision["status"] not in ("cycle limit", "recovery only"):
                raise SafetyStop("Unexpected earn outcome; inspect run")
        else:
            record.update(status="completed", outcome="step limit")
    except BaseException as exc:
        unwinding = True
        record.update(
            status=(
                "stopped"
                if isinstance(exc, SafetyStop)
                else (
                    "interrupted"
                    if isinstance(exc, KeyboardInterrupt | SystemExit)
                    else "failed"
                )
            ),
            outcome=(
                str(exc) if isinstance(exc, SafetyStop) else type(exc).__name__
            ),
        )
        raise
    finally:
        record["finished_at"] = datetime.now(UTC).isoformat()
        try:
            persist()
        except sqlite3.Error as exc:
            logging.getLogger(__name__).error(
                "Pilot terminal persistence failed: %s", type(exc).__name__
            )
            if not unwinding:
                raise
    return record
