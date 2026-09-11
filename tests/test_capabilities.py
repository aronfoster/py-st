"""Offline transport proof for the publishable capability snapshot."""

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli import capabilities_cmd
from py_st.cli.app import app
from py_st.client.client import SpaceTradersClient
from py_st.client.transport import APIError, RequestAborted
from py_st.services.capabilities import SnapshotTimeBudget, capability_snapshot


def peer(
    *,
    failure: int | None = None,
    code: int | None = None,
    waypoints: list[Any] | None = None,
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
            if waypoints is not None:
                return httpx.Response(
                    200,
                    json={
                        "data": waypoints,
                        "meta": {
                            "total": len(waypoints),
                            "limit": max(1, len(waypoints)),
                            "page": 1,
                        },
                    },
                )
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
    assert report["scope"]["truncated"] is False


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
    report = json.loads(result.output)
    assert report["schema_version"] == 1
    agent = report["account_observations"]["agent"]["data"]
    assert agent["symbol"] == "[REDACTED]"


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


def test_detail_budget_limits_reads() -> None:
    # Arrange: 82 detail candidates, exceeding the 80-read cap.
    waypoints = [
        {
            "symbol": f"X1-TEST-A{i}",
            "traits": [{"symbol": "MARKETPLACE"}, {"symbol": "SHIPYARD"}],
        }
        for i in range(41)
    ]
    client, calls = peer(waypoints=waypoints)
    # Act.
    with client:
        report = capability_snapshot(client)
    # Assert: five initial reads followed by exactly 80 detail reads.
    assert len(calls) == 85
    assert report["scope"]["truncation_reasons"] == ["detail_budget"]
    for kind in ("markets", "shipyards"):
        last = report["opportunity_observations"][kind][-1]
        assert last["reason"] == "detail_budget"
        assert last["details_unknown_reason"] == "detail_budget"


def test_time_budget_stops_read_attempts() -> None:
    # Arrange: expire after the initial six requests including waypoint pages.
    client, calls = peer()
    waits = 0

    def wait(seconds: float) -> None:
        nonlocal waits
        waits += 1
        if len(calls) >= 6:
            raise SnapshotTimeBudget("SECRET")

    client.set_wait(wait)
    # Act.
    with client:
        report = capability_snapshot(client)
    # Assert: only one rejected attempt; subsequent rows are deferred locally.
    assert len(calls) == 6
    assert waits == 7
    assert report["scope"]["truncated"] is True
    assert report["scope"]["truncation_reasons"] == ["time_budget"]
    for kind in ("markets", "shipyards"):
        for row in report["opportunity_observations"][kind]:
            assert row["reason"] == "time_budget"
            assert row["details_observed_at"] is None
    assert "SECRET" not in json.dumps(report)


def test_other_abort_is_not_mislabeled_as_time_budget() -> None:
    # Arrange.
    client, calls = peer()

    def wait(seconds: float) -> None:
        raise RuntimeError("unrelated interruption")

    client.set_wait(wait)
    # Act / Assert.
    with client, pytest.raises(RequestAborted):
        capability_snapshot(client)
    assert calls == []


def test_malformed_waypoint_and_trait_items_preserve_valid_sites() -> None:
    # Arrange.
    client, _ = peer(
        waypoints=[
            None,
            "bad-waypoint",
            {
                "symbol": "X1-TEST-A",
                "traits": [None, {"symbol": "MARKETPLACE"}],
            },
        ]
    )
    # Act.
    with client:
        report = capability_snapshot(client)
    # Assert: malformed entries remain null; valid site discovery survives.
    opportunities = report["opportunity_observations"]
    assert opportunities["waypoints"]["data"][:2] == [None, None]
    assert len(opportunities["markets"]) == 1
    assert opportunities["markets"][0]["details_state"] == "observed"


@pytest.mark.parametrize("save_fails", [False, True])
def test_output_creates_parents_or_preserves_json_on_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, save_fails: bool
) -> None:
    # Arrange: a missing output parent, or an existing directory as the file.
    client, calls = peer()
    output = tmp_path if save_fails else tmp_path / "new" / "snapshot.json"
    monkeypatch.setenv("ST_TOKEN", "SECRET")
    monkeypatch.setattr(capabilities_cmd, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        capabilities_cmd, "SpaceTradersClient", lambda _: client
    )
    monkeypatch.setattr(time, "sleep", lambda _: None)
    # Act.
    result = CliRunner().invoke(
        app, ["capability-snapshot", "--output", str(output)]
    )
    # Assert: saving failure does not replay reads or discard collected data.
    assert result.exit_code == (1 if save_fails else 0)
    rendered = result.stdout if save_fails else output.read_text()
    assert (
        json.loads(rendered)["account_observations"]["agent"]["data"]["symbol"]
        == "TEST"
    )
    assert calls.count("/my/agent") == 1
    assert "SECRET" not in rendered
    assert str(tmp_path) not in result.output
    if save_fails:
        assert "file save failed" in result.stderr


def test_cli_deadline_marks_report_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: clock advances to the deadline after constructing the client.
    client, calls = peer()
    clock = 0.0

    def factory(token: str) -> SpaceTradersClient:
        nonlocal clock
        clock = 180.0
        return client

    monkeypatch.setenv("ST_TOKEN", "SECRET")
    monkeypatch.setattr(capabilities_cmd, "load_dotenv", lambda: None)
    monkeypatch.setattr(capabilities_cmd, "SpaceTradersClient", factory)
    monkeypatch.setattr(time, "monotonic", lambda: clock)
    # Act.
    result = CliRunner().invoke(app, ["capability-snapshot"])
    # Assert: deadline prevents even the first request and labels partial data.
    assert result.exit_code == 0
    assert calls == []
    report = json.loads(result.stdout)
    assert report["scope"]["truncation_reasons"] == ["time_budget"]
    assert report["account_observations"]["agent"]["reason"] == "time_budget"
