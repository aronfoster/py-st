from __future__ import annotations

from typing import Any, cast

from tenacity import retry, stop_after_attempt, wait_exponential

from py_st.client.transport import HttpTransport
from py_st.models import Market, Shipyard, Waypoint


class SystemsEndpoint:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

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
        data = self._transport.request_json("GET", url)
        return [Waypoint.model_validate(w) for w in data]

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def list_waypoints_all(
        self, system_symbol: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Fetch ALL waypoints in a system via pagination.
        """
        page = 1
        out: list[dict[str, Any]] = []
        while True:
            url = f"/systems/{system_symbol}/waypoints"
            data = self._transport.request_json("GET", url)
            out.extend(data)
            page = 1
            out: list[dict[str, Any]] = []
            while True:
                r = self._client._client.get(
                    f"/systems/{system_symbol}/waypoints",
                    params={"page": page, "limit": limit},
                )
                r.raise_for_status()
                payload: dict[str, Any] = cast(dict[str, Any], r.json())
                data: list[dict[str, Any]] = cast(
                    list[dict[str, Any]], payload["data"]
                )
                out.extend(data)
                meta: dict[str, Any] = cast(
                    dict[str, Any], payload.get("meta", {})
                )
                total = int(meta.get("total", len(out)))
                page_limit = int(meta.get("limit", limit))
                if page * page_limit >= total:
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
        data = self._transport.request_json("GET", url)
        return Shipyard.model_validate(data)

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_market(self, system_symbol: str, waypoint_symbol: str) -> Market:
        """
        Retrieve market info plus prices if you have a ship present
        """
        url = f"/systems/{system_symbol}/waypoints/{waypoint_symbol}/market"
        data = self._transport.request_json("GET", url)
        return Market.model_validate(data)
