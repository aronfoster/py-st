"""Pure, offline planning for complete procurement contract obligations."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _remaining(delivery: dict[str, Any]) -> int:
    required = _positive_int(delivery.get("unitsRequired"), "unitsRequired")
    fulfilled = delivery.get("unitsFulfilled", 0)
    if not isinstance(fulfilled, int) or isinstance(fulfilled, bool):
        raise ValueError("unitsFulfilled must be a non-negative integer")
    if fulfilled < 0 or fulfilled > required:
        raise ValueError(
            "unitsFulfilled must be between zero and unitsRequired"
        )
    return required - fulfilled


def _quote_capacity(quote: dict[str, Any], remaining: int) -> int:
    maximum = quote.get("available_units", remaining)
    return min(_non_negative_int(maximum, "available_units"), remaining)


def _deadline_seconds(contract: dict[str, Any], now: datetime) -> int | None:
    deadline = contract.get("terms", {}).get("deadline")
    if not deadline:
        return None
    parsed = datetime.fromisoformat(deadline)
    if parsed.tzinfo is None:
        raise ValueError("contract deadline must include a timezone")
    return math.floor((parsed - now).total_seconds())


def plan_contract_procurement(
    contract: dict[str, Any],
    quotes: list[dict[str, Any]],
    *,
    ship_capacity: int,
    credits: int,
    credit_floor: int = 50_000,
    fuel_allowance: int = 1_000,
    price_margin: float = 0.20,
    deadline_margin_seconds: int = 3_600,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Model a complete multi-good, multi-load procurement plan.

    This function performs no I/O. Quotes must be explicit snapshots supplied
    by the caller; the result is a counterfactual plan, not execution
    authority. Each quote describes one source-to-delivery route and its
    complete per-trip fuel cost and travel duration. The planner never infers
    either value.
    """
    capacity = _positive_int(ship_capacity, "ship_capacity")
    if (
        not isinstance(credits, int)
        or isinstance(credits, bool)
        or credits < 0
    ):
        raise ValueError("credits must be a non-negative integer")
    if credit_floor < 0 or fuel_allowance < 0:
        raise ValueError("reserves must be non-negative")
    if price_margin < 0:
        raise ValueError("price_margin must be non-negative")
    if deadline_margin_seconds < 0:
        raise ValueError("deadline margin must be non-negative")

    terms = contract.get("terms", {})
    deliveries = terms.get("deliver", [])
    if not deliveries:
        raise ValueError("contract has no delivery obligations")
    payment = terms.get("payment", {})
    future_revenue = _non_negative_int(
        payment.get("onFulfilled"), "onFulfilled"
    )
    if not contract.get("accepted", False):
        future_revenue += _non_negative_int(
            payment.get("onAccepted"), "onAccepted"
        )

    steps: list[dict[str, Any]] = []
    reasons: list[str] = []
    total_goods = 0
    total_fuel = 0
    total_travel = 0
    total_units = 0
    total_trips = 0

    for delivery in deliveries:
        symbol = delivery.get("tradeSymbol")
        destination = delivery.get("destinationSymbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("delivery tradeSymbol is required")
        if not isinstance(destination, str) or not destination:
            raise ValueError("delivery destinationSymbol is required")
        remaining = _remaining(delivery)
        total_units += remaining
        if remaining == 0:
            continue
        candidates = []
        for quote in quotes:
            if (
                quote.get("trade_symbol") != symbol
                or quote.get("destination") != destination
            ):
                continue
            source = quote.get("source")
            if not isinstance(source, str) or not source:
                raise ValueError("quote source is required")
            price = _positive_int(
                quote.get("purchase_price"), "purchase_price"
            )
            volume = _positive_int(quote.get("trade_volume"), "trade_volume")
            fuel = _non_negative_int(quote.get("fuel_cost"), "fuel_cost")
            travel = _non_negative_int(
                quote.get("travel_seconds"), "travel_seconds"
            )
            ceiling = math.ceil(price * (1 + price_margin))
            supply = _quote_capacity(quote, remaining)
            if supply == 0:
                continue
            # Rank full cargo chunks by conservative landed cost. Fixed trip
            # costs are amortized only across units the route can actually
            # move.
            chunk = min(capacity, supply)
            landed = ceiling + fuel / chunk
            candidates.append(
                (landed, source, ceiling, price, volume, fuel, travel, supply)
            )
        candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))

        unallocated = remaining
        for (
            _,
            source,
            ceiling,
            price,
            volume,
            fuel,
            travel,
            supply,
        ) in candidates:
            if unallocated == 0:
                break
            units = min(unallocated, supply)
            trips = math.ceil(units / capacity)
            purchases = math.ceil(units / volume)
            goods_cost = units * ceiling
            fuel_cost = trips * fuel
            step = {
                "trade_symbol": symbol,
                "source": source,
                "destination": destination,
                "units": units,
                "observed_unit_price": price,
                "max_unit_price": ceiling,
                "purchase_batches": purchases,
                "cargo_trips": trips,
                "conservative_goods_cost": goods_cost,
                "fuel_cost": fuel_cost,
                "travel_seconds": trips * travel,
            }
            steps.append(step)
            total_goods += goods_cost
            total_fuel += fuel_cost
            total_travel += trips * travel
            total_trips += trips
            unallocated -= units
        if unallocated:
            reasons.append(f"Missing {unallocated} units of {symbol} capacity")

    required_credits = credit_floor + fuel_allowance + total_goods + total_fuel
    deadline_seconds = _deadline_seconds(contract, now or datetime.now(UTC))
    if deadline_seconds is not None:
        if deadline_seconds <= 0:
            reasons.append("Contract deadline has expired")
        elif total_travel + deadline_margin_seconds > deadline_seconds:
            reasons.append("Insufficient modeled deadline margin")
    if credits < required_credits:
        reasons.append("Insufficient credits for goods, fuel, and reserves")
    conservative_net = (
        future_revenue - total_goods - total_fuel - fuel_allowance
    )
    if not contract.get("accepted", False) and conservative_net <= 0:
        reasons.append("Unaccepted contract has no conservative profit")

    return {
        "mode": "offline counterfactual",
        "contract": contract.get("id"),
        "accepted": bool(contract.get("accepted", False)),
        "obligation_count": len(deliveries),
        "remaining_units": total_units,
        "cargo_trips": total_trips,
        "steps": steps,
        "future_revenue": future_revenue,
        "conservative_goods_cost": total_goods,
        "fuel_cost": total_fuel,
        "fuel_allowance": fuel_allowance,
        "conservative_net": conservative_net,
        "required_credits": required_credits,
        "credits_after_reserves": credits - required_credits,
        "estimated_travel_seconds": total_travel,
        "deadline_seconds": deadline_seconds,
        "deadline_margin_seconds": deadline_margin_seconds,
        "feasible": not reasons,
        "reasons": reasons,
        "execution_authorized": False,
        "next_live_check": "Refresh contract, every selected market, fleet, "
        "fuel, deadlines, pending actions, positions, and STOP before "
        "mutation.",
    }
