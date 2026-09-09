"""Offline contract source discovery; no procurement or execution plan."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from py_st.services.intelligence import Intelligence


def contract_sources(
    database: Path,
    scope: str,
    contract_id: str,
    *,
    max_age: int = 900,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rank adverts without allocating supply or writing ledger records.

    SQLite mode=ro still reads committed WAL records and may create sidecars
    or update shared memory. It does not promise zero filesystem writes.
    """
    if len(scope.split(":")) != 2 or not all(scope.split(":")):
        raise ValueError("Explicit RESET:AGENT scope required")
    if type(max_age) is not int or max_age <= 0:
        raise ValueError("max_age must be a positive integer")
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    if not database.is_file():
        raise ValueError(
            "Offline sources requires an existing intelligence database; "
            "a fresh checkout has no ledger. No database was created."
        )
    store = Intelligence(database, read_only=True)
    try:
        store.db.execute("BEGIN")
        if scope not in store.scopes():
            raise ValueError("Unknown reset/agent scope")
        observation = next(
            (
                r
                for r in store.latest(scope, "contract")
                if r["key"] == contract_id
            ),
            None,
        )
        if observation is None:
            raise ValueError("Contract not found in requested scope")
        markets = store.latest(scope, "market")
        prices = {
            r["key"]: r
            for r in store.latest(scope, "market", priced_only=True)
        }
        waypoints = {
            r["key"]: r["data"] for r in store.latest(scope, "waypoint")
        }
    finally:
        store.close()

    contract = observation["data"]
    accepted = contract.get("accepted", False)
    fulfilled = contract.get("fulfilled", False)
    deadlines = {
        "acceptance": contract.get(
            "deadlineToAccept", contract.get("expiration")
        ),
        "delivery": contract["terms"].get("deadline"),
    }
    deadline_status = {}
    for kind, value in deadlines.items():
        try:
            deadline = datetime.fromisoformat(value)
            deadline_status[kind] = (
                ("expired" if deadline <= now else "open")
                if deadline.tzinfo is not None
                else "unknown"
            )
        except (TypeError, ValueError):
            deadline_status[kind] = "unknown"
    status = (
        "fulfilled" if fulfilled else "accepted" if accepted else "offered"
    )
    blocked = []
    if fulfilled:
        blocked.append("Contract already fulfilled")
    if not accepted and deadline_status["acceptance"] == "expired":
        blocked.append("Acceptance deadline expired")
    if deadline_status["delivery"] == "expired":
        blocked.append("Delivery deadline expired")

    # Consolidate repeated terms, never count one market as extra supply.
    remaining: dict[tuple[str, str], int] = {}
    for term in contract["terms"].get("deliver", []):
        units = max(0, term["unitsRequired"] - term["unitsFulfilled"])
        if units:
            key = (term["tradeSymbol"], term["destinationSymbol"])
            remaining[key] = remaining.get(key, 0) + units
    deliveries = []
    for (good, destination), units in sorted(remaining.items()):
        candidates = []
        target = waypoints.get(destination, {})
        for market in markets:
            source = market["key"]
            if source.rsplit("-", 1)[0] != destination.rsplit("-", 1)[0]:
                continue
            category = next(
                (
                    kind
                    for kind in ("exports", "exchange", "imports")
                    if any(
                        g["symbol"] == good
                        for g in market["data"].get(kind, [])
                    )
                ),
                None,
            )
            if category is None:
                continue
            origin = waypoints.get(source, {})
            distance = None
            if all("x" in w and "y" in w for w in (origin, target)):
                distance = math.hypot(
                    origin["x"] - target["x"], origin["y"] - target["y"]
                )
            detailed = prices.get(source)
            quote = (
                next(
                    (
                        g
                        for g in detailed["data"]["tradeGoods"]
                        if g["symbol"] == good
                    ),
                    None,
                )
                if detailed
                else None
            )
            observed_at = (
                detailed["observed_at"] if quote and detailed else None
            )
            age = None
            if observed_at:
                try:
                    age = (
                        now - datetime.fromisoformat(observed_at)
                    ).total_seconds()
                except (TypeError, ValueError):
                    age = None
            fresh = age is not None and 0 <= age <= max_age
            valid = quote is not None and all(
                type(quote.get(field)) is int and quote[field] > 0
                for field in ("purchasePrice", "tradeVolume")
            )
            current = detailed is not None and detailed["id"] == market["id"]
            if quote is None:
                quote_status = "missing"
            elif age is None or age < 0:
                quote_status = "invalid_timestamp"
            elif not fresh:
                quote_status = "stale"
            elif not valid:
                quote_status = "invalid_price_or_volume"
            else:
                quote_status = "fresh" if current else "fresh_historical"
            candidates.append(
                {
                    "source": source,
                    "category": category,
                    "advertised_at": market["observed_at"],
                    "distance": distance,
                    "geometry_status": (
                        "known"
                        if distance is not None
                        else "missing_waypoint_coordinates"
                    ),
                    "quote_observed_at": observed_at,
                    "quote_age_seconds": age,
                    "quote_status": quote_status,
                    "purchase_price": (
                        quote["purchasePrice"]
                        if fresh and valid and quote
                        else None
                    ),
                    "trade_volume": (
                        quote["tradeVolume"]
                        if fresh and valid and quote
                        else None
                    ),
                    "actionable_quote": bool(fresh and valid and current),
                }
            )
        candidates.sort(
            key=lambda c: (
                c["category"] == "imports",
                c["distance"] if c["distance"] is not None else math.inf,
                c["source"],
            )
        )
        deliveries.append(
            {
                "trade_symbol": good,
                "destination": destination,
                "remaining_units": units,
                "sources": candidates,
                "source_status": (
                    "advertised" if candidates else "no_same_system_adverts"
                ),
            }
        )
    return {
        "mode": "offline_only",
        "execution_authorized": False,
        "scope": scope,
        "contract_id": contract_id,
        "contract_observation": observation,
        "contract_observed_at": observation["observed_at"],
        "contract_status": status,
        "accepted": accepted,
        "fulfilled": fulfilled,
        "deadlines": deadlines,
        "deadline_status": deadline_status,
        "sourcing_blockers": blocked,
        "max_age_seconds": max_age,
        "evaluated_at": now.isoformat(),
        "deliveries": deliveries,
        "note": "Adverts are discovery evidence, not inventory. An actionable "
        "quote only means current stored detailed evidence is fresh, not "
        "permission to buy or accept. Fresh historical quotes are not current "
        "visibility. Use contract-model for the whole obligation with "
        "explicit capacity, credits, fuel and travel inputs; refresh live "
        "before action. "
        "No allocation, availability, fuel, travel or profit is inferred.",
    }
