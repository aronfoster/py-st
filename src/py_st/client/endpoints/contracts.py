from __future__ import annotations

from typing import cast

from py_st.client.transport import HttpTransport, JSONDict
from py_st.models import Agent, Contract, ShipCargo


class ContractsEndpoint:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def get_contracts(self) -> list[Contract]:
        """
        Fetches a paginated list of all your contracts.
        """
        data = self._transport.request_json("GET", "/my/contracts")
        return [Contract.model_validate(c) for c in data]

    def negotiate_contract(self, ship_symbol: str) -> Contract:
        """
        Negotiates a new contract using the specified ship.
        """
        url = f"/my/ships/{ship_symbol}/negotiate/contract"
        data = cast(JSONDict, self._transport.request_json("POST", url))
        return Contract.model_validate(data["contract"])

    def accept_contract(self, contract_id: str) -> dict[str, Agent | Contract]:
        """
        Accepts the contract with the given ID.
        """
        url = f"/my/contracts/{contract_id}/accept"
        data = cast(JSONDict, self._transport.request_json("POST", url))
        return {
            "agent": Agent.model_validate(data["agent"]),
            "contract": Contract.model_validate(data["contract"]),
        }

    def deliver_contract(
        self,
        contract_id: str,
        ship_symbol: str,
        trade_symbol: str,
        units: int,
    ) -> tuple[Contract, ShipCargo]:
        """
        Deliver cargo to a contract.
        """
        url = f"/my/contracts/{contract_id}/deliver"
        payload = {
            "shipSymbol": ship_symbol,
            "tradeSymbol": trade_symbol,
            "units": units,
        }
        data = cast(
            JSONDict, self._transport.request_json("POST", url, json=payload)
        )
        return (
            Contract.model_validate(data["contract"]),
            ShipCargo.model_validate(data["cargo"]),
        )

    def fulfill_contract(self, contract_id: str) -> tuple[Agent, Contract]:
        """
        Fulfill a contract.
        """
        url = f"/my/contracts/{contract_id}/fulfill"
        data = cast(JSONDict, self._transport.request_json("POST", url))
        return (
            Agent.model_validate(data["agent"]),
            Contract.model_validate(data["contract"]),
        )
