from __future__ import annotations

from typing import Any

from py_st._generated.models import Agent
from py_st.client.transport import HttpTransport


class AgentEndpoint:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def get_agent(self) -> Agent:
        """GET /my/agent — current authenticated agent."""
        data = self._transport.request_json("GET", "/my/agent")
        return Agent.model_validate(data)

    def register_agent(
        self, symbol: str | None, faction: str | None
    ) -> dict[str, Any]:
        """
        POST /register — register a new agent.

        Uses account token for authentication (not agent token).
        """
        payload = {}
        if symbol is not None:
            payload["symbol"] = symbol
        if faction is not None:
            payload["faction"] = faction

        data = self._transport.request_json("POST", "/register", json=payload)
        if not isinstance(data, dict):
            raise ValueError("Expected dict response from /register")
        return data
