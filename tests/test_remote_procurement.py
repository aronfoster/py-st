from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from py_st.services.automation import SafetyStop, Session
from py_st.services.intelligence import Intelligence
from py_st.services.strategies import contract_run, refuel_run


@pytest.fixture
def remote(tmp_path: Path) -> Iterator[tuple[Any, ...]]:
    agent: dict[str, Any] = {"symbol": "A", "credits": 397940}
    contract: dict[str, Any] = {
        "id": "C",
        "accepted": False,
        "fulfilled": False,
        "deadlineToAccept": "2099-01-01T00:00:00Z",
        "terms": {
            "deadline": "2099-01-02T00:00:00Z",
            "payment": {"onAccepted": 39972, "onFulfilled": 113766},
            "deliver": [
                {
                    "tradeSymbol": "EQUIPMENT",
                    "unitsRequired": 26,
                    "unitsFulfilled": 0,
                    "destinationSymbol": "X-A-D",
                }
            ],
        },
    }
    ship: dict[str, Any] = {
        "symbol": "S",
        "nav": {
            "systemSymbol": "X-A",
            "waypointSymbol": "X-A-S",
            "status": "IN_ORBIT",
            "flightMode": "CRUISE",
            "route": {"destination": {"x": 0, "y": 0}},
        },
        "fuel": {"capacity": 400, "current": 337},
        "cargo": {"capacity": 40, "units": 0, "inventory": []},
        "engine": {"speed": 30},
    }
    probe = deepcopy(ship)
    probe.update(
        symbol="P",
        frame={"symbol": "FRAME_PROBE"},
        fuel={"capacity": 0, "current": 0},
    )
    probe["nav"]["waypointSymbol"] = "X-A-D"
    markets: dict[str, Any] = {
        w: {
            "symbol": w,
            "tradeGoods": [
                {
                    "symbol": "EQUIPMENT",
                    "purchasePrice": 2076,
                    "tradeVolume": 20,
                },
                {"symbol": "FUEL", "purchasePrice": 72, "tradeVolume": 180},
            ],
        }
        for w in ("X-A-S", "X-A-D")
    }
    posts = []

    def request(method: str, path: str, **kwargs: Any) -> Any:
        result: Any
        if method == "GET":
            if path == "/my/agent":
                result = agent
            elif path == "/my/ships":
                result = [ship, probe]
            elif path == "/my/contracts":
                result = [contract]
            elif path == "/my/contracts/C":
                result = contract
            elif path == "/my/ships/S":
                result = ship
            elif path.endswith("/market"):
                result = markets[path.split("/")[-2]]
            else:
                result = {
                    "symbol": "X-A-D",
                    "x": 151,
                    "y": 0,
                    "traits": [{"symbol": "MARKETPLACE"}],
                }
            return deepcopy(result)
        posts.append((path, kwargs.get("body")))
        body = kwargs.get("body") or {}
        action = path.rsplit("/", 1)[-1]
        if action == "accept":
            contract["accepted"] = True
            agent["credits"] += 39972
        elif action == "purchase":
            ship["cargo"]["units"] += body["units"]
            ship["cargo"]["inventory"] = [
                {"symbol": "EQUIPMENT", "units": ship["cargo"]["units"]}
            ]
            agent["credits"] -= body["units"] * 2076
        elif action == "deliver":
            contract["terms"]["deliver"][0]["unitsFulfilled"] += body["units"]
            ship["cargo"].update(units=0, inventory=[])
        elif action == "fulfill":
            contract["fulfilled"] = True
            agent["credits"] += 113766
        elif action == "navigate":
            ship["nav"].update(
                waypointSymbol=body["waypointSymbol"], status="IN_ORBIT"
            )
            ship["nav"]["route"]["destination"] = {"x": 151, "y": 0}
            ship["fuel"]["current"] -= 151
        elif action == "refuel":
            agent["credits"] -= 216
            ship["fuel"]["current"] = 400
            return {
                "fuel": deepcopy(ship["fuel"]),
                "transaction": {
                    "totalPrice": 216,
                    "type": "PURCHASE",
                    "tradeSymbol": "FUEL",
                },
                "agent": deepcopy(agent),
            }
        else:
            assert action in ("dock", "orbit")
            ship["nav"]["status"] = (
                "DOCKED" if action == "dock" else "IN_ORBIT"
            )
        return {"agent": deepcopy(agent), "contract": deepcopy(contract)}

    client = MagicMock()
    client.status.return_value = {"resetDate": "r"}
    client.request.side_effect = request
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=True, root=tmp_path)
    with patch("py_st.services.automation.cache.clear_cache"):
        yield run, agent, contract, ship, probe, markets, posts
    run.close()
    store.close()


@pytest.mark.parametrize("stop_after", [0, 1, 3, 4, 6, 8])
def test_remote_recovery_aggregates_full_load(
    remote: tuple[Any, ...], stop_after: int
) -> None:
    run, agent, contract, ship, _, markets, posts = remote
    # Interrupt only after known journaled successes, including each purchase,
    # navigation and delivery. Restart never replays those actions.
    if stop_after:
        run.remaining = stop_after
        with pytest.raises(SafetyStop, match="budget"):
            contract_run(run, "S", "C", "X-A-S")
        run.remaining = 30
        if (
            ship["cargo"]["units"] == 26
            or contract["terms"]["deliver"][0]["unitsFulfilled"]
        ):
            markets["X-A-S"].pop("tradeGoods")
    result = contract_run(run, "S", "C", "X-A-S")
    assert result["status"] == "fulfilled"
    buys = [b["units"] for p, b in posts if p.endswith("/purchase")]
    assert buys == [20, 6]
    assert sum(p.endswith("/accept") for p, _ in posts) == 1
    assert sum(p.endswith("/navigate") for p, _ in posts) == 1
    assert sum(p.endswith("/fulfill") for p, _ in posts) == 1
    assert agent["credits"] == 497702
    assert ship["cargo"]["units"] == 0
    assert ship["fuel"]["current"] == 186
    assert (
        run.store.latest(run.scope, "position")[0]["data"]["status"]
        == "closed"
    )
    refuel_run(run, "S")
    assert agent["credits"] == 497486
    assert ship["fuel"]["current"] == 400


def test_remote_dryrun_costs_full_obligation_without_mutating(
    remote: tuple[Any, ...],
) -> None:
    run, _, _, _, _, _, posts = remote
    run.execute = False
    plan = contract_run(run, "S", "C", "X-A-S")
    assert plan["feasible"]
    assert plan["purchase_batches"] == 2
    assert plan["full_refill_credit_reserve"] == 348
    assert plan["protected_credits"] == 116140
    assert plan["conservative_net"] == 87598
    assert not posts
    assert not run.store.latest(run.scope, "position")


@pytest.mark.parametrize(
    "guard",
    [
        "capacity",
        "credits",
        "fuel",
        "probe",
        "source",
        "destfuel",
        "zero_fuel",
        "zero_volume",
        "price",
        "deadline",
        "expiration",
        "mode",
        "pending",
        "other_contract",
        "open_trade",
        "stale",
    ],
)
def test_remote_preaccept_guards(remote: tuple[Any, ...], guard: str) -> None:
    run, agent, contract, ship, probe, markets, posts = remote
    if guard == "capacity":
        ship["cargo"]["capacity"] = 25
    elif guard == "credits":
        agent["credits"] = 116139
    elif guard == "fuel":
        ship["fuel"]["current"] = 311
    elif guard == "probe":
        probe["nav"]["status"] = "IN_TRANSIT"
    elif guard == "source":
        ship["nav"]["waypointSymbol"] = "X-A-Z"
    elif guard == "destfuel":
        run.store.observe("r:A", "market", "X-A-D", markets["X-A-D"])
        markets["X-A-D"].pop("tradeGoods")
    elif guard == "zero_fuel":
        markets["X-A-D"]["tradeGoods"][1]["purchasePrice"] = 0
    elif guard == "zero_volume":
        markets["X-A-S"]["tradeGoods"][0]["tradeVolume"] = 0
    elif guard == "price":
        markets["X-A-S"]["tradeGoods"][0]["purchasePrice"] = 6664
    elif guard == "deadline":
        contract["terms"]["deadline"] = "2000-01-01T00:00:00Z"
    elif guard == "expiration":
        contract["deadlineToAccept"] = "2000-01-01T00:00:00Z"
    elif guard == "mode":
        ship["nav"]["flightMode"] = "DRIFT"
    elif guard == "pending":
        run.store.begin_action("r:A", "/my/ships/S/purchase", {})
    elif guard == "other_contract":
        original = run.client.request.side_effect

        def request(method: str, path: str, **kwargs: Any) -> Any:
            result = original(method, path, **kwargs)
            if path == "/my/contracts":
                result.append(contract | {"id": "OTHER", "accepted": True})
            return result

        run.client.request.side_effect = request
    elif guard == "open_trade":
        run.store.observe("r:A", "position", "trade:S", {"status": "open"})
    if guard == "stale":
        with patch("py_st.services.remote_procurement.time") as clock:
            clock.monotonic.side_effect = [0, 61]
            with pytest.raises(SafetyStop):
                contract_run(run, "S", "C", "X-A-S")
    else:
        with pytest.raises(SafetyStop):
            contract_run(run, "S", "C", "X-A-S")
    assert not posts


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize(
    "change", ["price", "fuel_price", "credits", "missing"]
)
def test_remote_resume_preserves_original_ceiling(
    remote: tuple[Any, ...], partial: bool, change: str
) -> None:
    run, agent, _, _, _, markets, posts = remote
    run.remaining = 3 if partial else 1
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C", "X-A-S")
    before = len(posts)
    run.remaining = 30
    if change == "price":
        markets["X-A-S"]["tradeGoods"][0]["purchasePrice"] = 2493
    elif change == "fuel_price":
        markets["X-A-D"]["tradeGoods"][1]["purchasePrice"] = 88
    elif change == "missing":
        markets["X-A-D"].pop("tradeGoods")
    else:
        agent["credits"] = 51000
    with pytest.raises(SafetyStop):
        contract_run(run, "S", "C", "X-A-S")
    assert len(posts) == before
    plan = run.store.latest(run.scope, "position")[0]["data"]["plan"]
    assert plan["max_unit_price"] == 2492


@pytest.mark.parametrize("stop_after", [4, 8])
def test_remote_completion_ignores_missing_quotes_and_uses_saved_source(
    remote: tuple[Any, ...], stop_after: int
) -> None:
    run, _, _, _, _, markets, posts = remote
    run.remaining = stop_after
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C", "X-A-S")
    for market in markets.values():
        market.pop("tradeGoods")
    run.remaining = 30
    result = contract_run(run, "S", "C")
    assert result["status"] == "fulfilled"
    assert sum(p.endswith("/purchase") for p, _ in posts) == 2


def test_remote_interruption_after_fulfillment_closes_without_replay(
    remote: tuple[Any, ...],
) -> None:
    run, _, _, _, _, markets, posts = remote
    finish = run.store.finish_action

    def interrupted(action: int, status: str, result: dict[str, Any]) -> None:
        finish(action, status, result)
        if result.get("contract", {}).get("fulfilled"):
            raise SafetyStop("confirmed fulfillment interruption")

    with (
        patch.object(run.store, "finish_action", side_effect=interrupted),
        pytest.raises(SafetyStop, match="confirmed fulfillment"),
    ):
        contract_run(run, "S", "C", "X-A-S")
    for market in markets.values():
        market.pop("tradeGoods")
    count = len(posts)
    assert contract_run(run, "S", "C")["status"] == "fulfilled"
    assert len(posts) == count
    assert not run.store.pending(run.scope)
    assert (
        run.store.latest(run.scope, "position")[0]["data"]["status"]
        == "closed"
    )
