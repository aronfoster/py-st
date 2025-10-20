from __future__ import annotations

from py_st.client.transport import HttpTransport
from py_st.models import Market, Shipyard, Waypoint


class SystemsEndpoint:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def get_waypoints_in_system(
        self, system_symbol: str, traits: list[str] | None = None
    ) -> list[Waypoint]:
        """
        Fetches waypoints in a system, optionally filtering by traits.
        """
        params = {}
        if traits:
            params["traits"] = ",".join(traits)
        url = f"/systems/{system_symbol}/waypoints"
        data = self._transport.request_json("GET", url, params=params)
        return [Waypoint.model_validate(w) for w in data]

    def list_waypoints_all(
        self, system_symbol: str, traits: list[str] | None = None
    ) -> list[Waypoint]:
        """
        Fetch ALL waypoints in a system via pagination.
        """
        rows = self._transport.request_json(
            "GET",
            f"/systems/{system_symbol}/waypoints",
            paginate=True,
        )
        return [Waypoint.model_validate(x) for x in rows]

    def get_shipyard(
        self, system_symbol: str, waypoint_symbol: str
    ) -> Shipyard:
        """
        Get the shipyard for a waypoint.
        """
        url = f"/systems/{system_symbol}/waypoints/{waypoint_symbol}/shipyard"
        data = self._transport.request_json("GET", url)
        return Shipyard.model_validate(data)

    def get_market(self, system_symbol: str, waypoint_symbol: str) -> Market:
        """
        Retrieve market info plus prices if you have a ship present
        """
        url = f"/systems/{system_symbol}/waypoints/{waypoint_symbol}/market"
        data = self._transport.request_json("GET", url)
        return Market.model_validate(data)
