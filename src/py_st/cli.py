from __future__ import annotations

import json
import logging
import os

import typer
from dotenv import load_dotenv

from py_st.models import ShipNavFlightMode

from . import services

# General options
TOKEN_OPTION = typer.Option(None, help="API token (overrides env).")
VERBOSE_OPTION = typer.Option(
    False, "--verbose", "-v", help="Verbose logging."
)
SHOW_OPTION = typer.Option(True, help="Show current agent info.")

# Contract-specific
SHIP_SYMBOL_ARG = typer.Argument(
    ..., help="The symbol of the ship to use for negotiation."
)
DELIVER_TRADE_SYMBOL_ARG = typer.Argument(
    ..., help="The symbol of the trade good to deliver."
)
DELIVER_UNITS_ARG = typer.Argument(..., help="The number of units to deliver.")
CONTRACT_ID_ARG = typer.Argument(..., help="The ID of the contract to accept.")

# Ships-specific
REFUEL_UNITS_OPTION = typer.Option(
    None, "--units", "-u", help="The number of units of fuel to purchase."
)
FLIGHT_MODE_ARG = typer.Argument(
    ..., help="The flight mode to set for the ship."
)

# Systems-specific
SYSTEM_SYMBOL_ARG = typer.Argument(..., help="The system to scan.")
WAYPOINT_SYMBOL_ARG = typer.Argument(..., help="The waypoint to use.")
TRAITS_OPTION = typer.Option(
    None, "--trait", help="Filter waypoints by trait."
)

app = typer.Typer(help="SpaceTraders CLI for py-st")

# Command groups
contracts_app = typer.Typer(help="Manage contracts.")
app.add_typer(contracts_app, name="contracts")

ships_app = typer.Typer(help="Manage your ships.")
app.add_typer(ships_app, name="ships")

systems_app = typer.Typer(help="View system information.")
app.add_typer(systems_app, name="systems")


@app.callback()
def callback() -> None:
    """
    SpaceTraders CLI for py-st
    """


def _get_token(token: str | None) -> str:
    load_dotenv()
    t = token or os.getenv("ST_TOKEN")
    if not t:
        raise typer.BadParameter(
            "Missing token. Set --token or ST_TOKEN env var."
        )
    return t


@app.command("agent")
def agent(
    show: bool = SHOW_OPTION,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Query and print agent info.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    if show:
        agent_info = services.get_agent_info(t)
        print(json.dumps(agent_info.model_dump(mode="json"), indent=2))


@contracts_app.command("list")
def list_contracts(
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    List all of your contracts.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    contracts = services.list_contracts(t)
    contracts_list = [c.model_dump(mode="json") for c in contracts]
    print(json.dumps(contracts_list, indent=2))


@contracts_app.command("negotiate")
def negotiate_contract_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Negotiate a new contract.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    new_contract = services.negotiate_contract(t, ship_symbol)
    print("🎉 New contract negotiated!")
    print(json.dumps(new_contract.model_dump(mode="json"), indent=2))


@contracts_app.command("deliver")
def deliver_contract_cli(
    contract_id: str = CONTRACT_ID_ARG,
    ship_symbol: str = SHIP_SYMBOL_ARG,
    trade_symbol: str = DELIVER_TRADE_SYMBOL_ARG,
    units: int = DELIVER_UNITS_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Deliver cargo to a contract.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    contract, cargo = services.deliver_contract(
        t, contract_id, ship_symbol, trade_symbol, units
    )
    print("📦 Cargo delivered!")
    output_data = {
        "contract": contract.model_dump(mode="json"),
        "cargo": cargo.model_dump(mode="json"),
    }
    print(json.dumps(output_data, indent=2))


@contracts_app.command("fulfill")
def fulfill_contract_cli(
    contract_id: str = CONTRACT_ID_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Fulfill a contract.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    agent, contract = services.fulfill_contract(t, contract_id)
    print("🎉 Contract fulfilled!")
    output_data = {
        "agent": agent.model_dump(mode="json"),
        "contract": contract.model_dump(mode="json"),
    }
    print(json.dumps(output_data, indent=2))


@ships_app.command("list")
def list_ships(
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    List all of your ships.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    ships = services.list_ships(t)
    ships_list = [s.model_dump(mode="json") for s in ships]
    print(json.dumps(ships_list, indent=2))


@ships_app.command("navigate")
def navigate_ship_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    waypoint_symbol: str = WAYPOINT_SYMBOL_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Navigate a ship to a waypoint.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    result = services.navigate_ship(t, ship_symbol, waypoint_symbol)
    print(f"🚀 Ship {ship_symbol} is navigating to {waypoint_symbol}.")
    print(json.dumps(result.model_dump(mode="json"), indent=2))


@ships_app.command("orbit")
def orbit_ship_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Move a ship into orbit.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    result = services.orbit_ship(t, ship_symbol)
    print(f"🛰️  Ship {ship_symbol} is now in orbit.")
    print(json.dumps(result.model_dump(mode="json"), indent=2))


@ships_app.command("dock")
def dock_ship_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Dock a ship.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    result = services.dock_ship(t, ship_symbol)
    print(f"⚓ Ship {ship_symbol} is now docked.")
    print(json.dumps(result.model_dump(mode="json"), indent=2))


@ships_app.command("extract")
def extract_resources_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Extract resources from a waypoint.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    extraction = services.extract_resources(t, ship_symbol)
    print("⛏️ Extraction successful!")
    print(json.dumps(extraction.model_dump(mode="json"), indent=2))


@ships_app.command("survey")
def create_survey_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Create a survey of the current waypoint.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    surveys = services.create_survey(t, ship_symbol)
    print("🔭 Survey complete!")
    surveys_list = [s.model_dump(mode="json") for s in surveys]
    print(json.dumps(surveys_list, indent=2))


@ships_app.command("refuel")
def refuel_ship_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    units: int | None = REFUEL_UNITS_OPTION,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Refuel a ship.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    agent, fuel, transaction = services.refuel_ship(t, ship_symbol, units)
    print("⛽ Refueling complete!")
    output_data = {
        "agent": agent.model_dump(mode="json"),
        "fuel": fuel.model_dump(mode="json"),
        "transaction": transaction.model_dump(mode="json"),
    }
    print(json.dumps(output_data, indent=2))


@ships_app.command("flight-mode")
def set_flight_mode_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    flight_mode: ShipNavFlightMode = FLIGHT_MODE_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Set the flight mode for a ship.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    nav = services.set_flight_mode(t, ship_symbol, flight_mode)
    print(f"✈️ Flight mode for {ship_symbol} set to {flight_mode.value}.")
    print(json.dumps(nav.model_dump(mode="json"), indent=2))


@contracts_app.command("accept")
def accept_contract_cli(
    contract_id: str = CONTRACT_ID_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Accept a contract.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    agent, contract = services.accept_contract(t, contract_id)
    print(f"✅ Contract {contract_id} accepted!")
    output_data = {
        "agent": agent.model_dump(mode="json"),
        "contract": contract.model_dump(mode="json"),
    }
    print(json.dumps(output_data, indent=2))


@systems_app.command("waypoints")
def list_waypoints(
    system_symbol: str = SYSTEM_SYMBOL_ARG,
    traits: list[str] = TRAITS_OPTION,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    List waypoints in a system, with an option to filter by traits.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    waypoints = services.list_waypoints(t, system_symbol, traits)
    waypoints_list = [w.model_dump(mode="json") for w in waypoints]
    print(json.dumps(waypoints_list, indent=2))


@systems_app.command("shipyard")
def get_shipyard_cli(
    system_symbol: str = SYSTEM_SYMBOL_ARG,
    waypoint_symbol: str = WAYPOINT_SYMBOL_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Get the shipyard for a waypoint.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    shipyard = services.get_shipyard(t, system_symbol, waypoint_symbol)
    print(json.dumps(shipyard.model_dump(mode="json"), indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
