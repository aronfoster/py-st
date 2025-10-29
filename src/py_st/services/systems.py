"""Services for interacting with system and waypoint endpoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from py_st._generated.models import (
    Market,
    Shipyard,
    TradeGood,
    TradeSymbol,
    Waypoint,
)
from py_st.cache import load_cache, save_cache
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
    Fetches all waypoints in a system, using file-based caching to
    reduce API calls.

    Waypoint data is cached per system and remains valid until
    manually cleared, as waypoints are generally static between
    weekly server resets.

    The traits parameter is kept for backward compatibility with existing CLI
    commands but may be removed in future refactoring.

    Args:
        token: API authentication token
        system_symbol: The system symbol (e.g., "X1-ABC")
        traits: Optional list of trait filters (currently unused)

    Returns:
        List of Waypoint models for the system
    """
    # Define cache key for this system
    cache_key = f"waypoints_{system_symbol}"

    # Load the full cache
    full_cache = load_cache()

    # Check if we have a cached entry for this system
    if cache_key in full_cache:
        cache_entry = full_cache[cache_key]

        # Validate cache entry structure
        if (
            isinstance(cache_entry, dict)
            and "last_updated" in cache_entry
            and "data" in cache_entry
        ):
            try:
                # Parse cached data back into Waypoint models
                cached_data = cache_entry["data"]
                if isinstance(cached_data, list):
                    waypoints = [
                        Waypoint.model_validate(wp_dict)
                        for wp_dict in cached_data
                    ]
                    logging.info(
                        "Cache hit for system %s waypoints (%d waypoints)",
                        system_symbol,
                        len(waypoints),
                    )
                    return waypoints
            except Exception as e:
                # Log validation error and proceed to cache miss
                logging.warning(
                    "Failed to validate cached waypoints for %s: %s",
                    system_symbol,
                    e,
                )

    # Cache miss or invalid data - fetch from API
    logging.info(
        "Cache miss for system %s waypoints, fetching from API",
        system_symbol,
    )

    client = SpaceTradersClient(token=token)
    # Fetch all waypoints without trait filtering for complete cache
    waypoints = client.systems.list_waypoints_all(system_symbol, traits=None)

    # Prepare data for caching - convert Waypoint models to dicts
    waypoint_dicts = [wp.model_dump(mode="json") for wp in waypoints]

    # Create cache entry with timestamp and data
    cache_entry = {
        "last_updated": datetime.now(UTC).isoformat(),
        "data": waypoint_dicts,
    }

    # Update and save the cache
    full_cache[cache_key] = cache_entry
    save_cache(full_cache)

    logging.info(
        "Cached %d waypoints for system %s", len(waypoints), system_symbol
    )

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
