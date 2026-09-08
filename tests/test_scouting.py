import copy
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.services.automation import SafetyStop, Session
from py_st.services.intelligence import Intelligence
from py_st.services.scouting import scout_plan, scout_run

SCOPE = "r:a"


@pytest.fixture
def world(tmp_path: Path) -> Iterator[dict[str, Any]]:
    waypoints: list[dict[str, Any]] = [
        {
            "symbol": f"X-A-{i}",
            "systemSymbol": "X-A",
            "x": i * 10,
            "y": 0,
            "traits": [{"symbol": "MARKETPLACE"}] if i else [],
        }
        for i in range(4)
    ]
    ship: dict[str, Any] = {
        "symbol": "A-1",
        "frame": {"symbol": "FRAME_PROBE"},
        "fuel": {"capacity": 0, "current": 0},
        "cargo": {"capacity": 0, "units": 0},
        "nav": {
            "status": "DOCKED",
            "flightMode": "CRUISE",
            "systemSymbol": "X-A",
            "waypointSymbol": "X-A-0",
            "route": {
                "destination": waypoints[0],
                "arrival": datetime.now(UTC).isoformat(),
            },
        },
    }
    state: dict[str, Any] = {
        "ships": [ship],
        "waypoints": waypoints,
        "posts": [],
        "markets": [],
        "sparse": False,
        "stop_after": "",
        "uncertain": False,
        "hold_transit": False,
    }

    def request(method: str, path: str, **kwargs: Any) -> Any:
        active = (
            next(
                s for s in state["ships"] if s["symbol"] == path.split("/")[3]
            )
            if path.startswith("/my/ships/")
            else ship
        )
        if method == "POST":
            state["posts"].append((path, kwargs.get("body")))
            if path.endswith("/orbit"):
                active["nav"]["status"] = "IN_ORBIT"
            elif path.endswith("/navigate"):
                target = kwargs["body"]["waypointSymbol"]
                active["nav"]["status"] = "IN_TRANSIT"
                active["nav"]["waypointSymbol"] = target
                active["nav"]["route"]["destination"] = next(
                    w for w in waypoints if w["symbol"] == target
                )
            else:
                pytest.fail(f"Unexpected scout mutation: {path}")
            if state["uncertain"]:
                raise httpx.ReadTimeout("unknown outcome")
            if path.endswith("/" + state["stop_after"]):
                (tmp_path / "STOP").touch()
            return {"nav": copy.deepcopy(active["nav"])}
        if path == "/my/agent":
            return {"symbol": "a", "credits": 397940}
        if path == "/my/ships":
            return copy.deepcopy(state["ships"])
        if path == "/my/contracts":
            return []
        if path.startswith("/my/ships/"):
            if (
                active["nav"]["status"] == "IN_TRANSIT"
                and not state["hold_transit"]
            ):
                active["nav"]["status"] = "IN_ORBIT"
                if state["stop_after"] == "arrival":
                    (tmp_path / "STOP").touch()
            return copy.deepcopy(active)
        if path.endswith("/market"):
            target = path.split("/")[-2]
            state["markets"].append(target)
            if state["stop_after"] == "market":
                (tmp_path / "STOP").touch()
            return {
                "symbol": target,
                "tradeGoods": [] if state["sparse"] else [{"symbol": "IRON"}],
            }
        if path == "/systems/X-A/waypoints":
            return copy.deepcopy(waypoints)
        return copy.deepcopy(
            next(w for w in waypoints if path.endswith(w["symbol"]))
        )

    client = MagicMock()
    client.status.return_value = {"resetDate": "r"}
    client.request.side_effect = request
    store = Intelligence(tmp_path / "scout.db")
    run = Session(client, store, execute=True, root=tmp_path)
    state.update(run=run, store=store, client=client, root=tmp_path)
    with patch("py_st.services.automation.cache.clear_cache"):
        yield state
    run.close()
    store.close()


def plan(world: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return scout_plan(
        world["store"],
        SCOPE,
        "X-A",
        world["ships"],
        world["waypoints"],
        **kwargs,
    )


def quote(
    world: dict[str, Any], target: str, age: int, sparse: bool = False
) -> None:
    store = world["store"]
    store.observe(
        SCOPE, "market", target, {"tradeGoods": [] if sparse else [{}]}
    )
    with store.db:
        store.db.execute(
            "UPDATE observations SET observed_at=? "
            "WHERE id=(SELECT MAX(id) FROM observations)",
            ((datetime.now(UTC) - timedelta(seconds=age)).isoformat(),),
        )


def test_selection_unknown_then_oldest_then_distance(
    world: dict[str, Any],
) -> None:
    # Arrange: newer sparse advertisements must not refresh old prices.
    quote(world, "X-A-1", 1800)
    quote(world, "X-A-2", 3600)
    quote(world, "X-A-2", 0, sparse=True)
    # Act
    result = plan(world)
    # Assert
    assert [c["target"] for c in result["candidates"]] == [
        "X-A-3",
        "X-A-2",
        "X-A-1",
    ]
    assert result["candidates"][1]["age_seconds"] >= 3600
    assert result["next"]["actions"] == 2


def test_freshness_scope_and_exact_boundary(world: dict[str, Any]) -> None:
    # Arrange
    quote(world, "X-A-1", 0)
    quote(world, "X-A-2", 900)
    world["store"].observe("new:a", "market", "X-A-3", {"tradeGoods": [{}]})
    # Act
    result = plan(world)
    # Assert
    assert [c["target"] for c in result["candidates"]] == ["X-A-3", "X-A-2"]
    assert result["skipped"] == [
        {"target": "X-A-1", "reason": "fresh detailed prices"}
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("fuel", {"capacity": 1}),
        ("fuel", {}),
        ("frame", {"symbol": "FRAME_DRONE"}),
        ("cargo", {"units": 1}),
        ("flightMode", "DRIFT"),
        ("flightMode", "BURN"),
        ("systemSymbol", "X-B"),
        ("status", "UNKNOWN"),
    ],
)
def test_ineligible_ships_never_move(
    world: dict[str, Any], field: str, value: Any
) -> None:
    # Arrange
    ship = world["ships"][0]
    target = ship if field in ("fuel", "frame", "cargo") else ship["nav"]
    target[field] = value
    # Act
    result = plan(world)
    # Assert
    assert result["next"] is None
    assert result["eligible_probes"] == []
    assert world["posts"] == []


def test_multiple_probes_and_foreign_waypoints(world: dict[str, Any]) -> None:
    # Arrange
    second = copy.deepcopy(world["ships"][0])
    second["symbol"] = "A-2"
    second["nav"].update(status="IN_ORBIT", waypointSymbol="X-A-3")
    second["nav"]["route"]["destination"] = world["waypoints"][3]
    world["ships"].append(second)
    world["waypoints"].append(world["waypoints"][1] | {"symbol": "X-B-1"})
    # Act
    result = plan(world)
    # Assert
    assert result["next"]["ship"] == "A-2"
    assert result["next"]["actions"] == 0
    assert all(c["target"].startswith("X-A-") for c in result["candidates"])


def test_dry_run_has_useful_plan_and_no_mutations(
    world: dict[str, Any],
) -> None:
    # Arrange
    world["run"].execute = False
    # Act
    result = scout_run(world["run"], "X-A")
    # Assert
    assert result["status"] == "dry run"
    assert result["plan"]["next"]["target"] == "X-A-1"
    assert world["posts"] == world["markets"] == []
    assert world["store"].latest(SCOPE, "plan")


def test_bounded_broad_scout_and_completed_resume(
    world: dict[str, Any],
) -> None:
    # Act
    result = scout_run(world["run"], "X-A", attempts=2)
    # Assert
    assert result["status"] == "attempt limit"
    assert world["markets"] == ["X-A-1", "X-A-2"]
    assert len(world["posts"]) == 3
    assert len(world["store"].latest(SCOPE, "market", priced_only=True)) == 2
    scout_run(world["run"], "X-A", attempts=2)
    assert world["markets"] == ["X-A-1", "X-A-2", "X-A-3"]
    assert len(world["posts"]) == 4
    assert all(
        a["status"] == "succeeded" for a in world["store"].actions(SCOPE)
    )


@pytest.mark.parametrize("stage", ["orbit", "navigate", "arrival", "market"])
def test_restart_uses_observed_state_not_old_plan(
    world: dict[str, Any], stage: str
) -> None:
    # Arrange
    world["stop_after"] = stage
    # Act
    with pytest.raises(SafetyStop, match="STOP"):
        scout_run(world["run"], "X-A", attempts=1)
    world["run"].close()
    world["root"].joinpath("STOP").unlink()
    world["stop_after"] = ""
    world["run"] = Session(
        world["client"], world["store"], execute=True, root=world["root"]
    )
    scout_run(world["run"], "X-A", attempts=1)
    # Assert: confirmed orbit/navigation is never replayed for the old leg.
    assert sum(p.endswith("/orbit") for p, _ in world["posts"]) == 1
    assert (
        sum(b == {"waypointSymbol": "X-A-1"} for _, b in world["posts"]) == 1
    )
    assert world["markets"].count("X-A-1") == 1
    assert not world["store"].pending(SCOPE)
    world["run"].close()


def test_sparse_visit_bounded_and_cooldown_survives_restart(
    world: dict[str, Any],
) -> None:
    # Arrange
    world["sparse"] = True
    # Act
    scout_run(world["run"], "X-A", attempts=4)
    scout_run(world["run"], "X-A", attempts=4)
    # Assert
    assert world["markets"] == ["X-A-1", "X-A-2", "X-A-3"]
    assert world["store"].latest(SCOPE, "market", priced_only=True) == []
    assert len(world["store"].latest(SCOPE, "scout_visit")) == 3
    with world["store"].db:
        world["store"].db.execute(
            "UPDATE observations SET observed_at='2000-01-01T00:00:00+00:00'"
        )
    assert plan(world)["next"]["target"] == "X-A-3"


@pytest.mark.parametrize(
    "guard", ["stop", "deadline", "actions", "pending", "position"]
)
def test_scout_safety_guards(world: dict[str, Any], guard: str) -> None:
    # Arrange
    run = world["run"]
    if guard == "stop":
        world["root"].joinpath("STOP").touch()
    elif guard == "deadline":
        run.deadline = 0
    elif guard == "actions":
        run.remaining = 1
    elif guard == "pending":
        world["store"].begin_action(SCOPE, "/my/ships/A-1/navigate", {})
    else:
        world["store"].observe(
            SCOPE, "position", "trade:A-2", {"status": "open"}
        )
    # Act
    with pytest.raises(SafetyStop):
        scout_run(run, "X-A")
    # Assert
    assert world["posts"] == world["markets"] == []
    if guard in ("stop", "deadline"):
        world["client"].status.assert_not_called()
        world["client"].request.assert_not_called()


def test_uncertain_navigation_blocks_even_if_ship_arrived(
    world: dict[str, Any],
) -> None:
    # Arrange
    world["ships"][0]["nav"]["status"] = "IN_ORBIT"
    world["uncertain"] = True
    # Act
    with pytest.raises(httpx.ReadTimeout):
        scout_run(world["run"], "X-A")
    world["uncertain"] = False
    with pytest.raises(SafetyStop, match="Pending"):
        scout_run(world["run"], "X-A")
    # Assert
    assert len(world["posts"]) == 1
    assert world["store"].pending(SCOPE)
    assert world["markets"] == []


@pytest.mark.parametrize(
    "args",
    [{"attempts": 0}, {"attempts": 101}, {"max_age": 0}, {"max_age": 86401}],
)
def test_invalid_bounds_before_requests(
    world: dict[str, Any], args: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="Bounds"):
        scout_run(world["run"], "X-A", **args)
    world["client"].request.assert_not_called()


def test_offline_cli_is_read_only_without_token_or_session(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    store = world["store"]
    for ship in world["ships"]:
        store.observe(SCOPE, "ship", ship["symbol"], ship)
    for waypoint in world["waypoints"]:
        store.observe(SCOPE, "waypoint", waypoint["symbol"], waypoint)
    before = store.db.serialize()
    monkeypatch.chdir(world["root"])
    monkeypatch.delenv("ST_TOKEN", raising=False)
    world["root"].joinpath("STOP").touch()
    # Act
    with patch(
        "py_st.cli.auto_cmd.session",
        side_effect=AssertionError("live session"),
    ):
        result = CliRunner().invoke(
            app,
            [
                "auto",
                "scout",
                "X-A",
                "--offline",
                "--scope",
                SCOPE,
                "--database",
                "scout.db",
            ],
        )
    # Assert
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["plan"]["next"]["target"] == "X-A-1"
    assert before == store.db.serialize()
    assert world["root"].joinpath("STOP").exists()
    reader = Intelligence(world["root"] / "scout.db", read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.observe(SCOPE, "test", "test", {})
    finally:
        reader.close()


@pytest.mark.parametrize(
    "options",
    [
        ["--offline"],
        ["--offline", "--scope", SCOPE, "--execute"],
        ["--attempts", "0"],
        ["--seconds", "0"],
        ["--actions", "201"],
        ["--scope", SCOPE],
    ],
)
def test_cli_rejects_invalid_options_before_session(
    options: list[str],
) -> None:
    with patch(
        "py_st.cli.auto_cmd.session",
        side_effect=AssertionError("live session"),
    ):
        result = CliRunner().invoke(app, ["auto", "scout", "X-A", *options])
    assert result.exit_code == 2, result.output


@pytest.mark.parametrize("interruption", ["stop", "deadline", "interrupt"])
def test_transit_wait_is_interruptible_and_never_redirected(
    world: dict[str, Any], interruption: str
) -> None:
    # Arrange: an existing flight to a stale market beats new discovery.
    ship = world["ships"][0]
    ship["nav"].update(status="IN_TRANSIT", waypointSymbol="X-A-3")
    ship["nav"]["route"]["destination"] = world["waypoints"][3]
    quote(world, "X-A-3", 1800)
    world["hold_transit"] = True
    run = world["run"]
    original_wait = run.wait

    def wait(seconds: float) -> None:
        if interruption == "interrupt":
            raise KeyboardInterrupt()
        if interruption == "stop":
            world["root"].joinpath("STOP").touch()
        else:
            run.deadline = 0
        original_wait(0)

    # Act
    with (
        patch.object(run, "wait", side_effect=wait),
        pytest.raises((SafetyStop, KeyboardInterrupt)),
    ):
        scout_run(run, "X-A", attempts=1)
    # Assert
    saved = world["store"].latest(SCOPE, "plan")[0]["data"]
    assert saved["next"]["reason"] == "resume observed transit"
    assert world["posts"] == world["markets"] == []
    assert not world["store"].pending(SCOPE)


def test_multiple_probes_execute_without_duplicate_targets(
    world: dict[str, Any],
) -> None:
    # Arrange
    second = copy.deepcopy(world["ships"][0])
    second["symbol"] = "A-2"
    second["nav"].update(status="IN_ORBIT", waypointSymbol="X-A-3")
    second["nav"]["route"]["destination"] = world["waypoints"][3]
    world["ships"].append(second)
    # Act
    result = scout_run(world["run"], "X-A", attempts=3)
    # Assert
    assert [(v["ship"], v["target"]) for v in result["visits"]] == [
        ("A-2", "X-A-3"),
        ("A-1", "X-A-1"),
        ("A-1", "X-A-2"),
    ]
    assert len(set(world["markets"])) == 3
    assert len(world["posts"]) == 3


def test_manual_relocation_ignores_persisted_plan(
    world: dict[str, Any],
) -> None:
    # Arrange
    world["run"].execute = False
    scout_run(world["run"], "X-A")
    ship = world["ships"][0]
    ship["nav"].update(status="IN_ORBIT", waypointSymbol="X-A-3")
    ship["nav"]["route"]["destination"] = world["waypoints"][3]
    world["run"].execute = True
    # Act
    scout_run(world["run"], "X-A", attempts=1)
    # Assert
    assert world["markets"] == ["X-A-3"]
    assert world["posts"] == []


def test_changed_probe_capability_stops_before_navigation(
    world: dict[str, Any],
) -> None:
    # Arrange
    ship = copy.deepcopy(world["ships"][0])
    ship["fuel"]["capacity"] = 100
    # Act
    with (
        patch.object(world["run"], "ship", return_value=ship),
        pytest.raises(SafetyStop, match="state changed"),
    ):
        scout_run(world["run"], "X-A")
    # Assert
    assert world["posts"] == world["markets"] == []


def test_wrong_arrival_is_not_recorded_as_visit(world: dict[str, Any]) -> None:
    # Act
    with (
        patch.object(world["run"], "navigate", return_value=world["ships"][0]),
        pytest.raises(SafetyStop, match="arrival"),
    ):
        scout_run(world["run"], "X-A")
    # Assert
    assert world["markets"] == []
    assert world["store"].latest(SCOPE, "scout_visit") == []


def test_action_bound_between_legs_preserves_observed_progress(
    world: dict[str, Any],
) -> None:
    # Arrange
    world["run"].remaining = 2
    # Act
    with pytest.raises(SafetyStop, match="Action budget"):
        scout_run(world["run"], "X-A", attempts=3)
    # Assert
    assert world["markets"] == ["X-A-1"]
    assert len(world["posts"]) == 2
    assert not world["store"].pending(SCOPE)


@pytest.mark.parametrize("execute", [False, True])
def test_cli_passes_bounded_options_and_defaults_to_dry_run(
    execute: bool,
) -> None:
    # Arrange
    options = ["--execute"] if execute else []
    # Act
    with (
        patch("py_st.cli.auto_cmd.session") as session,
        patch(
            "py_st.cli.auto_cmd.scout_run", return_value={"status": "mock"}
        ) as service,
    ):
        result = CliRunner().invoke(
            app, ["auto", "scout", "X-A", "--attempts", "2", *options]
        )
    # Assert
    assert result.exit_code == 0, result.output
    session.assert_called_once_with(execute, 600, 8)
    service.assert_called_once_with(
        session.return_value.__enter__.return_value, "X-A", 2, 900
    )


def test_offline_missing_database_does_not_create_one(tmp_path: Path) -> None:
    # Act
    result = CliRunner().invoke(
        app,
        [
            "auto",
            "scout",
            "X-A",
            "--offline",
            "--scope",
            SCOPE,
            "--database",
            str(tmp_path / "missing" / "db"),
        ],
    )
    # Assert
    assert result.exit_code == 2
    assert not (tmp_path / "missing").exists()
