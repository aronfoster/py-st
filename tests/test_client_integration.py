from __future__ import annotations

import os

import pytest

from py_st.client import SpaceTraders


@pytest.mark.skipif(not os.getenv("ST_TOKEN"), reason="requires ST_TOKEN")
def test_get_agent_live() -> None:
    token = os.environ["ST_TOKEN"]
    client = SpaceTraders(token=token)
    agent = client.agent.get_agent()
    assert agent.symbol  # has some non-empty value
