from __future__ import annotations

from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from py_st.models import (
    Agent,
    Extraction,
    MarketTransaction,
    Ship,
    ShipCargo,
    ShipFuel,
    ShipNav,
    ShipNavFlightMode,
    Survey,
)

from ..client import SpaceTradersClient


class ShipsEndpoint:
    def __init__(self, client: SpaceTradersClient) -> None:
        self._client = client

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_ships(self) -> list[Ship]:
        """
        Fetches a paginated list of all your ships.
        """
        data = self._client._make_request("GET", "/my/ships")
        return [Ship.model_validate(s) for s in data]

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def navigate_ship(self, ship_symbol: str, waypoint_symbol: str) -> ShipNav:
        """
        Navigate a ship to a waypoint.
        """
        url = f"/my/ships/{ship_symbol}/navigate"
        payload = {"waypointSymbol": waypoint_symbol}
        data = self._client._make_request("POST", url, json=payload)
        return ShipNav.model_validate(data["nav"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def orbit_ship(self, ship_symbol: str) -> ShipNav:
        """
        Move a ship into orbit.
        """
        url = f"/my/ships/{ship_symbol}/orbit"
        data = self._client._make_request("POST", url)
        return ShipNav.model_validate(data["nav"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def dock_ship(self, ship_symbol: str) -> ShipNav:
        """
        Dock a ship.
        """
        url = f"/my/ships/{ship_symbol}/dock"
        data = self._client._make_request("POST", url)
        return ShipNav.model_validate(data["nav"])

    def extract_resources(
        self, ship_symbol: str, survey: Survey | None = None
    ) -> Extraction:
        """
        Extract resources from a waypoint.
        """
        if survey:
            url = f"/my/ships/{ship_symbol}/extract/survey"
            payload = survey.model_dump(mode="json")
            data = self._client._make_request("POST", url, json=payload)
        else:
            url = f"/my/ships/{ship_symbol}/extract"
            data = self._client._make_request("POST", url)
        return Extraction.model_validate(data["extraction"])

    def refine_materials(
        self, ship_symbol: str, produce: str
    ) -> dict[str, Any]:
        """
        Refine raw materials on a ship.
        """
        url = f"/my/ships/{ship_symbol}/refine"
        payload = {"produce": produce}
        data = self._client._make_request("POST", url, json=payload)
        return data

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def create_survey(self, ship_symbol: str) -> list[Survey]:
        """
        Create a survey of the waypoint at the ship's current location.
        """
        url = f"/my/ships/{ship_symbol}/survey"
        data = self._client._make_request("POST", url)
        return [Survey.model_validate(s) for s in data["surveys"]]

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
        data = self._client._make_request("POST", url, json=payload)
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
        data = self._client._make_request("PATCH", url, json=payload)
        return ShipNav.model_validate(data["nav"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def jettison_cargo(
        self, ship_symbol: str, trade_symbol: str, units: int
    ) -> ShipCargo:
        """
        Jettison cargo from a ship.
        """
        url = f"/my/ships/{ship_symbol}/jettison"
        payload = {"symbol": trade_symbol, "units": units}
        data = self._client._make_request("POST", url, json=payload)
        return ShipCargo.model_validate(data["cargo"])

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def sell_cargo(
        self, ship_symbol: str, trade_symbol: str, units: int
    ) -> tuple[Agent, ShipCargo, MarketTransaction]:
        """
        Sell cargo from a ship at a marketplace.
        """
        url = f"/my/ships/{ship_symbol}/sell"
        payload = {"symbol": trade_symbol, "units": units}
        data = self._client._make_request("POST", url, json=payload)
        return (
            Agent.model_validate(data["agent"]),
            ShipCargo.model_validate(data["cargo"]),
            MarketTransaction.model_validate(data["transaction"]),
        )
