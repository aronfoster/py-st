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
from py_st.services.cache_merge import smart_merge_cache


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


def _fetch_and_cache_waypoints(
    token: str, system_symbol: str
) -> list[Waypoint]:
    """
    Internal function to fetch and cache all waypoints for a system.

    This function handles the API communication and file-based caching logic.
    Waypoint data is cached per system and remains valid until manually
    cleared, as waypoints are generally static between weekly server resets.

    Args:
        token: API authentication token
        system_symbol: The system symbol (e.g., "X1-ABC")

    Returns:
        List of all Waypoint models for the system
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


def list_waypoints(
    token: str, system_symbol: str, traits: list[str] | None
) -> list[Waypoint]:
    """
    Lists waypoints in a system, optionally filtered by traits.

    Fetches all waypoints using file-based caching and performs client-side
    AND filtering if traits are specified. Only waypoints possessing all
    specified traits are returned.

    Args:
        token: API authentication token
        system_symbol: The system symbol (e.g., "X1-ABC")
        traits: Optional list of trait symbols to filter by (AND logic)

    Returns:
        List of Waypoint models, filtered if traits are specified
    """
    all_waypoints = _fetch_and_cache_waypoints(token, system_symbol)

    # If no traits specified, return all waypoints
    if not traits:
        return all_waypoints

    # Create set of requested traits for efficient lookup
    requested_traits = set(traits)

    # Filter waypoints - keep only those with ALL requested traits
    filtered_waypoints = []
    for waypoint in all_waypoints:
        # Extract trait symbols from waypoint
        waypoint_trait_symbols = {
            trait.symbol.value for trait in waypoint.traits
        }

        # Check if waypoint has all requested traits (superset)
        if waypoint_trait_symbols.issuperset(requested_traits):
            filtered_waypoints.append(waypoint)

    return filtered_waypoints


def get_shipyard(
    token: str,
    system_symbol: str,
    waypoint_symbol: str,
    force_refresh: bool = False,
) -> Shipyard:
    """
    Gets the shipyard for a waypoint with smart caching.

    The cache preserves ship data (ships) even when API calls made from
    a distance return ships=null. The cache always stores the "best"
    version of the Shipyard object (one with ships is better).

    Args:
        token: API authentication token
        system_symbol: The system symbol (e.g., "X1-ABC")
        waypoint_symbol: The waypoint symbol (e.g., "X1-ABC-1")
        force_refresh: If True, fetch fresh data from API regardless of cache

    Returns:
        Shipyard object with the most complete data available
    """
    # Define cache key for this shipyard
    cache_key = f"shipyard_{waypoint_symbol}"

    # Load the full cache
    full_cache = load_cache()

    # Try to get cached entry
    cached_entry = full_cache.get(cache_key)
    cached_shipyard: Shipyard | None = None

    if cached_entry:
        try:
            # Parse cached shipyard data
            cached_shipyard = Shipyard.model_validate(cached_entry["data"])
        except Exception as e:
            # Log validation error and proceed as cache miss
            logging.warning(
                "Failed to validate cached shipyard for %s: %s",
                waypoint_symbol,
                e,
            )
            cached_shipyard = None

    # Case 1: Return from cache (no API call)
    if cached_shipyard is not None and not force_refresh:
        logging.debug(f"Returning cached shipyard data for {waypoint_symbol}")
        return cached_shipyard

    # Case 2: API call (cache miss or force_refresh=True)
    logging.debug(f"Fetching fresh shipyard data for {waypoint_symbol}")

    client = SpaceTradersClient(token=token)
    fresh_shipyard: Shipyard = client.systems.get_shipyard(
        system_symbol, waypoint_symbol
    )

    # Use smart merge helper to handle cache preservation logic
    return_shipyard, new_timestamp = smart_merge_cache(
        Shipyard,
        cached_entry,
        fresh_shipyard,
        "ships",
        "ships_updated",
        ["shipTypes"],
    )

    # Save and return
    full_cache[cache_key] = {
        "ships_updated": new_timestamp,
        "data": return_shipyard.model_dump(mode="json"),
    }
    save_cache(full_cache)

    return return_shipyard


def get_market(
    token: str,
    system_symbol: str,
    waypoint_symbol: str,
    force_refresh: bool = False,
) -> Market:
    """
    Gets the market for a waypoint with smart caching.

    The cache preserves price data (tradeGoods) even when API calls made from
    a distance return tradeGoods=null. The cache always stores the "best"
    version of the Market object (one with tradeGoods is better).

    Args:
        token: API authentication token
        system_symbol: The system symbol (e.g., "X1-ABC")
        waypoint_symbol: The waypoint symbol (e.g., "X1-ABC-1")
        force_refresh: If True, fetch fresh data from API regardless of cache

    Returns:
        Market object with the most complete data available
    """
    # Define cache key for this market
    cache_key = f"market_{waypoint_symbol}"

    # Load the full cache
    full_cache = load_cache()

    # Try to get cached entry
    cached_entry = full_cache.get(cache_key)
    cached_market: Market | None = None

    if cached_entry:
        try:
            # Parse cached market data
            cached_market = Market.model_validate(cached_entry["data"])
        except Exception as e:
            # Log validation error and proceed as cache miss
            logging.warning(
                "Failed to validate cached market for %s: %s",
                waypoint_symbol,
                e,
            )
            cached_market = None

    # Case 1: Return from cache (no API call)
    if cached_market is not None and not force_refresh:
        logging.debug(f"Returning cached market data for {waypoint_symbol}")
        return cached_market

    # Case 2: API call (cache miss or force_refresh=True)
    logging.debug(f"Fetching fresh market data for {waypoint_symbol}")

    client = SpaceTradersClient(token=token)
    fresh_market: Market = client.systems.get_market(
        system_symbol, waypoint_symbol
    )

    # Use smart merge helper to handle cache preservation logic
    return_market, new_timestamp = smart_merge_cache(
        Market,
        cached_entry,
        fresh_market,
        "tradeGoods",
        "prices_updated",
        ["exports", "imports", "exchange"],
    )

    # Save and return
    full_cache[cache_key] = {
        "prices_updated": new_timestamp,
        "data": return_market.model_dump(mode="json"),
    }
    save_cache(full_cache)

    return return_market


def list_system_goods(token: str, system_symbol: str) -> SystemGoods:
    """
    Aggregate goods across all markets in a system (no prices).
    - sells := exports ∪ exchange
    - buys  := imports ∪ exchange
    Returns real TradeGood objects grouped by waypoint, plus a reverse
    index.
    """
    waypoints: list[Waypoint] = _fetch_and_cache_waypoints(
        token, system_symbol
    )
    waypoints = [wp for wp in waypoints if _has_marketplace(wp)]

    by_waypoint: dict[str, MarketGoods] = {}
    by_good_sells: dict[str, list[str]] = {}
    by_good_buys: dict[str, list[str]] = {}

    for wp in waypoints:
        wp_sym = wp.symbol.root
        mkt: Market = get_market(token, system_symbol, wp_sym)

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
