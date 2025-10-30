"""CLI helper functions."""

from __future__ import annotations

import logging

import typer

from py_st.services import ships


def resolve_ship_id(token: str, ship_id_arg: str) -> str:
    """
    Resolves a ship identifier to a full ship symbol.

    Args:
        token: The API authentication token.
        ship_id_arg: Either a full ship symbol or a 0-based index.

    Returns:
        The full ship symbol.

    Raises:
        typer.Exit: If the index is out of bounds.
    """
    if not ship_id_arg.isdigit():
        return ship_id_arg

    index = int(ship_id_arg)

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
