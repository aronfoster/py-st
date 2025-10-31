"""CLI helper functions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import typer

from py_st._generated.models import Ship, ShipNavStatus
from py_st.services import agent, ships, systems


def resolve_ship_id(token: str, ship_id_arg: str) -> str:
    """
    Resolves a ship identifier to a full ship symbol.

    Args:
        token: The API authentication token.
        ship_id_arg: Either a full ship symbol or a prefixed 0-based index
            (e.g., 's-0', 'S-1').

    Returns:
        The full ship symbol.

    Raises:
        typer.Exit: If the index is out of bounds.
    """
    # Check for index prefix (s- or S-)
    if ship_id_arg.lower().startswith("s-"):
        index_str = ship_id_arg[2:]
        if not index_str.isdigit():
            return ship_id_arg
        index = int(index_str)
    else:
        return ship_id_arg

    all_ships = ships.list_ships(token)
    all_ships.sort(key=lambda s: s.symbol)

    if 0 <= index < len(all_ships):
        resolved = all_ships[index].symbol
        logging.info("Resolved ship index %d to symbol: %s", index, resolved)
        return resolved

    typer.secho(
        f"Error: Invalid ship index '{ship_id_arg}'. "
        f"Valid indexes are 0 to {len(all_ships) - 1}.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=1)


def resolve_waypoint_id(token: str, system_symbol: str, wp_id_arg: str) -> str:
    """
    Resolves a waypoint identifier to a full waypoint symbol.

    Args:
        token: The API authentication token.
        system_symbol: The system symbol (e.g., "X1-ABC").
        wp_id_arg: Either a full waypoint symbol or a prefixed 0-based index
            (e.g., 'w-0', 'W-1').

    Returns:
        The full waypoint symbol.

    Raises:
        typer.Exit: If the index is out of bounds.
    """
    # Check for index prefix (w- or W-)
    if wp_id_arg.lower().startswith("w-"):
        index_str = wp_id_arg[2:]
        if not index_str.isdigit():
            return wp_id_arg
        index = int(index_str)
    else:
        return wp_id_arg

    all_waypoints = systems.list_waypoints(token, system_symbol, traits=None)
    all_waypoints.sort(key=lambda w: w.symbol.root)

    if 0 <= index < len(all_waypoints):
        resolved: str = all_waypoints[index].symbol.root
        logging.info(
            "Resolved waypoint index %d to symbol: %s", index, resolved
        )
        return resolved

    typer.secho(
        f"Error: Invalid waypoint index '{wp_id_arg}' for system "
        f"{system_symbol}. Valid indexes are 0 to {len(all_waypoints) - 1}.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=1)


def _format_time_remaining(arrival: datetime) -> str:
    """
    Format the time remaining until arrival.

    Args:
        arrival: The arrival datetime.

    Returns:
        A formatted string like "5m 23s" or "42s", or "Arrived" if
        arrival is in the past.
    """
    now = datetime.now(UTC)
    if arrival <= now:
        return "Arrived"

    delta = arrival - now
    total_seconds = int(delta.total_seconds())
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def format_ship_status(ship: Ship) -> str:
    """
    Format the status of a ship for display.

    Args:
        ship: The Ship object to format.

    Returns:
        A formatted status string showing location or transit info.
    """
    status = ship.nav.status

    if status == ShipNavStatus.DOCKED:
        return f"DOCKED at {ship.nav.waypointSymbol.root}"
    elif status == ShipNavStatus.IN_ORBIT:
        return f"IN_ORBIT at {ship.nav.waypointSymbol.root}"
    elif status == ShipNavStatus.IN_TRANSIT:
        destination = ship.nav.route.destination.symbol
        time_str = _format_time_remaining(ship.nav.route.arrival)
        return f"IN_TRANSIT to {destination} ({time_str})"
    else:
        return f"{status.value}"


def get_default_system(token: str) -> str:
    """
    Get the default system symbol from the agent's headquarters.

    Args:
        token: The API authentication token.

    Returns:
        The system symbol (e.g., "X1-ABC") extracted from the agent's
        headquarters waypoint.

    Raises:
        typer.Exit: If the system symbol cannot be parsed from the
        agent headquarters.
    """
    try:
        agent_info = agent.get_agent_info(token)
        hq_symbol_str: str = agent_info.headquarters

        # Validate headquarters is not None or empty
        if not hq_symbol_str:
            raise ValueError("Headquarters symbol is empty or None")

        # Split on the last hyphen to separate system from waypoint
        parts = hq_symbol_str.rsplit("-", 1)

        # Validate that we actually split on a hyphen
        if len(parts) < 2:
            raise ValueError(
                f"Invalid headquarters format '{hq_symbol_str}': "
                "expected format SECTOR-SYSTEM-WAYPOINT"
            )

        system_symbol = parts[0]

        # Validate the result is not empty
        if not system_symbol:
            raise ValueError(
                f"Could not extract system from headquarters "
                f"'{hq_symbol_str}'"
            )

        return system_symbol
    except (ValueError, IndexError, AttributeError) as e:
        typer.secho(
            f"Error: Could not parse system symbol from agent "
            f"headquarters: {e}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from e
