"""Single-load remote procurement with unchanged Session navigation guards."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Any

from py_st.services.automation import SafetyStop, Session
from py_st.services.strategies import CREDIT_FLOOR, FUEL_ALLOWANCE


def remote_contract_run(
    run: Session, ship_symbol: str, contract_id: str, source: str
) -> dict[str, Any]:
    key = f"procurement:{contract_id}"
    original = None
    while True:
        run.check()
        state = run.refresh()
        if run.store.pending(run.scope) or any(
            p["data"].get("status") == "open" and p["key"] != key
            for p in run.store.latest(run.scope, "position")
        ):
            raise SafetyStop("Resolve pending actions/open positions first")
        contract = next(
            c for c in state["contracts"] if c["id"] == contract_id
        )
        if any(
            c["accepted"] and not c["fulfilled"] and c["id"] != contract_id
            for c in state["contracts"]
        ):
            raise SafetyStop(
                "Other obligations need a separate costed reserve"
            )
        previous = next(
            (
                p["data"]
                for p in run.store.latest(run.scope, "position")
                if p["key"] == key
            ),
            None,
        )
        if previous:
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
        delivery = contract["terms"]["deliver"][0]
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
            run.mutate(f"/my/contracts/{contract_id}/fulfill")
            continue
        ship = run.arrive(ship_symbol)
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
            run.navigate(ship_symbol, destination)
            run.dock(ship_symbol)
            run.mutate(
                f"/my/contracts/{contract_id}/deliver",
                {
                    "shipSymbol": ship_symbol,
                    "tradeSymbol": good,
                    "units": held,
                },
            )
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
        fuel = next(
            (g for g in market.get("tradeGoods", []) if g["symbol"] == "FUEL"),
            None,
        )
        if (
            market.get("symbol") != destination
            or not fuel
            or fuel.get("purchasePrice", 0) <= 0
            or fuel.get("tradeVolume", 0) <= 0
        ):
            raise SafetyStop("No fresh usable destination fuel quote")
        fuel_ceiling = (
            original["fuel_price_ceiling"]
            if original
            else math.ceil(fuel["purchasePrice"] * 1.2)
        )
        if fuel["purchasePrice"] > fuel_ceiling:
            raise SafetyStop("Destination fuel exceeds original ceiling")
        refill = math.ceil(ship["fuel"]["capacity"] / 100) * fuel_ceiling
        seller = run.market(source)
        quote = next(
            (g for g in seller.get("tradeGoods", []) if g["symbol"] == good),
            None,
        )
        if (
            seller.get("symbol") != source
            or not quote
            or quote.get("purchasePrice", 0) <= 0
            or quote.get("tradeVolume", 0) <= 0
        ):
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
        expiration = contract.get(
            "deadlineToAccept", contract.get("expiration")
        )
        if (
            not contract["accepted"]
            and expiration
            and datetime.fromisoformat(expiration) <= datetime.now(UTC)
        ):
            raise SafetyStop("Contract acceptance expired")
        credits = run.get("/my/agent")["credits"]
        protected = CREDIT_FLOOR + FUEL_ALLOWANCE + refill + needed * ceiling
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
        if time.monotonic() - observed > 60:
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
        if not contract["accepted"]:
            run.mutate(f"/my/contracts/{contract_id}/accept")
        elif nav["status"] != "DOCKED":
            run.dock(ship_symbol)
        else:
            run.mutate(
                f"/my/ships/{ship_symbol}/purchase",
                {
                    "symbol": good,
                    "units": min(needed, quote["tradeVolume"]),
                },
            )
