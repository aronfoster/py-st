from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field
from py_st.client.transport import HttpTransport, JSONDict
from py_st.models import (
    Agent,
    Cooldown,
    Extraction,
    MarketTransaction,
    Ship,
    ShipCargo,
    ShipFuel,
    ShipNav,
    ShipNavFlightMode,
    ShipyardTransaction,
    Survey,
)


class RefineItem(BaseModel):
    """A good that was produced or consumed in a refining process."""

    tradeSymbol: str = Field(..., description="Symbol of the good.")
    units: int = Field(..., description="Amount of units of the good.")


class RefineResult(BaseModel):
    """The result of a successful refining process."""

    cargo: ShipCargo
    cooldown: Cooldown
    produced: list[RefineItem]
    consumed: list[RefineItem]


class ShipsEndpoint:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def get_ships(self) -> list[Ship]:
        """
        Fetches a paginated list of all your ships.
        """
        data = self._transport.request_json("GET", "/my/ships")
        return [Ship.model_validate(s) for s in data]

    def navigate_ship(self, ship_symbol: str, waypoint_symbol: str) -> ShipNav:
        """
        Navigate a ship to a waypoint.
        """
        url = f"/my/ships/{ship_symbol}/navigate"
        payload = {"waypointSymbol": waypoint_symbol}
        data = cast(JSONDict, self._transport.request_json("POST", url, json=payload))
        return ShipNav.model_validate(data["nav"])

    def orbit_ship(self, ship_symbol: str) -> ShipNav:
        """
        Move a ship into orbit.
        """
        url = f"/my/ships/{ship_symbol}/orbit"
        data = cast(JSONDict, self._transport.request_json("POST", url))
        return ShipNav.model_validate(data["nav"])

    def dock_ship(self, ship_symbol: str) -> ShipNav:
        """
        Dock a ship.
        """
        url = f"/my/ships/{ship_symbol}/dock"
        data = cast(JSONDict, self._transport.request_json("POST", url))
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
            data = cast(JSONDict, self._transport.request_json("POST", url, json=payload))
        else:
            url = f"/my/ships/{ship_symbol}/extract"
            data = cast(JSONDict, self._transport.request_json("POST", url))
        return Extraction.model_validate(data["extraction"])

    def refine_materials(
        self, ship_symbol: str, produce: str
    ) -> RefineResult:
        """
        Refine raw materials on a ship.
        """
        url = f"/my/ships/{ship_symbol}/refine"
        payload = {"produce": produce}
        data = cast(JSONDict, self._transport.request_json("POST", url, json=payload))
        return RefineResult.model_validate(data)

    def create_survey(self, ship_symbol: str) -> list[Survey]:
        """
        Create a survey of the waypoint at the ship's current location.
        """
        url = f"/my/ships/{ship_symbol}/survey"
        data = cast(JSONDict, self._transport.request_json("POST", url))
        return [Survey.model_validate(s) for s in data["surveys"]]

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
        data = cast(JSONDict, self._transport.request_json("POST", url, json=payload))
        return (
            Agent.model_validate(data["agent"]),
            ShipFuel.model_validate(data["fuel"]),
            MarketTransaction.model_validate(data["transaction"]),
        )

    def set_flight_mode(
        self, ship_symbol: str, flight_mode: ShipNavFlightMode
    ) -> ShipNav:
        """
        Set the flight mode of a ship.
        """
        url = f"/my/ships/{ship_symbol}/nav"
        payload = {"flightMode": flight_mode.value}
        data = cast(JSONDict, self._transport.request_json("PATCH", url, json=payload))
        return ShipNav.model_validate(data["nav"])

    def jettison_cargo(
        self, ship_symbol: str, trade_symbol: str, units: int
    ) -> ShipCargo:
        """
        Jettison cargo from a ship.
        """
        url = f"/my/ships/{ship_symbol}/jettison"
        payload = {"symbol": trade_symbol, "units": units}
        data = cast(JSONDict, self._transport.request_json("POST", url, json=payload))
        return ShipCargo.model_validate(data["cargo"])

    def sell_cargo(
        self, ship_symbol: str, trade_symbol: str, units: int
    ) -> tuple[Agent, ShipCargo, MarketTransaction]:
        """
        Sell cargo from a ship at a marketplace.
        """
        url = f"/my/ships/{ship_symbol}/sell"
        payload = {"symbol": trade_symbol, "units": units}
        data = cast(JSONDict, self._transport.request_json("POST", url, json=payload))
        return (
            Agent.model_validate(data["agent"]),
            ShipCargo.model_validate(data["cargo"]),
            MarketTransaction.model_validate(data["transaction"]),
        )

    def purchase_ship(
        self, ship_type: str, waypoint_symbol: str
    ) -> tuple[Agent, Ship, ShipyardTransaction]:
        """
        Purchase a ship of the specified type at a waypoint.
        """
        url = "/my/ships"
        payload = {"shipType": ship_type, "waypointSymbol": waypoint_symbol}
        data = cast(JSONDict, self._transport.request_json("POST", url, json=payload))
        return (
            Agent.model_validate(data["agent"]),
            Ship.model_validate(data["ship"]),
            ShipyardTransaction.model_validate(data["transaction"]),
        )
