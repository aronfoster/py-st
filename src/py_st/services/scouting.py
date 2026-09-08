"""Bounded local discovery, resumed from observed ships and price history."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Any, cast

from py_st.client.transport import JSONList
from py_st.services.automation import SafetyStop, Session
from py_st.services.intelligence import Intelligence


def scout_plan(
    store: Intelligence,
    scope: str,
    system: str,
    ships: list[dict[str, Any]],
    waypoints: list[dict[str, Any]],
    *,
    attempts: int = 4,
    max_age: int = 900,
    attempted: set[str] | None = None,
) -> dict[str, Any]:
    """Rank one next target per market; no persisted itinerary is replayed."""
    if not 1 <= attempts <= 100 or not 1 <= max_age <= 86400:
        raise ValueError("Bounds: 1..100 attempts, 1..86400 max-age seconds")
    now = datetime.now(UTC)
    prices = {
        row["key"]: row
        for row in store.latest(scope, "market", priced_only=True)
    }
    visits = {row["key"]: row for row in store.latest(scope, "scout_visit")}
    probes = []
    excluded = []
    for ship in ships:
        nav = ship["nav"]
        if (
            ship.get("frame", {}).get("symbol") != "FRAME_PROBE"
            or ship.get("fuel", {}).get("capacity") != 0
            or ship.get("cargo", {}).get("units") != 0
            or nav["systemSymbol"] != system
            or nav["flightMode"] != "CRUISE"
            or nav["status"] not in ("DOCKED", "IN_ORBIT", "IN_TRANSIT")
            or nav["waypointSymbol"].rsplit("-", 1)[0] != system
            or nav["route"]["destination"]["symbol"].rsplit("-", 1)[0]
            != system
        ):
            excluded.append(ship["symbol"])
        else:
            probes.append(ship)
    candidates = []
    skipped = []
    for waypoint in waypoints:
        key = waypoint["symbol"]
        if (
            waypoint["systemSymbol"] != system
            or key.rsplit("-", 1)[0] != system
            or not any(
                t["symbol"] == "MARKETPLACE" for t in waypoint["traits"]
            )
        ):
            continue
        price = prices.get(key)
        age = (
            (
                now - datetime.fromisoformat(price["observed_at"])
            ).total_seconds()
            if price
            else None
        )
        visit = visits.get(key)
        reason = ""
        if attempted and key in attempted:
            reason = "attempted this invocation"
        elif age is not None and 0 <= age < max_age:
            reason = "fresh detailed prices"
        elif visit and visit["data"]["status"] == "unpriced":
            visit_age = (
                now - datetime.fromisoformat(visit["observed_at"])
            ).total_seconds()
            if 0 <= visit_age < max_age:
                reason = "unpriced visit cooldown"
        if reason:
            skipped.append({"target": key, "reason": reason})
            continue
        choices = []
        for ship in probes:
            nav = ship["nav"]
            origin = nav["route"]["destination"]
            transit = nav["status"] == "IN_TRANSIT"
            # Never redirect an already travelling probe to a different market.
            if transit and origin["symbol"] != key:
                continue
            present = not transit and nav["waypointSymbol"] == key
            distance = math.hypot(
                waypoint["x"] - origin["x"], waypoint["y"] - origin["y"]
            )
            actions = 0
            if not transit and not present:
                actions = 2 if nav["status"] == "DOCKED" else 1
            choices.append(
                (
                    0 if transit else 1 if present else 2,
                    distance,
                    ship["symbol"],
                    actions,
                )
            )
        if not choices:
            skipped.append({"target": key, "reason": "no eligible probe"})
            continue
        recovery, distance, symbol, actions = min(choices)
        candidates.append(
            {
                "ship": symbol,
                "target": key,
                "reason": (
                    "resume observed transit"
                    if recovery == 0
                    else (
                        "observe current market"
                        if recovery == 1
                        else (
                            "never priced" if price is None else "stale prices"
                        )
                    )
                ),
                "price_observed_at": price["observed_at"] if price else None,
                "age_seconds": round(age) if age is not None else None,
                "distance": round(distance, 2),
                "actions": actions,
                "rank": (
                    recovery,
                    price is not None,
                    -(age or 0),
                    distance,
                    key,
                ),
            }
        )
    candidates.sort(key=lambda candidate: candidate["rank"])
    for candidate in candidates:
        del candidate["rank"]
    blockers = []
    if store.pending(scope):
        blockers.append("Pending action requires explicit reconciliation")
    if any(
        row["data"]["status"] != "closed"
        for row in store.latest(scope, "position")
    ):
        blockers.append(
            "Recover open trade positions before moving price scouts"
        )
    return {
        "scope": scope,
        "system": system,
        "attempt_limit": attempts,
        "max_age_seconds": max_age,
        "eligible_probes": [ship["symbol"] for ship in probes],
        "excluded_ships": excluded,
        "blockers": blockers,
        "next": candidates[0] if candidates and not blockers else None,
        "candidates": candidates,
        "skipped": skipped,
        "note": "Replan after every visit; candidates are not an itinerary. "
        "Zero fuel/credit spending; prices are observations, not profit.",
    }


def scout_run(
    run: Session,
    system: str,
    attempts: int = 4,
    max_age: int = 900,
    *,
    excluded: set[str] | None = None,
) -> dict[str, Any]:
    if not 1 <= attempts <= 100 or not 1 <= max_age <= 86400:
        raise ValueError("Bounds: 1..100 attempts, 1..86400 max-age seconds")
    run.check()
    state = run.refresh()
    if not any(s["nav"]["systemSymbol"] == system for s in state["ships"]):
        raise SafetyStop("Scouting requires an owned ship in the same system")
    run.check()
    waypoints = cast(
        JSONList,
        run.client.request(
            "GET", f"/systems/{system}/waypoints", paginate=True
        ),
    )
    for waypoint in waypoints:
        run.check()
        run.store.observe(run.scope, "waypoint", waypoint["symbol"], waypoint)
    attempted: set[str] = set()
    results: list[dict[str, Any]] = []
    while True:
        run.check()
        plan = scout_plan(
            run.store,
            run.scope,
            system,
            state["ships"],
            waypoints,
            attempts=attempts,
            max_age=max_age,
            attempted=attempted | (excluded or set()),
        )
        plan["remaining_actions"] = run.remaining
        plan["remaining_seconds"] = max(
            0, round(run.deadline - time.monotonic())
        )
        run.store.observe(
            run.scope, "plan", f"scout:{system}", plan, "strategy"
        )
        if not run.execute:
            return {"status": "dry run", "plan": plan}
        if plan["blockers"]:
            raise SafetyStop("; ".join(plan["blockers"]))
        if len(attempted) >= attempts or not plan["next"]:
            return {
                "status": (
                    "attempt limit"
                    if len(attempted) >= attempts
                    else "no targets"
                ),
                "visits": results,
                "plan": plan,
            }
        target = plan["next"]
        if target["actions"] > run.remaining:
            raise SafetyStop("Action budget cannot cover next scout leg")
        symbol, destination = target["ship"], target["target"]
        attempted.add(destination)
        # Guard against changed capability/mode before Session navigation.
        ship = run.ship(symbol)
        checked = scout_plan(
            run.store,
            run.scope,
            system,
            [ship],
            waypoints,
            attempts=attempts,
            max_age=max_age,
        )
        if not any(c["target"] == destination for c in checked["candidates"]):
            raise SafetyStop(
                "Scout state changed; replan from fresh observations"
            )
        arrived = run.navigate(symbol, destination)
        if (
            arrived["nav"]["status"] not in ("DOCKED", "IN_ORBIT")
            or arrived["nav"]["systemSymbol"] != system
            or arrived["nav"]["waypointSymbol"] != destination
        ):
            raise SafetyStop("Scout arrival at target not confirmed")
        market = run.market(destination)
        visit = {
            "ship": symbol,
            "target": destination,
            "status": "priced" if market.get("tradeGoods") else "unpriced",
        }
        run.store.observe(
            run.scope, "scout_visit", destination, visit, "strategy"
        )
        results.append(visit)
        state = run.refresh()
