from __future__ import annotations

import json
import logging

import typer

from py_st._generated.models import ShipNavFlightMode
from py_st.cli._errors import handle_errors
from py_st.cli._helpers import resolve_ship_id

from ..services import ships
from .options import (
    DELIVER_TRADE_SYMBOL_ARG,
    DELIVER_UNITS_ARG,
    FLIGHT_MODE_ARG,
    PRODUCE_ARG,
    REFUEL_UNITS_OPTION,
    SHIP_SYMBOL_ARG,
    SHIP_TYPE_ARG,
    TOKEN_OPTION,
    VERBOSE_OPTION,
    WAYPOINT_SYMBOL_ARG,
    _get_token,
)

ships_app: typer.Typer = typer.Typer(help="Manage your ships.")


@ships_app.command("list")
@handle_errors
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
    ships_list_data = ships.list_ships(t)
    ships_list = [s.model_dump(mode="json") for s in ships_list_data]
    print(json.dumps(ships_list, indent=2))


@ships_app.command("navigate")
@handle_errors
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
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    result = ships.navigate_ship(t, resolved_symbol, waypoint_symbol)
    print(f"🚀 Ship {resolved_symbol} is navigating to {waypoint_symbol}.")
    print(json.dumps(result.model_dump(mode="json"), indent=2))


@ships_app.command("orbit")
@handle_errors
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
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    result = ships.orbit_ship(t, resolved_symbol)
    print(f"🛰️  Ship {resolved_symbol} is now in orbit.")
    print(json.dumps(result.model_dump(mode="json"), indent=2))


@ships_app.command("dock")
@handle_errors
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
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    result = ships.dock_ship(t, resolved_symbol)
    print(f"⚓ Ship {resolved_symbol} is now docked.")
    print(json.dumps(result.model_dump(mode="json"), indent=2))


@ships_app.command("extract")
@handle_errors
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
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    extraction = ships.extract_resources(t, resolved_symbol)
    if extraction is None:
        print("Extraction failed or aborted.")
        return
    print("⛏️ Extraction successful!")
    print(json.dumps(extraction.model_dump(mode="json"), indent=2))


@ships_app.command("survey")
@handle_errors
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
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    surveys = ships.create_survey(t, resolved_symbol)
    print("🔭 Survey complete!")
    surveys_list = [s.model_dump(mode="json") for s in surveys]
    print(json.dumps(surveys_list, indent=2))


@ships_app.command("refuel")
@handle_errors
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
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    agent, fuel, transaction = ships.refuel_ship(t, resolved_symbol, units)
    print("⛽ Refueling complete!")
    output_data = {
        "agent": agent.model_dump(mode="json"),
        "fuel": fuel.model_dump(mode="json"),
        "transaction": transaction.model_dump(mode="json"),
    }
    print(json.dumps(output_data, indent=2))


@ships_app.command("flight-mode")
@handle_errors
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
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    nav = ships.set_flight_mode(t, resolved_symbol, flight_mode)
    print(f"✈️ Flight mode for {resolved_symbol} set to {flight_mode.value}.")
    print(json.dumps(nav.model_dump(mode="json"), indent=2))


@ships_app.command("jettison")
@handle_errors
def jettison_cargo_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    trade_symbol: str = DELIVER_TRADE_SYMBOL_ARG,
    units: int = DELIVER_UNITS_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Jettison cargo from a ship.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    cargo = ships.jettison_cargo(t, resolved_symbol, trade_symbol, units)
    print("🗑️ Cargo jettisoned!")
    print(json.dumps(cargo.model_dump(mode="json"), indent=2))


@ships_app.command("refine")
@handle_errors
def refine_materials_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    produce: str = PRODUCE_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Refine raw materials on a ship.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    ships.refine_materials(t, resolved_symbol, produce)


@ships_app.command("sell")
@handle_errors
def sell_cargo_cli(
    ship_symbol: str = SHIP_SYMBOL_ARG,
    trade_symbol: str = DELIVER_TRADE_SYMBOL_ARG,
    units: int = DELIVER_UNITS_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Sell cargo from a ship at the current marketplace (must be DOCKED there).
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    resolved_symbol = resolve_ship_id(t, ship_symbol)
    agent, cargo, transaction = ships.sell_cargo(
        t, resolved_symbol, trade_symbol, units
    )
    print("💱 Sale complete!")
    output = {
        "agent": agent.model_dump(mode="json"),
        "cargo": cargo.model_dump(mode="json"),
        "transaction": transaction.model_dump(mode="json"),
    }
    print(json.dumps(output, indent=2))


@ships_app.command("purchase")
@handle_errors
def purchase_ship_cli(
    waypoint_symbol: str = WAYPOINT_SYMBOL_ARG,
    ship_type: str = SHIP_TYPE_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Purchase a ship of the specified type at a waypoint.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    agent, ship, transaction = ships.purchase_ship(
        t, ship_type, waypoint_symbol
    )
    print(f"🛒 Purchased ship {ship.symbol} of type {ship_type}.")
    output = {
        "agent": agent.model_dump(mode="json"),
        "ship": ship.model_dump(mode="json"),
        "transaction": transaction.model_dump(mode="json"),
    }
    print(json.dumps(output, indent=2))
