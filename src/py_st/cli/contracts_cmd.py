from __future__ import annotations

import json
import logging

import typer

from .. import services
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
