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
from py_st.services.strategies import contract_run


def pilot_run(
    run: Session,
    system: str,
    steps: int = 10,
    max_age: int = 900,
    *,
    reposition: bool = False,
    recover_contracts: bool = False,
) -> dict[str, Any]:
    """Count returned earn decisions, not trades; exceptions never retry.

    Dry runs inspect one decision. A fresh invocation recovers positions via
    earn_run or explicit procurement recovery, never by replaying records.
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
    if recover_contracts:
        command.append("--recover-contracts")
    record: dict[str, Any] = {
        "id": str(uuid4()),
        "system": system,
        "execute": run.execute,
        "reposition": reposition,
        "recover_contracts": recover_contracts,
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
            original = None
            if recover_contracts:
                state = run.refresh()
                if run.store.pending(run.scope):
                    raise SafetyStop(
                        "Pending action requires explicit reconciliation"
                    )
                positions = [
                    p
                    for p in run.store.latest(run.scope, "position")
                    if p["data"].get("status") != "closed"
                ]
                if any(p["key"].startswith("procurement:") for p in positions):
                    if (
                        len(positions) != 1
                        or positions[0]["data"].get("status") != "open"
                    ):
                        raise SafetyStop(
                            "Multiple/unknown positions; inspect recovery"
                        )
                    original = positions[0]["data"].get("plan")
                    if (
                        not isinstance(original, dict)
                        or any(
                            not isinstance(original.get(k), str)
                            or not original[k].strip()
                            for k in ("ship", "source", "contract")
                        )
                        or positions[0]["key"]
                        != f"procurement:{original['contract']}"
                    ):
                        raise SafetyStop(
                            "Invalid original procurement identity"
                        )
                    contracts = state["contracts"]
                    if (
                        sum(
                            c.get("id") == original["contract"]
                            for c in contracts
                        )
                        != 1
                        or sum(
                            s.get("symbol") == original["ship"]
                            for s in state["ships"]
                        )
                        != 1
                        or any(
                            type(c.get(k)) is not bool
                            for c in contracts
                            for k in ("accepted", "fulfilled")
                        )
                    ):
                        raise SafetyStop(
                            "Ambiguous procurement ship/contracts or statuses"
                        )
                    if any(
                        c["accepted"]
                        and not c["fulfilled"]
                        and c["id"] != original["contract"]
                        for c in contracts
                    ):
                        raise SafetyStop(
                            "Other accepted contracts need review"
                        )
            if original is not None:
                result = contract_run(
                    run,
                    original["ship"],
                    original["contract"],
                    original["source"],
                )
                if run.execute and result.get("status") != "fulfilled":
                    raise SafetyStop(
                        "Unexpected contract outcome; inspect run"
                    )
                decision = {
                    "status": "recovery only" if run.execute else "dry run",
                    "kind": "contract recovery",
                    "result": result,
                }
            else:
                decision = earn_run(
                    run,
                    system,
                    cycles=1,
                    max_age=max_age,
                    reposition=reposition,
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
