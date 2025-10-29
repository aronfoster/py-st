"""Services for contract-related operations."""

from __future__ import annotations

from typing import cast

from py_st._generated.models import Agent, Contract, ShipCargo
from py_st.client import SpaceTradersClient


def list_contracts(token: str) -> list[Contract]:
    """
    Fetches all contracts from the API.
    """
    client = SpaceTradersClient(token=token)
    contracts = client.contracts.get_contracts()
    return contracts


def negotiate_contract(token: str, ship_symbol: str) -> Contract:
    """
    Negotiates a new contract using the specified ship.
    """
    client = SpaceTradersClient(token=token)
    new_contract = client.contracts.negotiate_contract(ship_symbol)
    return new_contract


def deliver_contract(
    token: str,
    contract_id: str,
    ship_symbol: str,
    trade_symbol: str,
    units: int,
) -> tuple[Contract, ShipCargo]:
    """
    Delivers cargo to fulfill part of a contract.
    """
    client = SpaceTradersClient(token=token)
    contract, cargo = client.contracts.deliver_contract(
        contract_id, ship_symbol, trade_symbol, units
    )
    return contract, cargo


def fulfill_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Fulfills a contract.
    """
    client = SpaceTradersClient(token=token)
    agent, contract = client.contracts.fulfill_contract(contract_id)
    return agent, contract


def accept_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Accepts a contract.
    """
    client = SpaceTradersClient(token=token)
    result = client.contracts.accept_contract(contract_id)
    agent: Agent = cast(Agent, result["agent"])
    contract: Contract = cast(Contract, result["contract"])
    return agent, contract
