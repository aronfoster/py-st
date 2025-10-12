from __future__ import annotations

import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from py_st.models import (
    Agent,
    Contract,
    Extraction,
    Market,
    MarketTransaction,
    Ship,
    ShipCargo,
    ShipFuel,
    ShipNav,
    ShipNavFlightMode,
    Shipyard,
    Survey,
    Waypoint,
)


class CooldownException(Exception):
    def __init__(self, cooldown_data: dict) -> None:
        self.cooldown = cooldown_data
        remaining = cooldown_data.get("remainingSeconds", 0)
        super().__init__(
            f"Ship is on cooldown. Try again in {remaining} seconds."
        )


class APIError(Exception):
    """Custom exception for API errors."""

    pass


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

    def _make_request(
        self, method: str, url: str, json: dict | None = None
    ) -> dict | list:
        """
        Makes a request to the API, handling errors and cooldowns.
        """
        try:
            r = self._client.request(method, url, json=json)

            if r.status_code == 409:
                error_data = r.json().get("error", {})
                cooldown = error_data.get("data", {}).get("cooldown", {})
                wait_time = cooldown.get("remainingSeconds", 0)

                print(f"Ship on cooldown. Waiting for {wait_time} seconds...")
                time.sleep(wait_time + 1)

                r = self._client.request(method, url, json=json)

            r.raise_for_status()
            return r.json()["data"]

        except httpx.HTTPStatusError as e:
            error_details = e.response.json().get("error", {})
            message = error_details.get("message", e.response.text)
            raise APIError(f"API Error: {message}") from e
        except httpx.RequestError as e:
            raise APIError(f"Request failed: {e}") from e

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
    def list_waypoints_all(
        self, system_symbol: str, limit: int = 20
    ) -> list[dict]:
        """
        Fetch ALL waypoints in a system via pagination.
        Returns the raw waypoint dicts (useful for traits filtering).
        """
        page = 1
        out: list[dict] = []
        while True:
            r = self._client.get(
                f"/systems/{system_symbol}/waypoints",
                params={"page": page, "limit": limit},
            )
            r.raise_for_status()
            payload = r.json()
            out.extend(payload["data"])
            meta = payload.get("meta", {})
            total = meta.get("total", len(out))
            if page * meta.get("limit", limit) >= total:
                break
            page += 1
        return out

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

    def extract_resources(
        self, ship_symbol: str, survey: Survey | None = None
    ) -> Extraction:
        """
        Extract resources from a waypoint.
        """
        if survey:
            url = f"/my/ships/{ship_symbol}/extract/survey"
            payload = survey.model_dump(mode="json")
            data = self._make_request("POST", url, json=payload)
        else:
            url = f"/my/ships/{ship_symbol}/extract"
            data = self._make_request("POST", url)

        return Extraction.model_validate(data["extraction"])

    def refine_materials(
        self, ship_symbol: str, produce: str
    ) -> dict[str, any]:
        """
        Refine raw materials on a ship.
        """
        url = f"/my/ships/{ship_symbol}/refine"
        payload = {"produce": produce}
        data = self._make_request("POST", url, json=payload)
        return data

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def create_survey(self, ship_symbol: str) -> list[Survey]:
        """
        Create a survey of the waypoint at the ship's current location.
        """
        url = f"/my/ships/{ship_symbol}/survey"
        r = self._client.post(url)
        r.raise_for_status()
        surveys_data = r.json()["data"]["surveys"]
        return [Survey.model_validate(s) for s in surveys_data]

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
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()["data"]
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
        r = self._client.post(url)
        r.raise_for_status()
        data = r.json()["data"]
        return (
            Agent.model_validate(data["agent"]),
            Contract.model_validate(data["contract"]),
        )

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def refuel_ship(
        self, ship_symbol: str, units: int | None = None
    ) -> tuple[Agent, ShipFuel, MarketTransaction]:
        """
        Refuel a ship.
        """
        url = f"/my/ships/{ship_symbol}/refuel"
        payload = {}
        if units:
            payload["units"] = units
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()["data"]
        return (
            Agent.model_validate(data["agent"]),
            ShipFuel.model_validate(data["fuel"]),
            MarketTransaction.model_validate(data["transaction"]),
        )

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def set_flight_mode(
        self, ship_symbol: str, flight_mode: ShipNavFlightMode
    ) -> ShipNav:
        """
        Set the flight mode of a ship.
        """
        url = f"/my/ships/{ship_symbol}/nav"
        payload = {"flightMode": flight_mode.value}
        r = self._client.patch(url, json=payload)
        r.raise_for_status()
        return ShipNav.model_validate(r.json()["data"]["nav"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def jettison_cargo(
        self, ship_symbol: str, trade_symbol: str, units: int
    ) -> ShipCargo:
        """
        Jettison cargo from a ship.
        """
        url = f"/my/ships/{ship_symbol}/jettison"
        payload = {"symbol": trade_symbol, "units": units}
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()["data"]
        return ShipCargo.model_validate(data["cargo"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_market(self, system_symbol: str, waypoint_symbol: str) -> Market:
        """
        Retrieve market info (imports/exports/exchange, plus prices if you have
        a ship present
        """
        url = f"/systems/{system_symbol}/waypoints/{waypoint_symbol}/market"
        r = self._client.get(url)
        r.raise_for_status()
        return Market.model_validate(r.json()["data"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def sell_cargo(
        self, ship_symbol: str, trade_symbol: str, units: int
    ) -> tuple[Agent, ShipCargo, MarketTransaction]:
        """
        Sell cargo from a ship at a marketplace.
        """
        url = f"/my/ships/{ship_symbol}/sell"
        payload = {"symbol": trade_symbol, "units": units}
        r = self._client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()["data"]
        return (
            Agent.model_validate(data["agent"]),
            ShipCargo.model_validate(data["cargo"]),
            MarketTransaction.model_validate(data["transaction"]),
        )
