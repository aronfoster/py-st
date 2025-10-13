from __future__ import annotations

import httpx

from .endpoints.agent import AgentEndpoint
from .endpoints.contracts import ContractsEndpoint
from .endpoints.ships import ShipsEndpoint
from .endpoints.systems import SystemsEndpoint
from .transport import HttpTransport


class SpaceTradersClient:
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
        self._agent = AgentEndpoint(self._transport)
        self._contracts = ContractsEndpoint(self._transport)
        self._ships = ShipsEndpoint(self._transport)
        self._systems = SystemsEndpoint(self._transport)

    @property
    def agent(self) -> AgentEndpoint:
        return self._agent

    @property
    def contracts(self) -> ContractsEndpoint:
        return self._contracts

    @property
    def ships(self) -> ShipsEndpoint:
        return self._ships

    @property
    def systems(self) -> SystemsEndpoint:
        return self._systems
