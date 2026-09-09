"""One bounded return to a completed trade's source, never a purchase plan."""

from __future__ import annotations

import json
import math
import time
from datetime import UTC, datetime
from typing import Any

from py_st.client import APIError
from py_st.services.automation import SafetyStop, Session
from py_st.services.strategies import CREDIT_FLOOR, FUEL_ALLOWANCE, refuel_run


def reposition_plan(
    run: Session, system: str, max_age: int = 900
) -> dict[str, Any]:
    if type(max_age) is not int or not 1 <= max_age <= 86400:
        raise ValueError("Bounds: 1..86400 max-age seconds")
    run.check()
    state = run.refresh()
    if run.store.pending(run.scope):
        raise SafetyStop("Pending action requires explicit reconciliation")
    if any(c["accepted"] and not c["fulfilled"] for c in state["contracts"]):
        raise SafetyStop("Reposition blocked by contract obligations")
    positions = run.store.latest(run.scope, "position")
    closed = sorted(
        (
            p
            for p in positions
            if p["key"].startswith("trade:")
            and p["data"].get("status") == "closed"
            and p["data"].get("bought") is True
        ),
        key=lambda p: p["id"],
        reverse=True,
    )
    if not closed:
        return {"status": "declined", "reason": "No completed original trade"}
    prior = closed[0]
    original = prior["data"].get("plan", {})
    if not isinstance(original, dict):
        original = {}
    source, buyer, good = (
        original.get(k) for k in ("source", "destination", "good")
    )
    result: dict[str, Any] = {
        "status": "blocked",
        "original_position_id": prior["id"],
        "original_observed_at": prior["observed_at"],
        "hauler": prior["key"].removeprefix("trade:"),
        "source": source,
        "destination": buyer,
        "good": good,
        "max_age": max_age,
        "purchase_authorized": False,
    }

    def blocked(reason: str, *, expired: bool = False) -> dict[str, Any]:
        return result | {
            "reason": reason,
            "status": (
                "declined"
                if expired
                and not any(
                    p["data"].get("status") != "closed" for p in positions
                )
                else "blocked"
            ),
        }

    if (
        not isinstance(source, str)
        or not isinstance(buyer, str)
        or not isinstance(good, str)
        or not all((source, buyer, good))
    ):
        return blocked("Original route/good missing")
    if source == buyer or any(
        k.rsplit("-", 1)[0] != system for k in (source, buyer)
    ):
        return blocked("Original route must be distinct and in this system")
    age = (
        datetime.now(UTC) - datetime.fromisoformat(prior["observed_at"])
    ).total_seconds()
    if not 0 <= age <= max_age:
        return blocked("Completed original trade expired", expired=True)
    if any(
        p["data"].get("status") != "closed"
        and not (
            p["key"] == f"reposition:{result['hauler']}"
            and p["data"].get("status") == "open"
            and p["data"].get("plan", {}).get("original_position_id")
            == prior["id"]
        )
        for p in positions
    ):
        return blocked("Other/unknown positions require recovery")
    ship = next(
        (s for s in state["ships"] if s["symbol"] == result["hauler"]), None
    )
    if not ship or (
        ship["cargo"]["units"]
        or ship["cargo"]["inventory"]
        or ship["nav"]["flightMode"] != "CRUISE"
        or ship["nav"]["status"] == "IN_TRANSIT"
        or ship["nav"]["waypointSymbol"] != buyer
        or ship["nav"]["systemSymbol"] != system
    ):
        return blocked(
            "Original ship must be empty, stationary CRUISE at buyer"
        )
    observers = [
        s["symbol"]
        for s in state["ships"]
        if s["symbol"] != ship["symbol"]
        and s["nav"]["waypointSymbol"] == buyer
        and s["nav"]["status"] != "IN_TRANSIT"
    ]
    if not observers:
        return blocked("Independent stationary buyer observer required")
    result["price_scout"] = observers[0]
    seller = next(
        (
            q
            for q in run.store.latest(run.scope, "market", priced_only=True)
            if q["key"] == source
        ),
        None,
    )
    if not seller:
        return blocked("No original detailed source quote")
    quote_age = (
        datetime.now(UTC) - datetime.fromisoformat(seller["observed_at"])
    ).total_seconds()
    result["source_quote"] = {
        "observed_at": seller["observed_at"],
        "age_seconds": quote_age,
        "authority": "historical reposition evidence only",
    }
    if not 0 <= quote_age <= max_age:
        return blocked("Original detailed source quote expired", expired=True)
    target = run.market(buyer)
    if seller["data"].get("symbol") != source or target.get("symbol") != buyer:
        return blocked("Source/buyer quote identity changed")
    result["buyer_quote_observed_at"] = datetime.now(UTC).isoformat()
    quotes = []
    for market, symbol, price in (
        (seller["data"], good, "purchasePrice"),
        (target, good, "sellPrice"),
        (seller["data"], "FUEL", "purchasePrice"),
        (target, "FUEL", "purchasePrice"),
    ):
        quote = next(
            (g for g in market.get("tradeGoods", []) if g["symbol"] == symbol),
            None,
        )
        if (
            not quote
            or quote.get(price, 0) <= 0
            or quote.get("tradeVolume", 0) <= 0
        ):
            return blocked("Missing positive goods/fuel price or volume")
        quotes.append(quote)
    try:
        origin = run.get(f"/systems/{system}/waypoints/{source}")
        destination = run.get(f"/systems/{system}/waypoints/{buyer}")
    except APIError as exc:
        if exc.status != 404:
            raise
        return blocked("Original route waypoint no longer exists")
    if not all(k in w for w in (origin, destination) for k in ("x", "y")):
        return blocked("Missing route coordinates")
    if any(
        w.get("symbol") != symbol or w.get("systemSymbol") != system
        for w, symbol in ((origin, source), (destination, buyer))
    ):
        return blocked("Original route waypoint identity changed")
    distance = max(
        1,
        math.ceil(
            math.hypot(
                origin["x"] - destination["x"], origin["y"] - destination["y"]
            )
        ),
    )
    tank = ship["fuel"]["capacity"]
    # Returning from source must itself pass Session's round-trip guard.
    required = 3 * distance + 10 if tank else 0
    fuel_price = math.ceil(max(q["purchasePrice"] for q in quotes[2:]) * 1.2)
    approach_cost = math.ceil(2 * distance / 100) * fuel_price if tank else 0
    trade_cost = math.ceil(2 * distance / 100) * fuel_price if tank else 0
    refill = math.ceil(tank / 100) * math.ceil(
        math.ceil(quotes[2]["purchasePrice"] * 1.2) * 1.2
    )
    units = min(
        ship["cargo"]["capacity"], *(q["tradeVolume"] for q in quotes[:2])
    )
    max_buy = math.ceil(quotes[0]["purchasePrice"] * 1.05)
    min_sell = math.floor(quotes[1]["sellPrice"] * 0.95)
    costed_fuel = approach_cost + trade_cost
    upfront_refill = (
        math.ceil((tank - ship["fuel"]["current"]) / 100)
        * math.ceil(quotes[3]["purchasePrice"] * 1.2)
        if ship["fuel"]["current"] < required
        else 0
    )
    protected = (
        CREDIT_FLOOR
        + FUEL_ALLOWANCE
        + units * max_buy
        + costed_fuel
        + refill
        + upfront_refill
    )
    net = units * (min_sell - max_buy) - costed_fuel - refill - upfront_refill
    result.update(
        units=units,
        max_buy=max_buy,
        min_sell=min_sell,
        approach_fuel=distance if tank else 0,
        source_return_required_fuel=2 * distance + 10 if tank else 0,
        required_carried_fuel=required,
        later_trade_required_fuel=required,
        approach_and_return_cost=approach_cost,
        trade_fuel_cost=trade_cost,
        costed_fuel=costed_fuel,
        source_full_refill_allowance=refill,
        buyer_upfront_refill_allowance=upfront_refill,
        protected_credits=protected,
        conservative_net=net,
        recovery="At source reobserve actual fuel and quotes. No purchase or "
        "DRIFT fallback; carried reserve supports a guarded physical return.",
    )
    if tank and tank < required:
        return blocked("Later trade exceeds full-tank range")
    if upfront_refill and any(
        p["data"].get("status") != "closed" for p in positions
    ):
        return blocked(
            "Buyer refill requires a new invocation without open exposure"
        )
    if units <= 0 or net <= 0:
        return blocked(
            "No positive margin after approach, trade fuel and refill"
        )
    if run.get("/my/agent")["credits"] < protected:
        return blocked(
            "Current credits cannot fund goods, fuel, refill and floor"
        )
    result.update(status="ready", reason="Costed original-source return")
    return result


def _validate_plan(run: Session, plan: dict[str, Any]) -> dict[str, Any]:
    """Bind supplied and saved identity to the scoped original trade record."""
    if (
        not isinstance(plan, dict)
        or not all(
            isinstance(plan.get(k), str) and plan[k]
            for k in ("hauler", "source", "destination", "good")
        )
        or not all(
            type(plan.get(k)) is int and plan[k] > 0
            for k in (
                "original_position_id",
                "max_age",
                "units",
                "max_buy",
                "min_sell",
                "protected_credits",
                "conservative_net",
            )
        )
        or plan["max_age"] > 86400
        or not all(
            type(plan.get(k)) is int and plan[k] >= 0
            for k in (
                "approach_fuel",
                "source_return_required_fuel",
                "required_carried_fuel",
                "later_trade_required_fuel",
                "approach_and_return_cost",
                "trade_fuel_cost",
                "costed_fuel",
                "source_full_refill_allowance",
            )
        )
    ):
        raise SafetyStop("Malformed reposition plan; inspect recovery first")
    row = run.store.db.execute(
        "SELECT * FROM observations "
        "WHERE scope=? AND kind='position' AND id=?",
        (run.scope, plan["original_position_id"]),
    ).fetchone()
    original = json.loads(row["data"]) if row else {}
    if not isinstance(original, dict):
        raise SafetyStop(
            "Malformed original trade observation; inspect recovery"
        )
    route = original.get("plan", {})
    if (
        not row
        or row["key"] != f"trade:{plan['hauler']}"
        or original.get("status") != "closed"
        or original.get("bought") is not True
        or not isinstance(route, dict)
        or any(
            plan[k] != route.get(k) for k in ("source", "destination", "good")
        )
        or plan["source"] == plan["destination"]
        or plan["source"].rsplit("-", 1)[0]
        != plan["destination"].rsplit("-", 1)[0]
    ):
        raise SafetyStop(
            "Reposition identity differs from original completed trade"
        )
    return dict(row)


def reposition_run(run: Session, plan: dict[str, Any]) -> dict[str, Any]:
    """Persist before moving; recover nav without replaying dispatch."""
    run.check()
    state = run.refresh()
    if run.store.pending(run.scope):
        raise SafetyStop("Pending action requires explicit reconciliation")
    if any(c["accepted"] and not c["fulfilled"] for c in state["contracts"]):
        raise SafetyStop("Reposition blocked by contract obligations")
    original = _validate_plan(run, plan)
    if not any(s["symbol"] == plan["hauler"] for s in state["ships"]):
        raise SafetyStop("Original reposition ship missing; inspect recovery")
    key = f"reposition:{plan['hauler']}"
    positions = [
        p
        for p in run.store.latest(run.scope, "position")
        if p["data"].get("status") != "closed"
    ]
    if positions and (
        len(positions) != 1
        or positions[0]["key"] != key
        or positions[0]["data"].get("status") != "open"
    ):
        raise SafetyStop("Ambiguous positions; inspect recovery first")
    intent = positions[0]["data"] if positions else None
    if intent:
        saved = intent.get("plan", {})
        _validate_plan(run, saved)
        if any(
            plan[k] != saved[k]
            for k in (
                "original_position_id",
                "hauler",
                "source",
                "destination",
                "good",
                "max_age",
            )
        ):
            raise SafetyStop(
                "Resume original saved reposition identity and bounds"
            )
        plan = saved
        if (
            type(intent.get("action_watermark")) is not int
            or intent["action_watermark"] < 0
        ):
            raise SafetyStop(
                "Missing dispatch boundary; inspect recovery first"
            )
    if not run.execute:
        return {
            "status": "dry run",
            "plan": plan,
            "resume": intent,
            "current_ship": next(
                (s for s in state["ships"] if s["symbol"] == plan["hauler"]),
                None,
            ),
        }
    if not intent:
        fresh = reposition_plan(
            run, plan["source"].rsplit("-", 1)[0], plan["max_age"]
        )
        if fresh["status"] != "ready" or any(
            fresh.get(k) != plan[k]
            for k in (
                "original_position_id",
                "hauler",
                "source",
                "destination",
                "good",
            )
        ):
            raise SafetyStop("New reposition candidate changed")
        if fresh["buyer_upfront_refill_allowance"]:
            run.dock(plan["hauler"])
            fresh = reposition_plan(
                run, plan["source"].rsplit("-", 1)[0], plan["max_age"]
            )
            if fresh["status"] != "ready" or any(
                fresh.get(k) != plan[k]
                for k in (
                    "original_position_id",
                    "hauler",
                    "source",
                    "destination",
                    "good",
                )
            ):
                raise SafetyStop(
                    "Buyer refill candidate changed after docking"
                )
            reserve = (
                fresh["protected_credits"]
                - fresh["buyer_upfront_refill_allowance"]
                - CREDIT_FLOOR
                - FUEL_ALLOWANCE
            )
            refill = refuel_run(
                run,
                plan["hauler"],
                plan_only=True,
                additional_reserve=reserve,
            )
            # Revalidate the complete return, not just fuel affordability.
            checked = reposition_plan(
                run, plan["source"].rsplit("-", 1)[0], plan["max_age"]
            )
            if (
                checked["status"] != "ready"
                or any(
                    checked.get(k) != fresh[k]
                    for k in (
                        "original_position_id",
                        "hauler",
                        "source",
                        "destination",
                        "good",
                        "protected_credits",
                        "conservative_net",
                        "buyer_upfront_refill_allowance",
                    )
                )
                or refill.get("maximum_estimated_cost")
                != checked["buyer_upfront_refill_allowance"]
            ):
                raise SafetyStop("Buyer refill economics changed")
            state = run.refresh()
            if any(
                c["accepted"] and not c["fulfilled"]
                for c in state["contracts"]
            ) or not any(
                s["symbol"] == checked["price_scout"]
                and s["nav"]["waypointSymbol"] == plan["destination"]
                and s["nav"]["status"] != "IN_TRANSIT"
                for s in state["ships"]
            ):
                raise SafetyStop("Buyer refill eligibility changed")
            current = run.ship(plan["hauler"])
            if (
                current["nav"]["status"] != "DOCKED"
                or current["nav"]["waypointSymbol"] != plan["destination"]
                or current["nav"]["systemSymbol"]
                != plan["destination"].rsplit("-", 1)[0]
                or current["nav"]["flightMode"] != "CRUISE"
                or current["cargo"]["units"]
                or current["cargo"]["inventory"]
                or current["fuel"]["capacity"] - current["fuel"]["current"]
                != refill["missing_fuel"]
            ):
                raise SafetyStop("Buyer refill ship changed")
            if run.get("/my/agent")["credits"] < checked["protected_credits"]:
                raise SafetyStop("Buyer refill credits changed")
            deadline = run.deadline
            now = datetime.now(UTC)
            remaining = min(
                limit
                - (now - datetime.fromisoformat(observed)).total_seconds()
                for observed, limit in (
                    (original["observed_at"], plan["max_age"]),
                    (checked["source_quote"]["observed_at"], plan["max_age"]),
                    (checked["buyer_quote_observed_at"], 60),
                )
            )
            run.deadline = min(deadline, time.monotonic() + remaining)
            try:
                run.mutate(f"/my/ships/{plan['hauler']}/refuel")
            finally:
                run.deadline = deadline
            fresh = reposition_plan(
                run, plan["source"].rsplit("-", 1)[0], plan["max_age"]
            )
            if (
                fresh["status"] != "ready"
                or fresh["buyer_upfront_refill_allowance"]
            ):
                raise SafetyStop("Replan after buyer refill before returning")
        plan = fresh
        intent = {
            "status": "open",
            "plan": plan,
            "action_watermark": run.store.db.execute(
                "SELECT COALESCE(MAX(id),0) FROM actions WHERE scope=?",
                (run.scope,),
            ).fetchone()[0],
        }
        run.store.observe(run.scope, "position", key, intent, "strategy")
    ship = run.ship(plan["hauler"])
    if ship["cargo"]["units"] or ship["nav"]["flightMode"] != "CRUISE":
        raise SafetyStop("Reposition cargo/mode changed; inspect recovery")
    undispatched_location = (
        ship["nav"]["status"] in ("DOCKED", "IN_ORBIT")
        and ship["nav"]["waypointSymbol"] == plan["destination"]
    )
    if ship["nav"]["status"] == "IN_TRANSIT":
        if ship["nav"]["route"]["destination"].get("symbol") != plan["source"]:
            raise SafetyStop("Reposition transit target changed")
        ship = run.arrive(plan["hauler"])
    if ship["nav"]["waypointSymbol"] != plan["source"]:
        navigation_query = (
            "SELECT 1 FROM actions WHERE scope=? AND id>? AND path=? "
            "AND status NOT IN ('not_sent','rejected') LIMIT 1"
        )
        navigation_args = (
            run.scope,
            intent["action_watermark"],
            f"/my/ships/{plan['hauler']}/navigate",
        )
        dispatched = run.store.db.execute(
            navigation_query, navigation_args
        ).fetchone()
        if dispatched:
            raise SafetyStop(
                "Approach already dispatched; reconcile nav, never replay"
            )
        fresh = reposition_plan(
            run, plan["source"].rsplit("-", 1)[0], plan["max_age"]
        )
        if fresh["status"] != "ready":
            ship = run.ship(plan["hauler"])
            run.check()
            active = [
                p
                for p in run.store.latest(run.scope, "position")
                if p["data"].get("status") != "closed"
            ]
            if (
                undispatched_location
                and len(active) == 1
                and active[0]["key"] == key
                and active[0]["data"] == intent
                and ship["nav"]["status"] in ("DOCKED", "IN_ORBIT")
                and ship["nav"]["waypointSymbol"] == plan["destination"]
                and ship["nav"]["systemSymbol"]
                == plan["destination"].rsplit("-", 1)[0]
                and ship["nav"]["flightMode"] == "CRUISE"
                and not ship["cargo"]["units"]
                and not ship["cargo"]["inventory"]
                and not run.store.pending(run.scope)
                and not run.store.db.execute(
                    navigation_query, navigation_args
                ).fetchone()
            ):
                result = intent | {
                    "status": "closed",
                    "outcome": "abandoned",
                    "reason": fresh["reason"],
                    "navigation_may_have_succeeded": False,
                    "purchase_authorized": False,
                    "recovery": "Recovery only. Approach abandoned at "
                    "original buyer; next invocation must replan.",
                }
                run.check()
                run.store.observe(
                    run.scope, "position", key, result, "strategy"
                )
                return result
            raise SafetyStop(
                f"Reposition revalidation blocked: {fresh.get('reason')}"
            )
        if any(
            fresh.get(k) != plan[k]
            for k in (
                "original_position_id",
                "hauler",
                "source",
                "destination",
                "good",
            )
        ):
            raise SafetyStop(
                f"Reposition revalidation blocked: {fresh.get('reason')}"
            )
        if ship["nav"]["status"] != "IN_ORBIT":
            run.mutate(f"/my/ships/{plan['hauler']}/orbit", reposition=key)
            # Orbit is a mutation/wait boundary: recheck economics and state.
            return reposition_run(run, plan)
        ship = run.ship(plan["hauler"])
        if ship["fuel"]["current"] < fresh["required_carried_fuel"]:
            raise SafetyStop("Carried return reserve changed")
        navigation = run.navigation_plan(ship, plan["source"])
        if (
            not navigation["feasible"]
            or navigation["policy"] != "round-trip"
            or navigation["estimated_leg_fuel"] != fresh["approach_fuel"]
        ):
            raise SafetyStop(
                "Reposition requires carried round-trip navigation"
            )
        # Preparation can wait. Reobserve the ship, without a second navigation
        # plan or orbit, then validate every evidence age at the POST boundary.
        state = run.refresh()
        if (
            any(
                c["accepted"] and not c["fulfilled"]
                for c in state["contracts"]
            )
            or state["agent"]["credits"] < fresh["protected_credits"]
            or not any(
                s["symbol"] == fresh["price_scout"]
                and s["nav"]["waypointSymbol"] == plan["destination"]
                and s["nav"]["status"] != "IN_TRANSIT"
                for s in state["ships"]
            )
        ):
            raise SafetyStop("Reposition reserves/contracts/observer changed")
        current = run.ship(plan["hauler"])
        if (
            current["nav"] != ship["nav"]
            or current["fuel"] != ship["fuel"]
            or current["cargo"] != ship["cargo"]
            or current["nav"]["status"] != "IN_ORBIT"
            or current["nav"]["waypointSymbol"] != plan["destination"]
        ):
            raise SafetyStop(
                "Reposition ship changed during navigation preparation"
            )
        _validate_plan(run, fresh)
        plan = fresh
        intent = intent | {"plan": plan}
        run.store.observe(run.scope, "position", key, intent, "strategy")
        run.store.observe(
            run.scope, "plan", f"move:{plan['hauler']}", navigation
        )
        run.check()
        dispatch_started = time.monotonic()
        now = datetime.now(UTC)
        evidence_ages = [
            ((now - datetime.fromisoformat(observed)).total_seconds(), limit)
            for observed, limit in (
                (original["observed_at"], plan["max_age"]),
                (plan["source_quote"]["observed_at"], plan["max_age"]),
                (plan["buyer_quote_observed_at"], 60),
            )
        ]
        if any(not 0 <= age <= limit for age, limit in evidence_ages):
            raise SafetyStop("Reposition evidence expired before departure")
        deadline = run.deadline
        run.deadline = min(
            deadline,
            dispatch_started
            + min(limit - age for age, limit in evidence_ages),
        )
        try:
            # Bound transport pacing/retries by evidence, not arrival polling.
            run.mutate(
                f"/my/ships/{plan['hauler']}/navigate",
                {"waypointSymbol": plan["source"]},
                reposition=key,
            )
        finally:
            run.deadline = deadline
        ship = run.arrive(plan["hauler"])
    run.check()
    if (
        ship["nav"]["status"] == "IN_TRANSIT"
        or ship["nav"]["waypointSymbol"] != plan["source"]
        or ship["cargo"]["units"]
        or ship["nav"]["flightMode"] != "CRUISE"
    ):
        raise SafetyStop("Source arrival not confirmed")
    market = run.market(plan["source"])
    run.check()
    result = {
        "status": "closed",
        "plan": plan,
        "arrival_fuel": ship["fuel"],
        "physical_return_fuel_ready": ship["fuel"]["current"]
        >= plan["source_return_required_fuel"],
        "source_market": market,
        "purchase_authorized": False,
        "recovery": "Recovery only. Next earn must obtain new source/buyer "
        "quotes and use actual fuel; no automatic return or purchase.",
    }
    run.store.observe(run.scope, "position", key, intent | result, "strategy")
    return result
