from __future__ import annotations

import json
import logging

import typer

from py_st._generated.models import Contract, TradeSymbol
from py_st.cli._errors import handle_errors
from py_st.cli._helpers import (
    format_relative_due,
    format_short_money,
    get_default_system,
    get_waypoint_index,
    resolve_contract_id,
    resolve_ship_id,
)

from ..services import contracts
from .options import (
    CONTRACT_ID_ARG,
    DELIVER_TRADE_SYMBOL_ARG,
    DELIVER_UNITS_ARG,
    SHIP_SYMBOL_ARG,
    TOKEN_OPTION,
    VERBOSE_OPTION,
    _get_token,
)

contracts_app: typer.Typer = typer.Typer(help="Manage contracts.")


def _format_deliverables(
    contract: Contract, system_symbol: str, max_len: int = 60
) -> str:
    """
    Format deliverables for display.

    Args:
        contract: The contract object.
        system_symbol: Current system symbol for waypoint index lookup.
        max_len: Maximum length before truncation.

    Returns:
        Formatted deliverables string.
    """
    if not contract.terms.deliver:
        return "No deliverables"

    parts = []
    for deliv in contract.terms.deliver:
        dest = deliv.destinationSymbol
        wp_idx = get_waypoint_index(dest, system_symbol)
        wp_suffix = f" [{wp_idx}]" if wp_idx else ""

        part = (
            f"{deliv.tradeSymbol} {deliv.unitsFulfilled}/"
            f"{deliv.unitsRequired} → {dest}{wp_suffix}"
        )
        parts.append(part)

    full_str = ", ".join(parts)

    if len(full_str) > max_len:
        visible_parts = []
        current_len = 0
        remaining = 0

        for part in parts:
            if current_len + len(part) + 2 <= max_len - 10:
                visible_parts.append(part)
                current_len += len(part) + 2
            else:
                remaining += 1

        if remaining > 0:
            return f"{', '.join(visible_parts)} … (+{remaining})"

    return full_str


def _print_contract_compact(
    idx: int, contract: Contract, system_symbol: str
) -> None:
    """Print contract in compact single-line format."""
    id6 = contract.id[:6]
    type_abbr = contract.type.value[:4].upper()
    acc = "✓" if contract.accepted else "✗"
    ful = "✓" if contract.fulfilled else "✗"
    due_rel = format_relative_due(contract.terms.deadline)
    deliver = _format_deliverables(contract, system_symbol, max_len=60)

    idx_str = f"c-{idx}"
    print(
        f"{idx_str:<5} {id6:<7} {type_abbr:<5} {acc}/{ful}  "
        f"{due_rel:<16} {deliver}"
    )


def _print_contract_stacked(
    idx: int, contract: Contract, system_symbol: str
) -> None:
    """Print contract in stacked two-line format."""
    id6 = contract.id[:6]
    type_abbr = contract.type.value[:4].upper()
    acc = "✓" if contract.accepted else "✗"
    ful = "✓" if contract.fulfilled else "✗"
    due_rel = format_relative_due(contract.terms.deadline)
    on_acc = format_short_money(contract.terms.payment.onAccepted)
    on_ful = format_short_money(contract.terms.payment.onFulfilled)
    fac = contract.factionSymbol[:2].upper()
    deliver = _format_deliverables(contract, system_symbol, max_len=1000)

    print(
        f"[c-{idx}] {id6} {type_abbr} A:{acc}/F:{ful} | "
        f"due in {due_rel} | Pay: A {on_acc}; F {on_ful} | Fac {fac}"
    )
    print(f"       {deliver}")


@contracts_app.command("list")
@handle_errors
def list_contracts(
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of summary."
    ),
    stacked: bool = typer.Option(
        False, "--stacked", help="Use two-line stacked format."
    ),
) -> None:
    """
    List all of your contracts.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    contracts_list_data = contracts.list_contracts(t)
    contracts_list_data.sort(key=lambda c: c.id)

    if json_output:
        contracts_list = [
            c.model_dump(mode="json") for c in contracts_list_data
        ]
        print(json.dumps(contracts_list, indent=2))
    else:
        system_symbol = get_default_system(t)

        if not stacked and contracts_list_data:
            print("IDX   ID6     T     A/F  DUE(REL)         DELIVER")

        for i, contract in enumerate(contracts_list_data):
            if stacked:
                _print_contract_stacked(i, contract, system_symbol)
            else:
                _print_contract_compact(i, contract, system_symbol)


@contracts_app.command("negotiate")
@handle_errors
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
    resolved_ship_symbol = resolve_ship_id(t, ship_symbol)
    new_contract = contracts.negotiate_contract(t, resolved_ship_symbol)
    print("🎉 New contract negotiated!")
    print(json.dumps(new_contract.model_dump(mode="json"), indent=2))


@contracts_app.command("deliver")
@handle_errors
def deliver_contract_cli(
    contract_id: str = CONTRACT_ID_ARG,
    ship_symbol: str = SHIP_SYMBOL_ARG,
    trade_symbol: TradeSymbol = DELIVER_TRADE_SYMBOL_ARG,
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
    resolved_contract_id = resolve_contract_id(t, contract_id)
    resolved_ship_symbol = resolve_ship_id(t, ship_symbol)
    contract, cargo = contracts.deliver_contract(
        t,
        resolved_contract_id,
        resolved_ship_symbol,
        trade_symbol.value,
        units,
    )
    print("📦 Cargo delivered!")
    output_data = {
        "contract": contract.model_dump(mode="json"),
        "cargo": cargo.model_dump(mode="json"),
    }
    print(json.dumps(output_data, indent=2))


@contracts_app.command("fulfill")
@handle_errors
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
    resolved_contract_id = resolve_contract_id(t, contract_id)
    agent, contract = contracts.fulfill_contract(t, resolved_contract_id)
    print("🎉 Contract fulfilled!")
    output_data = {
        "agent": agent.model_dump(mode="json"),
        "contract": contract.model_dump(mode="json"),
    }
    print(json.dumps(output_data, indent=2))


@contracts_app.command("accept")
@handle_errors
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
    resolved_contract_id = resolve_contract_id(t, contract_id)
    agent, contract = contracts.accept_contract(t, resolved_contract_id)
    print(f"✅ Contract {resolved_contract_id} accepted!")
    output_data = {
        "agent": agent.model_dump(mode="json"),
        "contract": contract.model_dump(mode="json"),
    }
    print(json.dumps(output_data, indent=2))
