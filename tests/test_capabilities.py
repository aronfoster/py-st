"""Offline transport proof for the publishable capability snapshot."""

import json
import time
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli import capabilities_cmd
from py_st.cli.app import app
from py_st.client.client import SpaceTradersClient
from py_st.client.transport import APIError
from py_st.services.capabilities import capability_snapshot


def peer(
    *, failure: int | None = None, code: int | None = None
) -> tuple[SpaceTradersClient, list[str]]:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        path = request.url.path.removeprefix("/v2")
        calls.append(path)
        if path == "/":
            return httpx.Response(200, json={"resetDate": "2026-09-06"})
        if path == "/my/agent" and failure:
            return httpx.Response(
                failure,
                json={"error": {"code": code, "message": "SECRET /private"}},
            )
        data: Any
        if path == "/my/agent":
            data = {
                "symbol": "TEST",
                "headquarters": "X1-TEST-A",
                "accountId": "SECRET",
                "token": "SECRET",
            }
        elif path == "/my/ships":
            data = [
                {
                    "symbol": "TEST-1",
                    "frame": {
                        "symbol": "FRAME_PROBE",
                        "description": "SECRET",
                    },
                    "fuel": {"capacity": 0, "current": 0},
                }
            ]
        elif path == "/my/contracts":
            data = []
        elif path.endswith("/waypoints"):
            page = request.url.params.get("page", "1")
            data = [
                {
                    "symbol": f"X1-TEST-{'A' if page == '1' else 'B'}",
                    "type": "ASTEROID",
                    "traits": [
                        {"symbol": "MARKETPLACE"},
                        {"symbol": "SHIPYARD"},
                    ],
                }
            ]
            return httpx.Response(
                200,
                json={
                    "data": data,
                    "meta": {"total": 2, "limit": 1, "page": int(page)},
                },
            )
        elif path.endswith("/market"):
            data = {
                "symbol": path.split("/")[-2],
                "imports": [{"symbol": "IRON", "description": "SECRET"}],
                "tradeGoods": (
                    [{"symbol": "IRON", "purchasePrice": 12}]
                    if "TEST-A/" in path
                    else None
                ),
                "transactions": [{"agentSymbol": "SECRET"}],
            }
        else:
            return httpx.Response(403, json={"error": {"message": "SECRET"}})
        return httpx.Response(200, json={"data": data})

    client = SpaceTradersClient(
        "SECRET",
        httpx.Client(
            base_url="https://offline.invalid/v2/",
            transport=httpx.MockTransport(handle),
        ),
    )
    client.set_wait(lambda seconds: None)
    return client, calls


def test_snapshot_fresh_pagination_unknowns_and_projection() -> None:
    # Arrange: two paginated sites, one location-gated price, denied shipyards.
    client, calls = peer()
    # Act.
    with client:
        report = capability_snapshot(client)
    # Assert: real transport pagination, GET-only peer, no private fields.
    opportunities = report["opportunity_observations"]
    assert len(opportunities["waypoints"]["data"]) == 2
    assert calls.count("/systems/X1-TEST/waypoints") == 2
    markets = opportunities["markets"]
    assert markets[0]["details_state"] == "observed"
    assert markets[0]["details_observed_at"]
    assert markets[1]["details_state"] == "unknown"
    assert markets[1]["details_observed_at"] is None
    assert opportunities["shipyards"][0]["state"] == "unknown"
    assert report["account_observations"]["contracts"]["data"] == []
    assert "SECRET" not in json.dumps(report)
    assert "transactions" not in json.dumps(report)


@pytest.mark.parametrize("status,code", [(401, None), (400, 4113)])
def test_auth_failure_stops_before_fleet(
    status: int, code: int | None
) -> None:
    # Arrange.
    client, calls = peer(failure=status, code=code)
    # Act / Assert.
    with client, pytest.raises(APIError):
        capability_snapshot(client)
    assert calls == ["/", "/my/agent"]


def test_unknown_agent_defers_system() -> None:
    # Arrange.
    client, calls = peer(failure=503)
    # Act.
    with client:
        report = capability_snapshot(client)
    # Assert.
    assert report["scope"]["system"] is None
    assert (
        report["opportunity_observations"]["waypoints"]["state"] == "unknown"
    )
    assert not any("/systems/" in path for path in calls)
    assert "SECRET" not in json.dumps(report)


def test_cli_redacts_token_even_in_allowed_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: credential deliberately matches a normally public symbol.
    client, _ = peer()
    monkeypatch.setenv("ST_TOKEN", "TEST")
    monkeypatch.setattr(capabilities_cmd, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        capabilities_cmd, "SpaceTradersClient", lambda _: client
    )
    monkeypatch.setattr(time, "sleep", lambda _: None)
    # Act.
    result = CliRunner().invoke(app, ["capability-snapshot"])
    # Assert.
    assert result.exit_code == 0
    assert "TEST" not in result.output
    assert "[REDACTED]" in result.output
    assert json.loads(result.output)["schema_version"] == 1


def test_cli_auth_error_has_no_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange.
    client, _ = peer(failure=401)
    monkeypatch.setenv("ST_TOKEN", "SECRET")
    monkeypatch.setattr(capabilities_cmd, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        capabilities_cmd, "SpaceTradersClient", lambda _: client
    )
    monkeypatch.setattr(time, "sleep", lambda _: None)
    # Act.
    result = CliRunner().invoke(app, ["capability-snapshot"])
    # Assert.
    assert result.exit_code == 1
    assert "authentication/reset mismatch" in result.output
    assert "SECRET" not in result.output
    assert "/private" not in result.output
