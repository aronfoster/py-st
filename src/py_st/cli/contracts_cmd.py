from __future__ import annotations

import json
import logging

import typer

from py_st.cli._errors import handle_errors
from py_st.cli._helpers import resolve_contract_id

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


@contracts_app.command("list")
@handle_errors
def list_contracts(
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of summary."
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
        for i, contract in enumerate(contracts_list_data):
            type_str = contract.type.value
            accepted_str = "Yes" if contract.accepted else "No"
            fulfilled_str = "Yes" if contract.fulfilled else "No"
            deadline_str = (
                contract.deadlineToAccept.isoformat()
                if contract.deadlineToAccept
                else contract.expiration.isoformat()
            )
            print(
                f"[c-{i}] {contract.id:<25} "
                f"type:{type_str:<12} "
                f"accepted:{accepted_str:<3} "
                f"fulfilled:{fulfilled_str:<3} "
                f"deadline:{deadline_str}"
            )


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
    new_contract = contracts.negotiate_contract(t, ship_symbol)
    print("🎉 New contract negotiated!")
    print(json.dumps(new_contract.model_dump(mode="json"), indent=2))


@contracts_app.command("deliver")
@handle_errors
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
    resolved_contract_id = resolve_contract_id(t, contract_id)
    contract, cargo = contracts.deliver_contract(
        t, resolved_contract_id, ship_symbol, trade_symbol, units
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
