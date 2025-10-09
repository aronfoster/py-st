from __future__ import annotations

import httpx

from py_st.client import Agent, SpaceTraders


def test_get_agent_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/my/agent"
        data = {"data": {"symbol": "FOO"}}
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    client = SpaceTraders(token="T")
    client._client = httpx.Client(
        transport=transport,
        base_url="https://api.spacetraders.io",  # type: ignore[attr-defined]
    )
    agent = client.get_agent()
    assert isinstance(agent, Agent)
    assert agent.symbol == "FOO"
