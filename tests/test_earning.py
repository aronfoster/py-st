import copy
import math
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
from py_st.services.strategies import refuel_run, trade_run


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
        "fuel_price": 72,
        "fuel_volume": 100,
        "seller_price": 100,
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
            result = {}
            if action in ("dock", "orbit"):
                ship["nav"]["status"] = (
                    "DOCKED" if action == "dock" else "IN_ORBIT"
                )
            elif action == "navigate":
                target = body["waypointSymbol"]
                origin = next(
                    w
                    for w in waypoints
                    if w["symbol"] == ship["nav"]["waypointSymbol"]
                )
                destination = next(
                    w for w in waypoints if w["symbol"] == target
                )
                if ship["fuel"]["capacity"]:
                    consumed = max(
                        1,
                        round(
                            math.hypot(
                                origin["x"] - destination["x"],
                                origin["y"] - destination["y"],
                            )
                        ),
                    )
                    assert ship["fuel"]["current"] >= consumed
                    ship["fuel"]["current"] -= consumed
                ship["nav"].update(waypointSymbol=target, status="IN_ORBIT")
                ship["nav"]["route"]["destination"] = destination
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
            elif action == "refuel":
                cost = (
                    math.ceil(
                        (ship["fuel"]["capacity"] - ship["fuel"]["current"])
                        / 100
                    )
                    * state["fuel_price"]
                )
                ship["fuel"]["current"] = ship["fuel"]["capacity"]
                state["agent"]["credits"] -= cost
                result = {
                    "agent": copy.deepcopy(state["agent"]),
                    "fuel": copy.deepcopy(ship["fuel"]),
                    "transaction": {"totalPrice": cost},
                }
            else:
                pytest.fail(f"Unexpected mutation {path}")
            if state["unknown"]:
                raise httpx.ReadTimeout("unknown")
            if action == state["stop_after"]:
                (tmp_path / "STOP").touch()
            return result
        if path.endswith("/market"):
            key = path.split("/")[-2]
            state["reads"].append(key)
            present = any(s["nav"]["waypointSymbol"] == key for s in ships)
            goods = [
                {
                    "symbol": "IRON",
                    "purchasePrice": (
                        state["seller_price"] if key.endswith("1") else 300
                    ),
                    "sellPrice": (
                        80
                        if key.endswith("1") or state["crash_price"]
                        else 250
                    ),
                    "tradeVolume": 40,
                },
                {
                    "symbol": "FUEL",
                    "purchasePrice": state["fuel_price"],
                    "sellPrice": 68,
                    "tradeVolume": state["fuel_volume"],
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
    state.update(
        run=run, store=store, client=client, root=tmp_path, waypoints=waypoints
    )
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
        world["ships"][0]["fuel"]["capacity"] = 30
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

    position = world["store"].latest(run.scope, "position")[0]["data"]
    assert position["status"] == "closed"
    assert position["bought"] is False
    assert position["purchase_dispatched"] is False
    assert position["cancellation_reason"] == (
        "Buyer quote no longer supports the trade"
    )
    assert not world["store"].pending(run.scope)

    # A new Session must replan, not recover/replay the cancelled route.
    run.close()
    restarted = Session(
        world["client"], world["store"], execute=True, root=world["root"]
    )
    try:
        result = earn_run(restarted, "X-A", cycles=1)
    finally:
        restarted.close()
    assert result["decisions"][0]["kind"] == "discover"
    assert not any(p.endswith("/purchase") for p in world["posts"])
    assert world["store"].latest(run.scope, "position")[0]["data"] == position


@pytest.mark.parametrize("guard", ["stop", "pending", "read_stop", "timeout"])
def test_fresh_intent_survives_non_quote_stops(
    world: dict[str, Any], guard: str
) -> None:
    # Arrange: interrupt the final buyer observation, after intent storage.
    world["ships"][1]["nav"]["waypointSymbol"] = "X-A-2"
    run: Session = world["run"]
    original = run.market
    buyer_reads = 0

    def market(key: str) -> dict[str, Any]:
        nonlocal buyer_reads
        quote = original(key)
        if key == "X-A-2":
            buyer_reads += 1
            if buyer_reads == 2:
                if guard == "read_stop":
                    raise SafetyStop("observation interrupted")
                if guard == "timeout":
                    raise httpx.ReadTimeout("observation uncertain")
                quote["tradeGoods"][0]["sellPrice"] = 1
                if guard == "stop":
                    world["root"].joinpath("STOP").touch()
                else:
                    world["store"].begin_action(
                        run.scope, "/my/ships/H/purchase", {}
                    )
        return quote

    # Act
    with (
        patch.object(run, "market", side_effect=market),
        pytest.raises(
            httpx.ReadTimeout if guard == "timeout" else SafetyStop,
            match={
                "stop": "STOP",
                "pending": "Buyer quote",
                "read_stop": "observation interrupted",
                "timeout": "observation uncertain",
            }[guard],
        ),
    ):
        trade_run(run, "H", "X-A-1", "X-A-2", "IRON", require_source=True)
    # Assert
    position = world["store"].latest(run.scope, "position")[0]["data"]
    assert position["status"] == "open"
    assert position["bought"] is False
    assert "cancellation_reason" not in position
    assert "purchase_dispatched" not in position
    assert bool(world["store"].pending(run.scope)) is (guard == "pending")
    assert not any(p.endswith("/purchase") for p in world["posts"])


def test_uncertain_purchase_keeps_intent_and_pending_on_restart(
    world: dict[str, Any],
) -> None:
    # Arrange: purchase takes effect but the response is lost.
    world["ships"][0]["nav"]["status"] = "DOCKED"
    world["ships"][1]["nav"]["waypointSymbol"] = "X-A-2"
    world["unknown"] = True
    run: Session = world["run"]
    # Act
    with pytest.raises(httpx.ReadTimeout):
        earn_run(run, "X-A", cycles=1)
    position = world["store"].latest(run.scope, "position")[0]["data"]
    pending = world["store"].pending(run.scope)
    world["unknown"] = False
    run.close()
    restarted = Session(
        world["client"], world["store"], execute=True, root=world["root"]
    )
    try:
        with pytest.raises(SafetyStop, match="Pending"):
            earn_run(restarted, "X-A", cycles=1)
    finally:
        restarted.close()
    # Assert: bought=False is not evidence that nothing was purchased.
    assert position["status"] == "open"
    assert position["bought"] is False
    assert "cancellation_reason" not in position
    assert "purchase_dispatched" not in position
    assert world["ships"][0]["cargo"]["units"] == 40
    assert pending and world["store"].pending(run.scope) == pending
    assert world["store"].latest(run.scope, "position")[0]["data"] == position
    assert world["posts"] == ["/my/ships/H/purchase"]


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


@pytest.fixture
def low_fuel(world: dict[str, Any]) -> dict[str, Any]:
    world["ships"][0]["fuel"]["current"] = 10
    world["ships"][1]["nav"]["waypointSymbol"] = "X-A-2"
    return world


@pytest.mark.parametrize("execute", [False, True])
def test_manual_trade_away_source_dry_run_then_execution(
    world: dict[str, Any], execute: bool
) -> None:
    # Arrange: enough fuel to approach, but not to run the trade unrefueled.
    ship = world["ships"][0]
    ship["nav"]["waypointSymbol"] = "X-A-0"
    ship["nav"]["route"]["destination"] = {"x": 0, "y": 0}
    ship["fuel"]["current"] = 30
    world["ships"][1]["nav"]["waypointSymbol"] = "X-A-2"
    observer = copy.deepcopy(world["ships"][1])
    observer["symbol"] = "P2"
    observer["nav"]["waypointSymbol"] = "X-A-1"
    world["ships"].append(observer)
    world["run"].execute = execute

    # Act
    result = trade_run(world["run"], "H", "X-A-1", "X-A-2", "IRON")

    # Assert
    if execute:
        assert result["completed_cycles"] == 1
        assert world["posts"].count("/my/ships/H/navigate") == 2
        assert world["posts"].count("/my/ships/H/refuel") == 1
        assert world["posts"].index("/my/ships/H/navigate") < world[
            "posts"
        ].index("/my/ships/H/refuel")
        assert ship["fuel"]["current"] == 390
        assert world["agent"]["credits"] == 105712
    else:
        assert result["feasible"]
        assert result["required_fuel"] == 40
        assert "refill" not in result
        assert "not modeled" in result["note"]
        assert ship["fuel"]["current"] == 30
        assert world["posts"] == []
        assert all(
            call.args[0] == "GET"
            for call in world["client"].request.call_args_list
        )


@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize("credits", [100000, 55620])
def test_earn_funded_local_refill(
    low_fuel: dict[str, Any], execute: bool, credits: int
) -> None:
    low_fuel["run"].execute = execute
    low_fuel["agent"]["credits"] = credits
    result = earn_run(low_fuel["run"], "X-A", cycles=1)
    decision = result["decisions"][0]
    assert decision["kind"] == "trade"
    assert not decision["selected"]["fuel_ready"]
    assert decision["selected"]["required_fuel"] == 40
    assert decision["selected"]["refill"]["maximum_estimated_cost"] == 348
    if execute:
        assert low_fuel["agent"]["credits"] == credits + 5712
        assert low_fuel["posts"].count("/my/ships/H/refuel") == 1
        assert low_fuel["posts"].count("/my/ships/H/purchase") == 1
        assert not low_fuel["store"].pending("r:a")
    else:
        assert decision["result"]["refill"]["maximum_estimated_cost"] == 348
        assert low_fuel["posts"] == []
        assert low_fuel["store"].latest("r:a", "position") == []
        assert all(
            call.args[0] == "GET"
            for call in low_fuel["client"].request.call_args_list
        )


@pytest.mark.parametrize("ready", [False, True])
def test_earn_exhausts_ready_then_funded_candidates(
    low_fuel: dict[str, Any], ready: bool
) -> None:
    other = copy.deepcopy(low_fuel["ships"][0])
    other["symbol"] = "H2"
    other["engine"]["speed"] = 10
    other["fuel"] = {"capacity": 40, "current": 40 if ready else 10}
    low_fuel["ships"].append(other)
    if not ready:
        low_fuel["agent"]["credits"] = 55400
    result = earn_run(low_fuel["run"], "X-A", cycles=1)
    assert result["decisions"][0]["selected"]["hauler"] == "H2"
    assert "/my/ships/H/refuel" not in low_fuel["posts"]
    assert low_fuel["posts"].count("/my/ships/H2/refuel") == (not ready)


@pytest.mark.parametrize(
    "guard", ["range", "price", "volume", "reserve", "mode"]
)
def test_earn_rejects_unfunded_or_invalid_refill(
    low_fuel: dict[str, Any], guard: str
) -> None:
    if guard == "range":
        low_fuel["ships"][0]["fuel"]["capacity"] = 39
    elif guard == "price":
        low_fuel["fuel_price"] = 0
    elif guard == "volume":
        low_fuel["fuel_volume"] = 0
    elif guard == "reserve":
        low_fuel["agent"]["credits"] = 55619
    else:
        low_fuel["ships"][0]["nav"]["flightMode"] = "DRIFT"
    earn_run(low_fuel["run"], "X-A", cycles=1)
    assert low_fuel["posts"] == []


@pytest.mark.parametrize("missing", ["fuel", "volume"])
def test_earn_requires_explicit_local_fuel_quote(
    low_fuel: dict[str, Any], missing: str
) -> None:
    run: Session = low_fuel["run"]
    original = run.market

    def market(key: str) -> dict[str, Any]:
        quote = original(key)
        if key == "X-A-1":
            if missing == "fuel":
                quote["tradeGoods"] = quote["tradeGoods"][:1]
            else:
                quote["tradeGoods"][1].pop("tradeVolume")
        return quote

    with patch.object(run, "market", side_effect=market):
        earn_run(run, "X-A", cycles=1)
    assert low_fuel["posts"] == []


@pytest.mark.parametrize("execute", [False, True])
def test_trade_rejects_full_tank_range_before_refill(
    low_fuel: dict[str, Any], execute: bool
) -> None:
    low_fuel["run"].execute = execute
    low_fuel["ships"][0]["fuel"]["capacity"] = 39
    with pytest.raises(SafetyStop, match="full-tank"):
        trade_run(
            low_fuel["run"],
            "H",
            "X-A-1",
            "X-A-2",
            "IRON",
            require_source=True,
        )
    assert low_fuel["posts"] == []


def test_refill_preview_observes_scope_before_pending_check(
    low_fuel: dict[str, Any],
) -> None:
    low_fuel["store"].begin_action("r:a", "/my/ships/H/refuel", {})
    assert not low_fuel["run"].scope
    with pytest.raises(SafetyStop, match="Pending"):
        refuel_run(low_fuel["run"], "H", plan_only=True)
    assert low_fuel["posts"] == []


@pytest.mark.parametrize("stage", ["entry", "purchase"])
def test_earning_never_approaches_changed_source(
    low_fuel: dict[str, Any], stage: str
) -> None:
    run: Session = low_fuel["run"]
    if stage == "purchase":
        low_fuel["ships"][0]["fuel"]["current"] = 400
        original = run.dock

        def dock(symbol: str) -> dict[str, Any]:
            ship = original(symbol)
            low_fuel["ships"][0]["nav"]["waypointSymbol"] = "X-A-0"
            return ship

        with (
            patch.object(run, "dock", side_effect=dock),
            pytest.raises(SafetyStop, match="already at source"),
        ):
            earn_run(run, "X-A", cycles=1)
    else:

        def trade(*args: Any, **kwargs: Any) -> dict[str, Any]:
            low_fuel["ships"][0]["nav"]["waypointSymbol"] = "X-A-0"
            return trade_run(*args, **kwargs)

        with (
            patch("py_st.services.earning.trade_run", side_effect=trade),
            pytest.raises(SafetyStop, match="already at source"),
        ):
            earn_run(run, "X-A", cycles=1)
    assert not any(
        p.endswith(("/navigate", "/refuel", "/purchase"))
        for p in low_fuel["posts"]
    )


@pytest.mark.parametrize("interrupt", ["stop", "actions", "unknown"])
def test_refill_interruption_and_reentry(
    low_fuel: dict[str, Any], interrupt: str
) -> None:
    low_fuel["ships"][0]["nav"]["status"] = "DOCKED"
    if interrupt == "stop":
        low_fuel["stop_after"] = "refuel"
    elif interrupt == "actions":
        low_fuel["run"].remaining = 1
    else:
        low_fuel["unknown"] = True
    with pytest.raises(
        httpx.ReadTimeout if interrupt == "unknown" else SafetyStop
    ):
        earn_run(low_fuel["run"], "X-A", cycles=1)
    assert low_fuel["posts"] == ["/my/ships/H/refuel"]
    low_fuel["unknown"] = False
    low_fuel["stop_after"] = ""
    low_fuel["root"].joinpath("STOP").unlink(missing_ok=True)
    low_fuel["run"].remaining = 30
    if interrupt == "unknown":
        with pytest.raises(SafetyStop, match="Pending"):
            earn_run(low_fuel["run"], "X-A", cycles=1)
        assert low_fuel["posts"] == ["/my/ships/H/refuel"]
    else:
        earn_run(low_fuel["run"], "X-A", cycles=1)
        assert low_fuel["posts"].count("/my/ships/H/refuel") == 1
        assert low_fuel["posts"].count("/my/ships/H/purchase") == 1
        assert low_fuel["agent"]["credits"] == 105712


@pytest.mark.parametrize(
    "change",
    [
        "buyer",
        "seller",
        "credits",
        "volume",
        "fuel_price",
        "cargo",
        "transit",
        "mode",
        "location",
        "contract",
        "range",
    ],
)
def test_refill_rechecks_after_selection_and_docking(
    low_fuel: dict[str, Any], change: str
) -> None:
    run: Session = low_fuel["run"]
    original = run.dock

    def dock(symbol: str) -> dict[str, Any]:
        ship = original(symbol)
        if change == "buyer":
            low_fuel["crash_price"] = True
        elif change == "credits":
            low_fuel["agent"]["credits"] = 55619
        elif change == "volume":
            low_fuel["fuel_volume"] = 0
        elif change == "fuel_price":
            low_fuel["fuel_price"] = 100000
        elif change == "cargo":
            low_fuel["ships"][0]["cargo"]["units"] = 1
        elif change == "transit":
            low_fuel["ships"][0]["nav"]["status"] = "IN_TRANSIT"
        elif change == "mode":
            low_fuel["ships"][0]["nav"]["flightMode"] = "DRIFT"
        elif change == "location":
            low_fuel["ships"][0]["nav"]["waypointSymbol"] = "X-A-0"
        elif change == "contract":
            low_fuel["contracts"].append(
                {"id": "C", "accepted": True, "fulfilled": False}
            )
        elif change == "range":
            low_fuel["ships"][0]["fuel"]["capacity"] = 39
        else:
            low_fuel["seller_price"] = 200
        return ship

    with (
        patch.object(run, "dock", side_effect=dock),
        pytest.raises(SafetyStop),
    ):
        earn_run(run, "X-A", cycles=1)
    assert low_fuel["posts"] == ["/my/ships/H/dock"]


@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize("reposition", [False, True])
def test_cli_bounded_options(execute: bool, reposition: bool) -> None:
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
                *(["--reposition"] if reposition else []),
            ],
        )
    assert result.exit_code == 0, result.output
    session.assert_called_once_with(execute, 600, 30)
    service.assert_called_once_with(
        session.return_value.__enter__.return_value,
        "X-A",
        2,
        900,
        reposition=reposition,
    )
