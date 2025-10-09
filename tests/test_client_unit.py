from __future__ import annotations

import httpx

from py_st.client import Agent, SpaceTraders


def test_get_agent_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/my/agent"
        return httpx.Response(200, json={"data": {"symbol": "FOO"}})

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )

    st = SpaceTraders(token="T", client=fake_client)
    agent = st.get_agent()

    assert isinstance(agent, Agent)
    assert agent.symbol == "FOO"
