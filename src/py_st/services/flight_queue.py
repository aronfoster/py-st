"""Versioned local flight commands, separate from the existing game ledger."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KINDS = {
    "refresh",
    "trip",
    "orbit",
    "dock",
    "refuel",
    "purchase",
    "sell",
    "reconcile",
}
STATES = {
    "queued",
    "running",
    "dispatching",
    "in_transit",
    "completed",
    "blocked",
    "reconciliation_required",
    "cancelled",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_root() -> Path:
    value = os.environ.get("ST_STATE_ROOT", "")
    if not value or not Path(value).is_absolute():
        raise ValueError("Set ST_STATE_ROOT to the absolute canonical root")
    return Path(value).resolve(strict=True)


def validate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("kind") not in KINDS:
        raise ValueError("Unknown flight command kind")
    kind = payload["kind"]
    if kind == "reconcile":
        if (
            set(payload) != {"kind", "command", "explanation"}
            or type(payload["command"]) is not int
            or payload["command"] < 1
            or not isinstance(payload["explanation"], str)
            or not 20 <= len(payload["explanation"].strip()) <= 2000
        ):
            raise ValueError(
                "Provide command ID and 20..2000 character outcome explanation"
            )
        return payload
    fields = {"kind", "system"} if kind == "refresh" else {"kind", "ship"}
    if kind == "trip":
        fields |= {"destination", "dock", "refuel"}
    if kind in ("purchase", "sell"):
        fields |= {"good", "units", "waypoint", "quote", "observed_at"}
    if set(payload) != fields:
        raise ValueError("Unexpected or missing flight fields")
    for key in fields - {"kind", "dock", "refuel", "observed_at"}:
        if key in {"units", "quote"}:
            if type(payload[key]) is not int or payload[key] <= 0:
                raise ValueError(f"Invalid {key}")
            continue
        value = payload[key]
        if not isinstance(value, str) or not re.fullmatch(
            r"[A-Z0-9_-]{1,80}", value
        ):
            raise ValueError(f"Invalid {key}")
    if kind in ("purchase", "sell"):
        try:
            stamp = datetime.fromisoformat(payload["observed_at"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid observed_at") from exc
        if stamp.tzinfo is None:
            raise ValueError("Invalid observed_at")
    if kind == "trip" and (
        type(payload["dock"]) is not bool
        or type(payload["refuel"]) is not bool
        or (payload["refuel"] and not payload["dock"])
    ):
        raise ValueError("Trip flags must be booleans; refuel requires dock")
    return payload


def steps(payload: dict[str, Any]) -> list[str]:
    kind = payload["kind"]
    if kind == "trip":
        return (
            ["orbit", "navigate", "arrival"]
            + (["dock"] if payload["dock"] else [])
            + (["refuel"] if payload["refuel"] else [])
        )
    return ["dock", "refuel"] if kind == "refuel" else [kind]


class FlightQueue:
    def __init__(
        self,
        root: Path,
        *,
        create: bool = False,
        scope: str = "",
        mode: str = "live",
    ) -> None:
        self.root = root.resolve(strict=True)
        path = self.root / ".state/flight.sqlite3"
        self.db = sqlite3.connect(
            path.as_uri() + ("?mode=rwc" if create else "?mode=rw"),
            uri=True,
            timeout=10,
        )
        self.db.row_factory = sqlite3.Row
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if create and version == 0:
                if not scope or mode not in ("live", "demo"):
                    raise ValueError(
                        "Explicit verified scope and mode required"
                    )
                self.db.execute("PRAGMA journal_mode=WAL")
                self.db.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE settings (
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        scope TEXT NOT NULL, root TEXT NOT NULL,
                        mode TEXT NOT NULL, paused INTEGER NOT NULL,
                        heartbeat TEXT, worker_state TEXT NOT NULL
                    );
                    CREATE TABLE commands (
                        id INTEGER PRIMARY KEY,
                        request_id TEXT UNIQUE NOT NULL,
                        scope TEXT NOT NULL, version INTEGER NOT NULL,
                        payload TEXT NOT NULL, steps TEXT NOT NULL,
                        step INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL, created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL, detail TEXT NOT NULL,
                        before_action INTEGER, evidence TEXT
                    );
                    PRAGMA user_version=1;
                    COMMIT;
                """
                )
                with self.db:
                    self.db.execute(
                        "INSERT INTO settings "
                        "VALUES(1,?,?,?,1,NULL,'stopped')",
                        (scope, str(self.root), mode),
                    )
            elif version != 1:
                raise ValueError(
                    "Unsupported flight schema; restore matching code/backup"
                )
            self.db.execute("PRAGMA synchronous=FULL")
            self.settings = dict(
                self.db.execute("SELECT * FROM settings WHERE id=1").fetchone()
            )
            if self.settings["root"] != str(self.root):
                raise ValueError(
                    "State root moved; deliberate migration needed"
                )
            self.scope = str(self.settings["scope"])
            self.check_compatibility()
        except BaseException:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def check_compatibility(self) -> None:
        if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Unsupported flight schema; use matching code")
        settings = self.db.execute(
            "SELECT * FROM settings WHERE id=1"
        ).fetchone()
        if (
            settings is None
            or settings["mode"] not in ("live", "demo")
            or settings["paused"] not in (0, 1)
            or settings["scope"] != self.scope
            or settings["root"] != str(self.root)
        ):
            raise ValueError("Invalid managed account configuration")
        for row in self.db.execute(
            "SELECT * FROM commands WHERE status NOT IN "
            "('completed','cancelled','blocked')"
        ):
            payload = validate(json.loads(row["payload"]))
            expected = steps(payload)
            if (
                row["version"] != 1
                or row["scope"] != self.scope
                or json.loads(row["steps"]) != expected
                or row["status"] not in STATES
                or not 0 <= row["step"] <= len(expected)
                or (
                    row["status"]
                    in ("queued", "running", "in_transit", "dispatching")
                    and row["step"] == len(expected)
                )
                or (
                    row["status"] == "dispatching"
                    and row["before_action"] is None
                )
            ):
                raise ValueError(
                    "Unsupported persisted command; use matching code/backup"
                )

    def enqueue(
        self, scope: str, request_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        validate(payload)
        if scope != self.scope:
            raise ValueError("Command scope differs from managed account")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", request_id):
            raise ValueError("Use a stable 16..80 character request ID")
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            existing = self.db.execute(
                "SELECT * FROM commands WHERE request_id=?", (request_id,)
            ).fetchone()
            if existing:
                if (
                    existing["payload"] != encoded
                    or existing["scope"] != scope
                ):
                    raise ValueError(
                        "Request ID reused with different payload"
                    )
                return self.decode(existing)
            if (
                self.db.execute(
                    "SELECT COUNT(*) FROM commands WHERE status NOT IN "
                    "('completed','cancelled','blocked')"
                ).fetchone()[0]
                >= 100
            ):
                raise ValueError("Queue is full; inspect outstanding work")
            cursor = self.db.execute(
                "INSERT INTO commands(request_id,scope,version,payload,steps,"
                "status,created_at,updated_at,detail) "
                "VALUES(?,?,1,?,?,'queued',?,?,'Awaiting worker')",
                (
                    request_id,
                    scope,
                    encoded,
                    json.dumps(steps(payload)),
                    now(),
                    now(),
                ),
            )
            command_id = cursor.lastrowid
        assert command_id is not None
        return self.get(command_id)

    @staticmethod
    def decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for key in ("payload", "steps", "evidence"):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def get(self, command_id: int) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM commands WHERE id=?", (command_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Unknown command")
        return self.decode(row)

    def update(
        self, command_id: int, status: str, detail: str, **fields: Any
    ) -> None:
        if status not in STATES or set(fields) - {
            "step",
            "before_action",
            "evidence",
        }:
            raise ValueError("Invalid command update")
        if "evidence" in fields:
            fields["evidence"] = json.dumps(fields["evidence"])
        fields.update(status=status, detail=detail, updated_at=now())
        with self.db:
            self.db.execute(
                "UPDATE commands SET "
                + ",".join(f"{k}=?" for k in fields)
                + " WHERE id=?",
                (*fields.values(), command_id),
            )

    def control(self, paused: bool) -> None:
        with self.db:
            self.db.execute("UPDATE settings SET paused=?", (int(paused),))

    def heartbeat(self, state: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE settings SET heartbeat=?,worker_state=?",
                (now(), state),
            )

    def report(self) -> dict[str, Any]:
        return {
            "settings": dict(
                self.db.execute("SELECT * FROM settings WHERE id=1").fetchone()
            ),
            "commands": [
                self.decode(r)
                for r in self.db.execute(
                    "SELECT * FROM commands WHERE id IN "
                    "(SELECT id FROM commands ORDER BY id DESC LIMIT 100) "
                    "OR status IN ('queued','running','dispatching',"
                    "'in_transit','reconciliation_required') ORDER BY id DESC"
                )
            ],
        }
