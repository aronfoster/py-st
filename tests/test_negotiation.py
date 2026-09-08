from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.client import APIError, SpaceTradersClient
from py_st.services.automation import SafetyStop, Session
from py_st.services.intelligence import Intelligence
from py_st.services.negotiation import negotiate_run
from tests.factories import ContractFactory


@pytest.fixture
def world(tmp_path: Path) -> Iterator[dict[str, Any]]:
    state: dict[str, Any] = {
        "contracts": [],
        "ship": {
            "symbol": "S",
            "nav": {
                "systemSymbol": "X-A",
                "waypointSymbol": "X-A-1",
                "status": "DOCKED",
            },
            "cooldown": {"remainingSeconds": 0},
        },
        "waypoint": {"symbol": "X-A-1", "faction": {"symbol": "COSMIC"}},
        "posts": [],
        "error": 0,
        "unknown": False,
        "malformed": False,
        "reset": "r",
    }

    def request(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            if req.url.path == "/":
                return httpx.Response(200, json={"resetDate": state["reset"]})
            data = {
                "/my/agent": {"symbol": "a", "credits": 397940},
                "/my/ships": [state["ship"]],
                "/my/contracts": state["contracts"],
                "/systems/X-A/waypoints/X-A-1": state["waypoint"],
            }[req.url.path]
            return httpx.Response(200, json={"data": data})
        assert req.method == "POST"
        assert req.url.path == "/my/ships/S/negotiate/contract"
        state["posts"].append(req.url.path)
        if state["error"]:
            return httpx.Response(
                state["error"],
                json={"error": {"code": 4000, "message": "rejected"}},
            )
        contract = ContractFactory.build_minimal()
        state["contracts"].append(contract)
        if state["unknown"]:
            raise httpx.ReadTimeout("Outcome unknown")
        return httpx.Response(
            200,
            json={
                "data": {} if state["malformed"] else {"contract": contract}
            },
        )

    client = SpaceTradersClient(
        "fake",
        httpx.Client(
            transport=httpx.MockTransport(request), base_url="https://test"
        ),
    )
    client._transport._interval = 0
    store = Intelligence(tmp_path / "db")
    state["store"] = store
    state["run"] = Session(client, store, root=tmp_path, execute=True)
    with patch("py_st.services.automation.cache.clear_cache"):
        try:
            yield state
        finally:
            state["run"].close()
            client.close()
            store.close()


def test_dry_run_reports_prerequisites_without_post(
    world: dict[str, Any],
) -> None:
    # Arrange
    world["run"].execute = False
    world["ship"]["cooldown"]["remainingSeconds"] = 20
    # Act
    result = negotiate_run(world["run"], "S")
    # Assert: cooldown is observable, not an invented server requirement.
    assert result["plan"]["eligible"]
    assert result["plan"]["cooldown"]["remainingSeconds"] == 20
    assert result["plan"]["nav_status"] == "DOCKED"
    assert result["plan"]["faction"] == "COSMIC"
    assert not world["posts"]
    assert not world["store"].actions("r:a")


@pytest.mark.parametrize("nav", ["DOCKED", "IN_ORBIT"])
def test_success_persists_offer_and_restart_never_duplicates(
    world: dict[str, Any], nav: str
) -> None:
    # Arrange
    world["ship"]["nav"]["status"] = nav
    run = world["run"]
    # Act
    result = negotiate_run(run, "S")
    run.close()
    world["run"] = Session(run.client, run.store, root=run.root, execute=True)
    with pytest.raises(SafetyStop, match="Existing unfulfilled"):
        negotiate_run(world["run"], "S")
    # Assert
    assert result["contract"]["accepted"] is False
    assert len(world["posts"]) == 1
    assert run.store.actions("r:a")[0]["status"] == "succeeded"
    assert run.store.latest("r:a", "contract")[0]["data"] == result["contract"]
    assert run.store.negotiated_contracts("r:a") == [result["contract"]]
    assert run.store.economics("r:a")["journal_net_cash"] == 0


@pytest.mark.parametrize("guard", ["pending", "transit", "faction", "offer"])
def test_ineligible_plan_and_execution_never_post(
    world: dict[str, Any], guard: str
) -> None:
    # Arrange
    run = world["run"]
    if guard == "pending":
        run.store.begin_action("r:a", "/unknown", None)
    elif guard == "transit":
        world["ship"]["nav"]["status"] = "IN_TRANSIT"
    elif guard == "faction":
        world["waypoint"].pop("faction")
    else:
        world["contracts"].append(ContractFactory.build_minimal())
    run.execute = False
    # Act
    result = negotiate_run(run, "S")
    run.execute = True
    with pytest.raises(SafetyStop):
        negotiate_run(run, "S")
    # Assert
    assert not result["plan"]["eligible"]
    assert result["plan"]["blockers"]
    assert not world["posts"]


@pytest.mark.parametrize("status", [400, 409, 429, 401, 500])
def test_error_is_one_dispatch_and_journaled(
    world: dict[str, Any], status: int
) -> None:
    # Arrange
    world["error"] = status
    # Act
    with pytest.raises(APIError):
        negotiate_run(world["run"], "S")
    # Assert: even cooldown/rate-limit rejection is not replayed.
    assert len(world["posts"]) == 1
    action = world["store"].actions("r:a")[0]
    assert action["status"] == ("pending" if status == 500 else "rejected")


@pytest.mark.parametrize("offer_visible", [False, True])
def test_timeout_restart_requires_reconciliation_even_with_offer(
    world: dict[str, Any], offer_visible: bool
) -> None:
    # Arrange
    world["unknown"] = True
    run = world["run"]
    # Act
    with pytest.raises(httpx.ReadTimeout):
        negotiate_run(run, "S")
    if not offer_visible:
        world["contracts"].clear()
    run.close()
    world["run"] = Session(run.client, run.store, root=run.root, execute=True)
    with pytest.raises(SafetyStop, match="Pending action"):
        negotiate_run(world["run"], "S")
    # Assert
    assert len(world["posts"]) == 1
    assert run.store.pending("r:a")


def test_malformed_success_stays_pending(world: dict[str, Any]) -> None:
    # Arrange
    world["malformed"] = True
    # Act
    with pytest.raises(SafetyStop, match="Invalid negotiation response"):
        negotiate_run(world["run"], "S")
    # Assert
    assert world["store"].pending("r:a")
    assert len(world["posts"]) == 1


def test_receipt_protects_crash_before_observation(
    world: dict[str, Any],
) -> None:
    # Arrange
    run = world["run"]
    observe = run.store.observe

    def crash(*args: Any, **kwargs: Any) -> None:
        if args[1] == "contract":
            raise KeyboardInterrupt()
        observe(*args, **kwargs)

    # Act
    with (
        patch.object(run.store, "observe", side_effect=crash),
        pytest.raises(KeyboardInterrupt),
    ):
        negotiate_run(run, "S")
    world["contracts"].clear()
    with pytest.raises(SafetyStop, match="Journaled offer missing"):
        negotiate_run(run, "S")
    # Assert
    assert len(world["posts"]) == 1
    assert not run.store.latest("r:a", "contract")
    assert run.store.actions("r:a")[0]["status"] == "succeeded"


def test_fulfilled_receipt_allows_new_offer_and_is_scope_isolated(
    world: dict[str, Any],
) -> None:
    # Arrange
    run = world["run"]
    negotiate_run(run, "S")
    world["contracts"][0]["fulfilled"] = True
    # Act
    run.execute = False
    plan = negotiate_run(run, "S")["plan"]
    world["contracts"].clear()
    world["reset"] = "new"
    run.close()
    world["run"] = Session(run.client, run.store, root=run.root)
    new_plan = negotiate_run(world["run"], "S")["plan"]
    # Assert
    assert plan["eligible"]
    assert new_plan["eligible"]
    assert run.store.negotiated_contracts("new:a") == []
    assert len(world["posts"]) == 1


@pytest.mark.parametrize("guard", ["stop", "deadline", "budget", "ship"])
def test_session_guards_and_unknown_ship(
    world: dict[str, Any], guard: str
) -> None:
    # Arrange
    run = world["run"]
    if guard == "stop":
        (run.root / "STOP").touch()
    elif guard == "deadline":
        run.deadline = 0
    elif guard == "budget":
        run.remaining = 0
    # Act
    with pytest.raises(SafetyStop):
        negotiate_run(run, "MISSING" if guard == "ship" else "S")
    # Assert
    assert not world["posts"]


def test_cli_defaults_to_one_action_dry_run() -> None:
    # Arrange
    with (
        patch("py_st.cli.auto_cmd.session") as session,
        patch("py_st.cli.auto_cmd.negotiate_run", return_value={}) as run,
    ):
        # Act
        result = CliRunner().invoke(app, ["auto", "negotiate", "S"])
    # Assert
    assert result.exit_code == 0
    session.assert_called_once_with(False, 120, 1)
    run.assert_called_once()


def test_cli_bounds_precede_session() -> None:
    # Arrange
    with patch("py_st.cli.auto_cmd.session") as session:
        # Act
        result = CliRunner().invoke(
            app, ["auto", "negotiate", "S", "--seconds", "0"]
        )
    # Assert
    assert result.exit_code != 0
    session.assert_not_called()


@pytest.mark.parametrize(
    "path",
    [
        "/my/ships/S/negotiate",
        "/my/ships/S/negotiate/anything",
        "/my/ships/S/negotiate/contract/extra",
        "/my/ships/S/extract",
    ],
)
def test_allowlist_remains_narrow(world: dict[str, Any], path: str) -> None:
    # Arrange
    run = world["run"]
    run.refresh()
    # Act
    with pytest.raises(SafetyStop, match="allowlist"):
        run.mutate(path)
    # Assert
    assert not world["posts"]
    assert not run.store.actions("r:a")
