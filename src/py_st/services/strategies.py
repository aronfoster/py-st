"""Inspectable economic decisions; orchestration uses guarded Sessions."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Any

from py_st.services.automation import SafetyStop, Session

CREDIT_FLOOR = 50_000
FUEL_ALLOWANCE = 1_000


def fleet_run(
    run: Session,
    cycles: int = 1,
    *,
    plan_only: bool = False,
    system: str = "",
) -> dict[str, Any]:
    """Assign existing ships using visible markets; never purchase a fleet."""
    if not 1 <= cycles <= 20:
        raise ValueError("Use 1..20 cycles")
    state = run.refresh()
    positions = [
        p
        for p in run.store.latest(run.scope, "position")
        if p["key"].startswith("trade:") and p["data"]["status"] == "open"
    ]
    if positions:
        if not run.execute or plan_only:
            return {"resume": positions}
        resumed = []
        for position in positions:
            plan = position["data"]["plan"]
            hauler = position["key"].removeprefix("trade:")
            resumed.append(
                {
                    "hauler": hauler,
                    "result": trade_run(
                        run,
                        hauler,
                        plan["source"],
                        plan["destination"],
                        plan["good"],
                        cycles=1,
                    ),
                }
            )
        # Recovery closes existing cycles, never opens extra cycles or routes.
        return {"resumed": resumed}
    markets = {m["key"] for m in run.store.latest(run.scope, "market")}
    markets.update(
        w["key"]
        for w in run.store.latest(run.scope, "waypoint")
        if any(
            t["symbol"] == "MARKETPLACE" for t in w["data"].get("traits", [])
        )
    )
    fresh = {}
    for ship in state["ships"]:
        location = ship["nav"]["waypointSymbol"]
        if system and location.rsplit("-", 1)[0] != system:
            continue
        if location in markets and ship["nav"]["status"] != "IN_TRANSIT":
            fresh[location] = run.market(location)
    candidates = []
    for ship in state["ships"]:
        if (
            ship["cargo"]["units"]
            or ship["nav"]["status"] == "IN_TRANSIT"
            or ship["nav"]["flightMode"] != "CRUISE"
        ):
            continue
        for route in run.store.routes(run.scope, ship["cargo"]["capacity"]):
            if (
                route["stale"]
                or ship["nav"]["waypointSymbol"] != route["source"]
                or route["source"] not in fresh
                or route["destination"] not in fresh
            ):
                continue
            scouts = [
                s["symbol"]
                for s in state["ships"]
                if s["symbol"] != ship["symbol"]
                and s["nav"]["waypointSymbol"] == route["destination"]
                and s["nav"]["status"] != "IN_TRANSIT"
            ]
            if not scouts:
                continue
            if not all(
                any(
                    g["symbol"] == route["good"] and g[price] > 0
                    for g in fresh[key].get("tradeGoods", [])
                )
                for key, price in (
                    (route["source"], "purchasePrice"),
                    (route["destination"], "sellPrice"),
                )
            ):
                continue
            plan = trade_plan(
                fresh[route["source"]],
                fresh[route["destination"]],
                route["good"],
                ship["cargo"]["capacity"],
                state["agent"]["credits"],
                route["fuel_allowance"],
            )
            if not plan["feasible"]:
                continue
            seconds = 50 + 25 * route["round_trip_fuel"] / max(
                1, ship["engine"]["speed"]
            )
            candidates.append(
                plan
                | {
                    "hauler": ship["symbol"],
                    "price_scout": scouts[0],
                    "estimated_round_trip_seconds": round(seconds),
                    "estimated_credits_per_hour": round(
                        plan["conservative_net"] * 3600 / seconds
                    ),
                    "fuel_ready": not ship["fuel"]["capacity"]
                    or ship["fuel"]["current"]
                    >= 1.5 * route["round_trip_fuel"] + 10,
                }
            )
    candidates.sort(
        key=lambda p: p["estimated_credits_per_hour"], reverse=True
    )
    result = {
        "candidates": candidates,
        "note": "Approximate CRUISE time; "
        "existing ships only. No active contract obligations permitted.",
    }
    run.store.observe(run.scope, "plan", "fleet", result, "scheduler")
    if not run.execute or plan_only:
        return result
    selected = next((p for p in candidates if p["fuel_ready"]), None)
    if not selected:
        raise SafetyStop(
            "No ready route; scout counterparties or refuel first"
        )
    return {
        "selected": selected,
        "result": trade_run(
            run,
            selected["hauler"],
            selected["source"],
            selected["destination"],
            selected["good"],
            cycles,
        ),
    }


def refuel_run(run: Session, ship_symbol: str) -> dict[str, Any]:
    state = run.refresh()
    if any(c["accepted"] and not c["fulfilled"] for c in state["contracts"]):
        raise SafetyStop(
            "Refuel requires explicit reserve for active contracts"
        )
    ship = run.arrive(ship_symbol)
    missing = ship["fuel"]["capacity"] - ship["fuel"]["current"]
    if missing <= 0:
        return {"status": "full or fuel-free", "ship": ship_symbol}
    market = run.market(ship["nav"]["waypointSymbol"])
    fuel = next(
        (g for g in market.get("tradeGoods", []) if g["symbol"] == "FUEL"),
        None,
    )
    if not fuel or fuel["purchasePrice"] <= 0:
        raise SafetyStop("No live fuel quote at current location")
    maximum_cost = math.ceil(missing / 100) * math.ceil(
        fuel["purchasePrice"] * 1.2
    )
    if (
        state["agent"]["credits"] - maximum_cost
        < CREDIT_FLOOR + FUEL_ALLOWANCE
    ):
        raise SafetyStop("Refuel would violate credit reserve")
    plan = {
        "ship": ship_symbol,
        "missing_fuel": missing,
        "maximum_estimated_cost": maximum_cost,
    }
    if not run.execute:
        return plan
    run.dock(ship_symbol)
    result = run.mutate(f"/my/ships/{ship_symbol}/refuel")
    run.ship(ship_symbol)
    return plan | {
        "transaction": result["transaction"],
        "fuel": result["fuel"],
    }


def trade_plan(
    source: dict[str, Any],
    target: dict[str, Any],
    good: str,
    capacity: int,
    credits: int,
    fuel_cost: int,
) -> dict[str, Any]:
    seller = next(
        (g for g in source.get("tradeGoods", []) if g["symbol"] == good), None
    )
    buyer = next(
        (g for g in target.get("tradeGoods", []) if g["symbol"] == good), None
    )
    if (
        not seller
        or not buyer
        or min(seller["purchasePrice"], buyer["sellPrice"]) <= 0
    ):
        raise SafetyStop(
            "Both counterparties need live positive prices; scout first"
        )
    max_buy = math.ceil(seller["purchasePrice"] * 1.05)
    min_sell = math.floor(buyer["sellPrice"] * 0.95)
    units = min(
        capacity,
        seller["tradeVolume"],
        buyer["tradeVolume"],
        max(0, (credits - CREDIT_FLOOR - FUEL_ALLOWANCE) // max_buy),
    )
    net = units * (min_sell - max_buy) - fuel_cost
    return {
        "source": source["symbol"],
        "destination": target["symbol"],
        "good": good,
        "units": units,
        "max_buy": max_buy,
        "min_sell": min_sell,
        "fuel_allowance": fuel_cost,
        "conservative_net": net,
        "feasible": units > 0 and net > 0,
    }


def trade_run(
    run: Session,
    ship_symbol: str,
    source: str,
    destination: str,
    good: str,
    cycles: int = 1,
) -> dict[str, Any]:
    if not 1 <= cycles <= 20 or source == destination:
        raise ValueError("Use distinct markets and 1..20 cycles")
    started = time.monotonic()
    state = run.refresh()
    initial_credits = state["agent"]["credits"]
    if any(c["accepted"] and not c["fulfilled"] for c in state["contracts"]):
        raise SafetyStop(
            "Trade blocked by contract obligations; fulfill first"
        )
    key = f"trade:{ship_symbol}"
    for _ in range(cycles):
        run.check()
        previous = next(
            (
                r["data"]
                for r in run.store.latest(run.scope, "position")
                if r["key"] == key and r["data"]["status"] == "open"
            ),
            None,
        )
        ship = run.arrive(ship_symbol)
        if ship["nav"]["flightMode"] != "CRUISE":
            raise SafetyStop("Only CRUISE is enabled for trading")
        if previous:
            plan = previous["plan"]
            if (source, destination, good) != (
                plan["source"],
                plan["destination"],
                plan["good"],
            ):
                raise SafetyStop(
                    "Resume the open trade's original route and good"
                )
        else:
            if ship["cargo"]["units"]:
                raise SafetyStop(
                    "Untracked cargo; inspect before opening a trade"
                )
            origin = run.get(
                f"/systems/{source.rsplit('-', 1)[0]}/waypoints/{source}"
            )
            target = run.get(
                f"/systems/{destination.rsplit('-', 1)[0]}"
                f"/waypoints/{destination}"
            )
            if origin["systemSymbol"] != target["systemSymbol"]:
                raise SafetyStop("Cross-system trading is disabled")
            distance = max(
                1,
                math.ceil(
                    math.hypot(
                        origin["x"] - target["x"], origin["y"] - target["y"]
                    )
                ),
            )
            if run.execute:
                run.navigate(ship_symbol, source)
            seller, buyer = run.market(source), run.market(destination)
            fuels = [
                g["purchasePrice"]
                for market in (seller, buyer)
                for g in market.get("tradeGoods", [])
                if g["symbol"] == "FUEL"
            ]
            if not fuels:
                raise SafetyStop("No fuel price for route costing")
            fuel_cost = math.ceil(2 * distance / 100) * max(fuels)
            agent = run.get("/my/agent")
            plan = trade_plan(
                seller,
                buyer,
                good,
                ship["cargo"]["capacity"],
                agent["credits"],
                fuel_cost,
            )
            plan["required_fuel"] = 3 * distance + 10
            run.store.observe(run.scope, "plan", key, plan, "strategy")
            if not run.execute:
                return plan
            if not plan["feasible"]:
                raise SafetyStop("No positive conservative trade margin")
            run.navigate(ship_symbol, source)
            ship = run.dock(ship_symbol)
            if (
                ship["fuel"]["capacity"]
                and ship["fuel"]["current"] < 3 * distance + 10
            ):
                refuel_run(run, ship_symbol)
                ship = run.ship(ship_symbol)
                if ship["fuel"]["current"] < plan["required_fuel"]:
                    raise SafetyStop("Route exceeds full-tank safety range")
            # Intent survives a crash before/after buying. Pending actions stop
            # ambiguous outcomes; known held cargo is sold before buying again.
            previous = {"status": "open", "plan": plan, "bought": False}
            run.store.observe(run.scope, "position", key, previous, "strategy")
        if not run.execute:
            return {"resume": previous}
        ship = run.arrive(ship_symbol)
        held = sum(
            g["units"]
            for g in ship["cargo"]["inventory"]
            if g["symbol"] == good
        )
        if not held and not previous["bought"]:
            # On restart, never buy at an unverified waypoint/price.
            run.navigate(ship_symbol, source)
            ship = run.dock(ship_symbol)
            if ship["cargo"]["units"] or (
                ship["fuel"]["capacity"]
                and ship["fuel"]["current"] < plan["required_fuel"]
            ):
                raise SafetyStop("Resume cargo/fuel preconditions changed")
            quote = next(
                (
                    g
                    for g in run.market(source).get("tradeGoods", [])
                    if g["symbol"] == good
                ),
                None,
            )
            if (
                not quote
                or not 0 < quote["purchasePrice"] <= plan["max_buy"]
                or quote["tradeVolume"] < plan["units"]
            ):
                raise SafetyStop("Resume acquisition quote no longer valid")
            buyer_quote = next(
                (
                    g
                    for g in run.market(destination).get("tradeGoods", [])
                    if g["symbol"] == good
                ),
                None,
            )
            if (
                not buyer_quote
                or buyer_quote["sellPrice"] < plan["min_sell"]
                or buyer_quote["tradeVolume"] < plan["units"]
                or plan["units"] * (plan["min_sell"] - plan["max_buy"])
                <= plan["fuel_allowance"]
            ):
                raise SafetyStop("Buyer quote no longer supports the trade")
            if (
                run.get("/my/agent")["credits"]
                - plan["units"] * plan["max_buy"]
                < CREDIT_FLOOR + FUEL_ALLOWANCE
            ):
                raise SafetyStop("Resume would violate reserves")
            run.mutate(
                f"/my/ships/{ship_symbol}/purchase",
                {"symbol": good, "units": plan["units"]},
            )
            held = plan["units"]
        if held:
            previous["bought"] = True
            run.store.observe(run.scope, "position", key, previous, "strategy")
        while held:
            run.navigate(ship_symbol, destination)
            ship = run.dock(ship_symbol)
            quote = next(
                (
                    g
                    for g in run.market(destination).get("tradeGoods", [])
                    if g["symbol"] == good
                ),
                None,
            )
            if (
                not quote
                or quote["sellPrice"] < plan["min_sell"]
                or quote["tradeVolume"] <= 0
            ):
                raise SafetyStop(
                    "Buyer price/volume changed; hold cargo for review"
                )
            units = min(held, quote["tradeVolume"])
            run.mutate(
                f"/my/ships/{ship_symbol}/sell",
                {"symbol": good, "units": units},
            )
            ship = run.ship(ship_symbol)
            held = sum(
                g["units"]
                for g in ship["cargo"]["inventory"]
                if g["symbol"] == good
            )
        run.store.observe(
            run.scope,
            "position",
            key,
            previous | {"status": "closed"},
            "strategy",
        )
    final = run.refresh()
    return {
        "completed_cycles": cycles,
        "session_credit_change": final["agent"]["credits"] - initial_credits,
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }


def contract_plan(
    contract: dict[str, Any],
    market: dict[str, Any],
    credits: int,
    *,
    max_unit_price: int | None = None,
) -> dict[str, Any]:
    deliveries = contract["terms"].get("deliver", [])
    if len(deliveries) != 1:
        raise SafetyStop("First contract strategy supports one delivery good")
    delivery = deliveries[0]
    remaining = delivery["unitsRequired"] - delivery["unitsFulfilled"]
    good = next(
        (
            g
            for g in market.get("tradeGoods", [])
            if g["symbol"] == delivery["tradeSymbol"]
        ),
        None,
    )
    if not good or good["purchasePrice"] <= 0:
        raise SafetyStop("No live acquisition price; scout source first")
    payment = contract["terms"]["payment"]
    revenue = payment["onFulfilled"] + (
        0 if contract["accepted"] else payment["onAccepted"]
    )
    max_price = (
        math.ceil(good["purchasePrice"] * 1.2)
        if max_unit_price is None
        else max_unit_price
    )
    cost = remaining * max_price
    return {
        "contract": contract["id"],
        "good": delivery["tradeSymbol"],
        "remaining": remaining,
        "source": market["symbol"],
        "destination": delivery["destinationSymbol"],
        "observed_unit_price": good["purchasePrice"],
        "max_unit_price": max_price,
        "future_revenue": revenue,
        "estimated_goods_cost": remaining * good["purchasePrice"],
        "conservative_net": revenue - cost - FUEL_ALLOWANCE,
        "reserve_after_acquisition": credits - cost - FUEL_ALLOWANCE,
        # An accepted, saved plan is an obligation, not a new profit decision.
        "feasible": (
            revenue > cost + FUEL_ALLOWANCE
            or (contract["accepted"] and max_unit_price is not None)
        )
        and credits - cost - FUEL_ALLOWANCE >= CREDIT_FLOOR,
        "strategy": "buy",
        "alternative": "Extraction has stochastic yield/cooldown and cargo "
        "opportunity cost; choose bounded positive-margin purchase instead.",
    }


def contract_run(
    run: Session,
    ship_symbol: str,
    contract_id: str,
    source: str = "",
) -> dict[str, Any]:
    started = time.monotonic()
    state = run.refresh()
    initial_credits = state["agent"]["credits"]
    contract = next(
        (c for c in state["contracts"] if c["id"] == contract_id), None
    )
    if contract is None:
        raise SafetyStop("Contract not found")
    remote = next(
        (
            p["data"]
            for p in run.store.latest(run.scope, "position")
            if p["key"] == f"procurement:{contract_id}"
        ),
        None,
    )
    if remote:
        if source and source != remote["plan"]["source"]:
            raise SafetyStop("Resume original procurement source")
        source = remote["plan"]["source"]
    deliveries = contract["terms"].get("deliver", [])
    if (
        len(deliveries) == 1
        and source
        and source != deliveries[0]["destinationSymbol"]
    ):
        from py_st.services.remote_procurement import remote_contract_run

        return remote_contract_run(run, ship_symbol, contract_id, source)
    if contract["fulfilled"]:
        return {"status": "already fulfilled", "contract": contract_id}
    if any(
        c["accepted"] and not c["fulfilled"] and c["id"] != contract_id
        for c in state["contracts"]
    ):
        raise SafetyStop("Other obligations need a separate costed reserve")
    deliveries = contract["terms"].get("deliver", [])
    if len(deliveries) != 1:
        raise SafetyStop("Only single-good procurement is enabled")
    delivery = deliveries[0]
    source = source or delivery["destinationSymbol"]
    previous = next(
        (
            p["data"]
            for p in run.store.latest(run.scope, "plan")
            if p["key"] == contract_id
        ),
        None,
    )
    if contract["accepted"] and previous and previous["source"] != source:
        raise SafetyStop("Resume with the original acquisition source")
    plan = None
    while True:
        run.check()
        contract = run.get(f"/my/contracts/{contract_id}")
        run.store.observe(run.scope, "contract", contract_id, contract)
        if contract["fulfilled"]:
            break
        deadline = datetime.fromisoformat(contract["terms"]["deadline"])
        if run.execute and deadline <= datetime.now(UTC):
            raise SafetyStop("Contract deadline expired")
        delivery = contract["terms"]["deliver"][0]
        remaining = delivery["unitsRequired"] - delivery["unitsFulfilled"]
        if contract["accepted"] and remaining <= 0:
            if not run.execute:
                return {"status": "ready to fulfill", "contract": contract_id}
            run.mutate(f"/my/contracts/{contract_id}/fulfill")
            continue
        ship = run.arrive(ship_symbol)
        held = sum(
            g["units"]
            for g in ship["cargo"]["inventory"]
            if g["symbol"] == delivery["tradeSymbol"]
        )
        if contract["accepted"] and held:
            if not run.execute:
                return {
                    "status": "ready to deliver",
                    "contract": contract_id,
                    "units": min(held, remaining),
                }
            run.navigate(ship_symbol, delivery["destinationSymbol"])
            run.dock(ship_symbol)
            run.mutate(
                f"/my/contracts/{contract_id}/deliver",
                {
                    "shipSymbol": ship_symbol,
                    "tradeSymbol": delivery["tradeSymbol"],
                    "units": min(held, remaining),
                },
            )
            continue
        # Price and reserve only the goods still needing acquisition, after
        # delivering owned cargo. Completion needs neither a quote nor cash.
        if plan is None:
            plan = contract_plan(
                contract,
                run.market(source),
                run.get("/my/agent")["credits"],
                max_unit_price=(
                    previous["max_unit_price"]
                    if contract["accepted"] and previous
                    else None
                ),
            )
            run.store.observe(run.scope, "plan", contract_id, plan, "strategy")
        if not run.execute:
            return plan
        if not plan["feasible"]:
            raise SafetyStop("Contract fails conservative profit/reserve test")
        if (deadline - datetime.now(UTC)).total_seconds() < 3600:
            raise SafetyStop(
                "Contract needs at least one hour of deadline margin"
            )
        if not contract["accepted"]:
            expiration = contract.get(
                "deadlineToAccept", contract.get("expiration")
            )
            if expiration and datetime.fromisoformat(
                expiration
            ) <= datetime.now(UTC):
                raise SafetyStop("Contract acceptance expired")
            if ship["cargo"]["capacity"] <= 0:
                raise SafetyStop("Ship has no cargo capacity")
            run.navigate(ship_symbol, source)
            run.mutate(f"/my/contracts/{contract_id}/accept")
            continue
        run.navigate(ship_symbol, source)
        ship = run.dock(ship_symbol)
        market = run.market(source)
        good = next(
            (
                g
                for g in market.get("tradeGoods", [])
                if g["symbol"] == plan["good"]
            ),
            None,
        )
        if not good or not 0 < good["purchasePrice"] <= plan["max_unit_price"]:
            raise SafetyStop(
                "Price exceeded plan; preserve obligation and replan"
            )
        units = min(
            remaining,
            ship["cargo"]["capacity"] - ship["cargo"]["units"],
            good["tradeVolume"],
        )
        if units <= 0:
            raise SafetyStop("No free cargo capacity or trade volume")
        agent = run.get("/my/agent")
        obligation = (remaining - units) * plan["max_unit_price"]
        if agent["credits"] - units * good["purchasePrice"] < (
            CREDIT_FLOOR + FUEL_ALLOWANCE + obligation
        ):
            raise SafetyStop(
                "Purchase would violate floor/remaining obligation"
            )
        run.mutate(
            f"/my/ships/{ship_symbol}/purchase",
            {
                "symbol": plan["good"],
                "units": units,
            },
        )
    final = run.refresh()
    return {
        "status": "fulfilled",
        "contract": contract_id,
        "plan": plan,
        "session_credit_change": final["agent"]["credits"] - initial_credits,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "note": "Credit change excludes fuel depletion; see journal.",
    }
