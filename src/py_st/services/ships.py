"""Services for ship-related operations."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from pydantic import ValidationError

from py_st import cache
from py_st._generated.models import (
    Agent,
    Extraction,
    MarketTransaction,
    Ship,
    ShipCargo,
    ShipFuel,
    ShipNav,
    ShipNavFlightMode,
    ShipyardTransaction,
    Survey,
    TradeSymbol,
)
from py_st._manual_models import RefineResult
from py_st.client import APIError, SpaceTradersClient
from py_st.services.cache_keys import key_for_ship_list


def _mark_ship_list_dirty() -> None:
    """
    Marks the ship list cache as dirty without updating timestamps.

    If the cache entry doesn't exist, does nothing (missing cache
    is already treated as dirty by list_ships).
    """
    full_cache = cache.load_cache()

    cached_entry = full_cache.get(key_for_ship_list())
    if cached_entry is not None and isinstance(cached_entry, dict):
        cached_entry["is_dirty"] = True
        cache.save_cache(full_cache)


def _fetch_and_cache_ships(token: str) -> list[Ship]:
    """
    Fetches ships from API and updates the cache.

    Returns:
        List of Ship objects from the API.
    """
    client = SpaceTradersClient(token=token)
    ships = client.ships.get_ships()

    now_utc = datetime.now(UTC)
    now_iso = now_utc.isoformat()
    new_entry = {
        "last_updated": now_iso,
        "is_dirty": False,
        "data": [ship.model_dump(mode="json") for ship in ships],
    }

    full_cache = cache.load_cache()
    full_cache[key_for_ship_list()] = new_entry
    cache.save_cache(full_cache)

    return ships


def list_ships(token: str, need_clean: bool = True) -> list[Ship]:
    """
    Fetches all ships from the API with caching.

    Checks the cache first and returns cached data based on the
    "is_dirty" flag and need_clean parameter. When need_clean is True,
    also checks if any IN_TRANSIT ships have arrived and treats that
    as dirty, forcing a refresh.

    Args:
        token: The API authentication token.
        need_clean: If True, require clean/fresh data. If False,
            allow returning stale cached data.

    Returns:
        List of Ship objects.
    """
    cached_entry = cache.load_cache().get(key_for_ship_list())

    if not cached_entry or not isinstance(cached_entry, dict):
        return _fetch_and_cache_ships(token)

    try:
        ships_data = cached_entry["data"]
        ships = [Ship.model_validate(s) for s in ships_data]
    except (ValueError, ValidationError, KeyError) as e:
        logging.warning("Invalid cache entry for ship list: %s", e)
        return _fetch_and_cache_ships(token)

    is_dirty = bool(cached_entry.get("is_dirty", True))

    # If we don't need clean cache, return cached ships immediately
    if not need_clean:
        return ships

    # Need clean cache, so if dirty, refresh
    if is_dirty:
        return _fetch_and_cache_ships(token)

    # Check if any IN_TRANSIT ships have arrived since last fetch
    now_utc = datetime.now(UTC)
    arrival_passed = any(
        ship.nav.status.value == "IN_TRANSIT"
        and ship.nav.route.arrival <= now_utc
        for ship in ships
    )

    if arrival_passed:
        return _fetch_and_cache_ships(token)

    return ships


def navigate_ship(
    token: str, ship_symbol: str, waypoint_symbol: str
) -> ShipNav:
    """
    Navigates a ship to a waypoint.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship to navigate.
        waypoint_symbol: The destination waypoint symbol.

    Returns:
        ShipNav object containing updated navigation information.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.navigate_ship(ship_symbol, waypoint_symbol)
    _mark_ship_list_dirty()
    return result


def orbit_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Moves a ship into orbit.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship to move into orbit.

    Returns:
        ShipNav object with updated status showing the ship is in orbit.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.orbit_ship(ship_symbol)
    _mark_ship_list_dirty()
    return result


def dock_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Docks a ship at its current location.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship to dock.

    Returns:
        ShipNav object with updated status showing the ship is docked.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.dock_ship(ship_symbol)
    _mark_ship_list_dirty()
    return result


def extract_resources(
    token: str, ship_symbol: str, survey_json: str | None = None
) -> Extraction | None:
    """
    Extracts resources from a waypoint, optionally using a survey.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship performing extraction.
        survey_json: Optional JSON string representing a survey to use.

    Returns:
        Extraction object on success, None on failure or invalid input.
    """
    try:
        client = SpaceTradersClient(token=token)
        survey_to_use = None
        if survey_json:
            try:
                survey_data = json.loads(survey_json)
                survey_to_use = Survey.model_validate(survey_data)
            except (json.JSONDecodeError, TypeError):
                print("Error: Invalid survey JSON provided. Aborting.")
                return None

        extraction = client.ships.extract_resources(
            ship_symbol, survey=survey_to_use
        )
        return extraction
    except APIError as e:
        print(f"Extraction failed: {e}")
        return None


def create_survey(token: str, ship_symbol: str) -> list[Survey]:
    """
    Creates a survey of the current waypoint.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship performing the survey.

    Returns:
        List of Survey objects generated at the waypoint.
    """
    client = SpaceTradersClient(token=token)
    surveys = client.ships.create_survey(ship_symbol)
    return surveys


def refuel_ship(
    token: str, ship_symbol: str, units: int | None
) -> tuple[Agent, ShipFuel, MarketTransaction]:
    """
    Refuels a ship at its current docked location.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship to refuel.
        units: Optional number of fuel units to purchase. If None, refuels
            to full capacity.

    Returns:
        Tuple of (Agent, ShipFuel, MarketTransaction) with updated state.
    """
    client = SpaceTradersClient(token=token)
    agent, fuel, transaction = client.ships.refuel_ship(ship_symbol, units)
    _mark_ship_list_dirty()
    return agent, fuel, transaction


def jettison_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> ShipCargo:
    """
    Jettisons cargo from a ship into space.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship jettisoning cargo.
        trade_symbol: The trade good symbol to jettison.
        units: The number of units to jettison.

    Returns:
        ShipCargo object with updated cargo hold information.
    """
    client = SpaceTradersClient(token=token)
    cargo = client.ships.jettison_cargo(ship_symbol, trade_symbol, units)
    _mark_ship_list_dirty()
    return cargo


def set_flight_mode(
    token: str, ship_symbol: str, flight_mode: ShipNavFlightMode
) -> ShipNav:
    """
    Sets the flight mode for a ship.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship to configure.
        flight_mode: The desired flight mode (e.g., CRUISE, BURN, DRIFT).

    Returns:
        ShipNav object with updated flight mode information.
    """
    client = SpaceTradersClient(token=token)
    nav = client.ships.set_flight_mode(ship_symbol, flight_mode)
    _mark_ship_list_dirty()
    return nav


def refine_materials(
    token: str, ship_symbol: str, produce: str
) -> RefineResult:
    """
    Refines raw materials on a ship into processed goods.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship with refining capability.
        produce: The trade good symbol to produce from refining.

    Returns:
        RefineResult object containing produced/consumed items and cargo.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.refine_materials(ship_symbol, produce)
    _mark_ship_list_dirty()
    return result


def sell_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> tuple[Agent, ShipCargo, MarketTransaction]:
    """
    Sells cargo from a ship at the current marketplace.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship selling cargo.
        trade_symbol: The trade good symbol to sell.
        units: The number of units to sell.

    Returns:
        Tuple of (Agent, ShipCargo, MarketTransaction) with updated state.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.sell_cargo(ship_symbol, trade_symbol, units)
    _mark_ship_list_dirty()
    return result


def purchase_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> tuple[Agent, ShipCargo, MarketTransaction]:
    """
    Purchases cargo at the current marketplace.

    Args:
        token: The API authentication token.
        ship_symbol: The symbol of the ship purchasing cargo.
        trade_symbol: The trade good symbol to purchase.
        units: The number of units to purchase.

    Returns:
        Tuple of (Agent, ShipCargo, MarketTransaction) with updated state.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.purchase_cargo(ship_symbol, trade_symbol, units)
    _mark_ship_list_dirty()
    return result


def purchase_ship(
    token: str, ship_type: str, waypoint_symbol: str
) -> tuple[Agent, Ship, ShipyardTransaction]:
    """
    Purchases a ship of the specified type at a waypoint.

    Args:
        token: The API authentication token.
        ship_type: The type of ship to purchase (e.g., SHIP_MINING_DRONE).
        waypoint_symbol: The waypoint with a shipyard selling the ship.

    Returns:
        Tuple of (Agent, Ship, ShipyardTransaction) with updated state.
    """
    client = SpaceTradersClient(token=token)
    agent, ship, transaction = client.ships.purchase_ship(
        ship_type, waypoint_symbol
    )
    _mark_ship_list_dirty()
    return agent, ship, transaction


def transfer_cargo(
    token: str,
    from_ship: str,
    to_ship: str,
    trade_symbol: TradeSymbol,
    units: int,
) -> ShipCargo:
    """
    Transfers cargo between two ships.

    Args:
        token: The API authentication token.
        from_ship: The symbol of the ship transferring cargo.
        to_ship: The symbol of the ship receiving cargo.
        trade_symbol: The trade good symbol to transfer.
        units: The number of units to transfer.

    Returns:
        ShipCargo object with updated cargo hold for the source ship.
    """
    client = SpaceTradersClient(token=token)
    cargo = client.ships.transfer_cargo(
        from_ship, to_ship, trade_symbol.value, units
    )
    _mark_ship_list_dirty()
    return cargo
