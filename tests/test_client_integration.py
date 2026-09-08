from __future__ import annotations

import os

import pytest

from py_st.client import SpaceTradersClient


@pytest.mark.skipif(
    os.getenv("ST_LIVE_TESTS") != "1" or not os.getenv("ST_TOKEN"),
    reason="requires explicit ST_LIVE_TESTS=1 and ST_TOKEN",
)
def test_get_agent_live() -> None:
    token = os.environ["ST_TOKEN"]
    with SpaceTradersClient(token=token) as client:
        agent = client.agent.get_agent()
    assert agent.symbol  # has some non-empty value
