from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from .transport import HttpTransport

if TYPE_CHECKING:
    from .endpoints.agent import AgentEndpoint
    from .endpoints.contracts import ContractsEndpoint
    from .endpoints.ships import ShipsEndpoint
    from .endpoints.systems import SystemsEndpoint


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
        self._transport = HttpTransport(self._client)

    def _make_request(
        self, method: str, url: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """
        Makes a request to the API, handling errors and cooldowns.
        """
        return self._transport.request_json(method, url, json=json)

    @property
    def agent(self) -> AgentEndpoint:
        from .endpoints.agent import AgentEndpoint

        if not hasattr(self, "_agent"):
            self._agent = AgentEndpoint(self)
        return self._agent

    @property
    def contracts(self) -> ContractsEndpoint:
        from .endpoints.contracts import ContractsEndpoint

        if not hasattr(self, "_contracts"):
            self._contracts = ContractsEndpoint(self)
        return self._contracts

    @property
    def ships(self) -> ShipsEndpoint:
        from .endpoints.ships import ShipsEndpoint

        if not hasattr(self, "_ships"):
            self._ships = ShipsEndpoint(self)
        return self._ships

    @property
    def systems(self) -> SystemsEndpoint:
        from .endpoints.systems import SystemsEndpoint

        if not hasattr(self, "_systems"):
            self._systems = SystemsEndpoint(self)
        return self._systems
