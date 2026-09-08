import copy
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.services.automation import SafetyStop, Session
from py_st.services.earning import earn_run
from py_st.services.intelligence import Intelligence


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
        for i in range(3)
    ]
    ships: list[dict[str, Any]] = [
        {
            "symbol": symbol,
            "frame": {"symbol": frame},
            "engine": {"speed": 30},
            "cargo": {"capacity": capacity, "units": 0, "inventory": []},
            "fuel": {"capacity": fuel, "current": fuel},
            "nav": {
                "systemSymbol": "X-A",
                "waypointSymbol": waypoints[location]["symbol"],
                "status": "IN_ORBIT",
                "flightMode": "CRUISE",
                "route": {
                    "destination": waypoints[location],
                    "arrival": datetime.now(UTC).isoformat(),
                },
            },
        }
        for symbol, frame, capacity, fuel, location in (
            ("H", "FRAME_FRIGATE", 40, 400, 1),
            ("P", "FRAME_PROBE", 0, 0, 0),
        )
    ]
    state: dict[str, Any] = {
        "agent": {"symbol": "a", "credits": 100000},
        "ships": ships,
        "contracts": [],
        "posts": [],
        "reads": [],
        "sparse": False,
        "stop_after": "",
        "unknown": False,
        "crash_price": False,
    }

    def request(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/my/agent":
            return copy.deepcopy(state["agent"])
        if path in ("/my/ships", "/my/contracts"):
            return copy.deepcopy(state[path.removeprefix("/my/")])
        if path == "/systems/X-A/waypoints":
            return copy.deepcopy(waypoints)
        if path.startswith("/my/ships/"):
            ship = next(s for s in ships if s["symbol"] == path.split("/")[3])
            if method == "GET":
                return copy.deepcopy(ship)
            state["posts"].append(path)
            body = kwargs.get("body") or {}
            action = path.split("/")[-1]
            if action in ("dock", "orbit"):
                ship["nav"]["status"] = (
                    "DOCKED" if action == "dock" else "IN_ORBIT"
                )
            elif action == "navigate":
                target = body["waypointSymbol"]
                ship["nav"].update(waypointSymbol=target, status="IN_ORBIT")
                ship["nav"]["route"]["destination"] = next(
                    w for w in waypoints if w["symbol"] == target
                )
            elif action in ("purchase", "sell"):
                units = body["units"]
                buying = action == "purchase"
                ship["cargo"].update(
                    units=units if buying else 0,
                    inventory=(
                        [{"symbol": "IRON", "units": units}] if buying else []
                    ),
                )
                state["agent"]["credits"] += units * (-100 if buying else 250)
            else:
                pytest.fail(f"Unexpected mutation {path}")
            if state["unknown"]:
                raise httpx.ReadTimeout("unknown")
            if action == state["stop_after"]:
                (tmp_path / "STOP").touch()
            return {}
        if path.endswith("/market"):
            key = path.split("/")[-2]
            state["reads"].append(key)
            present = any(s["nav"]["waypointSymbol"] == key for s in ships)
            goods = [
                {
                    "symbol": "IRON",
                    "purchasePrice": 100 if key.endswith("1") else 300,
                    "sellPrice": (
                        80
                        if key.endswith("1") or state["crash_price"]
                        else 250
                    ),
                    "tradeVolume": 40,
                },
                {
                    "symbol": "FUEL",
                    "purchasePrice": 72,
                    "sellPrice": 68,
                    "tradeVolume": 100,
                },
            ]
            return {
                "symbol": key,
                "tradeGoods": goods if present and not state["sparse"] else [],
            }
        return copy.deepcopy(
            next(w for w in waypoints if path.endswith(w["symbol"]))
        )

    client = MagicMock()
    client.status.return_value = {"resetDate": "r"}
    client.request.side_effect = request
    store = Intelligence(Path(":memory:"))
    run = Session(client, store, execute=True, root=tmp_path)
    state.update(run=run, store=store, client=client, root=tmp_path)
    with patch("py_st.services.automation.cache.clear_cache"):
        yield state
    run.close()
    store.close()


def test_discovery_hands_fresh_route_to_real_trade(
    world: dict[str, Any],
) -> None:
    # Act: no markets or waypoints were seeded in SQLite.
    result = earn_run(world["run"], "X-A", cycles=2)
    # Assert: discover buyer, then buy/sell without a manual route command.
    assert [d["kind"] for d in result["decisions"]] == ["discover", "trade"]
    assert world["agent"]["credits"] == 106000
    assert world["ships"][0]["cargo"]["units"] == 0
    assert world["posts"].count("/my/ships/P/navigate") == 1
    assert world["posts"].count("/my/ships/H/purchase") == 1
    assert not world["store"].pending("r:a")


@pytest.mark.parametrize("ready", [False, True])
def test_dry_run_only_gets_next_decision(
    world: dict[str, Any], ready: bool
) -> None:
    # Arrange
    world["run"].execute = False
    if ready:
        world["ships"][1]["nav"]["waypointSymbol"] = "X-A-2"
    # Act
    result = earn_run(world["run"], "X-A", cycles=5)
    # Assert
    assert result["status"] == "dry run"
    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["kind"] == ("trade" if ready else "discover")
    assert world["posts"] == []
    assert world["store"].latest("r:a", "position") == []


@pytest.mark.parametrize(
    "guard", ["stop", "deadline", "pending", "contract", "actions"]
)
def test_guards_before_mutations(world: dict[str, Any], guard: str) -> None:
    # Arrange
    run = world["run"]
    if guard == "stop":
        world["root"].joinpath("STOP").touch()
    elif guard == "deadline":
        run.deadline = 0
    elif guard == "pending":
        world["store"].begin_action("r:a", "/my/ships/H/purchase", {})
    elif guard == "contract":
        world["contracts"].append(
            {"id": "C", "accepted": True, "fulfilled": False}
        )
    else:
        run.remaining = 0
    # Act
    with pytest.raises(SafetyStop):
        earn_run(run, "X-A")
    # Assert
    assert world["posts"] == []


@pytest.mark.parametrize("stage", ["purchase", "sell"])
def test_restart_recovers_without_moving_observer(
    world: dict[str, Any], stage: str
) -> None:
    # Arrange
    world["stop_after"] = stage
    # Act
    with pytest.raises(SafetyStop, match="STOP"):
        earn_run(world["run"], "X-A", cycles=3)
    world["root"].joinpath("STOP").unlink()
    world["stop_after"] = ""
    moves = world["posts"].count("/my/ships/P/navigate")
    result = earn_run(world["run"], "X-A", cycles=5)
    # Assert
    assert result["status"] == "recovery only"
    assert world["posts"].count("/my/ships/P/navigate") == moves
    assert world["posts"].count("/my/ships/H/purchase") == 1
    assert world["agent"]["credits"] == 106000


def test_unknown_scout_outcome_blocks_reentry(world: dict[str, Any]) -> None:
    world["unknown"] = True
    with pytest.raises(httpx.ReadTimeout):
        earn_run(world["run"], "X-A")
    world["unknown"] = False
    with pytest.raises(SafetyStop, match="Pending"):
        earn_run(world["run"], "X-A")
    assert len(world["posts"]) == 1


def test_shared_action_budget_after_discovery(world: dict[str, Any]) -> None:
    world["run"].remaining = 1
    with pytest.raises(SafetyStop, match="Action budget"):
        earn_run(world["run"], "X-A", cycles=2)
    assert world["posts"] == ["/my/ships/P/navigate"]
    assert world["run"].remaining == 0


@pytest.mark.parametrize("change", ["fuel", "credits", "mode"])
def test_unready_route_does_not_spend(
    world: dict[str, Any], change: str
) -> None:
    earn_run(world["run"], "X-A", cycles=1)
    if change == "fuel":
        world["ships"][0]["fuel"]["current"] = 10
    elif change == "credits":
        world["agent"]["credits"] = 51000
    else:
        world["ships"][0]["nav"]["flightMode"] = "DRIFT"
    earn_run(world["run"], "X-A", cycles=2)
    assert world["posts"] == ["/my/ships/P/navigate"]


def test_buyer_deteriorates_after_ranking_before_purchase(
    world: dict[str, Any],
) -> None:
    earn_run(world["run"], "X-A", cycles=1)
    run: Session = world["run"]
    original = run.market
    buyer_reads = 0

    def market(key: str) -> dict[str, Any]:
        nonlocal buyer_reads
        if key == "X-A-2":
            buyer_reads += 1
            if buyer_reads >= 3:
                world["crash_price"] = True
        return original(key)

    with (
        patch.object(world["run"], "market", side_effect=market),
        pytest.raises(SafetyStop, match="Buyer quote"),
    ):
        earn_run(world["run"], "X-A", cycles=2)
    assert not any(p.endswith("/purchase") for p in world["posts"])


def test_recovery_dry_run_precedes_system_discovery(
    world: dict[str, Any],
) -> None:
    world["store"].observe(
        "r:a", "position", "trade:H", {"status": "open", "plan": {}}
    )
    world["run"].execute = False
    result = earn_run(world["run"], "X-OTHER")
    assert result["status"] == "recovery only"
    assert world["posts"] == world["reads"] == []


@pytest.mark.parametrize("keys", [("trade:H", "trade:P"), ("unknown",)])
def test_ambiguous_positions_do_not_move_observers(
    world: dict[str, Any], keys: tuple[str, ...]
) -> None:
    for key in keys:
        world["store"].observe("r:a", "position", key, {"status": "open"})
    with pytest.raises(SafetyStop, match="inspect recovery"):
        earn_run(world["run"], "X-A")
    assert world["posts"] == world["reads"] == []


def test_sparse_discovery_never_spends_or_revisits(
    world: dict[str, Any],
) -> None:
    world["sparse"] = True
    result = earn_run(world["run"], "X-A", cycles=5)
    assert result["status"] == "no ready routes or scout targets"
    assert not any(p.endswith("/purchase") for p in world["posts"])
    assert len(world["store"].latest("r:a", "scout_visit")) == 2


@pytest.mark.parametrize("change", ["sparse", "crash_price"])
def test_historical_profit_cannot_authorize_purchase(
    world: dict[str, Any], change: str
) -> None:
    earn_run(world["run"], "X-A", cycles=1)
    world[change] = True
    earn_run(world["run"], "X-A", cycles=1)
    assert not any(p.endswith("/purchase") for p in world["posts"])


@pytest.mark.parametrize("cycles", [0, 6])
def test_invalid_cycles_before_requests(
    world: dict[str, Any], cycles: int
) -> None:
    with pytest.raises(ValueError, match="Bounds"):
        earn_run(world["run"], "X-A", cycles=cycles)
    world["client"].request.assert_not_called()


@pytest.mark.parametrize("execute", [False, True])
def test_cli_bounded_options(execute: bool) -> None:
    with (
        patch("py_st.cli.auto_cmd.session") as session,
        patch("py_st.cli.auto_cmd.earn_run", return_value={}) as service,
    ):
        result = CliRunner().invoke(
            app,
            [
                "auto",
                "earn",
                "X-A",
                "--cycles",
                "2",
                *(["--execute"] if execute else []),
            ],
        )
    assert result.exit_code == 0, result.output
    session.assert_called_once_with(execute, 600, 30)
    service.assert_called_once_with(
        session.return_value.__enter__.return_value, "X-A", 2, 900
    )
