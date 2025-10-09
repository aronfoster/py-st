from __future__ import annotations

import httpx

from py_st.client import SpaceTraders
from py_st.models import Agent


def test_get_agent_parses_response() -> None:
    # Minimal valid Agent payload per schema (accountId is optional)
    agent_json = {
        "symbol": "FOO",
        "headquarters": "X1-ABC-1",
        "credits": 42,
        "startingFaction": "COSMIC",
        "shipCount": 1,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        # client base_url is ".../v2", and method calls "/my/agent"
        assert request.url.path == "/v2/my/agent"
        return httpx.Response(200, json={"data": agent_json})

    transport = httpx.MockTransport(handler)
    fake_client = httpx.Client(
        transport=transport, base_url="https://api.spacetraders.io/v2"
    )

    st = SpaceTraders(token="T", client=fake_client)
    agent = st.get_agent()

    # Type & field assertions
    assert isinstance(agent, Agent)
    assert agent.symbol == "FOO"
    assert agent.headquarters == "X1-ABC-1"
    assert agent.credits == 42
    assert agent.startingFaction == "COSMIC"
    assert agent.shipCount == 1
