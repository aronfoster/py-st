import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.client import APIError
from py_st.services.automation import SafetyStop, Session
from py_st.services.earning import earn_run
from py_st.services.intelligence import Intelligence
from py_st.services.pilot import pilot_run
from tests import test_earning

world = test_earning.world


def test_real_discover_trade_return_trade(world: dict[str, Any]) -> None:
    result = pilot_run(world["run"], "X-A", steps=4, reposition=True)
    assert result["status"] == "completed"
    assert result["outcome"] == "step limit"
    assert result["completed_steps"] == 4
    assert result["last_decision"]["decisions"][0]["kind"] == "trade"
    assert world["posts"].count("/my/ships/H/purchase") == 2
    assert world["posts"].count("/my/ships/H/navigate") == 3
    assert world["agent"]["credits"] > 111000
    assert not world["store"].pending("r:a")
    assert "--reposition" in result["resume_command"]


def test_hundred_distance_cycle_with_buyer_and_source_refills(
    world: dict[str, Any],
) -> None:
    for waypoint in world["waypoints"]:
        waypoint["x"] *= 10
    run = world["run"]
    lock, deadline = run.lock, run.deadline
    result = pilot_run(run, "X-A", steps=4, reposition=True)
    assert result["completed_steps"] == 4
    assert result["outcome"] == "step limit"
    assert run.lock is lock and run.deadline == deadline
    assert world["posts"].count("/my/ships/H/refuel") == 2
    assert world["posts"].count("/my/ships/H/purchase") == 2
    assert world["ships"][0]["fuel"]["current"] == 300
    assert world["agent"]["credits"] == 111856
    assert not world["store"].pending("r:a")


def test_same_session_budgets_and_history(tmp_path: Path) -> None:
    database = tmp_path / "ledger.sqlite3"
    store = Intelligence(database)
    run = Session(MagicMock(), store, root=tmp_path, execute=True, actions=3)
    run.scope = "r:a"
    deadline, lock = run.deadline, run.lock
    kinds = iter(["trade", "reposition", "trade"])

    def step(actual: Session, system: str, **kwargs: Any) -> dict[str, Any]:
        assert actual is run and actual.lock is lock
        assert actual.deadline == deadline
        assert kwargs == {"cycles": 1, "max_age": 900, "reposition": True}
        actual.remaining -= 1
        kind = next(kinds)
        return {
            "status": (
                "recovery only" if kind == "reposition" else "cycle limit"
            ),
            "decisions": [{"kind": kind}],
        }

    try:
        with patch("py_st.services.pilot.earn_run", side_effect=step):
            result = pilot_run(run, "X-A", steps=3, reposition=True)
        UUID(result["id"])
        assert result["actions_used"] == 3
        assert result["remaining_actions"] == 0
        rows = store.db.execute(
            "SELECT data FROM observations WHERE kind='automation_run' "
            "ORDER BY id"
        ).fetchall()
        history = [json.loads(row[0]) for row in rows]
        assert [r["completed_steps"] for r in history] == [0, 1, 2, 3, 3]
        assert [r["status"] for r in history] == ["running"] * 4 + [
            "completed"
        ]
    finally:
        run.close()
        store.close()
    reopened = Intelligence(database)
    try:
        assert reopened.latest("r:a", "automation_run")[0]["data"] == result
    finally:
        reopened.close()


def test_dryrun_one(world: dict[str, Any]) -> None:
    world["run"].execute = False
    result = pilot_run(world["run"], "X-A", steps=100, reposition=True)
    assert result["completed_steps"] == 1
    assert result["outcome"] == "dry run"
    assert result["actions_used"] == 0
    assert world["posts"] == []


@pytest.mark.parametrize(
    "status", ["no ready routes or scout targets", "reposition blocked"]
)
def test_terminal_no_repeat(world: dict[str, Any], status: str) -> None:
    with patch(
        "py_st.services.pilot.earn_run", return_value={"status": status}
    ) as earn:
        result = pilot_run(world["run"], "X-A")
    earn.assert_called_once()
    assert result["status"] == "stopped"
    assert result["outcome"] == status


@pytest.mark.parametrize(
    "error, status, outcome",
    [
        (
            SafetyStop("STOP sentinel present; remove deliberately"),
            "stopped",
            "STOP",
        ),
        (httpx.ReadTimeout("secret header/token"), "failed", "ReadTimeout"),
        (KeyboardInterrupt(), "interrupted", "KeyboardInterrupt"),
    ],
)
def test_exception_terminal_then_reraise(
    world: dict[str, Any], error: BaseException, status: str, outcome: str
) -> None:
    with (
        patch("py_st.services.pilot.earn_run", side_effect=error) as earn,
        pytest.raises(type(error)),
    ):
        pilot_run(world["run"], "X-A")
    earn.assert_called_once()
    record = world["store"].latest("r:a", "automation_run")[0]["data"]
    assert record["status"] == status
    assert outcome in record["outcome"]
    assert record["completed_steps"] == 0
    assert "secret" not in json.dumps(record)


def test_stop_midstep_recovery(world: dict[str, Any]) -> None:
    world["stop_after"] = "navigate"
    with pytest.raises(SafetyStop, match="STOP"):
        pilot_run(world["run"], "X-A", reposition=True)
    record = world["store"].latest("r:a", "automation_run")[0]["data"]
    assert record["status"] == "stopped"
    assert record["actions_used"] == 1
    assert world["root"].joinpath("STOP").exists()


@pytest.mark.parametrize(
    "error",
    [
        SafetyStop("STOP"),
        APIError("secret API payload", status=401),
        httpx.ReadTimeout("secret timeout"),
        KeyboardInterrupt(),
    ],
)
def test_terminal_storage_failure_preserves_original(
    world: dict[str, Any],
    error: BaseException,
    caplog: pytest.LogCaptureFixture,
) -> None:
    world["run"].scope = "r:a"
    with (
        patch("py_st.services.pilot.earn_run", side_effect=error),
        patch.object(
            world["store"],
            "observe",
            side_effect=[None, sqlite3.OperationalError("secret database")],
        ),
        pytest.raises(type(error)) as caught,
    ):
        pilot_run(world["run"], "X-A")
    assert caught.value is error
    assert "Pilot terminal persistence failed: OperationalError" in caplog.text
    assert "secret" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_terminal_storage_failure_after_success_is_failure(
    world: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    world["run"].scope = "r:a"
    error = sqlite3.OperationalError("secret database")
    with (
        patch(
            "py_st.services.pilot.earn_run",
            return_value={"status": "cycle limit"},
        ),
        patch.object(
            world["store"], "observe", side_effect=[None, None, error]
        ),
        pytest.raises(sqlite3.OperationalError) as caught,
    ):
        pilot_run(world["run"], "X-A", steps=1)
    assert caught.value is error
    assert "OperationalError" in caplog.text
    assert "secret" not in caplog.text


def test_unknown_pending_never_replayed(world: dict[str, Any]) -> None:
    world["unknown"] = True
    with pytest.raises(httpx.ReadTimeout):
        pilot_run(world["run"], "X-A")
    assert world["store"].pending("r:a")
    posts = list(world["posts"])
    world["unknown"] = False
    with pytest.raises(SafetyStop, match="Pending"):
        pilot_run(world["run"], "X-A")
    assert world["posts"] == posts
    assert len(world["store"].latest("r:a", "automation_run")) == 2


@pytest.mark.parametrize("position", ["trade", "reposition"])
def test_new_session_recovers_original_position(
    world: dict[str, Any], position: str
) -> None:
    earn_run(world["run"], "X-A", cycles=2 if position == "reposition" else 1)
    world["stop_after"] = (
        "navigate" if position == "reposition" else "purchase"
    )
    with pytest.raises(SafetyStop, match="STOP"):
        pilot_run(world["run"], "X-A", reposition=True)
    before = list(world["posts"])
    first_id = world["store"].latest("r:a", "automation_run")[0]["key"]
    # Simulate explicit operator clearance in the disposable synthetic root.
    world["root"].joinpath("STOP").unlink()
    world["stop_after"] = ""
    world["run"].close()
    restarted = Session(
        world["client"], world["store"], execute=True, root=world["root"]
    )
    try:
        result = pilot_run(restarted, "X-OTHER", steps=1)
    finally:
        restarted.close()
    assert result["id"] != first_id
    assert result["last_decision"]["status"] == "recovery only"
    positions = world["store"].latest("r:a", "position")
    recovered = next(p for p in positions if p["key"] == f"{position}:H")
    assert recovered["data"]["status"] == "closed"
    guarded = (
        "/my/ships/H/navigate"
        if position == "reposition"
        else "/my/ships/H/purchase"
    )
    assert world["posts"].count(guarded) == before.count(guarded)


def test_real_blocked_return_stops_without_discovery(
    world: dict[str, Any],
) -> None:
    earn_run(world["run"], "X-A", cycles=2)
    world["ships"][0]["fuel"]["current"] = 0
    world["fuel_volume"] = 0
    before = list(world["posts"])
    result = pilot_run(world["run"], "X-A", reposition=True)
    assert result["status"] == "stopped"
    assert result["outcome"] == "reposition blocked"
    assert result["completed_steps"] == 1
    assert world["posts"] == before


def test_auth_before_scope_has_no_invalid_writes(
    world: dict[str, Any],
) -> None:
    world["client"].status.side_effect = httpx.HTTPError("secret")
    with pytest.raises(httpx.HTTPError):
        pilot_run(world["run"], "X-A")
    assert world["store"].latest("", "automation_run") == []
    assert world["store"].scopes() == []


@pytest.mark.parametrize("guard", ["actions", "deadline"])
def test_budget_stops_before_next_step(
    world: dict[str, Any], guard: str
) -> None:
    def step(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if guard == "actions":
            world["run"].remaining = 0
        else:
            world["run"].deadline = 0
        return {"status": "cycle limit"}

    with (
        patch("py_st.services.pilot.earn_run", side_effect=step) as earn,
        pytest.raises(SafetyStop, match="budget"),
    ):
        pilot_run(world["run"], "X-A")
    earn.assert_called_once()
    assert (
        world["store"].latest("r:a", "automation_run")[0]["data"]["status"]
        == "stopped"
    )


@pytest.mark.parametrize(
    "steps,max_age", [(0, 900), (101, 900), (1, 0), (1, 86401)]
)
def test_invalid_service_bounds_no_io(steps: int, max_age: int) -> None:
    run = MagicMock()
    with pytest.raises(ValueError):
        pilot_run(run, "X-A", steps, max_age)
    assert run.mock_calls == []


@pytest.mark.parametrize(
    "flag,value",
    [
        ("steps", "0"),
        ("steps", "101"),
        ("seconds", "0"),
        ("seconds", "7201"),
        ("actions", "0"),
        ("actions", "201"),
        ("max-age", "0"),
        ("max-age", "86401"),
    ],
)
def test_cli_invalid_bounds_before_session(flag: str, value: str) -> None:
    with patch("py_st.cli.auto_cmd.session") as session:
        result = CliRunner().invoke(
            app, ["auto", "pilot", "X-A", f"--{flag}", value]
        )
    assert result.exit_code == 2
    session.assert_not_called()


def test_cli_defaults() -> None:
    with (
        patch("py_st.cli.auto_cmd.session") as session,
        patch("py_st.cli.auto_cmd.pilot_run", return_value={}) as pilot,
    ):
        result = CliRunner().invoke(app, ["auto", "pilot", "X-A"])
    assert result.exit_code == 0
    session.assert_called_once_with(False, 3600, 100)
    pilot.assert_called_once_with(
        session.return_value.__enter__.return_value,
        "X-A",
        10,
        900,
        reposition=False,
    )


@pytest.mark.parametrize("scope", ["r:a", ""])
@pytest.mark.parametrize(
    "error",
    [
        SafetyStop("STOP"),
        APIError("secret API payload", status=401),
        httpx.ReadTimeout("secret timeout"),
        KeyboardInterrupt(),
        sqlite3.OperationalError("secret database"),
    ],
)
def test_cli_failure_guidance_preserves_handler(
    scope: str, error: BaseException
) -> None:
    run = MagicMock(scope=scope)
    store = MagicMock()
    store.economics.return_value = {}
    store.pending.return_value = None
    with (
        patch("py_st.cli.auto_cmd.load_dotenv"),
        patch("py_st.cli.auto_cmd.find_dotenv", return_value=""),
        patch("py_st.cli.auto_cmd.os.environ", {"ST_TOKEN": "synthetic"}),
        patch("py_st.cli.auto_cmd.SpaceTradersClient"),
        patch("py_st.cli.auto_cmd.Intelligence", return_value=store),
        patch("py_st.cli.auto_cmd.Session", return_value=run),
        patch("py_st.cli.auto_cmd.pilot_run", side_effect=error),
    ):
        result = CliRunner().invoke(app, ["auto", "pilot", "X-A"])
    assert result.exit_code != 0
    assert "NEW budgets and fresh decisions" in result.output
    assert (
        "never replays recorded decisions or uncertain actions"
        in result.output
    )
    assert "secret" not in result.output
    if scope:
        assert "automation_runs" in result.output
        assert "auto report --scope r:a" in result.output
        assert "dashboard" in result.output
    else:
        assert "scope unavailable" in result.output
        assert "auto report --scope" not in result.output
    if isinstance(error, APIError):
        assert "Owner must update ST_TOKEN" in result.output
        assert result.exit_code == 1
    elif isinstance(error, SafetyStop | httpx.HTTPError):
        assert "Stopped:" in result.output
        assert result.exit_code == 1
    elif isinstance(error, sqlite3.Error):
        assert result.exception is error
    run.close.assert_called_once()
    store.close.assert_called_once()
