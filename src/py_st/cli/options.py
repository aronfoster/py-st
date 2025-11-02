from __future__ import annotations

import os

import typer
from dotenv import load_dotenv

# General options
TOKEN_OPTION = typer.Option(None, help="API token (overrides env).")
VERBOSE_OPTION = typer.Option(
    False, "--verbose", "-v", help="Verbose logging."
)
SHOW_OPTION = typer.Option(True, help="Show current agent info.")

# Contract-specific
SHIP_SYMBOL_ARG = typer.Argument(
    ...,
    help=(
        "The ship's full symbol or s-0 based index " "(e.g., 's-0', 'S-1')."
    ),
)
DELIVER_TRADE_SYMBOL_ARG = typer.Argument(
    ..., help="The trade symbol of the good to deliver."
)
DELIVER_UNITS_ARG = typer.Argument(..., help="The number of units to deliver.")
CONTRACT_ID_ARG = typer.Argument(..., help="The ID of the contract to accept.")
PURCHASE_TRADE_SYMBOL_ARG = typer.Argument(
    ..., help="The trade symbol of the good to purchase."
)
PURCHASE_UNITS_ARG = typer.Argument(
    ..., help="The number of units to purchase."
)

# Ships-specific
REFUEL_UNITS_OPTION = typer.Option(
    None, "--units", "-u", help="The number of units of fuel to purchase."
)
FLIGHT_MODE_ARG = typer.Argument(
    ..., help="The flight mode to set for the ship."
)
PRODUCE_ARG = typer.Argument(
    ..., help="The trade symbol of the good to produce from refining."
)
SHIP_TYPE_ARG = typer.Argument(..., help="The type of ship to purchase.")
FROM_SHIP_ARG = typer.Argument(
    ...,
    help=(
        "Source ship's full symbol or s-0 based index " "(e.g., 's-0', 'S-1')."
    ),
)
TO_SHIP_ARG = typer.Argument(
    ...,
    help=(
        "Destination ship's full symbol or s-0 based index "
        "(e.g., 's-0', 'S-1')."
    ),
)
TRANSFER_TRADE_SYMBOL_ARG = typer.Argument(
    ..., help="The trade symbol of the good to transfer."
)
TRANSFER_UNITS_ARG = typer.Argument(
    ..., help="The number of units to transfer."
)

# Systems-specific
SYSTEM_SYMBOL_OPTION = typer.Option(
    None,
    "--system",
    "-s",
    help="The system symbol. Defaults to your agent's HQ system.",
)
WAYPOINT_SYMBOL_ARG = typer.Argument(
    ...,
    help=(
        "The waypoint's full symbol or w-0 based index "
        "(e.g., 'w-0', 'W-1')."
    ),
)
TRAITS_OPTION = typer.Option(
    None, "--trait", help="Filter waypoints by trait symbol."
)


def _get_token(token: str | None) -> str:
    load_dotenv()
    t = token or os.getenv("ST_TOKEN")
    if not t:
        raise typer.BadParameter(
            "Missing token. Set --token or ST_TOKEN env var."
        )
    return t
