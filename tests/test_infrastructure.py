"""Synthetic GET-only discovery against the real scoped observation store."""

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli import auto_cmd
from py_st.client import APIError, SpaceTradersClient
from py_st.client.transport import RequestAborted
from py_st.services.automation import SafetyStop, Session
from py_st.services.infrastructure import infrastructure_run
from py_st.services.intelligence import Intelligence


def waypoint(n: int, **extra: Any) -> dict[str, Any]:
    return {
        "symbol": f"X1-ABC-{n}",
        "systemSymbol": "X1-ABC",
        "type": "PLANET",
        "traits": [],
        "isUnderConstruction": False,
        "x": 0,
        "y": 0,
        "orbitals": [],
    } | extra


class FakeSession:
    def __init__(self, store: Intelligence) -> None:
        self.store = store
        self.scope = "reset:TEST"
        self.client = self
        self.pages: list[list[dict[str, Any]]] = [[]]
        self.payloads: dict[str, Any] = {}
        self.calls: list[str] = []
        self.stop: Exception | None = None
        self.stop_after: int | None = None
        self.deadline = float("inf")

    def check(self) -> None:
        if time.monotonic() >= self.deadline:
            raise SafetyStop("Wall-clock budget exhausted")
        if self.stop and (
            self.stop_after is None or len(self.calls) >= self.stop_after
        ):
            raise self.stop

    def refresh(self) -> None:
        self.calls.append("refresh")

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        assert method == "GET"
        self.calls.append(path)
        if path.endswith("/waypoints"):
            assert kwargs == {"paginate": True}
            return [item for page in self.pages for item in page]
        payload = self.payloads[path.rsplit("/", 1)[-1]]
        if isinstance(payload, Exception):
            raise payload
        return payload | {"symbol": path.split("/")[-2]}

    def get(self, path: str) -> Any:
        return self.request("GET", path)


@pytest.fixture
def run(tmp_path: Path) -> Iterator[FakeSession]:
    store = Intelligence(tmp_path / "observations.sqlite3")
    fake = FakeSession(store)
    yield fake
    store.close()


def discover(run: FakeSession, **kwargs: Any) -> dict[str, Any]:
    return infrastructure_run(cast(Session, run), "X1-ABC", **kwargs)


def test_spec_matching_and_shared_report(run: FakeSession) -> None:
    run.pages = [
        [
            waypoint(1, type="JUMP_GATE", isUnderConstruction=True),
            waypoint(2, traits=[{"symbol": "SHIPYARD"}]),
            waypoint(3, traits=[{"symbol": "JUMP_GATE"}]),
            waypoint(4, type="SHIPYARD"),
        ]
    ]
    run.payloads = {
        "jump-gate": {"connections": ["X1-OTHER-A"]},
        "construction": {
            "isComplete": False,
            "materials": [
                {"tradeSymbol": "IRON", "required": 10, "fulfilled": 3}
            ],
        },
        "shipyard": {
            "shipTypes": [{"type": "SHIP_PROBE"}],
            "modificationsFee": 100,
        },
    }
    result = discover(run)
    assert result["counts"] == {
        "jump_gates": 1,
        "shipyards": 1,
        "construction": 1,
    }
    assert [p.rsplit("/", 1)[-1] for p in run.calls] == [
        "refresh",
        "waypoints",
        "jump-gate",
        "construction",
        "shipyard",
    ]
    assert result["sites"][1]["price_status"] == "unknown"
    assert (
        result["sites"][1]["construction_status"] == "not under construction"
    )
    assert not result["execution_authorized"]
    report = run.store.report(run.scope)
    assert len(report["waypoints"]) == 4
    assert report["construction"][0]["data"]["materials"][0]["fulfilled"] == 3
    assert report["shipyards"][0]["source"] == "live-api"
    assert report["jump_gates"][0]["observed_at"]
    assert run.store.report("other:TEST")["shipyards"] == []
    assert run.store.report("reset:OTHER")["jump_gates"] == []


def test_completed_construction_no_guessed_requirements(
    run: FakeSession,
) -> None:
    run.pages = [[waypoint(1, isUnderConstruction=True)]]
    run.payloads = {"construction": {"isComplete": True, "materials": []}}
    result = discover(run)
    assert result["sites"][0]["construction_status"] == "complete"
    assert result["sites"][0]["construction"]["materials"] == []


def test_site_limit_independent_of_pagination(run: FakeSession) -> None:
    run.pages = [
        [waypoint(i) for i in range(20)],
        [waypoint(20, type="JUMP_GATE"), waypoint(21, type="JUMP_GATE")],
    ]
    run.payloads = {"jump-gate": {"connections": []}}
    result = discover(run, max_sites=1)
    assert result["status"] == "site limit"
    assert result["remaining_sites"] == 1
    assert result["truncated"] and not result["remaining_unknown"]
    assert result["site_attempts"] == 1
    assert len(run.calls) == 3
    assert len(run.store.latest(run.scope, "waypoint")) == 22


@pytest.mark.parametrize(
    "message", ["STOP sentinel present", "Wall-clock budget exhausted"]
)
@pytest.mark.parametrize("after", [0, 1, 2, 3])
def test_bounds_between_reads(
    run: FakeSession, message: str, after: int
) -> None:
    run.pages = [[waypoint(1, type="JUMP_GATE", isUnderConstruction=True)]]
    run.payloads = {"jump-gate": {"connections": []}}
    run.stop = SafetyStop(message)
    run.stop_after = after
    result = discover(run)
    assert result["status"] in ("stopped", "time limit")
    assert len(run.calls) == after
    assert result["truncated"]
    if after == 3:
        assert len(run.store.latest(run.scope, "jump_gate")) == 1
        assert result["remaining_sites"] == 1


@pytest.mark.parametrize(
    "error",
    [
        APIError("auth", status=401),
        APIError("reset", payload={"error": {"code": 4113}}),
        APIError("absent", status=404),
    ],
)
def test_errors_propagate_without_fallback(
    run: FakeSession, error: APIError
) -> None:
    run.pages = [[waypoint(1, type="JUMP_GATE", isUnderConstruction=True)]]
    run.payloads = {"jump-gate": {"connections": []}, "construction": error}
    with pytest.raises(APIError) as caught:
        discover(run)
    assert caught.value is error
    assert len(run.calls) == 4
    assert len(run.store.latest(run.scope, "jump_gate")) == 1


def test_sparse_quotes_preserve_history_without_merge(
    run: FakeSession, tmp_path: Path
) -> None:
    run.pages = [[waypoint(1, traits=[{"symbol": "SHIPYARD"}])]]
    old = {
        "symbol": "X1-ABC-1",
        "shipTypes": [],
        "ships": [{"purchasePrice": 900}],
    }
    run.store.observe(run.scope, "shipyard", "X1-ABC-1", old, "historical")
    previous = run.store.latest(run.scope, "shipyard")[0]
    run.payloads = {"shipyard": {"shipTypes": [], "modificationsFee": 1}}
    result = discover(run)
    assert result["sites"][0]["price_status"] == "unknown"
    reader = Intelligence(tmp_path / "observations.sqlite3", read_only=True)
    try:
        latest = reader.report(run.scope)["shipyards"][0]
        assert "ships" not in latest["data"]
        assert latest["id"] > previous["id"]
        row = reader.db.execute(
            "SELECT data,source,observed_at FROM observations WHERE id=?",
            (previous["id"],),
        ).fetchone()
        assert json.loads(row["data"]) == old
        assert row["observed_at"] == previous["observed_at"]
        assert row["source"] == "historical"
    finally:
        reader.close()


@pytest.mark.parametrize(
    "system", ["x1-abc", "X1-ABC/secret", "X1-ABC?q=1", "X1-ABC-A", ""]
)
def test_invalid_system_before_io(run: FakeSession, system: str) -> None:
    with pytest.raises(ValueError):
        infrastructure_run(cast(Session, run), system)
    assert not run.calls


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_invalid_limit_before_io(run: FakeSession, limit: Any) -> None:
    with pytest.raises(ValueError):
        discover(run, max_sites=limit)
    assert not run.calls


def test_cli_get_only(
    run: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def session(
        execute: bool, seconds: int, actions: int
    ) -> Iterator[FakeSession]:
        assert (execute, seconds, actions) == (False, 300, 1)
        yield run

    monkeypatch.setattr(auto_cmd, "session", session)
    runner = CliRunner()
    result = runner.invoke(auto_cmd.auto_app, ["infrastructure", "X1-ABC"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["execution_authorized"] is False
    run.calls.clear()
    for args in (
        ["--execute"],
        ["--seconds", "0"],
        ["--seconds", "7201"],
        ["--max-sites", "101"],
    ):
        assert (
            runner.invoke(
                auto_cmd.auto_app, ["infrastructure", "X1-ABC", *args]
            ).exit_code
            != 0
        )
    assert (
        runner.invoke(
            auto_cmd.auto_app, ["infrastructure", "X1-ABC?x=1"]
        ).exit_code
        != 0
    )
    assert not run.calls


def test_transport_bound_retains_partial(run: FakeSession) -> None:
    run.pages = [[waypoint(1, type="JUMP_GATE")]]
    error = RequestAborted("Interrupted before dispatch")
    error.__cause__ = SafetyStop("Wall-clock budget exhausted")
    run.payloads = {"jump-gate": error}
    assert discover(run)["status"] == "time limit"
    assert len(run.store.latest(run.scope, "waypoint")) == 1


def test_foreign_waypoint_rejected_before_endpoint(run: FakeSession) -> None:
    run.pages = [[waypoint(1, systemSymbol="X1-OTHER", type="JUMP_GATE")]]
    with pytest.raises(SafetyStop, match="requested system"):
        discover(run)
    assert len(run.calls) == 2


def test_monotonic_deadline_after_page(
    run: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    run.deadline = 1.0
    run.pages = [[waypoint(1, type="JUMP_GATE")]]
    request = run.request

    def delayed_request(*args: Any, **kwargs: Any) -> Any:
        data = request(*args, **kwargs)
        clock[0] = 1.0
        return data

    monkeypatch.setattr(run, "request", delayed_request)
    result = discover(run)
    assert result["status"] == "time limit"
    assert len(run.calls) == 2
    assert result["remaining_unknown"]
    assert len(run.store.latest(run.scope, "waypoint")) == 0


def test_stop_after_discovery_before_observation(run: FakeSession) -> None:
    run.pages = [[waypoint(i) for i in range(20)]]
    run.stop = SafetyStop("STOP sentinel present")
    run.stop_after = 2
    result = discover(run)
    assert result["status"] == "stopped"
    assert result["remaining_unknown"]
    assert len(run.calls) == 2
    assert len(run.store.latest(run.scope, "waypoint")) == 0


@pytest.mark.parametrize(
    "scenario",
    ["complete", "repeated", "interrupted", "final_page", "final_site"],
)
@pytest.mark.parametrize(
    "bound", ["STOP sentinel present", "Wall-clock budget exhausted"]
)
def test_real_sdk_pagination_and_final_bounds(
    run: FakeSession,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    bound: str,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        if request.url.path.endswith("/waypoints"):
            page = int(request.url.params.get("page", "1"))
            assert request.url.params["limit"] == "20"
            data = (
                [waypoint(i) for i in range(20)]
                if page == 1
                else [waypoint(20, type="JUMP_GATE")]
            )
            if (scenario == "interrupted" and page == 1) or (
                scenario == "final_page" and page == 2
            ):
                run.stop = SafetyStop(bound)
            return httpx.Response(
                200,
                json={
                    "data": data,
                    "meta": {
                        "page": 1 if scenario == "repeated" else page,
                        "limit": 20,
                        "total": 21,
                    },
                },
            )
        assert request.url.path.endswith("/X1-ABC-20/jump-gate")
        if scenario == "final_site":
            run.stop = SafetyStop(bound)
        return httpx.Response(
            200, json={"data": {"symbol": "X1-ABC-20", "connections": []}}
        )

    with (
        httpx.Client(
            base_url="https://example.test",
            transport=httpx.MockTransport(handler),
        ) as http,
        SpaceTradersClient("synthetic", client=http) as client,
    ):
        client.set_wait(lambda seconds: run.check())
        monkeypatch.setattr(run, "client", client)
        monkeypatch.setattr(
            run, "get", lambda path: client.request("GET", path)
        )
        result: dict[str, Any] | None
        if scenario == "repeated":
            with pytest.raises(APIError, match="pagination metadata"):
                discover(run)
            result = None
        else:
            result = discover(run)

    assert dict(requests[0].url.params) == {"limit": "20"}
    if scenario != "interrupted":
        assert dict(requests[1].url.params) == {"limit": "20", "page": "2"}
    rows = run.store.latest(run.scope, "waypoint")
    if scenario in ("complete", "final_site"):
        assert {row["key"] for row in rows} == {
            f"X1-ABC-{i}" for i in range(21)
        }
        assert (
            run.store.db.execute(
                "SELECT COUNT(*) FROM observations WHERE kind='waypoint'"
            ).fetchone()[0]
            == 21
        )
        assert len(requests) == 3
        assert len(run.store.latest(run.scope, "jump_gate")) == 1
    else:
        assert rows == []
        assert len(requests) == (1 if scenario == "interrupted" else 2)
    if result is not None:
        expected_status = "complete"
        if scenario != "complete":
            expected_status = (
                "stopped" if bound.startswith("STOP") else "time limit"
            )
        assert result["status"] == expected_status
        assert result["truncated"] is (scenario != "complete")
        assert result["remaining_unknown"] is (
            scenario in ("interrupted", "final_page")
        )


@pytest.mark.parametrize(
    "message", ["STOP sentinel present", "Wall-clock budget exhausted"]
)
def test_empty_final_page_checks_bound(
    run: FakeSession, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    request = run.request

    def stop_after_read(*args: Any, **kwargs: Any) -> Any:
        data = request(*args, **kwargs)
        run.stop = SafetyStop(message)
        return data

    monkeypatch.setattr(run, "request", stop_after_read)
    result = discover(run)
    assert result["status"] != "complete"
    assert result["truncated"]
    assert len(run.calls) == 2


def test_check_each_waypoint_retains_prior_observations(
    run: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    run.pages = [[waypoint(1), waypoint(2)]]
    observe = run.store.observe

    def stop_after_observe(*args: Any, **kwargs: Any) -> None:
        observe(*args, **kwargs)
        run.stop = SafetyStop("STOP sentinel present")

    monkeypatch.setattr(run.store, "observe", stop_after_observe)
    result = discover(run)
    assert result["status"] == "stopped"
    assert result["waypoint_count"] == 1
    assert result["remaining_unknown"]
    assert len(run.store.latest(run.scope, "waypoint")) == 1
