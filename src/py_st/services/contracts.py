"""Services for contract-related operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast

from pydantic import ValidationError

from py_st import cache
from py_st._generated.models import Agent, Contract, ShipCargo
from py_st.client import SpaceTradersClient
from py_st.services.cache_keys import key_for_contract_list


def _mark_contract_list_dirty() -> None:
    """
    Marks the contract list cache as dirty without updating timestamps.

    If the cache entry doesn't exist, does nothing (missing cache
    is already treated as dirty by list_contracts).
    """
    full_cache = cache.load_cache()

    cached_entry = full_cache.get(key_for_contract_list())
    if cached_entry is not None and isinstance(cached_entry, dict):
        cached_entry["is_dirty"] = True
        cache.save_cache(full_cache)


def list_contracts(token: str) -> list[Contract]:
    """
    Fetches all contracts from the API with caching.

    Checks the cache first and returns cached data if the
    "is_dirty" flag is False. Otherwise, fetches from the API
    and updates the cache.
    """
    full_cache = cache.load_cache()

    cached_entry = full_cache.get(key_for_contract_list())
    if cached_entry is not None and isinstance(cached_entry, dict):
        try:
            is_dirty = cached_entry.get("is_dirty", True)

            if not is_dirty:
                contracts_data = cached_entry["data"]
                contracts = [
                    Contract.model_validate(c) for c in contracts_data
                ]
                return contracts

        except (ValueError, ValidationError, KeyError) as e:
            logging.warning("Invalid cache entry for contract list: %s", e)

    client = SpaceTradersClient(token=token)
    contracts = client.contracts.get_contracts()

    now_utc = datetime.now(UTC)
    now_iso = now_utc.isoformat()
    new_entry = {
        "last_updated": now_iso,
        "is_dirty": False,
        "data": [contract.model_dump(mode="json") for contract in contracts],
    }
    full_cache[key_for_contract_list()] = new_entry
    cache.save_cache(full_cache)

    return contracts


def negotiate_contract(token: str, ship_symbol: str) -> Contract:
    """
    Negotiates a new contract using the specified ship.
    """
    client = SpaceTradersClient(token=token)
    new_contract = client.contracts.negotiate_contract(ship_symbol)
    _mark_contract_list_dirty()
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
    _mark_contract_list_dirty()
    return contract, cargo


def fulfill_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Fulfills a contract.
    """
    client = SpaceTradersClient(token=token)
    agent, contract = client.contracts.fulfill_contract(contract_id)
    _mark_contract_list_dirty()
    return agent, contract


def accept_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Accepts a contract.
    """
    client = SpaceTradersClient(token=token)
    result = client.contracts.accept_contract(contract_id)
    agent: Agent = cast(Agent, result["agent"])
    contract: Contract = cast(Contract, result["contract"])
    _mark_contract_list_dirty()
    return agent, contract
