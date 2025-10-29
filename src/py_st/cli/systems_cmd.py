from __future__ import annotations

import json
import logging
from typing import Any

import typer

from py_st.cli._errors import handle_errors

from ..services import systems
from .options import (
    SYSTEM_SYMBOL_ARG,
    TOKEN_OPTION,
    TRAITS_OPTION,
    VERBOSE_OPTION,
    WAYPOINT_SYMBOL_ARG,
    _get_token,
)

systems_app: typer.Typer = typer.Typer(help="View system information.")


@systems_app.command("waypoints")
@handle_errors
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
    waypoints = systems.list_waypoints(t, system_symbol, traits)
    waypoints_list = [w.model_dump(mode="json") for w in waypoints]
    print(json.dumps(waypoints_list, indent=2))


@systems_app.command("waypoints-all")
@handle_errors
def list_waypoints_all(
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
    waypoints = systems.list_waypoints_all(t, system_symbol, traits=traits)
    waypoints_list = [w.model_dump(mode="json") for w in waypoints]
    print(json.dumps(waypoints_list, indent=2))


@systems_app.command("shipyard")
@handle_errors
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
    shipyard = systems.get_shipyard(t, system_symbol, waypoint_symbol)
    print(json.dumps(shipyard.model_dump(mode="json"), indent=2))


@systems_app.command("market")
@handle_errors
def get_market_cli(
    system_symbol: str = SYSTEM_SYMBOL_ARG,
    waypoint_symbol: str = WAYPOINT_SYMBOL_ARG,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Get the market for a waypoint.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    market = systems.get_market(t, system_symbol, waypoint_symbol)
    if market is None:
        print(json.dumps({"market": None}, indent=2))
    else:
        print(json.dumps(market.model_dump(mode="json"), indent=2))


@systems_app.command("list-goods")
@handle_errors
def systems_list_goods_cli(
    system_symbol: str = SYSTEM_SYMBOL_ARG,
    by_good: bool = typer.Option(
        False, "--by-good", help="Show goods-centric view"
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit JSON instead of pretty text"
    ),
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    data = systems.list_system_goods(t, system_symbol)

    def _sym(obj: Any) -> str:
        s = getattr(obj, "symbol", obj)
        return s.value if hasattr(s, "value") else str(s)

    if json_out:
        out = {
            "by_waypoint": {
                wp: {
                    "sells": [_sym(g) for g in mg.sells],
                    "buys": [_sym(g) for g in mg.buys],
                }
                for wp, mg in data.by_waypoint.items()
            },
            "by_good": data.by_good,
        }
        print(json.dumps(out, indent=2))
        return

    if by_good:
        print(f"System {system_symbol} — Goods overview")
        for good, where in data.by_good.items():
            sells = ", ".join(where["sells"]) or "—"
            buys = ", ".join(where["buys"]) or "—"
            print(f"- {good}\n    sells @ {sells}\n    buys  @ {buys}")
    else:
        print(f"System {system_symbol} — Markets overview")
        for wp, mg in data.by_waypoint.items():
            sells = ", ".join(_sym(g) for g in mg.sells) or "—"
            buys = ", ".join(_sym(g) for g in mg.buys) or "—"
            print(f"- {wp}\n    sells: {sells}\n    buys : {buys}")
