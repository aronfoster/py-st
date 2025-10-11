from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from py_st.models import (
    Agent,
    Contract,
    Extraction,
    Ship,
    ShipNav,
    Shipyard,
    Waypoint,
)


class SpaceTraders:
    def __init__(self, token: str, client: httpx.Client | None = None) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self._client = client or httpx.Client(
            base_url="https://api.spacetraders.io/v2",
            headers=headers,
            timeout=30,
        )

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_agent(self) -> Agent:
        r = self._client.get("/my/agent")
        r.raise_for_status()
        return Agent.model_validate(r.json()["data"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_contracts(self) -> list[Contract]:
        """
        Fetches a paginated list of all your contracts.
        """
        r = self._client.get("/my/contracts")
        r.raise_for_status()
        response_json = r.json()
        contracts_data = response_json["data"]
        return [Contract.model_validate(c) for c in contracts_data]

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_ships(self) -> list[Ship]:
        """
        Fetches a paginated list of all your ships.
        """
        r = self._client.get("/my/ships")
        r.raise_for_status()
        response_json = r.json()
        ships_data = response_json["data"]
        return [Ship.model_validate(s) for s in ships_data]

    def negotiate_contract(self, ship_symbol: str) -> Contract:
        """
        Negotiates a new contract using the specified ship.
        """
        url = f"/my/ships/{ship_symbol}/negotiate/contract"
        r = self._client.post(url)
        r.raise_for_status()
        response_json = r.json()
        return Contract.model_validate(response_json["data"]["contract"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def accept_contract(self, contract_id: str) -> dict[str, Agent | Contract]:
        """
        Accepts the contract with the given ID.
        """
        url = f"/my/contracts/{contract_id}/accept"
        r = self._client.post(url)
        r.raise_for_status()
        response_json = r.json()
        data = response_json["data"]

        return {
            "agent": Agent.model_validate(data["agent"]),
            "contract": Contract.model_validate(data["contract"]),
        }

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_waypoints_in_system(
        self, system_symbol: str, traits: list[str] | None = None
    ) -> list[Waypoint]:
        """
        Fetches waypoints in a system, optionally filtering by traits.
        """
        params = {}
        if traits:
            params["traits"] = traits

        url = f"/systems/{system_symbol}/waypoints"
        r = self._client.get(url, params=params)
        r.raise_for_status()
        response_json = r.json()
        return [Waypoint.model_validate(w) for w in response_json["data"]]

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_shipyard(
        self, system_symbol: str, waypoint_symbol: str
    ) -> Shipyard:
        """
        Get the shipyard for a waypoint.
        """
        url = f"/systems/{system_symbol}/waypoints/{waypoint_symbol}/shipyard"
        r = self._client.get(url)
        r.raise_for_status()
        return Shipyard.model_validate(r.json()["data"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def navigate_ship(self, ship_symbol: str, waypoint_symbol: str) -> ShipNav:
        """
        Navigate a ship to a waypoint.
        """
        url = f"/my/ships/{ship_symbol}/navigate"
        payload = {"waypointSymbol": waypoint_symbol}
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        return ShipNav.model_validate(r.json()["data"]["nav"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def orbit_ship(self, ship_symbol: str) -> ShipNav:
        """
        Move a ship into orbit.
        """
        url = f"/my/ships/{ship_symbol}/orbit"
        r = self._client.post(url)
        r.raise_for_status()
        return ShipNav.model_validate(r.json()["data"]["nav"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def dock_ship(self, ship_symbol: str) -> ShipNav:
        """
        Dock a ship.
        """
        url = f"/my/ships/{ship_symbol}/dock"
        r = self._client.post(url)
        r.raise_for_status()
        return ShipNav.model_validate(r.json()["data"]["nav"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def extract_resources(self, ship_symbol: str) -> Extraction:
        """
        Extract resources from a waypoint.
        """
        url = f"/my/ships/{ship_symbol}/extract"
        r = self._client.post(url)
        r.raise_for_status()
        return Extraction.model_validate(r.json()["data"]["extraction"])
