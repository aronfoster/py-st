"""Offline recorded-state triage, never a readiness or process monitor.

Exit 0 means no recorded concerns, 1 attention, 2 invalid/unavailable input.
Per-key observations cannot prove fleet/contract list completeness or live
scope. Missing contract rows are unknown, not a freshly verified empty list.
SQLite mode=ro includes committed WAL data in one read transaction; it may
create WAL/shared-memory sidecars or update shared memory. This is not zero
filesystem writes. STOP is checked separately, not atomically with SQLite.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from py_st.services.intelligence import Intelligence


def diagnose(
    database: Path,
    scope: str,
    *,
    root: Path | None = None,
    max_age: int = 900,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Inspect an existing ledger without credentials, Session or API calls."""
    result: dict[str, Any] = {
        "scope": scope,
        "live_scope_verified": False,
        "execution_authorized": False,
        "process_state": "unknown",
        "findings": [],
    }
    findings = result["findings"]

    def concern(code: str, step: str, **details: Any) -> None:
        findings.append({"code": code, "next_step": step, **details})

    try:
        if len(scope.split(":")) != 2 or any(
            not part.strip() or part != part.strip()
            for part in scope.split(":")
        ):
            raise ValueError("Explicit RESET:AGENT scope required")
        if type(max_age) is not int or not 1 <= max_age <= 86400:
            raise ValueError("max_age must be 1..86400 seconds")
        now = now or datetime.now(UTC)
        if now.utcoffset() is None:
            raise ValueError("now must include a timezone")
        root = Path.cwd() if root is None else root
        if not root.is_dir():
            raise ValueError("STOP root must be an existing directory")
        try:
            (root / "STOP").lstat()
            stopped = True
        except FileNotFoundError:
            stopped = False
        if stopped:
            concern(
                "stop_present", "Review STOP with the owner; leave it intact."
            )
        if not database.is_file():
            raise ValueError(
                "Existing intelligence database required; none created"
            )
        store = Intelligence(database, read_only=True)
        try:
            store.db.execute("BEGIN")
            exists = store.db.execute(
                "SELECT 1 FROM observations WHERE scope=? UNION ALL "
                "SELECT 1 FROM actions WHERE scope=? LIMIT 1",
                (scope, scope),
            ).fetchone()
            if exists is None:
                raise ValueError("Unknown reset/agent scope")
            pending = store.pending_actions(scope)
            rows = {
                kind: store.latest(scope, kind)
                for kind in (
                    "position",
                    "contract",
                    "agent",
                    "ship",
                    "automation_run",
                )
            }
        finally:
            store.close()
        if any(
            not isinstance(r["data"], dict)
            for group in rows.values()
            for r in group
        ):
            raise ValueError("Expected object observation data")
        if pending:
            concern(
                "pending_actions",
                "Reconcile pending actions from fresh state; never replay.",
                actions=pending,
            )
        positions = [
            r for r in rows["position"] if r["data"].get("status") != "closed"
        ]
        if len(positions) > 1 or any(
            r["data"].get("status") != "open"
            or not r["key"].startswith(("trade:", "reposition:"))
            for r in positions
        ):
            concern(
                "unknown_or_multiple_positions",
                "Inspect all intents and exposure before choosing recovery.",
                keys=[r["key"] for r in positions],
            )
        elif positions:
            kind = positions[0]["key"].split(":")[0]
            concern(
                f"{kind}_recovery",
                "Review original intent with current recovery code and fresh "
                "state; do not infer executable arguments from this record.",
                key=positions[0]["key"],
            )
        active = [
            r["key"]
            for r in rows["contract"]
            if r["data"].get("accepted") is True
            and r["data"].get("fulfilled") is not True
        ]
        if active:
            concern(
                "accepted_contracts",
                "Protect cargo/funding; review delivery and fulfillment.",
                keys=active,
            )
        if any(
            type(r["data"].get(field)) is not bool
            for r in rows["contract"]
            for field in ("accepted", "fulfilled")
        ):
            concern(
                "contract_state_unknown",
                "Acceptance/fulfillment flags incomplete; inspect contracts.",
            )
        freshness: dict[str, Any] = {}
        for kind in ("agent", "ship", "contract"):
            states = []
            for row in rows[kind]:
                try:
                    stamp = datetime.fromisoformat(row["observed_at"])
                    age = (now - stamp).total_seconds()
                    if age < 0:
                        state = "invalid_timestamp"
                    elif age > max_age:
                        state = "stale"
                    else:
                        state = "fresh"
                except (TypeError, ValueError):
                    state = "invalid_timestamp"
                states.append({"key": row["key"], "state": state})
            freshness[kind] = states
            if not states or any(s["state"] != "fresh" for s in states):
                concern(
                    f"{kind}_freshness",
                    "Missing/stale/invalid observations; refresh only in a "
                    "separately authorized live workflow.",
                    records=states,
                )
        result["freshness"] = freshness
        runs = rows["automation_run"]
        last = max(runs, key=lambda r: r["id"]) if runs else None
        status = last["data"].get("status") if last else None
        if not isinstance(status, str) or status not in (
            "running",
            "completed",
            "stopped",
            "failed",
            "interrupted",
        ):
            status = "unknown"
        result["last_pilot"] = (
            None
            if last is None
            else {
                "key": last["key"],
                "observed_at": last["observed_at"],
                "recorded_status": status,
                "process_state": "unknown",
            }
        )
        if last and status != "completed":
            concern(
                "pilot_record_requires_review",
                "Review recorded outcome, not liveness. Future runs need "
                "fresh decisions, explicit authorization and new bounds.",
            )
        result["exit_code"] = int(bool(findings))
        result["status"] = "attention" if findings else "no_recorded_concerns"
        result["limits"] = (
            "Per-key records cannot verify complete lists or live state. "
            "No active contract known does not prove none exist. "
            "SQLite read-only may create/use WAL/shared-memory sidecars. "
            "STOP is a separate point-in-time check."
        )
    except (ValueError, TypeError, OSError, sqlite3.Error) as exc:
        concern(
            "unavailable",
            (
                str(exc)
                if isinstance(exc, ValueError)
                else "Cannot read state; inspect schema and filesystem access."
            ),
        )
        result.update(exit_code=2, status="invalid_or_unavailable")
    return result
