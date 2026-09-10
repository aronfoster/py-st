"""Recorded procurement progress for offline recovery triage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def procurement_status(
    position: dict[str, Any],
    contracts: list[dict[str, Any]],
    ships: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Join scoped records supplied by one read transaction.

    Timestamps remain separate: this is not a coherent live snapshot
    or proof that matching cargo was purchased for this contract.
    """
    result: dict[str, Any] = {
        "status": "unknown",
        "execution_authorized": False,
        "goods": [],
        "next_step": "Inspect original intent and incomplete evidence.",
    }
    plan = position["data"].get("plan")
    if not isinstance(plan, dict) or any(
        not isinstance(plan.get(k), str) or not plan[k]
        for k in ("ship", "contract", "source", "destination")
    ):
        return result
    result.update(
        {k: plan[k] for k in ("ship", "contract", "source", "destination")}
    )
    if position["key"] != f"procurement:{plan['contract']}":
        return result
    matching_contracts = [r for r in contracts if r["key"] == plan["contract"]]
    matching_ships = [r for r in ships if r["key"] == plan["ship"]]
    if len(matching_contracts) != 1 or len(matching_ships) != 1:
        return result
    contract_row, ship_row = matching_contracts[0], matching_ships[0]
    result["observations"] = {
        "position": position["observed_at"],
        "contract": contract_row["observed_at"],
        "ship": ship_row["observed_at"],
    }
    contract, ship = contract_row["data"], ship_row["data"]
    if (
        contract.get("id") != plan["contract"]
        or ship.get("symbol") != plan["ship"]
        or any(
            type(contract.get(k)) is not bool
            for k in ("accepted", "fulfilled")
        )
    ):
        return result
    terms, cargo = contract.get("terms"), ship.get("cargo")
    if not isinstance(terms, dict) or not isinstance(cargo, dict):
        return result
    deliveries, inventory = terms.get("deliver"), cargo.get("inventory")
    if (
        not isinstance(deliveries, list)
        or not deliveries
        or not isinstance(inventory, list)
        or type(cargo.get("units")) is not int
        or cargo["units"] < 0
    ):
        return result
    held: dict[str, int] = {}
    for item in inventory:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("symbol"), str)
            or type(item.get("units")) is not int
            or item["units"] < 0
        ):
            return result
        held[item["symbol"]] = held.get(item["symbol"], 0) + item["units"]
    if sum(held.values()) != cargo["units"]:
        return result
    goods = []
    seen = set()
    for term in deliveries:
        if (
            not isinstance(term, dict)
            or not isinstance(term.get("tradeSymbol"), str)
            or not term["tradeSymbol"]
            or term["tradeSymbol"] in seen
            or term.get("destinationSymbol") != plan["destination"]
            or type(term.get("unitsRequired")) is not int
            or type(term.get("unitsFulfilled")) is not int
            or not 0 <= term["unitsFulfilled"] <= term["unitsRequired"]
            or term["unitsRequired"] <= 0
        ):
            return result
        good = term["tradeSymbol"]
        seen.add(good)
        remaining = term["unitsRequired"] - term["unitsFulfilled"]
        units = held.get(good, 0)
        goods.append(
            {
                "good": good,
                "required": term["unitsRequired"],
                "delivered": term["unitsFulfilled"],
                "remaining": remaining,
                "held": units,
                "to_acquire": max(0, remaining - units),
                "excess": max(0, units - remaining),
            }
        )
    if contract["fulfilled"]:
        step = "Review local closure against fresh fulfillment evidence."
    elif not contract["accepted"]:
        step = "Review the original offer or explicit abandonment preflight."
    elif not any(g["remaining"] for g in goods):
        step = "Review fulfillment; recorded deliveries are complete."
    elif any(g["held"] for g in goods):
        step = "Review delivery of owned cargo before further acquisition."
    else:
        step = "Review original price ceilings and whole-obligation funding."
    result.update(
        status="recorded",
        goods=goods,
        accepted=contract["accepted"],
        fulfilled=contract["fulfilled"],
        delivery_deadline=terms.get("deadline"),
        unrelated_cargo={k: v for k, v in held.items() if k not in seen},
        next_step=step,
    )
    if (
        result["unrelated_cargo"]
        or any(g["excess"] for g in goods)
        or (
            contract["fulfilled"]
            and (
                not contract["accepted"] or any(g["remaining"] for g in goods)
            )
        )
    ):
        result.update(
            status="needs_review",
            next_step="Review conflicting progress or untracked cargo.",
        )
    now = now or datetime.now(UTC)
    deadlines = {"delivery": terms.get("deadline")}
    if not contract["accepted"]:
        deadlines["acceptance"] = contract.get(
            "deadlineToAccept", contract.get("expiration")
        )
    result["deadlines"] = {}
    for kind, value in deadlines.items():
        seconds = None
        try:
            if not isinstance(value, str):
                raise ValueError
            stamp = datetime.fromisoformat(value)
            seconds = (stamp - now).total_seconds()
            state = "expired" if seconds <= 0 else "open"
        except (TypeError, ValueError):
            state = "unknown"
        result["deadlines"][kind] = {
            "at": value,
            "state": state,
            "remaining_seconds": seconds,
        }
    if not contract["fulfilled"] and any(
        d["state"] != "open" for d in result["deadlines"].values()
    ):
        result.update(
            status="needs_review",
            next_step="Review expired/unknown deadlines before recovery; "
            "unaccepted intents may need explicit abandonment preflight.",
        )
    return result
