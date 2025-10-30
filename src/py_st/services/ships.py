"""Services for ship-related operations."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

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
)
from py_st._manual_models import RefineResult
from py_st.client import APIError, SpaceTradersClient

# Cache configuration for ship list
SHIP_LIST_CACHE_KEY = "ship_list"
CACHE_STALENESS_THRESHOLD = timedelta(hours=1)


def list_ships(token: str) -> list[Ship]:
    """
    Fetches all ships from the API with caching.

    Checks the cache first and returns cached data if it's fresh
    (less than 1 hour old). Otherwise, fetches from the API and
    updates the cache.
    """
    # Load cache
    full_cache = cache.load_cache()

    # Check for cached entry
    cached_entry = full_cache.get(SHIP_LIST_CACHE_KEY)
    if cached_entry is not None and isinstance(cached_entry, dict):
        try:
            # Try to parse timestamp
            last_updated_str = cached_entry.get("last_updated")
            if last_updated_str is None or not isinstance(
                last_updated_str, str
            ):
                raise ValueError("Missing or invalid last_updated")

            # Parse ISO format timestamp
            last_updated = datetime.fromisoformat(last_updated_str)

            # Ensure timezone-aware (assume UTC if naive)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=UTC)

            # Check if cache is fresh
            if datetime.now(UTC) - last_updated < CACHE_STALENESS_THRESHOLD:
                # Try to parse ship list data
                ships_data = cached_entry["data"]
                ships = [Ship.model_validate(s) for s in ships_data]
                return ships

        except (ValueError, ValidationError, KeyError) as e:
            logging.warning("Invalid cache entry for ship list: %s", e)

    # Cache miss or stale - fetch from API
    client = SpaceTradersClient(token=token)
    ships = client.ships.get_ships()

    # Update cache
    now_utc = datetime.now(UTC)
    now_iso = now_utc.isoformat()
    new_entry = {
        "last_updated": now_iso,
        "data": [ship.model_dump(mode="json") for ship in ships],
    }
    full_cache[SHIP_LIST_CACHE_KEY] = new_entry
    cache.save_cache(full_cache)

    return ships


def navigate_ship(
    token: str, ship_symbol: str, waypoint_symbol: str
) -> ShipNav:
    """
    Navigates a ship to a waypoint.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.navigate_ship(ship_symbol, waypoint_symbol)
    return result


def orbit_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Moves a ship into orbit.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.orbit_ship(ship_symbol)
    return result


def dock_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Docks a ship.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.dock_ship(ship_symbol)
    return result


def extract_resources(
    token: str, ship_symbol: str, survey_json: str | None = None
) -> Extraction | None:
    """
    Extracts resources from a waypoint, optionally using a survey.
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
    """
    client = SpaceTradersClient(token=token)
    surveys = client.ships.create_survey(ship_symbol)
    return surveys


def refuel_ship(
    token: str, ship_symbol: str, units: int | None
) -> tuple[Agent, ShipFuel, MarketTransaction]:
    """
    Refuels a ship.
    """
    client = SpaceTradersClient(token=token)
    agent, fuel, transaction = client.ships.refuel_ship(ship_symbol, units)
    return agent, fuel, transaction


def jettison_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> ShipCargo:
    """
    Jettisons cargo from a ship.
    """
    client = SpaceTradersClient(token=token)
    cargo = client.ships.jettison_cargo(ship_symbol, trade_symbol, units)
    return cargo


def set_flight_mode(
    token: str, ship_symbol: str, flight_mode: ShipNavFlightMode
) -> ShipNav:
    """
    Sets the flight mode for a ship.
    """
    client = SpaceTradersClient(token=token)
    nav = client.ships.set_flight_mode(ship_symbol, flight_mode)
    return nav


def refine_materials(
    token: str, ship_symbol: str, produce: str
) -> RefineResult:
    """
    Refines materials on a ship and prints the result.
    """
    client = SpaceTradersClient(token=token)
    return client.ships.refine_materials(ship_symbol, produce)


def sell_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> tuple[Agent, ShipCargo, MarketTransaction]:
    """
    Sells cargo from a ship at the current marketplace.
    """
    client = SpaceTradersClient(token=token)
    return client.ships.sell_cargo(ship_symbol, trade_symbol, units)


def purchase_ship(
    token: str, ship_type: str, waypoint_symbol: str
) -> tuple[Agent, Ship, ShipyardTransaction]:
    """
    Purchases a ship of the specified type at a waypoint.
    """
    client = SpaceTradersClient(token=token)
    agent, ship, transaction = client.ships.purchase_ship(
        ship_type, waypoint_symbol
    )
    return agent, ship, transaction
