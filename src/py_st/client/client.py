from __future__ import annotations

import atexit
from collections.abc import Callable
from types import TracebackType

import httpx

from .endpoints.agent import AgentEndpoint
from .endpoints.contracts import ContractsEndpoint
from .endpoints.ships import ShipsEndpoint
from .endpoints.systems import SystemsEndpoint
from .transport import JSON, APIError, HttpTransport, JSONDict


def worker_required(method: str, path: str) -> None:
    if method not in ("GET", "HEAD") and path != "/register":
        raise APIError(
            "Direct live mutations are retired. Use the flight worker and "
            "authenticated browser; registration remains owner-controlled."
        )


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
        if client is None:
            self._transport.dispatch_guard = worker_required
        self._agent = AgentEndpoint(self._transport)
        self._contracts = ContractsEndpoint(self._transport)
        self._ships = ShipsEndpoint(self._transport)
        self._systems = SystemsEndpoint(self._transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SpaceTradersClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def set_wait(self, wait: Callable[[float], None]) -> None:
        """Install an interruptible wait for bounded automation sessions."""
        self._transport._wait = wait

    def request(
        self,
        method: str,
        path: str,
        *,
        body: JSONDict | None = None,
        paginate: bool = False,
    ) -> JSON:
        """Raw endpoint access through the same pacing and error policy."""
        return self._transport.request_json(
            method, path, json=body, paginate=paginate
        )

    def status(self) -> JSONDict:
        return self._transport._send_with_retries("GET", "/")

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


_shared: tuple[str, SpaceTradersClient] | None = None


def close_shared_client() -> None:
    global _shared
    if _shared is not None:
        _shared[1].close()
        _shared = None


def get_client(token: str) -> SpaceTradersClient:
    """Reuse one session per CLI process; rotation closes the old session."""
    global _shared
    if _shared is None or _shared[0] != token:
        close_shared_client()
        _shared = (token, SpaceTradersClient(token))
    return _shared[1]


atexit.register(close_shared_client)
