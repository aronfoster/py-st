import sqlite3
from copy import deepcopy
from typing import Any
from unittest.mock import patch

import pytest
from click import unstyle
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.services.automation import SafetyStop, Session
from py_st.services.pilot import pilot_run
from py_st.services.strategies import contract_run
from tests import test_local_procurement

local = test_local_procurement.local


def intent(data: dict[str, Any], actions: int = 0) -> Session:
    data["run"].remaining = actions
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(data["run"], "S", "C")
    return test_local_procurement.restart(data)


@pytest.mark.parametrize("actions", range(13))
def test_new_pilot_recovers_interrupted_multigood(
    local: dict[str, Any], actions: int
) -> None:
    # Arrange: include a persisted, unaccepted intent with zero prior actions.
    run = intent(local, actions)
    original = local["store"].latest("r:A", "position")[0]["data"]["plan"]
    deadline, lock, budget = run.deadline, run.lock, run.remaining

    # Act: account-wide recovery ignores the requested earning system.
    with patch("py_st.services.pilot.earn_run") as earn:
        result = pilot_run(run, "X-OTHER", steps=1, recover_contracts=True)

    # Assert: all goods complete exactly once under the new shared Session.
    earn.assert_not_called()
    assert local["contract"]["fulfilled"]
    assert len(local["posts"]) == 13
    assert local["agent"]["credits"] == 128_900
    assert result["completed_steps"] == 1
    assert result["last_decision"]["kind"] == "contract recovery"
    assert result["last_decision"]["result"]["plan"] == original
    assert result["actions_used"] == 13 - actions
    assert run.remaining == budget - (13 - actions)
    assert run.deadline == deadline and run.lock is lock
    assert result["recover_contracts"] is True
    assert "--recover-contracts" in result["resume_command"]
    assert local["store"].latest("r:A", "automation_run")[0]["data"] == result
    assert local["store"].latest("r:A", "position")[0]["data"]["status"] == (
        "closed"
    )
    assert not local["store"].pending("r:A")


@pytest.mark.parametrize("actions", [0, 3, 12])
def test_dryrun_previews_one_without_position_writes(
    local: dict[str, Any], actions: int
) -> None:
    run = intent(local, actions)
    run.execute = False
    positions = local["store"].latest("r:A", "position")
    posts = deepcopy(local["posts"])
    with patch("py_st.services.pilot.earn_run") as earn:
        result = pilot_run(run, "X-A", steps=100, recover_contracts=True)
    earn.assert_not_called()
    assert result["completed_steps"] == 1
    assert result["outcome"] == "dry run"
    assert result["actions_used"] == 0
    assert "--execute" not in result["resume_command"]
    assert local["posts"] == posts
    assert local["store"].latest("r:A", "position") == positions


@pytest.mark.parametrize("actions", [0, 3])
def test_default_still_blocks_procurement(
    local: dict[str, Any], actions: int
) -> None:
    run = intent(local, actions)
    posts = deepcopy(local["posts"])
    with pytest.raises(SafetyStop):
        pilot_run(run, "X-A")
    record = local["store"].latest("r:A", "automation_run")[0]["data"]
    assert record["recover_contracts"] is False
    assert "--recover-contracts" not in record["resume_command"]
    assert local["posts"] == posts


@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        "multiple",
        "trade",
        "unknown",
        "status",
        "missing_status",
        "pending",
        "old_pending",
        "other_contract",
        "duplicate_contract",
        "missing_contract",
        "missing_ship",
        "contract_status",
    ],
)
def test_ambiguous_state_never_dispatches(
    local: dict[str, Any], execute: bool, change: str
) -> None:
    run = intent(local)
    run.execute = execute
    store = local["store"]
    position = store.latest("r:A", "position")[0]["data"]
    if change in ("multiple", "trade", "unknown"):
        key = {"multiple": "procurement:D", "trade": "trade:S"}.get(
            change, "unknown:S"
        )
        store.observe("r:A", "position", key, position)
    elif change in ("status", "missing_status"):
        position["status"] = "unknown"
        if change == "missing_status":
            position.pop("status")
        store.observe("r:A", "position", "procurement:C", position)
    elif change in ("pending", "old_pending"):
        store.begin_action("r:A", "/my/contracts/C/accept", {})
        if change == "old_pending":
            for _ in range(201):
                action = store.begin_action("r:A", "/my/ships/S/dock", {})
                store.finish_action(action, "succeeded", {})
    elif change == "other_contract":
        local["contracts"].append(
            local["contract"] | {"id": "D", "accepted": True}
        )
    elif change == "duplicate_contract":
        local["contracts"].append(deepcopy(local["contract"]))
    elif change == "missing_contract":
        local["contracts"].clear()
    elif change == "missing_ship":
        local["ship"]["symbol"] = "OTHER"
    else:
        local["contract"]["accepted"] = "unknown"
    positions = store.latest("r:A", "position")
    with pytest.raises(SafetyStop):
        pilot_run(run, "X-A", recover_contracts=True)
    assert not local["posts"]
    assert store.latest("r:A", "position") == positions


@pytest.mark.parametrize("field", ["ship", "source", "contract"])
@pytest.mark.parametrize("value", [None, "", " ", 42, True, [], {}])
def test_invalid_original_identity(
    local: dict[str, Any], field: str, value: Any
) -> None:
    run = intent(local)
    position = local["store"].latest("r:A", "position")[0]["data"]
    position["plan"][field] = value
    local["store"].observe("r:A", "position", "procurement:C", position)
    with pytest.raises(SafetyStop, match="identity"):
        pilot_run(run, "X-A", recover_contracts=True)
    assert not local["posts"]


@pytest.mark.parametrize("plan", [None, [], {}, {"contract": "OTHER"}])
def test_invalid_original_plan(local: dict[str, Any], plan: Any) -> None:
    run = intent(local)
    position = local["store"].latest("r:A", "position")[0]["data"]
    position["plan"] = plan
    local["store"].observe("r:A", "position", "procurement:C", position)
    with pytest.raises(SafetyStop, match="identity"):
        pilot_run(run, "X-A", recover_contracts=True)
    assert not local["posts"]


def test_key_must_match_original_contract(local: dict[str, Any]) -> None:
    run = intent(local)
    position = local["store"].latest("r:A", "position")[0]["data"]
    position["plan"]["contract"] = "OTHER"
    local["store"].observe("r:A", "position", "procurement:C", position)
    with pytest.raises(SafetyStop, match="identity"):
        pilot_run(run, "X-A", recover_contracts=True)
    assert not local["posts"]


def test_completed_recovery_next_step_earns_without_new_contracts(
    local: dict[str, Any],
) -> None:
    run = intent(local, 12)
    deadline, lock = run.deadline, run.lock
    refresh = run.refresh
    reads = 0

    def fresh() -> dict[str, Any]:
        nonlocal reads
        reads += 1
        return refresh()

    def earn(actual: Session, system: str, **kwargs: Any) -> dict[str, Any]:
        assert actual is run and actual.lock is lock
        assert actual.deadline == deadline
        assert reads >= 2 and local["contract"]["fulfilled"]
        assert actual.remaining == 29
        actual.remaining -= 1
        return {"status": "cycle limit"}

    with (
        patch.object(run, "refresh", side_effect=fresh),
        patch("py_st.services.pilot.earn_run", side_effect=earn) as earning,
    ):
        result = pilot_run(run, "X-A", steps=2, recover_contracts=True)
    earning.assert_called_once_with(
        run, "X-A", cycles=1, max_age=900, reposition=False
    )
    assert result["completed_steps"] == 2
    assert result["actions_used"] == 2
    assert len(local["posts"]) == 13


def test_offline_plan_does_not_authorize_recovery(
    local: dict[str, Any],
) -> None:
    run = local["run"]
    run.refresh()
    local["store"].observe(
        "r:A",
        "plan",
        "procurement:C",
        {"ship": "S", "source": "X-A-M", "contract": "C"},
    )
    with (
        patch("py_st.services.pilot.contract_run") as recover,
        patch(
            "py_st.services.pilot.earn_run",
            return_value={"status": "cycle limit"},
        ) as earn,
    ):
        pilot_run(run, "X-A", steps=1, recover_contracts=True)
    recover.assert_not_called()
    earn.assert_called_once()
    assert not local["posts"]


def test_cli_explicit_recovery_and_help() -> None:
    with (
        patch("py_st.cli.auto_cmd.session") as session,
        patch("py_st.cli.auto_cmd.pilot_run", return_value={}) as pilot,
    ):
        result = CliRunner().invoke(
            app, ["auto", "pilot", "X-A", "--execute", "--recover-contracts"]
        )
        help_result = CliRunner().invoke(
            app,
            ["auto", "pilot", "--help"],
            env={"COLUMNS": "240", "FORCE_COLOR": "1"},
        )
    assert result.exit_code == help_result.exit_code == 0
    session.assert_called_once_with(True, 3600, 100)
    pilot.assert_called_once_with(
        session.return_value.__enter__.return_value,
        "X-A",
        10,
        900,
        reposition=False,
        recover_contracts=True,
    )
    text = " ".join(
        unstyle(help_result.output).replace(chr(0x2502), " ").split()
    )
    assert "--recover-contracts" in text
    assert "--execute" in text
    assert "unaccepted intent" in text
    assert "never selects new offers or negotiates" in text


@pytest.mark.parametrize("budget", ["actions", "deadline"])
def test_recovery_cannot_reset_budget_for_next_step(
    local: dict[str, Any], budget: str
) -> None:
    run = intent(local, 12)
    run.remaining = 1
    request = local["client"].request.side_effect

    def dispatch(method: str, path: str, **kwargs: Any) -> Any:
        result = request(method, path, **kwargs)
        if budget == "deadline" and path.endswith("/fulfill"):
            run.deadline = 0
        return result

    local["client"].request.side_effect = dispatch
    with (
        patch("py_st.services.pilot.earn_run") as earn,
        pytest.raises(SafetyStop, match="budget"),
    ):
        pilot_run(run, "X-A", steps=2, recover_contracts=True)
    earn.assert_not_called()
    assert len(local["posts"]) == 13
    assert run.remaining == 0
    record = local["store"].latest("r:A", "automation_run")[0]["data"]
    assert record["status"] == "stopped"
    assert record["actions_used"] == 1


def test_unknown_recovery_is_never_replayed(local: dict[str, Any]) -> None:
    run = intent(local)
    local["unknown"] = "accept"
    with pytest.raises(TimeoutError):
        pilot_run(run, "X-A", recover_contracts=True)
    record = local["store"].latest("r:A", "automation_run")[0]["data"]
    assert record["status"] == "failed"
    run = test_local_procurement.restart(local)
    with pytest.raises(SafetyStop, match="Pending"):
        pilot_run(run, "X-A", recover_contracts=True)
    assert [a for a, _ in local["posts"]] == ["accept"]
    assert local["store"].pending("r:A")


def test_recovery_exception_survives_terminal_storage_failure(
    local: dict[str, Any],
) -> None:
    run = intent(local)
    observe = local["store"].observe
    error = KeyboardInterrupt()

    def persist(
        scope: str, kind: str, key: str, data: Any, *args: Any
    ) -> None:
        if kind == "automation_run" and data["status"] != "running":
            raise sqlite3.OperationalError("terminal failure")
        observe(scope, kind, key, data, *args)

    with (
        patch.object(local["store"], "observe", side_effect=persist),
        patch("py_st.services.pilot.contract_run", side_effect=error),
        pytest.raises(KeyboardInterrupt) as caught,
    ):
        pilot_run(run, "X-A", recover_contracts=True)
    assert caught.value is error
    assert not local["posts"]
