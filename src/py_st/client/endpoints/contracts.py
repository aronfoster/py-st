from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from py_st.models import Agent, Contract, ShipCargo

from ..client import SpaceTraders


class ContractsEndpoint:
    def __init__(self, client: SpaceTraders) -> None:
        self._client = client

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_contracts(self) -> list[Contract]:
        """
        Fetches a paginated list of all your contracts.
        """
        data = self._client._make_request("GET", "/my/contracts")
        return [Contract.model_validate(c) for c in data]

    def negotiate_contract(self, ship_symbol: str) -> Contract:
        """
        Negotiates a new contract using the specified ship.
        """
        url = f"/my/ships/{ship_symbol}/negotiate/contract"
        data = self._client._make_request("POST", url)
        return Contract.model_validate(data["contract"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def accept_contract(self, contract_id: str) -> dict[str, Agent | Contract]:
        """
        Accepts the contract with the given ID.
        """
        url = f"/my/contracts/{contract_id}/accept"
        data = self._client._make_request("POST", url)
        return {
            "agent": Agent.model_validate(data["agent"]),
            "contract": Contract.model_validate(data["contract"]),
        }

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
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
        data = self._client._make_request("POST", url, json=payload)
        return (
            Contract.model_validate(data["contract"]),
            ShipCargo.model_validate(data["cargo"]),
        )

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def fulfill_contract(self, contract_id: str) -> tuple[Agent, Contract]:
        """
        Fulfill a contract.
        """
        url = f"/my/contracts/{contract_id}/fulfill"
        data = self._client._make_request("POST", url)
        return (
            Agent.model_validate(data["agent"]),
            Contract.model_validate(data["contract"]),
        )
