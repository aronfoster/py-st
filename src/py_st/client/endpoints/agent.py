from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from py_st.models import Agent

from ..client import SpaceTraders


class AgentEndpoint:
    def __init__(self, client: SpaceTraders) -> None:
        self._client = client

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_agent(self) -> Agent:
        data = self._client._make_request("GET", "/my/agent")
        return Agent.model_validate(data)
