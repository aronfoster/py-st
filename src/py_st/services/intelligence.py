"""Reset-scoped observations and write-ahead action journal, not API cache."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Intelligence:
    def __init__(
        self,
        path: Path = Path(".state/intelligence.sqlite3"),
        *,
        read_only: bool = False,
        existing_only: bool = False,
        existing_or_create: bool = False,
    ) -> None:
        if read_only:
            self.db = sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10
            )
            self.db.row_factory = sqlite3.Row
            if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
                self.db.close()
                raise ValueError("Unsupported intelligence schema version")
            return
        if existing_or_create and not existing_only:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                existing_only = True
            else:
                temporary = path.with_name(
                    f".{path.name}.{uuid.uuid4().hex}.tmp"
                )
                try:
                    created = Intelligence(temporary)
                    created.close()
                    os.link(temporary, path)
                except FileExistsError:
                    pass
                finally:
                    temporary.unlink(missing_ok=True)
                    temporary.with_name(temporary.name + "-wal").unlink(
                        missing_ok=True
                    )
                    temporary.with_name(temporary.name + "-shm").unlink(
                        missing_ok=True
                    )
                existing_only = True
        if existing_only:
            self.db = sqlite3.connect(
                path.resolve().as_uri() + "?mode=rw", uri=True, timeout=10
            )
            try:
                self.db.row_factory = sqlite3.Row
                if self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("Unsupported intelligence schema version")
                # Validate the existing tables without repairing an empty DB.
                self.db.execute(
                    "SELECT id,scope,kind,key,observed_at,source,data "
                    "FROM observations LIMIT 0"
                )
                self.db.execute(
                    "SELECT id,scope,started_at,finished_at,path,body,status,"
                    "result FROM actions LIMIT 0"
                )
                mode = self.db.execute("PRAGMA journal_mode").fetchone()[0]
                if mode != "wal":
                    raise ValueError("Intelligence ledger requires WAL")
                self.db.execute("PRAGMA synchronous=FULL")
                if self.db.execute("PRAGMA synchronous").fetchone()[0] != 2:
                    raise ValueError("Intelligence ledger requires FULL sync")
            except BaseException:
                self.db.close()
                raise
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported intelligence schema version")
            with self.db:
                schema = """
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS observations (
                        id INTEGER PRIMARY KEY, scope TEXT NOT NULL,
                        kind TEXT NOT NULL, key TEXT NOT NULL,
                        observed_at TEXT NOT NULL, source TEXT NOT NULL,
                        data TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS observation_lookup
                        ON observations(scope, kind, key, id DESC);
                    CREATE TABLE IF NOT EXISTS actions (
                        id INTEGER PRIMARY KEY, scope TEXT NOT NULL,
                        started_at TEXT NOT NULL, finished_at TEXT,
                        path TEXT NOT NULL, body TEXT NOT NULL,
                        status TEXT NOT NULL, result TEXT
                    );
                    PRAGMA user_version=1;
                    COMMIT;
                    """
                self.db.executescript(schema)
        except BaseException:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def observe(
        self,
        scope: str,
        kind: str,
        key: str,
        data: Any,
        source: str = "live-api",
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO observations "
                "(scope,kind,key,observed_at,source,data) "
                "VALUES (?,?,?,?,?,?)",
                (
                    scope,
                    kind,
                    key,
                    datetime.now(UTC).isoformat(),
                    source,
                    json.dumps(data),
                ),
            )

    def latest(
        self,
        scope: str,
        kind: str,
        *,
        priced_only: bool = False,
    ) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM observations WHERE id IN "
            "(SELECT MAX(id) FROM observations WHERE scope=? AND kind=? "
            "AND (?=0 OR "
            "COALESCE(json_array_length(data,'$.tradeGoods'),0)>0) "
            "GROUP BY key) ORDER BY key",
            (scope, kind, int(priced_only)),
        ).fetchall()
        return [dict(r) | {"data": json.loads(r["data"])} for r in rows]

    def scopes(self) -> list[str]:
        return [
            r[0]
            for r in self.db.execute(
                "SELECT DISTINCT scope FROM observations ORDER BY scope DESC"
            )
        ]

    def begin_action(self, scope: str, path: str, body: Any) -> int:
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO actions (scope,started_at,path,body,status) "
                "VALUES (?,?,?,?, 'pending')",
                (scope, datetime.now(UTC).isoformat(), path, json.dumps(body)),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def finish_action(self, action: int, status: str, result: Any) -> None:
        with self.db:
            cursor = self.db.execute(
                "UPDATE actions SET status=?,finished_at=?,result=? "
                "WHERE id=? AND status='pending'",
                (
                    status,
                    datetime.now(UTC).isoformat(),
                    json.dumps(result),
                    action,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Action is missing or already finished")

    def actions(self, scope: str) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM actions WHERE scope=? "
                "ORDER BY id DESC LIMIT 200",
                (scope,),
            )
        ]

    def pending(self, scope: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM actions WHERE scope=? "
                "AND status='pending' LIMIT 1",
                (scope,),
            ).fetchone()
            is not None
        )

    def pending_actions(self, scope: str) -> list[dict[str, Any]]:
        """All unresolved actions, independent of the recent-history cap."""
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT id,started_at,status FROM actions "
                "WHERE scope=? AND status='pending' ORDER BY id",
                (scope,),
            )
        ]

    def pending_action(
        self, scope: str, action_id: int
    ) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM actions WHERE scope=? AND id=? "
            "AND status='pending'",
            (scope, action_id),
        ).fetchone()
        return dict(row) if row is not None else None

    def negotiated_contracts(self, scope: str) -> list[dict[str, Any]]:
        """Receipts survive interruption before contract observation."""
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT json_extract(result,'$.contract') FROM actions "
                "WHERE scope=? AND status='succeeded' "
                "AND path LIKE '/my/ships/%/negotiate/contract'",
                (scope,),
            )
        ]

    def report(self, scope: str) -> dict[str, Any]:
        credits = [
            dict(r)
            for r in self.db.execute(
                "SELECT observed_at, "
                "json_extract(data,'$.credits') AS credits "
                "FROM observations WHERE scope=? AND kind='agent' ORDER BY id",
                (scope,),
            )
        ]
        return {
            "scope": scope,
            "credits": credits,
            "credit_change": (
                credits[-1]["credits"] - credits[0]["credits"]
                if credits
                else 0
            ),
            "ships": self.latest(scope, "ship"),
            "contracts": self.latest(scope, "contract"),
            "markets": self.latest(scope, "market"),
            "waypoints": self.latest(scope, "waypoint"),
            "jump_gates": self.latest(scope, "jump_gate"),
            "shipyards": self.latest(scope, "shipyard"),
            "construction": self.latest(scope, "construction"),
            "actions": self.actions(scope),
            "plans": self.latest(scope, "plan"),
            "prices": self.latest(scope, "market", priced_only=True),
            "routes": self.routes(scope),
            "economics": self.economics(scope),
            "positions": self.latest(scope, "position"),
            "scout_visits": self.latest(scope, "scout_visit"),
            "automation_runs": self.latest(scope, "automation_run"),
        }

    def economics(self, scope: str) -> dict[str, Any]:
        """Reconcile confirmed journal cash flows against observed credits."""
        rows = [
            dict(r)
            for r in self.db.execute(
                "WITH tx AS (SELECT json_extract(result,'$.transaction') AS t "
                "FROM actions WHERE scope=? AND status='succeeded' "
                "AND json_type(result,'$.transaction')='object') "
                "SELECT json_extract(t,'$.tradeSymbol') AS good, "
                "SUM(CASE WHEN json_extract(t,'$.type')='PURCHASE' "
                "THEN json_extract(t,'$.units') ELSE 0 END) AS bought_units, "
                "SUM(CASE WHEN json_extract(t,'$.type')='SELL' "
                "THEN json_extract(t,'$.units') ELSE 0 END) AS sold_units, "
                "SUM(CASE WHEN json_extract(t,'$.type')='PURCHASE' "
                "THEN json_extract(t,'$.totalPrice') ELSE 0 END) AS spent, "
                "SUM(CASE WHEN json_extract(t,'$.type')='SELL' "
                "THEN json_extract(t,'$.totalPrice') ELSE 0 END) AS received "
                "FROM tx GROUP BY good ORDER BY good",
                (scope,),
            )
        ]
        receipts = self.db.execute(
            "SELECT COALESCE(SUM(CASE WHEN path LIKE '%/accept' "
            "THEN json_extract(result,'$.contract.terms.payment.onAccepted') "
            "WHEN path LIKE '%/fulfill' "
            "THEN json_extract(result,'$.contract.terms.payment.onFulfilled') "
            "ELSE 0 END),0) FROM actions WHERE scope=? AND status='succeeded'",
            (scope,),
        ).fetchone()[0]
        credits = self.db.execute(
            "SELECT json_extract(data,'$.credits') FROM observations "
            "WHERE scope=? AND kind='agent' ORDER BY id",
            (scope,),
        ).fetchall()
        observed = credits[-1][0] - credits[0][0] if credits else 0
        known_net = receipts + sum(r["received"] - r["spent"] for r in rows)
        return {
            "goods": rows,
            "contract_receipts": receipts,
            "journal_net_cash": known_net,
            "observed_credit_change": observed,
            "unexplained_credit_change": observed - known_net,
            "note": "Cash reconciliation, not inventory-adjusted profit. "
            "Refuel transaction units represent 100-unit fuel packs.",
        }

    def backup(self, destination: Path) -> None:
        """SQLite online backup includes WAL transactions consistently."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.open("xb").close()
        except FileExistsError:
            raise ValueError(
                "Backup destination exists; choose a new filename"
            ) from None
        target = sqlite3.connect(destination)
        try:
            self.db.backup(target)
        finally:
            target.close()

    def routes(
        self,
        scope: str,
        capacity: int = 40,
        max_age: int = 900,
    ) -> list[dict[str, Any]]:
        """Indicative round-trip margins, never authority to trade."""
        prices = self.latest(scope, "market", priced_only=True)
        waypoints = {
            w["key"]: w["data"] for w in self.latest(scope, "waypoint")
        }
        result = []
        now = datetime.now(UTC)
        for source in prices:
            for target in prices:
                if source["key"] == target["key"]:
                    continue
                a, b = (
                    waypoints.get(source["key"]),
                    waypoints.get(target["key"]),
                )
                if not a or not b or a["systemSymbol"] != b["systemSymbol"]:
                    continue
                distance = max(
                    1, math.ceil(math.hypot(a["x"] - b["x"], a["y"] - b["y"]))
                )
                buyers = {g["symbol"]: g for g in target["data"]["tradeGoods"]}
                fuels = [
                    g["purchasePrice"]
                    for p in (source, target)
                    for g in p["data"]["tradeGoods"]
                    if g["symbol"] == "FUEL"
                ]
                if not fuels:
                    continue
                fuel_cost = math.ceil(2 * distance / 100) * max(fuels)
                age = max(
                    (
                        now - datetime.fromisoformat(p["observed_at"])
                    ).total_seconds()
                    for p in (source, target)
                )
                for good in source["data"]["tradeGoods"]:
                    buyer = buyers.get(good["symbol"])
                    if not buyer:
                        continue
                    units = min(
                        capacity, good["tradeVolume"], buyer["tradeVolume"]
                    )
                    spread = buyer["sellPrice"] - good["purchasePrice"]
                    net = units * spread - fuel_cost
                    if net <= 0:
                        continue
                    result.append(
                        {
                            "source": source["key"],
                            "destination": target["key"],
                            "good": good["symbol"],
                            "units": units,
                            "buy": good["purchasePrice"],
                            "sell": buyer["sellPrice"],
                            "round_trip_fuel": 2 * distance,
                            "fuel_allowance": fuel_cost,
                            "net_estimate": net,
                            "age_seconds": round(age),
                            "stale": age > max_age,
                            "note": "Excludes slippage and opportunity cost",
                        }
                    )
        return sorted(result, key=lambda r: r["net_estimate"], reverse=True)
