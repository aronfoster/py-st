"""Stationary multi-good procurement; duplicate-good terms are ambiguous.

The delivery API selects a good, not a term. Until duplicate-term allocation
is verified, repeated goods are rejected rather than overdelivered.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from typing import Any

from py_st.services.automation import SafetyStop, Session
from py_st.services.contract_state import select_contract
from py_st.services.strategies import CREDIT_FLOOR, FUEL_ALLOWANCE


def local_contract_run(
    run: Session, ship_symbol: str, contract_id: str, source: str = ""
) -> dict[str, Any]:
    key = f"procurement:{contract_id}"
    initial_credits = None
    recovery = (
        "Resume original ship and market; no travel or refuel is enabled."
    )
    while True:
        run.check()
        state = run.refresh()
        contract = select_contract(state["contracts"], contract_id)
        if initial_credits is None:
            initial_credits = state["agent"]["credits"]
        positions = run.store.latest(run.scope, "position")
        if run.store.pending(run.scope) or any(
            p["key"] != key and p["data"].get("status") != "closed"
            for p in positions
        ):
            raise SafetyStop(
                "Resolve pending actions/nonclosed positions first"
            )
        if any(
            c.get("accepted")
            and not c.get("fulfilled")
            and c.get("id") != contract_id
            for c in state["contracts"]
        ):
            raise SafetyStop("Other accepted contracts need a costed reserve")
        terms = contract.get("terms", {})
        if not isinstance(terms, dict):
            raise SafetyStop("Invalid contract terms")
        deliveries = terms.get("deliver", [])
        if not isinstance(deliveries, list) or len(deliveries) < 2:
            raise SafetyStop("Local multi procurement requires multiple goods")
        goods: dict[str, Any] = {}
        immutable: list[dict[str, Any]] = []
        for term in deliveries:
            if not isinstance(term, dict):
                raise SafetyStop("Invalid delivery term")
            good = term.get("tradeSymbol")
            destination = term.get("destinationSymbol")
            required = term.get("unitsRequired")
            delivered = term.get("unitsFulfilled")
            if (
                not isinstance(good, str)
                or not good
                or not isinstance(destination, str)
                or not destination
                or type(required) is not int
                or required <= 0
                or type(delivered) is not int
                or not 0 <= delivered <= required
            ):
                raise SafetyStop("Invalid delivery quantities/destination")
            if good in goods:
                raise SafetyStop(
                    "Duplicate good terms have ambiguous delivery semantics"
                )
            source = source or destination
            if destination != source:
                raise SafetyStop(
                    "All goods require the same source/destination"
                )
            goods[good] = {"remaining": required - delivered, "held": 0}
            immutable.append(
                {
                    "tradeSymbol": good,
                    "destinationSymbol": destination,
                    "unitsRequired": required,
                }
            )
        payment = terms.get("payment", {})
        if not isinstance(payment, dict) or any(
            type(payment.get(k)) is not int or payment[k] < 0
            for k in ("onAccepted", "onFulfilled")
        ):
            raise SafetyStop("Invalid contract payment")
        try:
            deadline = datetime.fromisoformat(terms["deadline"])
            if deadline.tzinfo is None:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise SafetyStop("Invalid contract deadline") from None
        identity = {
            "strategy": "local-multi",
            "ship": ship_symbol,
            "contract": contract_id,
            "source": source,
            "destination": source,
            "terms": {
                "deliver": sorted(immutable, key=lambda t: t["tradeSymbol"]),
                "payment": payment,
                "deadline": terms["deadline"],
            },
        }
        previous = next(
            (p["data"] for p in positions if p["key"] == key), None
        )
        original = previous.get("plan") if previous else None
        if previous is not None and (
            previous.get("status") not in ("open", "closed")
            or previous.get("strategy") != "local-multi"
            or not isinstance(original, dict)
            or any(original.get(k) != v for k, v in identity.items())
            or (previous["status"] == "closed" and not contract["fulfilled"])
        ):
            raise SafetyStop(
                "Original local-multi ship/source/terms changed; review"
            )
        if contract["accepted"] and not original:
            raise SafetyStop(
                "Accepted local-multi procurement needs original plan"
            )
        ship = run.ship(ship_symbol)
        nav = ship.get("nav")
        if not isinstance(nav, dict):
            raise SafetyStop("Invalid ship navigation")
        if (
            ship.get("symbol") != ship_symbol
            or nav.get("status") not in ("DOCKED", "IN_ORBIT")
            or nav.get("flightMode") != "CRUISE"
            or nav.get("waypointSymbol") != source
            or nav.get("systemSymbol") != source.rsplit("-", 1)[0]
        ):
            raise SafetyStop(
                "Original ship must be stationary at market in CRUISE"
            )
        cargo = ship.get("cargo")
        if (
            not isinstance(cargo, dict)
            or type(cargo.get("capacity")) is not int
            or cargo["capacity"] <= 0
            or type(cargo.get("units")) is not int
            or not 0 <= cargo["units"] <= cargo["capacity"]
        ):
            raise SafetyStop("Invalid cargo capacity/units")
        if not isinstance(cargo.get("inventory"), list) or any(
            not isinstance(item, dict) for item in cargo["inventory"]
        ):
            raise SafetyStop("Invalid cargo inventory")
        for item in cargo["inventory"]:
            if (
                item.get("symbol") not in goods
                or type(item.get("units")) is not int
                or item["units"] < 0
            ):
                raise SafetyStop("Untracked cargo needs review")
            goods[item["symbol"]]["held"] += item["units"]
        if sum(g["held"] for g in goods.values()) != cargo["units"] or any(
            g["held"] > g["remaining"] for g in goods.values()
        ):
            raise SafetyStop("Untracked/excess cargo needs review")
        for g in goods.values():
            g["to_buy"] = g["remaining"] - g["held"]
            g["purchase_batches"] = None if g["to_buy"] else 0
        if original:
            ceilings = original.get("purchase_ceilings", {})
            if set(ceilings) != set(goods) or any(
                type(v) is not int or v < 0 for v in ceilings.values()
            ):
                raise SafetyStop("Invalid original purchase ceilings")
        else:
            # Already-owned goods need no quote and authorize no later rebuy.
            ceilings = dict.fromkeys(goods, 0)
        if contract["fulfilled"]:
            if any(g["remaining"] for g in goods.values()):
                raise SafetyStop("Fulfilled contract has outstanding goods")
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
                "recovery": recovery,
                "session_credit_change": state["agent"]["credits"]
                - initial_credits,
            }
        if deadline <= datetime.now(UTC):
            raise SafetyStop("Contract deadline expired")
        # Deliver any owned good first, even if another good cannot be bought.
        ready = contract["accepted"] and (
            cargo["units"] > 0
            or not any(g["remaining"] for g in goods.values())
        )
        quotes = {}
        observed = time.monotonic()
        expiry = None
        if not ready:
            if (deadline - datetime.now(UTC)).total_seconds() < 3600:
                raise SafetyStop(
                    "Acquisition requires one hour of deadline margin"
                )
            if not contract["accepted"]:
                try:
                    expiry = datetime.fromisoformat(
                        contract.get("deadlineToAccept")
                        or contract["expiration"]
                    )
                    if expiry.tzinfo is None or expiry <= datetime.now(UTC):
                        raise ValueError
                except (KeyError, TypeError, ValueError):
                    raise SafetyStop(
                        "Contract acceptance expired or invalid"
                    ) from None
            if any(g["to_buy"] for g in goods.values()):
                market = run.market(source)
                if market.get("symbol") != source:
                    raise SafetyStop("Acquisition market changed")
                for good, g in goods.items():
                    if not g["to_buy"]:
                        continue
                    matches = [
                        q
                        for q in market.get("tradeGoods", [])
                        if q.get("symbol") == good
                    ]
                    if len(matches) != 1 or any(
                        type(matches[0].get(k)) is not int
                        or matches[0][k] <= 0
                        for k in ("purchasePrice", "tradeVolume")
                    ):
                        raise SafetyStop(
                            "Missing/ambiguous acquisition price/volume"
                        )
                    quote = matches[0]
                    if not original:
                        ceilings[good] = math.ceil(
                            quote["purchasePrice"] * 1.2
                        )
                    if quote["purchasePrice"] > ceilings[good]:
                        raise SafetyStop("Price exceeds original good ceiling")
                    quotes[good] = quote
                    # Deliver each purchase immediately, not full remote loads:
                    # 80 units with capacity 40/volume 30 uses 30, 30, 20.
                    g["purchase_batches"] = math.ceil(
                        g["to_buy"]
                        / min(cargo["capacity"], quote["tradeVolume"])
                    )
        cost = sum(g["to_buy"] * ceilings[k] for k, g in goods.items())
        reserve = CREDIT_FLOOR + FUEL_ALLOWANCE + cost
        revenue = payment["onFulfilled"] + (
            0 if contract["accepted"] else payment["onAccepted"]
        )
        credits = run.get("/my/agent")["credits"]
        if run.execute:
            # Quote/credit GETs can wait. Revalidate only execution-relevant
            # fields; changing cooldown/route metadata is not a cargo change.
            fresh = run.refresh()
            fresh_ship = run.ship(ship_symbol)
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
                c.get("accepted")
                and not c.get("fulfilled")
                and c.get("id") != contract_id
                for c in fresh["contracts"]
            ):
                raise SafetyStop(
                    "Contract obligations changed before dispatch"
                )
            fleet = [
                s for s in fresh["ships"] if s.get("symbol") == ship_symbol
            ]
            if len(fleet) != 1 or any(
                s.get("symbol") != ship_symbol
                or s.get("cargo") != cargo
                or any(
                    s.get("nav", {}).get(k) != nav.get(k)
                    for k in (
                        "status",
                        "flightMode",
                        "waypointSymbol",
                        "systemSymbol",
                    )
                )
                for s in [*fleet, fresh_ship]
            ):
                raise SafetyStop(
                    "Ship cargo/navigation changed before dispatch"
                )
            positions = run.store.latest(run.scope, "position")
            if (
                run.store.pending(run.scope)
                or any(
                    p["key"] != key and p["data"].get("status") != "closed"
                    for p in positions
                )
                or next(
                    (p["data"] for p in positions if p["key"] == key), None
                )
                != previous
            ):
                raise SafetyStop(
                    "Procurement exposure changed before dispatch"
                )
            credits = fresh["agent"]["credits"]
        plan = identity | {
            "goods": goods,
            "purchase_ceilings": ceilings,
            "remaining_goods_reserve": cost,
            "protected_credits": reserve,
            "credit_floor": CREDIT_FLOOR,
            "fuel_allowance": FUEL_ALLOWANCE,
            "travel_fuel_reserve": 0,
            "conservative_net": revenue - cost - FUEL_ALLOWANCE,
            "feasible": bool(
                ready
                or (
                    credits >= reserve
                    and (
                        contract["accepted"] or revenue > cost + FUEL_ALLOWANCE
                    )
                )
            ),
            "recovery": recovery,
        }
        run.store.observe(run.scope, "plan", key, plan)
        if not run.execute:
            return plan
        if not plan["feasible"]:
            raise SafetyStop("Contract fails whole-goods profit/reserve test")
        if deadline <= datetime.now(UTC):
            raise SafetyStop("Contract deadline expired before dispatch")
        if not ready and (
            (deadline - datetime.now(UTC)).total_seconds() < 3600
            or (expiry is not None and expiry <= datetime.now(UTC))
            or time.monotonic() - observed > 60
        ):
            raise SafetyStop("Acquisition evidence expired before dispatch")
        original = original or plan
        run.store.observe(
            run.scope,
            "position",
            key,
            {
                "status": "open",
                "strategy": "local-multi",
                "plan": original,
                "stage": "completion" if ready else "acquiring",
                "goods": goods,
            },
        )
        run.check()
        body = None
        if not contract["accepted"]:
            path = f"/my/contracts/{contract_id}/accept"
        elif not any(g["remaining"] for g in goods.values()):
            path = f"/my/contracts/{contract_id}/fulfill"
        elif nav["status"] != "DOCKED":
            path = f"/my/ships/{ship_symbol}/dock"
        elif cargo["units"]:
            good = next(k for k, g in goods.items() if g["held"])
            path = f"/my/contracts/{contract_id}/deliver"
            body = {
                "shipSymbol": ship_symbol,
                "tradeSymbol": good,
                "units": goods[good]["held"],
            }
        else:
            good = next(k for k, g in goods.items() if g["to_buy"])
            path = f"/my/ships/{ship_symbol}/purchase"
            body = {
                "symbol": good,
                "units": min(
                    goods[good]["to_buy"],
                    cargo["capacity"],
                    quotes[good]["tradeVolume"],
                ),
            }
        # Session.wait enforces these cutoffs inside transport pacing/retries.
        budget = run.deadline
        monotonic = time.monotonic()
        now = datetime.now(UTC)
        actual_cutoff = monotonic + (deadline - now).total_seconds()
        run.deadline = min(budget, actual_cutoff)
        if not ready:
            run.deadline = min(
                run.deadline, observed + 60, actual_cutoff - 3600
            )
        if expiry is not None:
            run.deadline = min(
                run.deadline, monotonic + (expiry - now).total_seconds()
            )
        try:
            run.mutate(path, body)
        finally:
            run.deadline = budget
