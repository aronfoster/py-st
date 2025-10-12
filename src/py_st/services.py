from __future__ import annotations

import json

from .api_client import APIError, SpaceTraders
from .models import (
    Agent,
    Contract,
    Extraction,
    MarketTransaction,
    Ship,
    ShipCargo,
    ShipFuel,
    ShipNav,
    ShipNavFlightMode,
    Shipyard,
    Survey,
    Waypoint,
)


def get_agent_info(token: str) -> Agent:
    """
    Fetches agent data from the API.
    """
    client = SpaceTraders(token=token)
    agent = client.get_agent()
    return agent


def list_contracts(token: str) -> list[Contract]:
    """
    Fetches all contracts from the API.
    """
    client = SpaceTraders(token=token)
    contracts = client.get_contracts()
    return contracts


def negotiate_contract(token: str, ship_symbol: str) -> Contract:
    """
    Negotiates a new contract using the specified ship.
    """
    client = SpaceTraders(token=token)
    new_contract = client.negotiate_contract(ship_symbol)
    return new_contract


def deliver_contract(
    token: str,
    contract_id: str,
    ship_symbol: str,
    trade_symbol: str,
    units: int,
) -> tuple[Contract, ShipCargo]:
    """
    Delivers cargo to fulfill part of a contract.
    """
    client = SpaceTraders(token=token)
    contract, cargo = client.deliver_contract(
        contract_id, ship_symbol, trade_symbol, units
    )
    return contract, cargo


def fulfill_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Fulfills a contract.
    """
    client = SpaceTraders(token=token)
    agent, contract = client.fulfill_contract(contract_id)
    return agent, contract


def accept_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Accepts a contract.
    """
    client = SpaceTraders(token=token)
    result = client.accept_contract(contract_id)
    agent: Agent = result["agent"]
    contract: Contract = result["contract"]
    return agent, contract


def list_ships(token: str) -> list[Ship]:
    """
    Fetches all ships from the API.
    """
    client = SpaceTraders(token=token)
    ships = client.get_ships()
    return ships


def navigate_ship(
    token: str, ship_symbol: str, waypoint_symbol: str
) -> ShipNav:
    """
    Navigates a ship to a waypoint.
    """
    client = SpaceTraders(token=token)
    result = client.navigate_ship(ship_symbol, waypoint_symbol)
    return result


def orbit_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Moves a ship into orbit.
    """
    client = SpaceTraders(token=token)
    result = client.orbit_ship(ship_symbol)
    return result


def dock_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Docks a ship.
    """
    client = SpaceTraders(token=token)
    result = client.dock_ship(ship_symbol)
    return result


def extract_resources(
    token: str, ship_symbol: str, survey_json: str | None = None
) -> Extraction | None:
    """
    Extracts resources from a waypoint, optionally using a survey.
    """
    try:
        client = SpaceTraders(token=token)
        survey_to_use = None
        if survey_json:
            try:
                survey_data = json.loads(survey_json)
                survey_to_use = Survey.model_validate(survey_data)
            except (json.JSONDecodeError, TypeError):
                print("Error: Invalid survey JSON provided. Aborting.")
                return None

        extraction = client.extract_resources(
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
    client = SpaceTraders(token=token)
    surveys = client.create_survey(ship_symbol)
    return surveys


def refuel_ship(
    token: str, ship_symbol: str, units: int | None
) -> tuple[Agent, ShipFuel, MarketTransaction]:
    """
    Refuels a ship.
    """
    client = SpaceTraders(token=token)
    agent, fuel, transaction = client.refuel_ship(ship_symbol, units)
    return agent, fuel, transaction


def jettison_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> ShipCargo:
    """
    Jettisons cargo from a ship.
    """
    client = SpaceTraders(token=token)
    cargo = client.jettison_cargo(ship_symbol, trade_symbol, units)
    return cargo


def set_flight_mode(
    token: str, ship_symbol: str, flight_mode: ShipNavFlightMode
) -> ShipNav:
    """
    Sets the flight mode for a ship.
    """
    client = SpaceTraders(token=token)
    nav = client.set_flight_mode(ship_symbol, flight_mode)
    return nav


def list_waypoints(
    token: str, system_symbol: str, traits: list[str] | None
) -> list[Waypoint]:
    """
    Lists waypoints in a system, optionally filtered by traits.
    """
    client = SpaceTraders(token=token)
    waypoints = client.get_waypoints_in_system(system_symbol, traits=traits)
    return waypoints


def get_shipyard(
    token: str, system_symbol: str, waypoint_symbol: str
) -> Shipyard:
    """
    Gets the shipyard for a waypoint.
    """
    client = SpaceTraders(token=token)
    shipyard = client.get_shipyard(system_symbol, waypoint_symbol)
    return shipyard


def refine_materials(token: str, ship_symbol: str, produce: str) -> None:
    """
    Refines materials on a ship and prints the result.
    """
    try:
        client = SpaceTraders(token=token)
        result = client.refine_materials(ship_symbol, produce)
        print("🔬 Refining complete!")
        # The response contains multiple nested models.
        # For simplicity, we'll print the raw dictionary.
        print(json.dumps(result, indent=2))
    except APIError as e:
        print(f"Refining failed: {e}")
