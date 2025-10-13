from __future__ import annotations

from py_st.client.transport import HttpTransport
from py_st.models import Agent


class AgentEndpoint:
    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def get_agent(self) -> Agent:
        """GET /my/agent — current authenticated agent."""
        data = self._transport.request_json("GET", "/my/agent")
        return Agent.model_validate(data)
