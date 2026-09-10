"""Bounded, offline market observations from the shared read-only ledger."""

from __future__ import annotations

import heapq
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from py_st.services.intelligence import Intelligence


def market_history(
    database: Path,
    scope: str,
    waypoint: str,
    good: str,
    limit: int = 50,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the newest valid-time matching details in chronological order.

    Preserve raw observed_at; observed_at_ms is Unix time for browser plots.
    Scan only the selected market; retain at most limit points in memory.
    mode=ro includes committed WAL data, unlike immutable=1. SQLite may use
    WAL/shared-memory sidecars, but no ledger records are written.
    """
    if (
        not isinstance(scope, str)
        or len(scope) > 200
        or len(scope.split(":")) != 2
        or not all(part and part.strip() == part for part in scope.split(":"))
    ):
        raise ValueError("Explicit RESET:AGENT scope required")
    for name, symbol, pattern in (
        ("waypoint", waypoint, r"[A-Z0-9]+(?:-[A-Z0-9]+){2,}"),
        ("good", good, r"[A-Z][A-Z0-9_]*"),
    ):
        if (
            not isinstance(symbol, str)
            or len(symbol) > 100
            or not re.fullmatch(pattern, symbol)
        ):
            raise ValueError(f"Valid {name} symbol required")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 to 100")
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    if not database.is_file():
        raise ValueError(
            "Existing intelligence database required; none created"
        )
    store = Intelligence(database, read_only=True)
    points: list[tuple[datetime, int, dict[str, Any]]] = []
    skipped = {
        "invalid_timestamp": 0,
        "future_timestamp": 0,
        "invalid_data": 0,
    }
    total = 0
    latest = None
    try:
        store.db.execute("BEGIN")
        if scope not in store.scopes():
            raise ValueError("Unknown reset/agent scope")
        latest = store.db.execute(
            "SELECT id,observed_at,source FROM observations "
            "WHERE scope=? AND kind='market' AND key=? "
            "ORDER BY id DESC LIMIT 1",
            (scope, waypoint),
        ).fetchone()
        if latest is None:
            raise ValueError("Market not found in requested scope")
        for record in store.db.execute(
            "SELECT id,observed_at,source,data FROM observations "
            "WHERE scope=? AND kind='market' AND key=? ORDER BY id",
            (scope, waypoint),
        ):
            try:
                data = json.loads(record["data"])
            except (TypeError, ValueError):
                skipped["invalid_data"] += 1
                continue
            if not isinstance(data, dict):
                skipped["invalid_data"] += 1
                continue
            goods = data.get("tradeGoods", [])
            if not isinstance(goods, list):
                skipped["invalid_data"] += 1
                continue
            quotes = [
                q
                for q in goods
                if isinstance(q, dict) and q.get("symbol") == good
            ]
            if not quotes:
                continue
            try:
                observed = datetime.fromisoformat(record["observed_at"])
                if observed.tzinfo is None:
                    raise ValueError("Timezone required")
            except (TypeError, ValueError):
                skipped["invalid_timestamp"] += 1
                continue
            if observed > now:
                skipped["future_timestamp"] += 1
                continue
            quote = quotes[0] if len(quotes) == 1 else {}
            point = {
                "id": record["id"],
                "observed_at": record["observed_at"],
                "observed_at_ms": observed.timestamp() * 1000,
                "source": record["source"],
                "visibility": (
                    "current_detail"
                    if record["id"] == latest["id"]
                    else "retained_history"
                ),
                "age_seconds": (now - observed).total_seconds(),
                "stale": (now - observed).total_seconds() > 900,
                "quote_status": (
                    "detail" if len(quotes) == 1 else "duplicate_good"
                ),
            }
            for output, field in (
                ("purchase_price", "purchasePrice"),
                ("sell_price", "sellPrice"),
                ("trade_volume", "tradeVolume"),
            ):
                value = quote.get(field)
                point[output] = (
                    value if type(value) is int and value > 0 else None
                )
            for field in ("supply", "activity"):
                value = quote.get(field)
                point[field] = (
                    value if isinstance(value, str) and value else None
                )
            total += 1
            heapq.heappush(points, (observed, record["id"], point))
            if len(points) > limit:
                heapq.heappop(points)
    finally:
        store.close()
    return {
        "scope": scope,
        "waypoint": waypoint,
        "good": good,
        "limit": limit,
        "evaluated_at": now.isoformat(),
        "max_age_seconds": 900,
        "latest_market": dict(latest),
        "points": [point for _, _, point in sorted(points)],
        "truncated": total > limit,
        "skipped": skipped,
        "note": "Cached observations, not live quotes. Volume is a batch "
        "limit, not inventory. Null values are unknown; "
        "sparse adverts add no prices.",
    }
