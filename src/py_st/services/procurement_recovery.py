"""Explicit local retirement of provably unaccepted procurement intent."""

from __future__ import annotations

import re
from typing import Any

from py_st.services.automation import SafetyStop, Session


def abandon_procurement(
    run: Session,
    contract_id: str,
    *,
    execute: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    """GET-only preflight; execute permits one local observation, not POST."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", contract_id):
        raise SafetyStop("Use the full original contract ID")
    reason = reason.strip()
    if execute and len(reason) < 20:
        raise SafetyStop(
            "Execution requires --reason of at least 20 characters"
        )
    key = f"procurement:{contract_id}"
    original = None
    plan: dict[str, Any] = {}
    for _ in range(2 if execute else 1):
        run.check()
        state = run.refresh()
        scope = run.scope.split(":")
        if (
            len(scope) != 2
            or any(s.lower() in ("", "none", "unknown", "null") for s in scope)
            or scope[1] != state.get("agent", {}).get("symbol")
        ):
            raise SafetyStop(
                "Unknown reset/agent scope; review identity first"
            )
        positions = run.store.latest(run.scope, "position")
        matches = [p for p in positions if p["key"] == key]
        if len(matches) != 1:
            raise SafetyStop(
                "Exactly one original procurement intent is required"
            )
        saved = matches[0]
        position = saved["data"]
        if not isinstance(position, dict):
            raise SafetyStop("Invalid original procurement position")
        saved_plan = position.get("plan")
        if (
            not isinstance(saved_plan, dict)
            or saved_plan.get("contract") != contract_id
            or any(
                not isinstance(saved_plan.get(k), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]+", saved_plan[k])
                for k in ("ship", "source", "destination")
            )
            or len(saved_plan["source"].split("-")) != 3
        ):
            raise SafetyStop("Invalid original ship/source/contract identity")
        plan = saved_plan
        if original is not None and saved != original:
            raise SafetyStop(
                "Original saved position changed during preflight"
            )
        if position.get("status") == "closed":
            if (
                position.get("stage") == "abandoned"
                and position.get("purchased") is False
            ):
                return {"status": "already abandoned", "contract": contract_id}
            raise SafetyStop("Closed position is not an abandoned intent")
        if position.get("status") != "open":
            raise SafetyStop("Exactly one open procurement intent is required")
        if position.get("purchased", False) is not False or any(
            position.get(k, 0) != 0 for k in ("held", "delivered")
        ):
            raise SafetyStop("Recorded acquisition/delivery needs review")
        original = saved
        contracts = state.get("contracts")
        if not isinstance(contracts, list) or any(
            not isinstance(c, dict)
            or not isinstance(c.get("id"), str)
            or any(
                type(c.get(k)) is not bool for k in ("accepted", "fulfilled")
            )
            for c in contracts
        ):
            raise SafetyStop("Invalid contract identity or boolean flags")
        targets = [c for c in contracts if c["id"] == contract_id]
        if len(targets) != 1:
            raise SafetyStop("Fresh contract must be uniquely present")
        contract = targets[0]
        if contract["accepted"] or contract["fulfilled"]:
            raise SafetyStop("Contract must be unaccepted and unfulfilled")
        if any(c["accepted"] and not c["fulfilled"] for c in contracts):
            raise SafetyStop(
                "Resolve other accepted contract obligations first"
            )
        terms = contract.get("terms")
        if not isinstance(terms, dict) or not isinstance(
            terms.get("deliver"), list
        ):
            raise SafetyStop("Invalid original contract delivery identity")
        deliveries = terms["deliver"]
        if not deliveries or any(
            not isinstance(t, dict)
            or type(t.get("unitsFulfilled")) is not int
            or t["unitsFulfilled"] != 0
            or type(t.get("unitsRequired")) is not int
            or t["unitsRequired"] <= 0
            or not isinstance(t.get("tradeSymbol"), str)
            or not t["tradeSymbol"]
            or t.get("destinationSymbol") != plan["destination"]
            for t in deliveries
        ):
            raise SafetyStop(
                "Original delivery identity/progress needs review"
            )
        if position.get("strategy") == "local-multi":
            identity = {
                "deliver": sorted(
                    [
                        {
                            k: t[k]
                            for k in (
                                "tradeSymbol",
                                "destinationSymbol",
                                "unitsRequired",
                            )
                        }
                        for t in deliveries
                    ],
                    key=lambda t: t["tradeSymbol"],
                ),
                "payment": terms.get("payment"),
                "deadline": terms.get("deadline"),
            }
            if (
                plan.get("strategy") != "local-multi"
                or plan["source"] != plan["destination"]
                or plan.get("terms") != identity
            ):
                raise SafetyStop("Original local-multi identity changed")
            # Empty live cargo cannot erase saved acquisition/delivery.
            # Inspect both the immutable initial plan and the latest progress.
            required = {
                t["tradeSymbol"]: t["unitsRequired"] for t in deliveries
            }
            for record in (plan, position):
                goods = record.get("goods")
                if (
                    len(required) != len(deliveries)
                    or not isinstance(goods, dict)
                    or set(goods) != set(required)
                    or any(
                        not isinstance(goods[good], dict)
                        or any(
                            type(goods[good].get(field)) is not int
                            or goods[good][field] != expected
                            for field, expected in (
                                ("remaining", units),
                                ("held", 0),
                                ("to_buy", units),
                            )
                        )
                        for good, units in required.items()
                    )
                ):
                    raise SafetyStop(
                        "Recorded multi-good acquisition/delivery needs review"
                    )
        elif (
            position.get("strategy") is not None
            or plan.get("strategy") is not None
            or len(deliveries) != 1
            or plan.get("good") != deliveries[0]["tradeSymbol"]
        ):
            raise SafetyStop("Unrecognized original procurement strategy")
        fleet = state.get("ships")
        if not isinstance(fleet, list) or any(
            not isinstance(s, dict) for s in fleet
        ):
            raise SafetyStop("Invalid fresh fleet")
        ships = [s for s in fleet if s.get("symbol") == plan["ship"]]
        if len(ships) != 1:
            raise SafetyStop("Original ship must be uniquely present")
        ship = run.ship(plan["ship"])
        for current in [*ships, ship]:
            nav = current.get("nav", {})
            cargo = current.get("cargo", {})
            if (
                current.get("symbol") != plan["ship"]
                or not isinstance(nav, dict)
                or nav.get("status") not in ("DOCKED", "IN_ORBIT")
                or nav.get("flightMode") != "CRUISE"
                or nav.get("waypointSymbol") != plan["source"]
                or nav.get("systemSymbol") != plan["source"].rsplit("-", 1)[0]
            ):
                raise SafetyStop(
                    "Original ship must be stationary at source in CRUISE"
                )
            if (
                not isinstance(cargo, dict)
                or type(cargo.get("capacity")) is not int
                or cargo["capacity"] < 0
                or type(cargo.get("units")) is not int
                or cargo["units"] != 0
                or cargo.get("inventory") != []
                or cargo != ships[0].get("cargo")
                or nav != ships[0].get("nav")
            ):
                raise SafetyStop(
                    "Original ship needs consistent empty cargo/navigation"
                )
        # Acceptance evidence can precede actions()'s 200-row report cap.
        if run.store.db.execute(
            "SELECT 1 FROM actions WHERE scope=? AND path=? "
            "AND status NOT IN ('not_sent','rejected') LIMIT 1",
            (run.scope, f"/my/contracts/{contract_id}/accept"),
        ).fetchone():
            raise SafetyStop(
                "Acceptance journal evidence requires review; cannot abandon"
            )
        if run.store.pending(run.scope):
            raise SafetyStop(
                "Resolve global pending actions in this scope first"
            )
        current_positions = run.store.latest(run.scope, "position")
        if any(
            p["key"] != key
            and (
                not isinstance(p["data"], dict)
                or p["data"].get("status") != "closed"
            )
            for p in current_positions
        ):
            raise SafetyStop("Resolve unrelated nonclosed positions first")
        if [p for p in current_positions if p["key"] == key] != [original]:
            raise SafetyStop(
                "Original saved position changed during preflight"
            )
        run.check()
    if execute:
        run.store.observe(
            run.scope,
            "position",
            key,
            position
            | {
                "status": "closed",
                "stage": "abandoned",
                "purchased": False,
                "cancellation_reason": reason,
            },
            source="procurement-recovery",
        )
    return {
        "status": "abandoned" if execute else "ready to abandon",
        "contract": contract_id,
        "ship": plan["ship"],
        "source": plan["source"],
        "game_mutations_authorized": False,
        "next_step": (
            "Local intent only; original plan/history retained."
            if execute
            else "Use --execute --reason (at least 20 characters) "
            "to close local intent."
        ),
    }
