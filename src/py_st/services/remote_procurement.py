"""Single-load remote procurement with unchanged Session navigation guards."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Any

from py_st.services.automation import SafetyStop, Session
from py_st.services.contract_state import select_contract
from py_st.services.strategies import CREDIT_FLOOR, FUEL_ALLOWANCE


def _quote(market: dict[str, Any], good: str) -> dict[str, Any] | None:
    goods = market.get("tradeGoods")
    if not isinstance(goods, list) or any(
        not isinstance(q, dict) for q in goods
    ):
        return None
    matches = [q for q in goods if q.get("symbol") == good]
    if len(matches) != 1 or any(
        type(matches[0].get(k)) is not int or matches[0][k] <= 0
        for k in ("purchasePrice", "tradeVolume")
    ):
        return None
    quote: dict[str, Any] = matches[0]
    return quote


def remote_contract_run(
    run: Session, ship_symbol: str, contract_id: str, source: str
) -> dict[str, Any]:
    key = f"procurement:{contract_id}"
    original = None
    while True:
        run.check()
        state = run.refresh()
        run.check_reposition()
        positions = run.store.latest(run.scope, "position")
        if run.store.pending(run.scope) or any(
            p["data"].get("status") != "closed" and p["key"] != key
            for p in positions
        ):
            raise SafetyStop("Resolve pending actions/open positions first")
        contract = select_contract(state["contracts"], contract_id)
        terms = contract.get("terms")
        if not isinstance(terms, dict):
            raise SafetyStop("Invalid contract terms")
        deliveries = terms.get("deliver")
        if not isinstance(deliveries, list) or len(deliveries) != 1:
            raise SafetyStop("Remote procurement requires one delivery good")
        delivery = deliveries[0]
        if (
            not isinstance(delivery, dict)
            or type(delivery.get("unitsRequired")) is not int
            or type(delivery.get("unitsFulfilled")) is not int
            or delivery["unitsRequired"] <= 0
            or not 0 <= delivery["unitsFulfilled"] <= delivery["unitsRequired"]
        ):
            raise SafetyStop("Invalid contract delivery quantities")
        if contract["fulfilled"] and (
            not contract["accepted"]
            or delivery["unitsFulfilled"] != delivery["unitsRequired"]
        ):
            raise SafetyStop("Fulfilled contract has conflicting progress")
        if any(
            c["accepted"] and not c["fulfilled"] and c["id"] != contract_id
            for c in state["contracts"]
        ):
            raise SafetyStop(
                "Other obligations need a separate costed reserve"
            )
        previous = next(
            (p["data"] for p in positions if p["key"] == key),
            None,
        )
        if previous is not None:
            if (
                not isinstance(previous, dict)
                or previous.get("status") not in ("open", "closed")
                or previous.get("strategy") is not None
                or not isinstance(previous.get("plan"), dict)
                or previous["plan"].get("strategy") is not None
                or previous["plan"].get("contract") != contract_id
                or (
                    previous["status"] == "closed"
                    and previous.get("stage") != "abandoned"
                    and not contract["fulfilled"]
                )
            ):
                raise SafetyStop(
                    "Original remote procurement identity/status needs review"
                )
            if previous.get("stage") == "abandoned":
                raise SafetyStop("Abandoned procurement cannot be resumed")
            original = previous["plan"]
            if (original["ship"], original["source"]) != (ship_symbol, source):
                raise SafetyStop("Resume original procurement ship/source")
        if contract["fulfilled"]:
            if previous and run.execute:
                run.store.observe(
                    run.scope,
                    "position",
                    key,
                    previous | {"status": "closed", "stage": "fulfilled"},
                )
            return {
                "status": "fulfilled",
                "contract": contract_id,
                "plan": original,
                "recovery": "Run guarded auto refuel at destination before "
                "onward travel; full refill was reserved, not yet spent.",
            }
        destination = delivery["destinationSymbol"]
        good = delivery["tradeSymbol"]
        if original and (original["destination"], original["good"]) != (
            destination,
            good,
        ):
            raise SafetyStop("Original procurement terms changed; review")
        remaining = delivery["unitsRequired"] - delivery["unitsFulfilled"]
        deadline = datetime.fromisoformat(contract["terms"]["deadline"])
        if deadline <= datetime.now(UTC):
            raise SafetyStop("Contract deadline expired")
        if contract["accepted"] and remaining <= 0:
            if not run.execute:
                return {"status": "ready to fulfill", "contract": contract_id}
            if previous:
                run.store.observe(
                    run.scope,
                    "position",
                    key,
                    previous
                    | {
                        "stage": "delivered",
                        "held": 0,
                        "delivered": delivery["unitsFulfilled"],
                    },
                )
            budget = run.deadline
            run.deadline = min(
                budget,
                time.monotonic()
                + (deadline - datetime.now(UTC)).total_seconds(),
            )
            try:
                run.mutate(f"/my/contracts/{contract_id}/fulfill")
            finally:
                run.deadline = budget
            continue
        ship = run.arrive(ship_symbol)
        if any(
            s.get("symbol") == ship_symbol
            and s.get("nav", {}).get("status") == "IN_TRANSIT"
            for s in state["ships"]
        ):
            # Arrival polling may take minutes; discard the pre-wait contract.
            continue
        held = sum(
            g["units"]
            for g in ship["cargo"]["inventory"]
            if g["symbol"] == good
        )
        needed = remaining - held
        if ship["cargo"]["units"] != held or needed < 0:
            raise SafetyStop("Untracked/excess cargo needs review")
        if remaining > ship["cargo"]["capacity"]:
            raise SafetyStop("Remote procurement requires one full cargo load")
        nav = ship["nav"]
        if nav["flightMode"] != "CRUISE" or any(
            w.rsplit("-", 1)[0] != nav["systemSymbol"]
            for w in (source, destination)
        ):
            raise SafetyStop("Remote procurement requires same-system CRUISE")
        if contract["accepted"] and not original:
            raise SafetyStop("Accepted remote procurement needs original plan")
        # Completion needs neither source quotes nor acquisition liquidity.
        if contract["accepted"] and needed == 0:
            leg = run.navigation_plan(ship, destination)
            if not leg["feasible"]:
                raise SafetyStop(leg["reason"])
            travel = math.ceil(
                60
                + 30
                * leg.get("estimated_leg_fuel", 0)
                / max(1, ship["engine"]["speed"])
            )
            if (deadline - datetime.now(UTC)).total_seconds() < travel:
                raise SafetyStop("Insufficient delivery deadline margin")
            if not run.execute:
                return {
                    "status": "ready to deliver",
                    "units": held,
                    "navigation": leg,
                }
            run.store.observe(
                run.scope,
                "position",
                key,
                {
                    "status": "open",
                    "stage": "cargo acquired",
                    "held": held,
                    "delivered": delivery["unitsFulfilled"],
                    "plan": original,
                },
            )
            budget = run.deadline
            run.deadline = min(
                budget,
                time.monotonic()
                + (deadline - datetime.now(UTC)).total_seconds(),
            )
            try:
                if nav["waypointSymbol"] != destination:
                    run.navigate(ship_symbol, destination)
                elif nav["status"] != "DOCKED":
                    run.mutate(f"/my/ships/{ship_symbol}/dock")
                else:
                    run.mutate(
                        f"/my/contracts/{contract_id}/deliver",
                        {
                            "shipSymbol": ship_symbol,
                            "tradeSymbol": good,
                            "units": held,
                        },
                    )
            finally:
                run.deadline = budget
            # Every completed leg/preparation action gets fresh obligations.
            continue
        if nav["waypointSymbol"] != source:
            raise SafetyStop(
                "Reposition hauler to source using guarded move first"
            )
        if not any(
            s["symbol"] != ship_symbol
            and s.get("frame", {}).get("symbol") == "FRAME_PROBE"
            and s["fuel"]["capacity"] == 0
            and s["nav"]["waypointSymbol"] == destination
            and s["nav"]["status"] != "IN_TRANSIT"
            for s in state["ships"]
        ):
            raise SafetyStop("Independent destination probe required")
        leg = run.navigation_plan(ship, destination)
        if not leg["feasible"] or leg["policy"] != "round-trip":
            raise SafetyStop(
                "Carry full delivery-leg guarded fuel before acquisition"
            )
        target = run.get(
            f"/systems/{nav['systemSymbol']}/waypoints/{destination}"
        )
        if not any(
            t["symbol"] == "MARKETPLACE" for t in target.get("traits", [])
        ):
            raise SafetyStop("Destination must have a fuel marketplace")
        observed = time.monotonic()
        market = run.market(destination)
        fuel = _quote(market, "FUEL")
        if market.get("symbol") != destination or fuel is None:
            raise SafetyStop("No fresh usable destination fuel quote")
        fuel_ceiling = (
            original["fuel_price_ceiling"]
            if original
            else math.ceil(fuel["purchasePrice"] * 1.2)
        )
        if fuel["purchasePrice"] > fuel_ceiling:
            raise SafetyStop("Destination fuel exceeds original ceiling")
        # Fund refuel_run's own headroom even at the original price ceiling.
        refill = math.ceil(ship["fuel"]["capacity"] / 100) * math.ceil(
            fuel_ceiling * 1.2
        )
        seller = run.market(source)
        quote = _quote(seller, good)
        if seller.get("symbol") != source or quote is None:
            raise SafetyStop("No live acquisition price/volume")
        ceiling = (
            original["max_unit_price"]
            if original
            else math.ceil(quote["purchasePrice"] * 1.2)
        )
        if quote["purchasePrice"] > ceiling:
            raise SafetyStop("Source price exceeds original ceiling")
        # One hour of contingency plus a conservative travel estimate.
        travel = math.ceil(
            60
            + 30 * leg["estimated_leg_fuel"] / max(1, ship["engine"]["speed"])
        )
        if (deadline - datetime.now(UTC)).total_seconds() < 3600 + travel:
            raise SafetyStop(
                "Insufficient acquisition/delivery deadline margin"
            )
        expiration = None
        if not contract["accepted"]:
            try:
                value = contract.get(
                    "deadlineToAccept", contract.get("expiration")
                )
                if not isinstance(value, str):
                    raise ValueError
                expiration = datetime.fromisoformat(value)
                now = datetime.now(UTC)
                if expiration.tzinfo is None or expiration <= now:
                    raise ValueError
            except (TypeError, ValueError):
                raise SafetyStop(
                    "Contract acceptance expired or invalid"
                ) from None
        credits = run.get("/my/agent")["credits"]
        protected = CREDIT_FLOOR + FUEL_ALLOWANCE + refill + needed * ceiling
        if run.execute:
            fresh = run.refresh()
            current = select_contract(fresh["contracts"], contract_id)
            if any(
                current.get(k) != contract.get(k)
                for k in (
                    "id",
                    "accepted",
                    "fulfilled",
                    "terms",
                    "deadlineToAccept",
                    "expiration",
                )
            ) or any(
                c["accepted"] and not c["fulfilled"] and c["id"] != contract_id
                for c in fresh["contracts"]
            ):
                raise SafetyStop(
                    "Contract obligations changed before acquisition"
                )
            fleet = [
                s for s in fresh["ships"] if s.get("symbol") == ship_symbol
            ]
            fresh_ship = run.ship(ship_symbol)
            if len(fleet) != 1 or any(
                s.get("symbol") != ship_symbol
                or s.get("cargo") != ship["cargo"]
                or s.get("fuel") != ship["fuel"]
                or not isinstance(s.get("nav"), dict)
                or any(
                    s["nav"].get(k) != nav.get(k)
                    for k in (
                        "status",
                        "flightMode",
                        "waypointSymbol",
                        "systemSymbol",
                    )
                )
                for s in [*fleet, fresh_ship]
            ):
                raise SafetyStop("Ship state changed before acquisition")
            if not any(
                s["symbol"] != ship_symbol
                and s.get("frame", {}).get("symbol") == "FRAME_PROBE"
                and s.get("fuel", {}).get("capacity") == 0
                and s.get("nav", {}).get("waypointSymbol") == destination
                and s["nav"].get("status") in ("DOCKED", "IN_ORBIT")
                for s in fresh["ships"]
            ):
                raise SafetyStop(
                    "Destination observer changed before acquisition"
                )
            if (
                run.store.pending(run.scope)
                or run.store.latest(run.scope, "position") != positions
            ):
                raise SafetyStop(
                    "Procurement exposure changed before acquisition"
                )
            credits = fresh["agent"]["credits"]
        payment = contract["terms"]["payment"]
        revenue = payment["onFulfilled"] + (
            0 if contract["accepted"] else payment["onAccepted"]
        )
        net = revenue - needed * ceiling - refill - FUEL_ALLOWANCE
        plan = {
            "ship": ship_symbol,
            "contract": contract_id,
            "source": source,
            "destination": destination,
            "good": good,
            "max_unit_price": ceiling,
            "fuel_price_ceiling": fuel_ceiling,
            "full_refill_credit_reserve": refill,
            "protected_credits": protected,
            "remaining_to_buy": needed,
            "held": held,
            "delivered": delivery["unitsFulfilled"],
            "purchase_batches": math.ceil(needed / quote["tradeVolume"]),
            "navigation": leg,
            "estimated_travel_seconds": travel,
            "conservative_net": net,
            "feasible": credits >= protected
            and (bool(contract["accepted"] and original) or net > 0),
            "recovery": "Aggregate full load, deliver, fulfill, then guarded "
            "destination refill. No automatic return or source refuel.",
        }
        run.store.observe(run.scope, "plan", key, plan)
        if not run.execute:
            return plan
        if not plan["feasible"]:
            raise SafetyStop("Contract fails conservative profit/reserve test")
        if time.monotonic() - observed >= 60:
            raise SafetyStop("Destination fuel quote expired; replan")
        if original is None:
            original = plan
        run.store.observe(
            run.scope,
            "position",
            key,
            {
                "status": "open",
                "stage": "acquiring" if contract["accepted"] else "planned",
                "held": held,
                "delivered": delivery["unitsFulfilled"],
                "plan": original,
            },
        )
        # Evidence and contract cutoffs also bound transport pacing/retries.
        budget = run.deadline
        monotonic = time.monotonic()
        now = datetime.now(UTC)
        run.deadline = min(
            budget,
            observed + 60,
            monotonic + (deadline - now).total_seconds() - 3600 - travel,
        )
        if expiration is not None:
            run.deadline = min(
                run.deadline, monotonic + (expiration - now).total_seconds()
            )
        try:
            if not contract["accepted"]:
                run.mutate(f"/my/contracts/{contract_id}/accept")
            elif nav["status"] != "DOCKED":
                run.mutate(f"/my/ships/{ship_symbol}/dock")
            else:
                run.mutate(
                    f"/my/ships/{ship_symbol}/purchase",
                    {
                        "symbol": good,
                        "units": min(needed, quote["tradeVolume"]),
                    },
                )
        finally:
            run.deadline = budget
