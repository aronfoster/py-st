from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from py_st.services.automation import SafetyStop, Session
from py_st.services.intelligence import Intelligence
from py_st.services.strategies import (
    contract_plan,
    contract_run,
    fleet_run,
    refuel_run,
    trade_plan,
    trade_run,
)


def procurement(accepted: bool = False) -> dict[str, Any]:
    return {
        "id": "C",
        "accepted": accepted,
        "terms": {
            "payment": {"onAccepted": 1678, "onFulfilled": 11236},
            "deliver": [
                {
                    "tradeSymbol": "ALUMINUM_ORE",
                    "unitsRequired": 57,
                    "unitsFulfilled": 0,
                    "destinationSymbol": "X-A-1",
                }
            ],
        },
    }


@pytest.mark.parametrize(
    "price,credits,feasible",
    [(154, 175000, True), (500, 175000, False), (154, 55000, False)],
)
def test_contract_profit_and_reserves(
    price: int, credits: int, feasible: bool
) -> None:
    # Arrange
    market = {
        "symbol": "X-A-1",
        "tradeGoods": [{"symbol": "ALUMINUM_ORE", "purchasePrice": price}],
    }
    # Act
    plan = contract_plan(procurement(), market, credits)
    # Assert
    assert plan["feasible"] is feasible
    assert plan["max_unit_price"] >= price


def test_accepted_payment_is_not_counted_twice() -> None:
    # Arrange
    market = {
        "symbol": "X-A-1",
        "tradeGoods": [{"symbol": "ALUMINUM_ORE", "purchasePrice": 154}],
    }
    # Act
    plan = contract_plan(procurement(True), market, 175000)
    # Assert
    assert plan["future_revenue"] == 11236


def test_unpriced_contract_is_not_accepted() -> None:
    # Arrange / Act / Assert
    with pytest.raises(SafetyStop, match="price"):
        contract_plan(procurement(), {"symbol": "X-A-1"}, 175000)


def test_contract_workflow_two_batches_and_completed_resume() -> None:
    # Arrange
    contract = procurement()
    contract["fulfilled"] = False
    contract["terms"]["deadline"] = "2099-01-01T00:00:00Z"
    agent = {"credits": 175000}
    cargo: dict[str, Any] = {"capacity": 40, "units": 0, "inventory": []}
    run = MagicMock()
    run.execute = True
    run.refresh.return_value = {"agent": agent, "contracts": [contract]}
    run.store.pending.return_value = False
    run.market.return_value = {
        "symbol": "X-A-1",
        "tradeGoods": [
            {"symbol": "ALUMINUM_ORE", "purchasePrice": 154, "tradeVolume": 60}
        ],
    }
    run.ship.return_value = {"cargo": cargo}
    run.arrive.return_value = {"cargo": cargo}
    run.dock.return_value = {"cargo": cargo}
    run.get.side_effect = lambda path: (
        agent if path == "/my/agent" else contract
    )

    def mutate(path: str, body: dict[str, Any] | None = None) -> None:
        if path.endswith("/accept"):
            contract["accepted"] = True
            agent["credits"] += 1678
        elif path.endswith("/purchase"):
            assert body is not None
            cargo["units"] = body["units"]
            cargo["inventory"] = [
                {"symbol": body["symbol"], "units": body["units"]}
            ]
            agent["credits"] -= body["units"] * 154
        elif path.endswith("/deliver"):
            assert body is not None
            contract["terms"]["deliver"][0]["unitsFulfilled"] += body["units"]
            cargo["units"] = 0
            cargo["inventory"] = []
        elif path.endswith("/fulfill"):
            contract["fulfilled"] = True
            agent["credits"] += 11236

    run.mutate.side_effect = mutate
    # Act
    result = contract_run(run, "S", "C")
    count = run.mutate.call_count
    resumed = contract_run(run, "S", "C")
    # Assert
    assert result["session_credit_change"] == 4136
    assert cargo["units"] == 0
    assert contract["terms"]["deliver"][0]["unitsFulfilled"] == 57
    assert resumed["status"] == "already fulfilled"
    assert run.mutate.call_count == count == 6


def test_trade_plan_accounts_for_slippage_volume_and_fuel() -> None:
    # Arrange
    source = {
        "symbol": "X-A-1",
        "tradeGoods": [
            {"symbol": "IRON", "purchasePrice": 100, "tradeVolume": 60}
        ],
    }
    target = {
        "symbol": "X-A-2",
        "tradeGoods": [
            {"symbol": "IRON", "sellPrice": 250, "tradeVolume": 20}
        ],
    }
    # Act
    plan = trade_plan(source, target, "IRON", 40, 100000, 72)
    poor = trade_plan(source, target, "IRON", 40, 51000, 72)
    # Assert
    assert plan["units"] == 20
    assert plan["conservative_net"] == 20 * (237 - 105) - 72
    assert not poor["feasible"]


@pytest.mark.parametrize(
    "credits,units",
    [(51000, 0), (51176, 0), (51177, 1), (51281, 1), (51282, 2)],
)
def test_trade_plan_reserves_costed_fuel_before_sizing(
    credits: int, units: int
) -> None:
    # Arrange
    source = {
        "symbol": "X-A-1",
        "tradeGoods": [
            {"symbol": "IRON", "purchasePrice": 100, "tradeVolume": 60}
        ],
    }
    target = {
        "symbol": "X-A-2",
        "tradeGoods": [
            {"symbol": "IRON", "sellPrice": 250, "tradeVolume": 60}
        ],
    }
    # Act
    plan = trade_plan(source, target, "IRON", 40, credits, 72)
    # Assert
    assert plan["units"] == units
    assert plan["fuel_allowance"] == 72
    assert plan["conservative_net"] == units * (237 - 105) - 72
    assert plan["feasible"] is (units > 0)
    if units:
        assert credits - units * plan["max_buy"] >= 51000 + 72


@pytest.mark.parametrize("interrupt", ["purchase", "sell"])
@pytest.mark.parametrize("initial_fuel", [400, 50])
def test_trade_resumes_after_mutation_without_double_buy(
    tmp_path: Path,
    interrupt: str,
    initial_fuel: int,
) -> None:
    # Arrange
    run = MagicMock()
    run.execute = True
    run.scope = "r:a"
    run.store = Intelligence(tmp_path / "db")
    agent: dict[str, Any] = {"credits": 100000}
    ship: dict[str, Any] = {
        "nav": {"flightMode": "CRUISE"},
        "cargo": {"capacity": 40, "units": 0, "inventory": []},
        "fuel": {"capacity": 400, "current": initial_fuel},
    }
    run.refresh.return_value = {"agent": agent, "contracts": []}
    run.arrive.return_value = ship
    run.ship.return_value = ship
    run.dock.return_value = ship
    run.get.side_effect = lambda path: (
        agent
        if path == "/my/agent"
        else {
            "systemSymbol": "X-A",
            "x": 0 if path.endswith("-1") else 20,
            "y": 0,
        }
    )
    run.market.side_effect = lambda key: {
        "symbol": key,
        "tradeGoods": [
            {
                "symbol": "IRON",
                "purchasePrice": 100,
                "sellPrice": 250,
                "tradeVolume": 60,
            },
            {
                "symbol": "FUEL",
                "purchasePrice": 72,
                "sellPrice": 68,
                "tradeVolume": 180,
            },
        ],
    }
    interrupted = False

    def mutate(path: str, body: dict[str, Any]) -> None:
        nonlocal interrupted
        if path.endswith("purchase"):
            ship["cargo"]["inventory"] = [
                {"symbol": "IRON", "units": body["units"]}
            ]
            ship["cargo"]["units"] = body["units"]
            agent["credits"] -= body["units"] * 100
        else:
            ship["cargo"]["inventory"] = []
            ship["cargo"]["units"] = 0
            agent["credits"] += body["units"] * 250
        if path.endswith(interrupt) and not interrupted:
            interrupted = True
            raise SafetyStop("simulated interruption after confirmed mutation")

    run.mutate.side_effect = mutate
    # Act
    with patch("py_st.services.strategies.refuel_run") as refuel:
        refuel.side_effect = lambda *_, **__: ship["fuel"].update(
            {"current": 400}
        )
        with pytest.raises(SafetyStop, match="simulated"):
            trade_run(run, "S", "X-A-1", "X-A-2", "IRON")
        trade_run(run, "S", "X-A-1", "X-A-2", "IRON")
        assert refuel.call_count == (1 if initial_fuel == 50 else 0)
    # Assert
    assert run.mutate.call_count == 2
    assert agent["credits"] == 106000
    assert ship["cargo"]["units"] == 0
    assert run.store.latest("r:a", "position")[0]["data"]["status"] == "closed"
    run.store.close()


def test_refuel_dry_run_and_credit_floor() -> None:
    # Arrange
    run = MagicMock()
    run.execute = False
    run.store.pending.return_value = False
    run.refresh.return_value = {"agent": {"credits": 100000}, "contracts": []}
    run.get.side_effect = lambda _: run.refresh.return_value["agent"]
    run.ship.return_value = {
        "nav": {"waypointSymbol": "X-A-1"},
        "fuel": {"capacity": 400, "current": 338},
    }
    run.arrive.return_value = run.ship.return_value
    run.market.return_value = {
        "tradeGoods": [
            {"symbol": "FUEL", "purchasePrice": 72, "tradeVolume": 100}
        ]
    }
    # Act
    plan = refuel_run(run, "S")
    run.refresh.return_value["agent"]["credits"] = 50000
    with pytest.raises(SafetyStop, match="reserve"):
        refuel_run(run, "S")
    # Assert
    assert plan["missing_fuel"] == 62
    assert plan["maximum_estimated_cost"] == 87
    run.mutate.assert_not_called()


def test_fleet_assigns_hauler_and_present_price_scout(tmp_path: Path) -> None:
    # Arrange
    run = MagicMock()
    run.execute = False
    run.scope = "r:a"
    run.store = Intelligence(tmp_path / "db")
    for key, x, buy, sell in (("X-A-1", 0, 100, 80), ("X-A-2", 20, 300, 250)):
        run.store.observe(
            run.scope, "waypoint", key, {"systemSymbol": "X-A", "x": x, "y": 0}
        )
        run.store.observe(
            run.scope,
            "market",
            key,
            {
                "symbol": key,
                "tradeGoods": [
                    {
                        "symbol": "IRON",
                        "purchasePrice": buy,
                        "sellPrice": sell,
                        "tradeVolume": 60,
                    },
                    {
                        "symbol": "FUEL",
                        "purchasePrice": 72,
                        "sellPrice": 68,
                        "tradeVolume": 180,
                    },
                ],
            },
        )
    run.refresh.return_value = {
        "agent": {"credits": 100000},
        "ships": [
            {
                "symbol": "hauler",
                "nav": {
                    "waypointSymbol": "X-A-1",
                    "status": "DOCKED",
                    "flightMode": "CRUISE",
                },
                "cargo": {"capacity": 40, "units": 0},
                "engine": {"speed": 30},
                "fuel": {"capacity": 400, "current": 400},
            },
            {
                "symbol": "probe",
                "nav": {
                    "waypointSymbol": "X-A-2",
                    "status": "IN_ORBIT",
                    "flightMode": "CRUISE",
                },
                "cargo": {"capacity": 0, "units": 0},
                "engine": {"speed": 10},
                "fuel": {"capacity": 0, "current": 0},
            },
        ],
    }
    run.market.side_effect = lambda key: next(
        row["data"]
        for row in run.store.latest(run.scope, "market")
        if row["key"] == key
    )
    # Act
    plan = fleet_run(run)
    run.refresh.return_value["ships"][1]["nav"]["status"] = "IN_TRANSIT"
    unavailable = fleet_run(run)
    # Assert
    assert plan["candidates"][0]["hauler"] == "hauler"
    assert plan["candidates"][0]["price_scout"] == "probe"
    assert unavailable["candidates"] == []
    run.mutate.assert_not_called()
    run.store.close()


@pytest.fixture
def trading_run(tmp_path: Path) -> Iterator[MagicMock]:
    run = MagicMock()
    run.execute = True
    run.scope = "r:a"
    run.store = Intelligence(tmp_path / "db")
    agent: dict[str, Any] = {"credits": 100000}
    ship: dict[str, Any] = {
        "symbol": "S",
        "nav": {
            "waypointSymbol": "X-A-1",
            "status": "DOCKED",
            "flightMode": "CRUISE",
        },
        "cargo": {"capacity": 40, "units": 0, "inventory": []},
        "fuel": {"capacity": 400, "current": 400},
        "engine": {"speed": 30},
    }
    scout = ship | {
        "symbol": "P",
        "nav": ship["nav"] | {"waypointSymbol": "X-A-2"},
        "cargo": {"capacity": 0, "units": 0, "inventory": []},
    }
    run.refresh.return_value = {
        "agent": agent,
        "ships": [ship, scout],
        "contracts": [],
    }
    run.arrive.return_value = ship
    run.ship.return_value = ship
    run.dock.return_value = ship
    run.navigate.side_effect = lambda _, destination: ship["nav"].update(
        {"waypointSymbol": destination}
    )
    run.get.side_effect = lambda path: (
        agent
        if path == "/my/agent"
        else {
            "systemSymbol": "X-A",
            "x": 0 if path.endswith("-1") else 20,
            "y": 0,
        }
    )

    def market(key: str) -> dict[str, Any]:
        quote = {
            "symbol": key,
            "tradeGoods": [
                {
                    "symbol": "IRON",
                    "purchasePrice": 100 if key == "X-A-1" else 300,
                    "sellPrice": 80 if key == "X-A-1" else 250,
                    "tradeVolume": 60,
                },
                {
                    "symbol": "FUEL",
                    "purchasePrice": 72,
                    "sellPrice": 68,
                    "tradeVolume": 180,
                },
            ],
        }
        run.store.observe(run.scope, "market", key, quote)
        return quote

    def mutate(path: str, body: dict[str, Any]) -> None:
        if path.endswith("/purchase"):
            ship["cargo"]["inventory"] = [
                {"symbol": body["symbol"], "units": body["units"]}
            ]
            ship["cargo"]["units"] = body["units"]
            agent["credits"] -= 100 * body["units"]
        else:
            assert path.endswith("/sell")
            ship["cargo"]["inventory"] = []
            ship["cargo"]["units"] = 0
            agent["credits"] += 250 * body["units"]

    run.market.side_effect = market
    run.mutate.side_effect = mutate
    for key in ("X-A-1", "X-A-2"):
        market(key)
        run.store.observe(run.scope, "waypoint", key, run.get(key))
    try:
        yield run
    finally:
        run.store.close()


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("headroom", [-72, -1, 0, 1])
def test_trade_rechecks_costed_fuel_reserve_before_purchase(
    trading_run: MagicMock, resume: bool, headroom: int
) -> None:
    # Arrange: plan with ample credits, then lose credits before buying.
    run = trading_run
    if resume:
        plan = trade_plan(
            run.market("X-A-1"), run.market("X-A-2"), "IRON", 40, 100000, 72
        ) | {"required_fuel": 70}
        run.store.observe(
            run.scope,
            "position",
            "trade:S",
            {"status": "open", "bought": False, "plan": plan},
        )
    get = run.get.side_effect
    agent_reads = 0

    def changed_credits(path: str) -> dict[str, Any]:
        nonlocal agent_reads
        result: dict[str, Any] = get(path)
        if path == "/my/agent":
            agent_reads += 1
            if resume or agent_reads > 1:
                result["credits"] = 51000 + 72 + 40 * 105 + headroom
        return result

    run.get.side_effect = changed_credits
    # Act / Assert
    if headroom < 0:
        with pytest.raises(SafetyStop, match="Resume would violate reserves"):
            trade_run(run, "S", "X-A-1", "X-A-2", "IRON")
        run.mutate.assert_not_called()
    else:
        result = trade_run(run, "S", "X-A-1", "X-A-2", "IRON")
        assert result["completed_cycles"] == 1
        assert run.mutate.call_count == 2
        assert run.mutate.call_args_list[0].args == (
            "/my/ships/S/purchase",
            {"symbol": "IRON", "units": 40},
        )
    position = run.store.latest(run.scope, "position")[0]["data"]
    assert position["plan"]["units"] == 40
    assert position["plan"]["fuel_allowance"] == 72
    assert position["status"] == (
        "open" if resume and headroom < 0 else "closed"
    )
    if headroom < 0 and not resume:
        assert position["cancellation_reason"] == (
            "Resume would violate reserves"
        )
        assert position["purchase_dispatched"] is False
    else:
        assert "cancellation_reason" not in position
    assert position["bought"] is (headroom >= 0)
    assert run.ship.return_value["cargo"]["units"] == 0


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("change", ["price", "missing", "volume"])
def test_trade_rechecks_buyer_before_every_purchase(
    trading_run: MagicMock, resume: bool, change: str
) -> None:
    # Arrange
    run = trading_run
    if resume:
        plan = trade_plan(
            run.market("X-A-1"), run.market("X-A-2"), "IRON", 40, 100000, 72
        ) | {"required_fuel": 70}
        run.store.observe(
            run.scope,
            "position",
            "trade:S",
            {"status": "open", "bought": False, "plan": plan},
        )
    market = run.market.side_effect
    buyer_reads = 0

    def changed_market(key: str) -> dict[str, Any]:
        nonlocal buyer_reads
        quote: dict[str, Any] = market(key)
        if key == "X-A-2":
            buyer_reads += 1
            if resume or buyer_reads > 1:
                if change == "missing":
                    quote.pop("tradeGoods")
                elif change == "price":
                    quote["tradeGoods"][0]["sellPrice"] = 50
                else:
                    quote["tradeGoods"][0]["tradeVolume"] = 39
        return quote

    run.market.side_effect = changed_market
    # Act
    with pytest.raises(SafetyStop, match="Buyer quote"):
        trade_run(run, "S", "X-A-1", "X-A-2", "IRON")
    # Assert
    run.mutate.assert_not_called()
    assert run.ship.return_value["cargo"]["units"] == 0
    position = run.store.latest(run.scope, "position")[0]["data"]
    if resume:
        assert position == {"status": "open", "bought": False, "plan": plan}
    else:
        assert position["status"] == "closed"
        assert position["bought"] is False
        assert position["purchase_dispatched"] is False
        assert position["cancellation_reason"] == (
            "Buyer quote no longer supports the trade"
        )


@pytest.mark.parametrize("change", ["price", "missing", "volume"])
def test_fresh_trade_retires_invalid_seller_quote(
    trading_run: MagicMock, change: str
) -> None:
    # Arrange
    run = trading_run
    market = run.market.side_effect
    seller_reads = 0

    def changed_market(key: str) -> dict[str, Any]:
        nonlocal seller_reads
        quote: dict[str, Any] = market(key)
        if key == "X-A-1":
            seller_reads += 1
            if seller_reads > 1:
                if change == "missing":
                    quote.pop("tradeGoods")
                elif change == "price":
                    quote["tradeGoods"][0]["purchasePrice"] = 106
                else:
                    quote["tradeGoods"][0]["tradeVolume"] = 39
        return quote

    run.market.side_effect = changed_market
    # Act
    with pytest.raises(SafetyStop, match="acquisition quote"):
        trade_run(run, "S", "X-A-1", "X-A-2", "IRON")
    # Assert
    run.mutate.assert_not_called()
    position = run.store.latest(run.scope, "position")[0]["data"]
    assert position["status"] == "closed"
    assert position["bought"] is False
    assert position["purchase_dispatched"] is False
    assert position["cancellation_reason"] == (
        "Resume acquisition quote no longer valid"
    )


@pytest.mark.parametrize("mode", ["BURN", "DRIFT"])
@pytest.mark.parametrize("resume", [False, True])
def test_trade_rejects_unsafe_mode_before_spending(
    trading_run: MagicMock, mode: str, resume: bool
) -> None:
    # Arrange
    run = trading_run
    run.ship.return_value["nav"]["flightMode"] = mode
    run.ship.return_value["fuel"]["current"] = 50
    if resume:
        run.store.observe(
            run.scope,
            "position",
            "trade:S",
            {"status": "open", "bought": False, "plan": {}},
        )
    # Act
    with patch("py_st.services.strategies.refuel_run") as refuel:
        with pytest.raises(SafetyStop, match="CRUISE"):
            trade_run(run, "S", "X-A-1", "X-A-2", "IRON")
        # Assert
        refuel.assert_not_called()
    run.mutate.assert_not_called()
    run.navigate.assert_not_called()


@pytest.mark.parametrize("mode", ["BURN", "DRIFT"])
def test_fleet_excludes_unsafe_flight_modes(
    trading_run: MagicMock, mode: str
) -> None:
    # Arrange
    run = trading_run
    run.execute = False
    run.ship.return_value["nav"]["flightMode"] = mode
    # Act
    result = fleet_run(run)
    # Assert
    assert result["candidates"] == []
    run.mutate.assert_not_called()


@pytest.mark.parametrize("interrupt", ["purchase", "sell"])
def test_fleet_resumes_its_original_position_before_new_routes(
    trading_run: MagicMock, interrupt: str
) -> None:
    # Arrange
    run = trading_run
    mutate = run.mutate.side_effect
    interrupted = False

    def interrupted_mutation(path: str, body: dict[str, Any]) -> None:
        nonlocal interrupted
        mutate(path, body)
        if path.endswith(interrupt) and not interrupted:
            interrupted = True
            raise SafetyStop("simulated interruption after confirmed mutation")

    run.mutate.side_effect = interrupted_mutation
    # Act
    with pytest.raises(SafetyStop, match="simulated"):
        fleet_run(run, cycles=3)
    with patch.object(run.store, "routes") as routes:
        result = fleet_run(run, cycles=3)
        # Assert: resume finishes one cycle, not three additional cycles.
        routes.assert_not_called()
    assert result["resumed"][0]["hauler"] == "S"
    assert run.mutate.call_count == 2
    assert run.refresh.return_value["agent"]["credits"] == 106000
    assert run.ship.return_value["cargo"]["units"] == 0
    assert (
        run.store.latest(run.scope, "position")[0]["data"]["status"]
        == "closed"
    )


def test_fleet_recovery_dry_run_and_pending_guard(
    trading_run: MagicMock,
) -> None:
    # Arrange
    run = trading_run
    plan = trade_plan(
        run.market("X-A-1"), run.market("X-A-2"), "IRON", 40, 100000, 72
    ) | {"required_fuel": 70}
    run.store.observe(
        run.scope,
        "position",
        "trade:S",
        {"status": "open", "bought": False, "plan": plan},
    )
    run.store.begin_action(run.scope, "/my/ships/S/purchase", {})
    run.execute = False
    run.remaining = 30
    run.mutate.side_effect = lambda path, body: Session.mutate(run, path, body)
    # Act
    with patch.object(run.store, "routes") as routes:
        result = fleet_run(run)
        run.mutate.assert_not_called()
        run.execute = True
        with pytest.raises(SafetyStop, match="Pending"):
            fleet_run(run)
        # Assert
        routes.assert_not_called()
    assert result["resume"][0]["key"] == "trade:S"
    run.client.request.assert_not_called()
    assert run.store.pending(run.scope)


@pytest.fixture
def procurement_run(tmp_path: Path) -> Iterator[MagicMock]:
    run = MagicMock()
    run.execute = True
    run.scope = "r:a"
    run.store = Intelligence(tmp_path / "db")
    contract = procurement(True)
    contract["fulfilled"] = False
    contract["terms"]["deadline"] = "2099-01-01T00:00:00Z"
    contract["terms"]["deliver"][0]["unitsRequired"] = 40
    contract["terms"]["payment"] = {"onAccepted": 2000, "onFulfilled": 10000}
    agent = {"credits": 54000}
    cargo = {
        "capacity": 40,
        "units": 40,
        "inventory": [{"symbol": "ALUMINUM_ORE", "units": 40}],
    }
    run.refresh.return_value = {"agent": agent, "contracts": [contract]}
    run.ship.return_value = {"cargo": cargo}
    run.arrive.return_value = {"cargo": cargo}
    run.dock.return_value = {"cargo": cargo}
    run.market.return_value = {
        "symbol": "X-A-1",
        "tradeGoods": [
            {"symbol": "ALUMINUM_ORE", "purchasePrice": 100, "tradeVolume": 40}
        ],
    }
    run.get.side_effect = lambda path: (
        agent if path == "/my/agent" else contract
    )
    original = contract_plan(
        contract | {"accepted": False}, run.market.return_value, 56000
    )
    assert original["feasible"]
    run.store.observe(run.scope, "plan", "C", original)

    def mutate(path: str, body: dict[str, Any] | None = None) -> None:
        if path.endswith("/fulfill"):
            contract["fulfilled"] = True
            agent["credits"] += 10000
        else:
            assert body is not None
            if path.endswith("/deliver"):
                contract["terms"]["deliver"][0]["unitsFulfilled"] += body[
                    "units"
                ]
                cargo.update({"units": 0, "inventory": []})
            else:
                assert path.endswith("/purchase")
                agent["credits"] -= 100 * body["units"]
                cargo.update(
                    {
                        "units": body["units"],
                        "inventory": [
                            {"symbol": body["symbol"], "units": body["units"]}
                        ],
                    }
                )

    run.mutate.side_effect = mutate
    try:
        yield run
    finally:
        run.store.close()


@pytest.mark.parametrize("interrupt", ["accept", "purchase"])
@pytest.mark.parametrize(
    "change", ["none", "dry", "price", "reserve", "deadline"]
)
def test_accepted_procurement_resumes_without_sunk_profit_test(
    procurement_run: MagicMock, interrupt: str, change: str
) -> None:
    # Arrange: profitable overall, but fulfillment alone cannot fund buying.
    run = procurement_run
    contract = run.refresh.return_value["contracts"][0]
    agent = run.refresh.return_value["agent"]
    contract["accepted"] = False
    contract["terms"]["payment"] = {"onAccepted": 10000, "onFulfilled": 3000}
    agent["credits"] = 90000
    run.ship.return_value["cargo"].update(units=0, inventory=[])
    run.market.return_value["tradeGoods"][0]["tradeVolume"] = 20
    mutate = run.mutate.side_effect
    interrupted = False

    def stopped(path: str, body: dict[str, Any] | None = None) -> None:
        nonlocal interrupted
        if path.endswith("/accept"):
            contract["accepted"] = True
            agent["credits"] += 10000
        else:
            mutate(path, body)
        if path.endswith("/" + interrupt) and not interrupted:
            interrupted = True
            raise SafetyStop("Confirmed mutation interrupted")

    run.mutate.side_effect = stopped
    with pytest.raises(SafetyStop, match="Confirmed mutation"):
        contract_run(run, "S", "C")
    original = run.store.latest(run.scope, "plan")[0]["data"]
    assert original["feasible"]
    assert original["conservative_net"] == 7200
    held = run.ship.return_value["cargo"]["units"]
    assert held == (20 if interrupt == "purchase" else 0)
    if change == "price":
        run.market.return_value["tradeGoods"][0]["purchasePrice"] = 121
    elif change == "reserve":
        agent["credits"] = 51000 + (40 - held) * 120 - 1
    elif change == "deadline":
        contract["terms"]["deadline"] = (
            datetime.now(UTC) + timedelta(minutes=30)
        ).isoformat()
    elif change == "dry":
        run.execute = False
    before = run.mutate.call_count

    # Act / Assert: completion first, but no relaxation of acquisition guards.
    if change in {"price", "reserve", "deadline"}:
        with pytest.raises(SafetyStop, match="Price|reserve|deadline"):
            contract_run(run, "S", "C")
        calls = run.mutate.call_args_list[before:]
        assert all(c.args[0].endswith("/deliver") for c in calls)
    else:
        result = contract_run(run, "S", "C")
        if change == "dry":
            assert run.mutate.call_count == before
            if held:
                assert result["status"] == "ready to deliver"
            else:
                assert result["feasible"]
                assert result["conservative_net"] < 0
        else:
            assert result["status"] == "fulfilled"
            purchases = [
                c.args[1]["units"]
                for c in run.mutate.call_args_list
                if c.args[0].endswith("/purchase")
            ]
            assert purchases == [20, 20]
    assert (
        sum(c.args[0].endswith("/accept") for c in run.mutate.call_args_list)
        == 1
    )
    assert (
        run.store.latest(run.scope, "plan")[0]["data"]["max_unit_price"] == 120
    )


@pytest.mark.parametrize("held", [20, 40])
def test_procurement_delivers_owned_cargo_before_reserving_purchases(
    procurement_run: MagicMock, held: int
) -> None:
    # Arrange
    run = procurement_run
    cargo = run.ship.return_value["cargo"]
    cargo["units"] = cargo["inventory"][0]["units"] = held
    # Act
    result = contract_run(run, "S", "C")
    # Assert
    assert result["status"] == "fulfilled"
    assert run.mutate.call_args_list[0].args[0].endswith("/deliver")
    purchases = [
        c for c in run.mutate.call_args_list if c.args[0].endswith("/purchase")
    ]
    assert sum(c.args[1]["units"] for c in purchases) == 40 - held
    if held == 40:
        run.market.assert_not_called()
    else:
        assert result["plan"]["remaining"] == 20
        assert result["plan"]["reserve_after_acquisition"] == 50600


@pytest.mark.parametrize(
    "position", ["trade:S", "procurement:OTHER", "unknown"]
)
@pytest.mark.parametrize("accepted", [False, True])
def test_local_procurement_preserves_unrelated_exposure(
    procurement_run: MagicMock, position: str, accepted: bool
) -> None:
    # Arrange: matching trade cargo must not become contract cargo.
    run = procurement_run
    run.refresh.return_value["agent"]["credits"] = 90000
    run.refresh.return_value["contracts"][0]["accepted"] = accepted
    if not accepted:
        run.ship.return_value["cargo"].update(units=0, inventory=[])
    run.store.observe(run.scope, "position", position, {"status": "open"})
    before = run.store.latest(run.scope, "position")

    # Act / Assert
    with pytest.raises(SafetyStop, match="positions"):
        contract_run(run, "S", "C")
    run.mutate.assert_not_called()
    assert run.store.latest(run.scope, "position") == before


@pytest.mark.parametrize("delivered", [False, True])
@pytest.mark.parametrize("execute", [False, True])
def test_procurement_completion_needs_no_quote_or_acquisition_lead_time(
    procurement_run: MagicMock, delivered: bool, execute: bool
) -> None:
    # Arrange
    run = procurement_run
    run.execute = execute
    contract = run.refresh.return_value["contracts"][0]
    contract["terms"]["deadline"] = (
        datetime.now(UTC) + timedelta(minutes=30)
    ).isoformat()
    if delivered:
        contract["terms"]["deliver"][0]["unitsFulfilled"] = 40
    run.market.side_effect = AssertionError("Completion must not need a quote")
    # Act
    result = contract_run(run, "S", "C")
    # Assert
    run.market.assert_not_called()
    if execute:
        assert result["status"] == "fulfilled"
        assert run.mutate.call_count == (1 if delivered else 2)
    else:
        assert result["status"] == (
            "ready to fulfill" if delivered else "ready to deliver"
        )
        run.mutate.assert_not_called()


@pytest.mark.parametrize("delivered", [False, True])
def test_procurement_completion_still_refuses_expired_contracts(
    procurement_run: MagicMock, delivered: bool
) -> None:
    # Arrange
    run = procurement_run
    contract = run.refresh.return_value["contracts"][0]
    contract["terms"]["deadline"] = "2000-01-01T00:00:00Z"
    if delivered:
        contract["terms"]["deliver"][0]["unitsFulfilled"] = 40
    # Act
    with pytest.raises(SafetyStop, match="deadline expired"):
        contract_run(run, "S", "C")
    # Assert
    run.mutate.assert_not_called()


@pytest.mark.parametrize("guard", ["price", "reserve", "deadline"])
def test_procurement_recovery_retains_acquisition_guards(
    procurement_run: MagicMock, guard: str
) -> None:
    # Arrange
    run = procurement_run
    run.ship.return_value["cargo"].update({"units": 0, "inventory": []})
    if guard == "price":
        run.market.return_value["tradeGoods"][0]["purchasePrice"] = 121
        run.refresh.return_value["agent"]["credits"] = 100000
    elif guard == "deadline":
        run.refresh.return_value["agent"]["credits"] = 100000
        run.refresh.return_value["contracts"][0]["terms"]["deadline"] = (
            datetime.now(UTC) + timedelta(minutes=30)
        ).isoformat()
    # Act
    with pytest.raises(SafetyStop, match="Price|reserve|deadline"):
        contract_run(run, "S", "C")
    # Assert
    run.mutate.assert_not_called()
    plan = run.store.latest(run.scope, "plan")[0]["data"]
    assert plan["max_unit_price"] == 120
    assert plan["reserve_after_acquisition"] == (
        run.refresh.return_value["agent"]["credits"] - 4800 - 1000
    )
