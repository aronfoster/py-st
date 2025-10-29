"""Services for interacting with system and waypoint endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field

from py_st._generated.models import (
    Market,
    Shipyard,
    TradeGood,
    TradeSymbol,
    Waypoint,
)
from py_st.client import SpaceTradersClient


@dataclass
class MarketGoods:
    sells: list[TradeGood] = field(default_factory=list)
    buys: list[TradeGood] = field(default_factory=list)


@dataclass
class SystemGoods:
    by_waypoint: dict[str, MarketGoods] = field(default_factory=dict)
    by_good: dict[str, dict[str, list[str]]] = field(default_factory=dict)


def _sym(obj: TradeGood | TradeSymbol | str) -> str:
    """
    Return a plain string trade symbol from either:
    - a TradeGood (g.symbol may be Enum or str)
    - an Enum value (use .value)
    - a raw str
    """
    if hasattr(obj, "symbol"):
        s = obj.symbol
    elif hasattr(obj, "tradeSymbol"):
        s = obj.tradeSymbol
    else:
        s = obj
    return s.value if hasattr(s, "value") else str(s)


def _has_marketplace(wp: Waypoint) -> bool:
    """Checks if a Waypoint model has the MARKETPLACE trait."""
    return any(trait.symbol.value == "MARKETPLACE" for trait in wp.traits)


def _uniq_by_symbol(goods: list[TradeGood] | None) -> list[TradeGood]:
    if not goods:
        return []
    seen: set[str] = set()
    out: list[TradeGood] = []
    for g in goods:
        k = _sym(g)
        if k not in seen:
            seen.add(k)
            out.append(g)
    return out


def list_waypoints(
    token: str, system_symbol: str, traits: list[str] | None
) -> list[Waypoint]:
    """
    Lists waypoints in a system, optionally filtered by traits.

    Currently retrieves all waypoints via list_waypoints_all. The
    traits parameter is kept for backward compatibility and will be
    used for client-side filtering in a future step.
    """
    all_waypoints = list_waypoints_all(token, system_symbol)
    return all_waypoints


def list_waypoints_all(
    token: str, system_symbol: str, traits: list[str] | None = None
) -> list[Waypoint]:
    """
    Fetches all waypoints in a system from the API.

    This is the core function for retrieving waypoints. In the future,
    this will be backed by caching. The traits parameter is kept for
    backward compatibility with existing CLI commands but may be
    removed in future refactoring.
    """
    client = SpaceTradersClient(token=token)
    waypoints = client.systems.list_waypoints_all(system_symbol, traits=traits)
    return waypoints


def get_shipyard(
    token: str, system_symbol: str, waypoint_symbol: str
) -> Shipyard:
    """
    Gets the shipyard for a waypoint.
    """
    client = SpaceTradersClient(token=token)
    shipyard = client.systems.get_shipyard(system_symbol, waypoint_symbol)
    return shipyard


def get_market(token: str, system_symbol: str, waypoint_symbol: str) -> Market:
    """
    Gets the market for a waypoint.
    """
    client = SpaceTradersClient(token=token)
    return client.systems.get_market(system_symbol, waypoint_symbol)


def list_system_goods(token: str, system_symbol: str) -> SystemGoods:
    """
    Aggregate goods across all markets in a system (no prices).
    - sells := exports ∪ exchange
    - buys  := imports ∪ exchange
    Returns real TradeGood objects grouped by waypoint, plus a reverse
    index.
    """
    client = SpaceTradersClient(token=token)
    waypoints: list[Waypoint] = client.systems.list_waypoints_all(
        system_symbol
    )
    waypoints = [wp for wp in waypoints if _has_marketplace(wp)]

    by_waypoint: dict[str, MarketGoods] = {}
    by_good_sells: dict[str, list[str]] = {}
    by_good_buys: dict[str, list[str]] = {}

    for wp in waypoints:
        wp_sym = wp.symbol.root
        mkt: Market = client.systems.get_market(system_symbol, wp_sym)

        imports = list(mkt.imports or [])
        exports = list(mkt.exports or [])
        exchange = list(mkt.exchange or [])

        sells = _uniq_by_symbol(exports + exchange)
        buys = _uniq_by_symbol(imports + exchange)

        by_waypoint[wp_sym] = MarketGoods(
            sells=sorted(sells, key=_sym),
            buys=sorted(buys, key=_sym),
        )

        for g in by_waypoint[wp_sym].sells:
            by_good_sells.setdefault(_sym(g), []).append(wp_sym)
        for g in by_waypoint[wp_sym].buys:
            by_good_buys.setdefault(_sym(g), []).append(wp_sym)

    by_good: dict[str, dict[str, list[str]]] = {}
    for sym in sorted(set(by_good_sells) | set(by_good_buys)):
        by_good[sym] = {
            "sells": sorted(by_good_sells.get(sym, [])),
            "buys": sorted(by_good_buys.get(sym, [])),
        }

    return SystemGoods(by_waypoint=by_waypoint, by_good=by_good)
