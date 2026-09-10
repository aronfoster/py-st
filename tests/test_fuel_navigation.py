import math
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from py_st.cli.app import app
from py_st.services.automation import SafetyStop, Session
from py_st.services.intelligence import Intelligence
from py_st.services.strategies import refuel_run


@pytest.mark.parametrize(
    "case,feasible",
    [
        ("fresh", True),
        ("exchange", True),
        ("missing", False),
        ("stale", False),
        ("exchange_only", False),
        ("zero_price", False),
        ("zero_volume", False),
        ("credits", False),
        ("contract", False),
        ("position", False),
        ("pending", False),
        ("margin", False),
        ("expired", False),
        ("not_market", False),
    ],
)
def test_one_way_requires_funded_fresh_recovery(
    tmp_path: Path, case: str, feasible: bool
) -> None:
    # Arrange: 300 fuel leg fits a 400 tank, but not a 610 fuel round trip.
    ship: dict[str, Any] = {
        "nav": {
            "status": "DOCKED",
            "waypointSymbol": "X-A-1",
            "systemSymbol": "X-A",
            "flightMode": "CRUISE",
            "route": {"destination": {"x": 0, "y": 0}},
        },
        "fuel": {"capacity": 400, "current": 400},
    }
    target = {"x": 300, "y": 0, "traits": [{"symbol": "MARKETPLACE"}]}
    fuel = {"symbol": "FUEL", "purchasePrice": 100, "tradeVolume": 10}
    market = {"symbol": "X-A-2", "tradeGoods": [fuel]}
    state: dict[str, Any] = {"agent": {"credits": 51_576}, "contracts": []}
    store = Intelligence(tmp_path / "db")
    client = MagicMock()
    run = Session(client, store, execute=True, root=tmp_path)
    run.scope = "r:a"
    store.observe(run.scope, "market", "X-A-2", deepcopy(market))
    if case == "stale":
        store.db.execute(
            "UPDATE observations SET observed_at='2000-01-01T00:00:00+00:00'"
        )
    if case in {"missing", "stale", "exchange_only"}:
        market["tradeGoods"] = []
    if case in {"exchange", "exchange_only"}:
        market["exchange"] = [{"symbol": "FUEL"}]
    if case == "zero_price":
        fuel["purchasePrice"] = 0
    if case == "zero_volume":
        fuel["tradeVolume"] = 0
    if case == "credits":
        state["agent"]["credits"] -= 1
    if case == "contract":
        state["contracts"] = [{"accepted": True, "fulfilled": False}]
    if case == "position":
        store.observe(run.scope, "position", "trade:S", {"status": "open"})
    if case == "pending":
        store.begin_action(run.scope, "/my/ships/S/refuel", {})
    if case == "margin":
        ship["fuel"]["current"] = 329
    if case == "not_market":
        target["traits"] = []
    now = datetime.now(UTC)
    try:
        with (
            patch.object(run, "get", return_value=target),
            patch.object(run, "market", return_value=market),
            patch.object(run, "refresh", return_value=state),
            patch("py_st.services.automation.datetime") as clock,
        ):
            clock.now.side_effect = [
                now,
                now + timedelta(seconds=61 if case == "expired" else 0),
            ]
            # Act
            plan = run.navigation_plan(ship, "X-A-2")
        # Assert
        assert plan["feasible"] is feasible
        if feasible:
            assert plan["required_fuel"] == 330
            assert plan["full_refill_credit_reserve"] == 576
            assert plan["protected_credits"] == 51_576
            assert plan["policy"] == "destination-refuel"
        client.request.assert_not_called()
    finally:
        run.close()
        store.close()


def test_move_dry_run_prints_fuel_plan_without_navigation() -> None:
    # Arrange
    run = MagicMock()
    run.navigation_plan.return_value = {
        "feasible": True,
        "policy": "destination-refuel",
        "required_fuel": 330,
    }
    with patch("py_st.cli.auto_cmd.session") as session:
        session.return_value.__enter__.return_value = run
        # Act
        result = CliRunner().invoke(app, ["auto", "move", "S", "X-A-2"])
    # Assert
    assert result.exit_code == 0, result.output
    assert '"required_fuel": 330' in result.output
    run.navigate.assert_not_called()
    run.mutate.assert_not_called()


@pytest.mark.parametrize("initial_price", [100, 101])
@pytest.mark.parametrize(
    "price_growth,arrival_fuel", [(1, 50), (1.1, 50), (1.2, 50), (1.2, 0)]
)
def test_long_navigation_and_existing_refuel_recover_full_tank(
    tmp_path: Path, initial_price: int, price_growth: float, arrival_fuel: int
) -> None:
    # Arrange: real Session guards/journal and the existing refill workflow.
    ship: dict[str, Any] = {
        "symbol": "S",
        "nav": {
            "status": "DOCKED",
            "waypointSymbol": "X-A-1",
            "systemSymbol": "X-A",
            "flightMode": "CRUISE",
            "route": {"destination": {"x": 0, "y": 0}},
        },
        "fuel": {"capacity": 400, "current": 400},
    }
    reserve = 4 * math.ceil(math.ceil(initial_price * 1.2) * 1.2)
    agent: dict[str, Any] = {"symbol": "a", "credits": 51_000 + reserve}
    market: dict[str, Any] = {
        "symbol": "X-A-2",
        "tradeGoods": [
            {
                "symbol": "FUEL",
                "purchasePrice": initial_price,
                "tradeVolume": 10,
            }
        ],
    }

    def request(method: str, path: str, **kwargs: Any) -> Any:
        if method == "GET":
            if path == "/my/agent":
                return deepcopy(agent)
            if path == "/my/contracts":
                return []
            if path == "/my/ships":
                return [deepcopy(ship)]
            if path == "/my/ships/S":
                return deepcopy(ship)
            if path.endswith("/market"):
                return deepcopy(market)
            return {
                "x": 350,
                "y": 0,
                "traits": [{"symbol": "MARKETPLACE"}],
            }
        if path.endswith("/orbit"):
            ship["nav"]["status"] = "IN_ORBIT"
        elif path.endswith("/navigate"):
            ship["nav"]["waypointSymbol"] = "X-A-2"
            ship["nav"]["route"]["destination"] = {"x": 350, "y": 0}
            # Actual consumption is authoritative, even above the estimate.
            ship["fuel"]["current"] = arrival_fuel
            market["tradeGoods"][0]["purchasePrice"] = math.ceil(
                initial_price * price_growth
            )
        elif path.endswith("/dock"):
            ship["nav"]["status"] = "DOCKED"
        elif path.endswith("/refuel"):
            cost = (
                math.ceil((400 - arrival_fuel) / 100)
                * market["tradeGoods"][0]["purchasePrice"]
            )
            ship["fuel"]["current"] = 400
            agent["credits"] -= cost
            return {
                "fuel": deepcopy(ship["fuel"]),
                "agent": deepcopy(agent),
                "transaction": {"totalPrice": cost},
            }
        else:
            pytest.fail(f"Unexpected mutation: {path}")
        return {}

    client = MagicMock()
    client.status.return_value = {"resetDate": "r"}
    client.request.side_effect = request
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=True, root=tmp_path)
    try:
        with patch("py_st.services.automation.cache.clear_cache"):
            # Act
            run.refresh()
            arrival = run.navigate("S", "X-A-2")
            result = refuel_run(run, "S")
        # Assert
        assert arrival["fuel"]["current"] == arrival_fuel
        assert result["fuel"]["current"] == 400
        assert agent["credits"] >= 51_000
        assert len(store.actions(run.scope)) == 4
        assert not store.pending(run.scope)
        assert all(
            a["status"] == "succeeded" for a in store.actions(run.scope)
        )
    finally:
        run.close()
        store.close()


@pytest.mark.parametrize("expired", [False, True])
def test_navigation_checks_quote_after_orbit(
    tmp_path: Path, expired: bool
) -> None:
    # Arrange
    store = Intelligence(tmp_path / "db")
    run = Session(MagicMock(), store, execute=True, root=tmp_path)
    run.scope = "r:a"
    ship = {"nav": {"waypointSymbol": "X-A-1", "status": "DOCKED"}}
    plan = {
        "feasible": True,
        "policy": "destination-refuel",
        "fuel_quote_observed_at": datetime.now(UTC).isoformat(),
    }

    def mutate(path: str, body: Any = None) -> dict[str, Any]:
        if expired:
            plan["fuel_quote_observed_at"] = "2000-01-01T00:00:00+00:00"
        return {}

    try:
        with (
            patch.object(run, "arrive", return_value=ship),
            patch.object(run, "navigation_plan", return_value=plan),
            patch.object(run, "mutate", side_effect=mutate) as mutation,
        ):
            # Act
            if expired:
                with pytest.raises(SafetyStop, match="expired"):
                    run.navigate("S", "X-A-2")
            else:
                run.navigate("S", "X-A-2")
            # Assert
            assert mutation.call_count == (1 if expired else 2)
            assert store.latest(run.scope, "plan")[0]["key"] == "move:S"
    finally:
        run.close()
        store.close()
