"""CLI commands for system-related operations."""

from __future__ import annotations

import json
import logging
from typing import Any

import typer

from py_st._generated.models import WaypointTraitSymbol
from py_st.cli._errors import handle_errors
from py_st.cli._helpers import get_default_system, resolve_waypoint_id

from ..services import systems
from .options import (
    SYSTEM_SYMBOL_OPTION,
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
    system_symbol: str | None = SYSTEM_SYMBOL_OPTION,
    traits: list[WaypointTraitSymbol] = TRAITS_OPTION,
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of the default summary."
    ),
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
    if system_symbol is None:
        system_symbol = get_default_system(t)
    trait_values = [t.value for t in traits] if traits else []
    waypoints = systems.list_waypoints(t, system_symbol, trait_values)
    waypoints.sort(key=lambda w: w.symbol.root)

    if json_output:
        waypoints_list = [w.model_dump(mode="json") for w in waypoints]
        print(json.dumps(waypoints_list, indent=2))
    else:
        for i, w in enumerate(waypoints):
            traits_str = ", ".join(t.symbol.value for t in w.traits) or "N/A"
            print(
                f"[{i}] {w.symbol.root:<12} ({w.type.value:<18}) "
                f"Traits: {traits_str}"
            )


@systems_app.command("shipyard")
@handle_errors
def get_shipyard_cli(
    waypoint_symbol: str = WAYPOINT_SYMBOL_ARG,
    system_symbol: str | None = SYSTEM_SYMBOL_OPTION,
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
    if system_symbol is None:
        system_symbol = get_default_system(t)
    resolved_wp_symbol = resolve_waypoint_id(t, system_symbol, waypoint_symbol)
    shipyard = systems.get_shipyard(t, system_symbol, resolved_wp_symbol)
    print(json.dumps(shipyard.model_dump(mode="json"), indent=2))


@systems_app.command("market")
@handle_errors
def get_market_cli(
    waypoint_symbol: str = WAYPOINT_SYMBOL_ARG,
    system_symbol: str | None = SYSTEM_SYMBOL_OPTION,
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
    if system_symbol is None:
        system_symbol = get_default_system(t)
    resolved_wp_symbol = resolve_waypoint_id(t, system_symbol, waypoint_symbol)
    market = systems.get_market(t, system_symbol, resolved_wp_symbol)
    if market is None:
        print(json.dumps({"market": None}, indent=2))
    else:
        print(json.dumps(market.model_dump(mode="json"), indent=2))


@systems_app.command("list-goods")
@handle_errors
def systems_list_goods_cli(
    system_symbol: str | None = SYSTEM_SYMBOL_OPTION,
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
    if system_symbol is None:
        system_symbol = get_default_system(t)
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


@systems_app.command("markets")
@handle_errors
def systems_markets_cli(
    system_symbol: str | None = SYSTEM_SYMBOL_OPTION,
    buys: str | None = typer.Option(
        None, "--buys", help="Filter to waypoints buying this good"
    ),
    sells: str | None = typer.Option(
        None, "--sells", help="Filter to waypoints selling this good"
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit JSON instead of pretty text"
    ),
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    List market goods across all waypoints in a system.

    Supports filtering by goods being bought (--buys) or sold (--sells).
    Trade symbols are matched case-insensitively.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    if system_symbol is None:
        system_symbol = get_default_system(t)

    data = systems.list_system_goods(t, system_symbol)

    def _sym(obj: Any) -> str:
        s = getattr(obj, "symbol", obj)
        return s.value if hasattr(s, "value") else str(s)

    def _normalize_symbol(sym: str) -> str:
        return sym.upper().replace("-", "_")

    filtered_waypoints: dict[str, Any] = {}
    if buys or sells:
        filter_symbol = _normalize_symbol(buys or sells or "")
        for wp, mg in data.by_waypoint.items():
            if buys:
                wp_buys = [_normalize_symbol(_sym(g)) for g in mg.buys]
                if filter_symbol in wp_buys:
                    filtered_waypoints[wp] = mg
            elif sells:
                wp_sells = [_normalize_symbol(_sym(g)) for g in mg.sells]
                if filter_symbol in wp_sells:
                    filtered_waypoints[wp] = mg
    else:
        filtered_waypoints = data.by_waypoint

    if json_out:
        out = {
            wp: {
                "sells": [_sym(g) for g in mg.sells],
                "buys": [_sym(g) for g in mg.buys],
            }
            for wp, mg in filtered_waypoints.items()
        }
        print(json.dumps(out, indent=2))
    else:
        filter_desc = ""
        if buys:
            filter_desc = f" (buying {buys.upper()})"
        elif sells:
            filter_desc = f" (selling {sells.upper()})"
        print(f"System {system_symbol} — Markets{filter_desc}")
        if not filtered_waypoints:
            print("No matching waypoints found.")
        else:
            for i, (wp, mg) in enumerate(sorted(filtered_waypoints.items())):
                sells_str = ", ".join(_sym(g) for g in mg.sells) or "—"
                buys_str = ", ".join(_sym(g) for g in mg.buys) or "—"
                print(f"[{i}] {wp}")
                print(f"    sells: {sells_str}")
                print(f"    buys : {buys_str}")
