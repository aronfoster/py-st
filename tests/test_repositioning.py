import copy
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from py_st.client import SpaceTradersClient
from py_st.services.automation import SafetyStop, Session
from py_st.services.earning import earn_run
from py_st.services.intelligence import Intelligence
from py_st.services.remote_procurement import remote_contract_run
from py_st.services.repositioning import reposition_plan, reposition_run
from py_st.services.strategies import (
    contract_run,
    fleet_run,
    refuel_run,
    trade_run,
)
from tests import test_earning

world = test_earning.world


@pytest.fixture
def long_cycle(world: dict[str, Any]) -> dict[str, Any]:
    for waypoint in world["waypoints"]:
        waypoint["x"] *= 10
    earn_run(world["run"], "X-A", cycles=2)
    assert world["ships"][0]["fuel"]["current"] == 300
    world["posts"].clear()
    return world


def test_buyer_refill_return_then_fresh_source_refill_and_trade(
    long_cycle: dict[str, Any],
) -> None:
    run = long_cycle["run"]
    plan = reposition_plan(run, "X-A")
    assert plan["required_carried_fuel"] == 310
    assert plan["buyer_upfront_refill_allowance"] == 87
    assert plan["protected_credits"] == 56055
    assert plan["conservative_net"] == 4425
    result = reposition_run(run, plan)
    assert result["arrival_fuel"]["current"] == 300
    assert result["physical_return_fuel_ready"]
    assert not result["purchase_authorized"]
    assert long_cycle["posts"] == [
        "/my/ships/H/refuel",
        "/my/ships/H/orbit",
        "/my/ships/H/navigate",
    ]
    earn_run(run, "X-A", cycles=1)
    assert long_cycle["posts"].count("/my/ships/H/refuel") == 2
    assert long_cycle["posts"].count("/my/ships/H/purchase") == 1
    assert long_cycle["ships"][0]["fuel"]["current"] == 300
    assert long_cycle["agent"]["credits"] == 111856


def test_buyer_refill_dry_run(long_cycle: dict[str, Any]) -> None:
    run = long_cycle["run"]
    run.execute = False
    before = long_cycle["store"].latest("r:a", "position")
    result = earn_run(run, "X-A", reposition=True)
    assert (
        result["decisions"][0]["selected"]["buyer_upfront_refill_allowance"]
        == 87
    )
    assert long_cycle["posts"] == []
    assert long_cycle["store"].latest("r:a", "position") == before


@pytest.mark.parametrize("guard", ["funds", "price", "volume", "range"])
def test_buyer_refill_blocked_before_spending(
    long_cycle: dict[str, Any],
    guard: str,
) -> None:
    if guard == "funds":
        long_cycle["agent"]["credits"] = 56054
    elif guard == "price":
        long_cycle["fuel_price"] = 0
    elif guard == "volume":
        long_cycle["fuel_volume"] = 0
    else:
        long_cycle["ships"][0]["fuel"]["capacity"] = 309
    result = earn_run(long_cycle["run"], "X-A", reposition=True)
    assert result["status"] == "reposition blocked"
    assert long_cycle["posts"] == []


@pytest.mark.parametrize("unknown", [False, True])
def test_buyer_refill_interruption_never_replays(
    long_cycle: dict[str, Any],
    unknown: bool,
) -> None:
    run, store = long_cycle["run"], long_cycle["store"]
    long_cycle["unknown"] = unknown
    long_cycle["stop_after"] = "refuel"
    with pytest.raises(httpx.ReadTimeout if unknown else SafetyStop):
        earn_run(run, "X-A", reposition=True)
    assert long_cycle["posts"] == ["/my/ships/H/refuel"]
    assert not any(
        p["key"].startswith("reposition:")
        for p in store.latest("r:a", "position")
    )
    long_cycle["unknown"] = False
    long_cycle["stop_after"] = ""
    if unknown:
        with pytest.raises(SafetyStop, match="Pending"):
            earn_run(run, "X-A", reposition=True)
    else:
        long_cycle["root"].joinpath("STOP").unlink()
        earn_run(run, "X-A", reposition=True)
    assert long_cycle["posts"].count("/my/ships/H/refuel") == 1


@pytest.mark.parametrize(
    "guard", ["contract", "pending", "exposure", "mode", "cargo", "observer"]
)
def test_low_fuel_does_not_override_global_or_position_guards(
    long_cycle: dict[str, Any],
    guard: str,
) -> None:
    run, store = long_cycle["run"], long_cycle["store"]
    if guard == "contract":
        long_cycle["contracts"].append(
            {"id": "C", "accepted": True, "fulfilled": False}
        )
    elif guard == "pending":
        store.begin_action("r:a", "/my/ships/H/refuel", {})
    elif guard == "exposure":
        store.observe("r:a", "position", "unknown", {})
    elif guard == "mode":
        long_cycle["ships"][0]["nav"]["flightMode"] = "DRIFT"
    elif guard == "cargo":
        long_cycle["ships"][0]["cargo"]["units"] = 1
    else:
        long_cycle["ships"][1]["nav"]["waypointSymbol"] = "X-A-0"
    if guard in ("contract", "pending", "exposure"):
        with pytest.raises(SafetyStop):
            earn_run(run, "X-A", reposition=True)
    else:
        assert reposition_plan(run, "X-A")["status"] == "blocked"
    assert long_cycle["posts"] == []


@pytest.mark.parametrize(
    "change", ["credits", "price", "observer", "location"]
)
def test_buyer_refill_rechecks_after_docking(
    long_cycle: dict[str, Any],
    change: str,
) -> None:
    run = long_cycle["run"]
    long_cycle["ships"][0]["nav"]["status"] = "IN_ORBIT"
    dock = run.dock

    def changed(symbol: str) -> None:
        dock(symbol)
        if change == "credits":
            long_cycle["agent"]["credits"] = 56055
            long_cycle["fuel_price"] = 100
        elif change == "price":
            long_cycle["fuel_price"] = 10000
        elif change == "observer":
            long_cycle["ships"][1]["nav"]["status"] = "IN_TRANSIT"
        else:
            long_cycle["ships"][0]["nav"]["waypointSymbol"] = "X-A-0"

    with (
        patch.object(run, "dock", side_effect=changed),
        pytest.raises(SafetyStop),
    ):
        earn_run(run, "X-A", reposition=True)
    assert long_cycle["posts"] == ["/my/ships/H/dock"]


@pytest.mark.parametrize("reserve", [-1, True, 1.5, float("nan")])
def test_refuel_reserve_cannot_lower_floor(
    world: dict[str, Any],
    reserve: Any,
) -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        refuel_run(world["run"], "H", additional_reserve=reserve)
    assert world["posts"] == []


@pytest.mark.parametrize("change", ["price", "credits"])
def test_buyer_refill_fresh_cost_boundary(
    long_cycle: dict[str, Any],
    change: str,
) -> None:
    run = long_cycle["run"]

    def changed(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = refuel_run(*args, **kwargs)
        if change == "price":
            long_cycle["fuel_price"] += 1
        else:
            long_cycle["agent"]["credits"] = 56054
        return result

    with (
        patch("py_st.services.repositioning.refuel_run", side_effect=changed),
        pytest.raises(SafetyStop, match="economics changed"),
    ):
        earn_run(run, "X-A", reposition=True)
    assert long_cycle["posts"] == []


@pytest.mark.parametrize("change", ["observer", "contract"])
def test_buyer_refill_rechecks_eligibility_after_preparation(
    long_cycle: dict[str, Any], change: str
) -> None:
    run: Session = long_cycle["run"]
    plan = reposition_plan(run, "X-A")
    get = run.get
    armed = False

    def preview(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal armed
        result = refuel_run(*args, **kwargs)
        armed = True
        return result

    def changed(path: str) -> dict[str, Any]:
        nonlocal armed
        result = get(path)
        if armed and path.endswith("/waypoints/X-A-2"):
            armed = False
            if change == "observer":
                long_cycle["ships"][1]["nav"]["status"] = "IN_TRANSIT"
            else:
                long_cycle["contracts"].append(
                    {"id": "C", "accepted": True, "fulfilled": False}
                )
        return result

    with (
        patch("py_st.services.repositioning.refuel_run", side_effect=preview),
        patch.object(run, "get", side_effect=changed),
        pytest.raises(SafetyStop, match="eligibility changed"),
    ):
        reposition_run(run, plan)
    assert long_cycle["posts"] == []
    assert not long_cycle["store"].pending("r:a")


def test_shared_refuel_exact_additional_reserve(world: dict[str, Any]) -> None:
    world["ships"][0]["fuel"]["current"] = 300
    world["agent"]["credits"] = 52087
    result = refuel_run(world["run"], "H", additional_reserve=1000)
    assert result["maximum_estimated_cost"] == 87
    assert world["agent"]["credits"] == 52015
    assert world["ships"][0]["fuel"]["current"] == 400


def test_shared_refuel_preserves_additional_reserve_after_docking(
    world: dict[str, Any],
) -> None:
    run = world["run"]
    world["ships"][0]["fuel"]["current"] = 300
    world["agent"]["credits"] = 52087
    dock = run.dock

    def changed(symbol: str) -> None:
        dock(symbol)
        world["agent"]["credits"] -= 1

    with (
        patch.object(run, "dock", side_effect=changed),
        pytest.raises(SafetyStop, match="reserve"),
    ):
        refuel_run(run, "H", additional_reserve=1000)
    assert world["posts"] == ["/my/ships/H/dock"]


@pytest.fixture
def completed(world: dict[str, Any]) -> dict[str, Any]:
    # Complete a real guarded trade, retaining its original detailed quote.
    earn_run(world["run"], "X-A", cycles=2)
    world["posts"].clear()
    world["reads"].clear()
    return world


@pytest.fixture
def undispatched(completed: dict[str, Any]) -> dict[str, Any]:
    run = completed["run"]
    run.remaining = 1
    with pytest.raises(SafetyStop, match="Action budget"):
        earn_run(run, "X-A", reposition=True)
    assert completed["posts"] == ["/my/ships/H/orbit"]
    run.remaining = 30
    completed["posts"].clear()
    return completed


@pytest.mark.parametrize("blocker", ["expired", "cost"])
def test_abandon_undispatched_approach_then_next_invocation_can_replan(
    undispatched: dict[str, Any],
    blocker: str,
) -> None:
    run, store = undispatched["run"], undispatched["store"]
    if blocker == "expired":
        with store.db:
            store.db.execute(
                "UPDATE observations SET observed_at=? "
                "WHERE kind='position' AND key='trade:H'",
                ((datetime.now(UTC) - timedelta(hours=1)).isoformat(),),
            )
    else:
        undispatched["agent"]["credits"] = 51000
    before = next(
        p
        for p in store.latest("r:a", "position")
        if p["key"] == "reposition:H"
    )
    trade = next(
        p for p in store.latest("r:a", "position") if p["key"] == "trade:H"
    )
    actions = store.actions("r:a")
    result = earn_run(run, "X-OTHER", cycles=5)
    assert result["status"] == "recovery only"
    closed = result["result"]
    assert closed["status"] == "closed"
    assert closed["outcome"] == "abandoned"
    assert closed["reason"]
    assert closed["navigation_may_have_succeeded"] is False
    assert closed["plan"] == before["data"]["plan"]
    assert (
        json.loads(
            store.db.execute(
                "SELECT data FROM observations WHERE id=?", (before["id"],)
            ).fetchone()[0]
        )
        == before["data"]
    )
    assert (
        next(
            p
            for p in store.latest("r:a", "position")
            if p["key"] == "reposition:H"
        )["id"]
        > before["id"]
    )
    assert (
        next(
            p for p in store.latest("r:a", "position") if p["key"] == "trade:H"
        )
        == trade
    )
    assert store.actions("r:a") == actions
    assert not store.pending("r:a")
    assert undispatched["posts"] == []
    # Closing exposure is terminal; only a subsequent invocation may discover.
    next_result = earn_run(
        run, "X-A", cycles=1, reposition=blocker == "expired"
    )
    assert next_result["decisions"][0]["kind"] == "discover"


@pytest.mark.parametrize(
    "status",
    ["pending", "succeeded", "reviewed", "unknown", "not_sent", "rejected"],
)
def test_only_definitively_undispatched_navigation_allows_abandonment(
    undispatched: dict[str, Any],
    status: str,
) -> None:
    run, store = undispatched["run"], undispatched["store"]
    undispatched["agent"]["credits"] = 51000
    action = store.begin_action(
        "r:a", "/my/ships/H/navigate", {"waypointSymbol": "X-A-1"}
    )
    if status != "pending":
        store.finish_action(action, status, {})
    before, actions = store.latest("r:a", "position"), store.actions("r:a")
    if status in ("not_sent", "rejected"):
        result = earn_run(run, "X-OTHER")
        assert result["result"]["outcome"] == "abandoned"
    else:
        with pytest.raises(SafetyStop, match="Pending|already dispatched"):
            earn_run(run, "X-OTHER")
        assert store.latest("r:a", "position") == before
    assert store.actions("r:a") == actions
    assert undispatched["posts"] == []


@pytest.mark.parametrize(
    "guard",
    [
        "stop",
        "deadline",
        "pending",
        "location",
        "cargo",
        "transit",
        "other_position",
        "late_dispatch",
    ],
)
def test_abandonment_reobserves_safety_before_closing(
    undispatched: dict[str, Any],
    guard: str,
) -> None:
    run: Session = undispatched["run"]
    store = undispatched["store"]
    undispatched["agent"]["credits"] = 51000
    original = reposition_plan

    def blocked(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        if guard == "stop":
            undispatched["root"].joinpath("STOP").touch()
        elif guard == "deadline":
            run.deadline = 0
        elif guard in ("pending", "late_dispatch"):
            action = store.begin_action("r:a", "/my/ships/H/navigate", {})
            if guard == "late_dispatch":
                store.finish_action(action, "succeeded", {})
        elif guard == "location":
            undispatched["ships"][0]["nav"]["waypointSymbol"] = "X-A-0"
        elif guard == "cargo":
            undispatched["ships"][0]["cargo"]["units"] = 1
        elif guard == "transit":
            undispatched["ships"][0]["nav"]["status"] = "IN_TRANSIT"
        else:
            store.observe("r:a", "position", "trade:P", {"status": "open"})
        return result

    before = next(
        p
        for p in store.latest("r:a", "position")
        if p["key"] == "reposition:H"
    )
    with (
        patch(
            "py_st.services.repositioning.reposition_plan", side_effect=blocked
        ),
        pytest.raises(SafetyStop),
    ):
        earn_run(run, "X-OTHER")
    assert (
        next(
            p
            for p in store.latest("r:a", "position")
            if p["key"] == "reposition:H"
        )
        == before
    )
    assert undispatched["posts"] == []


def test_arrived_source_finishes_recovery_instead_of_abandoning(
    completed: dict[str, Any],
) -> None:
    run, store = completed["run"], completed["store"]
    completed["stop_after"] = "navigate"
    with pytest.raises(SafetyStop):
        earn_run(run, "X-A", reposition=True)
    completed["root"].joinpath("STOP").unlink()
    with store.db:
        store.db.execute(
            "UPDATE observations SET observed_at=? WHERE kind='market'",
            ((datetime.now(UTC) - timedelta(hours=1)).isoformat(),),
        )
    completed["posts"].clear()
    result = earn_run(run, "X-OTHER")
    assert result["status"] == "recovery only"
    assert result["result"]["status"] == "closed"
    assert "outcome" not in result["result"]
    assert "arrival_fuel" in result["result"]
    assert completed["posts"] == []


def test_opt_in_is_terminal_then_next_invocation_trades(
    completed: dict[str, Any],
) -> None:
    observer = copy.deepcopy(completed["ships"][1])
    result = earn_run(completed["run"], "X-A", cycles=5, reposition=True)
    decision = result["decisions"][0]
    assert result["status"] == "recovery only"
    assert len(result["decisions"]) == 1
    assert decision["kind"] == "reposition"
    plan = decision["selected"]
    assert (
        plan["hauler"],
        plan["source"],
        plan["destination"],
        plan["good"],
    ) == ("H", "X-A-1", "X-A-2", "IRON")
    assert plan["required_carried_fuel"] == 40
    assert plan["source_return_required_fuel"] == 30
    assert plan["costed_fuel"] == 174
    assert plan["source_full_refill_allowance"] == 420
    assert plan["protected_credits"] == 55794
    assert plan["conservative_net"] == 4686
    assert decision["result"]["arrival_fuel"]["current"] == 380
    assert not decision["result"]["purchase_authorized"]
    assert completed["posts"] == ["/my/ships/H/orbit", "/my/ships/H/navigate"]
    assert completed["ships"][1] == observer
    earn_run(completed["run"], "X-A", cycles=1)
    assert completed["posts"].count("/my/ships/H/purchase") == 1
    assert completed["ships"][1] == observer


def test_default_does_not_return(completed: dict[str, Any]) -> None:
    earn_run(completed["run"], "X-A", cycles=1)
    assert not any(p.startswith("/my/ships/H/") for p in completed["posts"])
    assert not any(
        p["key"].startswith("reposition:")
        for p in completed["store"].latest("r:a", "position")
    )


def test_dry_run_preserves_positions(completed: dict[str, Any]) -> None:
    before = completed["store"].latest("r:a", "position")
    completed["run"].execute = False
    result = earn_run(completed["run"], "X-A", reposition=True)
    assert result["status"] == "dry run"
    assert result["decisions"][0]["selected"]["status"] == "ready"
    assert completed["store"].latest("r:a", "position") == before
    assert completed["posts"] == []


@pytest.mark.parametrize("stage", ["orbit", "navigate", "arrival"])
def test_stop_restart_recovers_original_ship_across_systems(
    completed: dict[str, Any],
    stage: str,
) -> None:
    run: Session = completed["run"]
    market = run.market

    def stop_at_arrival(key: str) -> dict[str, Any]:
        quote = market(key)
        if key == "X-A-1":
            completed["root"].joinpath("STOP").touch()
        return quote

    completed["stop_after"] = stage
    with (
        patch.object(
            run,
            "market",
            side_effect=(stop_at_arrival if stage == "arrival" else market),
        ),
        pytest.raises(SafetyStop, match="STOP"),
    ):
        earn_run(run, "X-A", reposition=True)
    positions = completed["store"].latest("r:a", "position")
    assert (
        next(p for p in positions if p["key"] == "reposition:H")["data"][
            "status"
        ]
        == "open"
    )
    completed["root"].joinpath("STOP").unlink()
    completed["stop_after"] = ""
    run.close()
    restarted = Session(
        completed["client"],
        completed["store"],
        execute=True,
        root=completed["root"],
    )
    try:
        result = earn_run(restarted, "X-OTHER", cycles=5)
    finally:
        restarted.close()
    assert result["status"] == "recovery only"
    assert result["result"]["status"] == "closed"
    assert completed["posts"].count("/my/ships/H/navigate") == 1
    assert not any(
        p.endswith("/purchase") or "/P/" in p for p in completed["posts"]
    )


def test_unknown_navigation_blocks_even_at_source(
    completed: dict[str, Any],
) -> None:
    completed["ships"][0]["nav"]["status"] = "IN_ORBIT"
    completed["unknown"] = True
    with pytest.raises(httpx.ReadTimeout):
        earn_run(completed["run"], "X-A", reposition=True)
    completed["unknown"] = False
    with pytest.raises(SafetyStop, match="Pending"):
        earn_run(completed["run"], "X-OTHER")
    assert completed["posts"] == ["/my/ships/H/navigate"]


def test_confirmed_dispatch_never_replayed_with_adverse_nav(
    completed: dict[str, Any],
) -> None:
    completed["stop_after"] = "navigate"
    with pytest.raises(SafetyStop):
        earn_run(completed["run"], "X-A", reposition=True)
    completed["root"].joinpath("STOP").unlink()
    completed["ships"][0]["nav"]["waypointSymbol"] = "X-A-2"
    with pytest.raises(SafetyStop, match="already dispatched"):
        earn_run(completed["run"], "X-A")
    assert completed["posts"].count("/my/ships/H/navigate") == 1


@pytest.mark.parametrize(
    "change",
    [
        "seller_missing",
        "buyer_sparse",
        "adverse",
        "reserves",
        "range",
        "observer",
        "cargo",
        "mode",
        "source_missing",
        "fuel_quote",
        "volume",
        "ship_missing",
    ],
)
def test_unsafe_candidate_terminal_without_scouting(
    completed: dict[str, Any],
    change: str,
) -> None:
    store, ship = completed["store"], completed["ships"][0]
    if change == "seller_missing":
        with store.db:
            store.db.execute(
                "DELETE FROM observations WHERE kind='market' AND key='X-A-1'"
            )
    elif change == "buyer_sparse":
        completed["sparse"] = True
    elif change == "adverse":
        completed["crash_price"] = True
    elif change == "reserves":
        completed["agent"]["credits"] = 55793
    elif change == "range":
        ship["fuel"] = {"capacity": 39, "current": 39}
    elif change == "observer":
        completed["ships"][1]["nav"]["waypointSymbol"] = "X-A-0"
    elif change == "cargo":
        ship["cargo"]["units"] = 1
    elif change == "mode":
        ship["nav"]["flightMode"] = "DRIFT"
    elif change == "source_missing":
        prior = store.latest("r:a", "position")[0]["data"]
        prior["plan"].pop("source")
        store.observe("r:a", "position", "trade:H", prior)
    elif change == "fuel_quote":
        completed["fuel_price"] = 0
    elif change == "volume":
        completed["fuel_volume"] = 0
    else:
        completed["ships"].remove(ship)
    result = earn_run(completed["run"], "X-A", reposition=True)
    assert result["decisions"][0]["selected"]["status"] == "blocked"
    assert result["decisions"][0]["selected"]["reason"]
    assert completed["posts"] == []


@pytest.mark.parametrize(
    "guard", ["stop", "deadline", "actions", "contract", "pending"]
)
def test_global_guards(completed: dict[str, Any], guard: str) -> None:
    run = completed["run"]
    if guard == "stop":
        completed["root"].joinpath("STOP").touch()
    elif guard == "deadline":
        run.deadline = 0
    elif guard == "actions":
        run.remaining = 0
    elif guard == "contract":
        completed["contracts"].append(
            {"id": "C", "accepted": True, "fulfilled": False}
        )
    else:
        completed["store"].begin_action("r:a", "/my/ships/H/purchase", {})
    with pytest.raises(SafetyStop):
        earn_run(run, "X-A", reposition=True)
    assert completed["posts"] == []


@pytest.mark.parametrize("missing", ["goods", "fuel"])
def test_source_quote_lost_after_arrival_never_buys(
    completed: dict[str, Any],
    missing: str,
) -> None:
    run: Session = completed["run"]
    original = run.market

    def market(key: str) -> dict[str, Any]:
        quote = original(key)
        if key == "X-A-1":
            quote["tradeGoods"] = (
                [] if missing == "goods" else quote["tradeGoods"][:1]
            )
        return quote

    with patch.object(run, "market", side_effect=market):
        result = earn_run(run, "X-A", reposition=True)
        assert result["decisions"][0]["result"]["status"] == "closed"
        if missing == "fuel":
            with pytest.raises(SafetyStop, match="fresh usable FUEL"):
                earn_run(run, "X-A", cycles=1)
        else:
            earn_run(run, "X-A", cycles=1)
    assert not any(
        p.endswith(("/purchase", "/refuel")) for p in completed["posts"]
    )


def test_sparse_source_does_not_freshen_evidence(
    completed: dict[str, Any],
) -> None:
    run = completed["run"]
    before = reposition_plan(run, "X-A")["source_quote"]["observed_at"]
    run.market("X-A-1")
    after = reposition_plan(run, "X-A")["source_quote"]["observed_at"]
    assert before == after


def test_ready_route_precedes_reposition(world: dict[str, Any]) -> None:
    world["ships"][1]["nav"]["waypointSymbol"] = "X-A-2"
    with patch("py_st.services.earning.reposition_plan") as planning:
        result = earn_run(world["run"], "X-A", cycles=1, reposition=True)
    assert result["decisions"][0]["kind"] == "trade"
    planning.assert_not_called()


def test_funded_route_precedes_reposition(world: dict[str, Any]) -> None:
    world["ships"][1]["nav"]["waypointSymbol"] = "X-A-2"
    world["ships"][0]["fuel"]["current"] = 10
    with patch("py_st.services.earning.reposition_plan") as planning:
        result = earn_run(world["run"], "X-A", cycles=1, reposition=True)
    assert result["decisions"][0]["selected"]["refill"]
    planning.assert_not_called()


def test_no_completed_route_declines_to_discovery(
    world: dict[str, Any],
) -> None:
    result = earn_run(world["run"], "X-A", cycles=1, reposition=True)
    assert result["decisions"][0]["kind"] == "discover"
    assert result["decisions"][0]["reposition"]["status"] == "declined"


@pytest.mark.parametrize(
    "change", ["credits", "fuel", "buyer", "observer", "contract"]
)
def test_revalidation_after_orbit(
    completed: dict[str, Any], change: str
) -> None:
    run = completed["run"]
    mutate = run.mutate

    def mutate_and_change(path: str, body: Any = None, **kwargs: Any) -> Any:
        result = mutate(path, body, **kwargs)
        if path.endswith("/orbit"):
            if change == "credits":
                completed["agent"]["credits"] = 51000
            elif change == "fuel":
                completed["ships"][0]["fuel"]["current"] = 39
            elif change == "buyer":
                completed["crash_price"] = True
            elif change == "observer":
                completed["ships"][1]["nav"]["status"] = "IN_TRANSIT"
            else:
                completed["contracts"].append(
                    {"id": "C", "accepted": True, "fulfilled": False}
                )
        return result

    with patch.object(run, "mutate", side_effect=mutate_and_change):
        if change == "contract":
            with pytest.raises(SafetyStop):
                earn_run(run, "X-A", reposition=True)
        else:
            result = earn_run(run, "X-A", reposition=True)
            assert result["status"] == "recovery only"
            assert result["decisions"][0]["result"]["outcome"] == "abandoned"
    assert completed["posts"] == ["/my/ships/H/orbit"]
    assert next(
        p
        for p in completed["store"].latest("r:a", "position")
        if p["key"] == "reposition:H"
    )["data"]["status"] == ("open" if change == "contract" else "closed")


@pytest.mark.parametrize("kind", ["other", "unknown", "malformed", "trade"])
def test_ambiguous_or_exposed_positions_preserved(
    completed: dict[str, Any],
    kind: str,
) -> None:
    completed["stop_after"] = "orbit"
    with pytest.raises(SafetyStop):
        earn_run(completed["run"], "X-A", reposition=True)
    completed["root"].joinpath("STOP").unlink()
    store = completed["store"]
    if kind == "other":
        store.observe("r:a", "position", "reposition:P", {"status": "open"})
    elif kind == "unknown":
        store.observe("r:a", "position", "unrecognized", {})
    elif kind == "malformed":
        store.observe("r:a", "position", "reposition:H", {"status": "open"})
    else:
        store.observe(
            "r:a",
            "position",
            "trade:H",
            {"status": "open", "bought": False, "plan": {}},
        )
    before = store.latest("r:a", "position")
    with pytest.raises(SafetyStop, match="inspect recovery"):
        earn_run(completed["run"], "X-OTHER")
    assert store.latest("r:a", "position") == before
    assert completed["posts"] == ["/my/ships/H/orbit"]


def test_recovery_dry_run_observes_nav_without_position_writes(
    completed: dict[str, Any],
) -> None:
    completed["stop_after"] = "navigate"
    with pytest.raises(SafetyStop):
        earn_run(completed["run"], "X-A", reposition=True)
    completed["root"].joinpath("STOP").unlink()
    completed["run"].execute = False
    before = completed["store"].latest("r:a", "position")
    result = earn_run(completed["run"], "X-OTHER")
    assert result["result"]["current_ship"]["nav"]["waypointSymbol"] == "X-A-1"
    assert completed["store"].latest("r:a", "position") == before


def test_arrival_wait_recovers_without_navigation_replay(
    completed: dict[str, Any],
) -> None:
    completed["stop_after"] = "navigate"
    with pytest.raises(SafetyStop):
        earn_run(completed["run"], "X-A", reposition=True)
    completed["root"].joinpath("STOP").unlink()
    ship = completed["ships"][0]
    ship["nav"]["status"] = "IN_TRANSIT"
    with patch.object(
        completed["run"],
        "wait",
        side_effect=lambda _: ship["nav"].update(status="IN_ORBIT"),
    ) as wait:
        result = earn_run(completed["run"], "X-OTHER")
    wait.assert_called_once()
    assert result["result"]["status"] == "closed"
    assert completed["posts"].count("/my/ships/H/navigate") == 1


def test_exact_carried_reserve_allows_guarded_physical_return(
    completed: dict[str, Any],
) -> None:
    completed["ships"][0]["fuel"]["current"] = 40
    result = earn_run(completed["run"], "X-A", reposition=True)
    assert result["decisions"][0]["result"]["physical_return_fuel_ready"]
    run = completed["run"]
    navigation = run.navigation_plan(run.ship("H"), "X-A-2")
    assert navigation["feasible"] and navigation["policy"] == "round-trip"
    assert completed["posts"].count("/my/ships/H/refuel") == 0


def test_action_budget_after_orbit_recovers_once(
    completed: dict[str, Any],
) -> None:
    completed["run"].remaining = 1
    with pytest.raises(SafetyStop, match="Action budget"):
        earn_run(completed["run"], "X-A", reposition=True)
    assert completed["posts"] == ["/my/ships/H/orbit"]
    completed["run"].remaining = 10
    result = earn_run(completed["run"], "X-OTHER")
    assert result["status"] == "recovery only"
    assert completed["posts"] == ["/my/ships/H/orbit", "/my/ships/H/navigate"]


def test_open_intent_needing_fuel_retires_before_new_funded_invocation(
    undispatched: dict[str, Any],
) -> None:
    run = undispatched["run"]
    undispatched["ships"][0]["fuel"]["current"] = 39
    result = earn_run(run, "X-A", reposition=True)
    assert result["result"]["outcome"] == "abandoned"
    assert undispatched["posts"] == []
    result = earn_run(run, "X-A", reposition=True)
    assert result["decisions"][0]["result"]["status"] == "closed"
    assert undispatched["posts"] == [
        "/my/ships/H/dock",
        "/my/ships/H/refuel",
        "/my/ships/H/orbit",
        "/my/ships/H/navigate",
    ]


@pytest.mark.parametrize("stage", ["orbit", "navigate"])
def test_deadline_after_mutation_keeps_recovery_intent(
    completed: dict[str, Any],
    stage: str,
) -> None:
    run: Session = completed["run"]
    original = run.mutate
    clock = time.monotonic()
    deadline = run.deadline

    def mutate(path: str, body: Any = None, **kwargs: Any) -> Any:
        nonlocal clock
        result = original(path, body, **kwargs)
        if path.endswith(f"/{stage}"):
            clock = deadline + 1
        return result

    with (
        patch(
            "py_st.services.repositioning.time.monotonic",
            side_effect=lambda: clock,
        ),
        patch.object(run, "mutate", side_effect=mutate),
        pytest.raises(SafetyStop, match="Wall-clock"),
    ):
        earn_run(run, "X-A", reposition=True)
    assert (
        next(
            p
            for p in completed["store"].latest("r:a", "position")
            if p["key"] == "reposition:H"
        )["data"]["status"]
        == "open"
    )
    assert not any(
        "/P/" in p or p.endswith("/purchase") for p in completed["posts"]
    )


def test_positive_gross_margin_does_not_replace_all_in_costs(
    completed: dict[str, Any],
) -> None:
    run: Session = completed["run"]
    original = run.market

    def market(key: str) -> dict[str, Any]:
        result = original(key)
        if key == "X-A-2":
            result["tradeGoods"][0]["sellPrice"] = 120
        return result

    with patch.object(run, "market", side_effect=market):
        result = earn_run(run, "X-A", reposition=True)
    plan = result["decisions"][0]["selected"]
    assert plan["min_sell"] > plan["max_buy"]
    assert plan["conservative_net"] < 0
    assert result["status"] == "reposition blocked"
    assert completed["posts"] == []


def test_missing_waypoint_is_explained(completed: dict[str, Any]) -> None:
    run: Session = completed["run"]
    original = run.get

    def get(path: str) -> dict[str, Any]:
        return {} if path.endswith("/waypoints/X-A-1") else original(path)

    with patch.object(run, "get", side_effect=get):
        plan = reposition_plan(run, "X-A")
    assert plan["status"] == "blocked"
    assert plan["reason"] == "Missing route coordinates"
    assert completed["posts"] == []


@pytest.mark.parametrize("kind", ["market", "position"])
@pytest.mark.parametrize("open_intent", [False, True])
def test_expired_evidence_recovers_before_discovery(
    completed: dict[str, Any],
    kind: str,
    open_intent: bool,
) -> None:
    run, store = completed["run"], completed["store"]
    if open_intent:
        completed["stop_after"] = "orbit"
        with pytest.raises(SafetyStop):
            earn_run(run, "X-A", reposition=True)
        completed["root"].joinpath("STOP").unlink()
        completed["stop_after"] = ""
    completed["posts"].clear()
    with store.db:
        store.db.execute(
            "UPDATE observations SET observed_at=? WHERE kind=?",
            ((datetime.now(UTC) - timedelta(hours=1)).isoformat(), kind),
        )
    if kind == "market":
        store.observe("r:a", "market", "X-A-1", {"symbol": "X-A-1"})
    if open_intent:
        result = earn_run(run, "X-A", cycles=1, reposition=True)
        assert result["status"] == "recovery only"
        assert result["result"]["status"] == "closed"
        assert result["result"]["outcome"] == "abandoned"
        assert "expired" in result["result"]["reason"]
        assert completed["posts"] == []
    else:
        result = earn_run(run, "X-A", cycles=1, reposition=True)
        assert result["decisions"][0]["kind"] == "discover"
        assert result["decisions"][0]["reposition"]["status"] == "declined"
        assert "expired" in result["decisions"][0]["reposition"]["reason"]
        assert completed["posts"] == (
            ["/my/ships/P/navigate"] if kind == "market" else []
        )


@pytest.mark.parametrize("stage", ["orbit", "navigate"])
@pytest.mark.parametrize(
    "command", ["fleet", "trade", "refuel", "contract", "remote"]
)
@pytest.mark.parametrize("execute", [False, True])
def test_standalone_strategies_fail_closed_on_reposition(
    completed: dict[str, Any],
    stage: str,
    command: str,
    execute: bool,
) -> None:
    run = completed["run"]
    completed["stop_after"] = stage
    with pytest.raises(SafetyStop):
        earn_run(run, "X-A", reposition=True)
    completed["root"].joinpath("STOP").unlink()
    completed["stop_after"] = ""
    completed["posts"].clear()
    run.execute = execute
    before = completed["store"].latest("r:a", "position")
    with pytest.raises(SafetyStop, match="open reposition"):
        if command == "fleet":
            fleet_run(run)
        elif command == "trade":
            trade_run(run, "H", "X-A-1", "X-A-2", "IRON")
        elif command == "refuel":
            refuel_run(run, "H")
        elif command == "contract":
            contract_run(run, "H", "C", "X-A-1")
        else:
            remote_contract_run(run, "H", "C", "X-A-1")
    assert completed["posts"] == []
    assert completed["store"].latest("r:a", "position") == before


@pytest.mark.parametrize(
    "action",
    [
        "orbit",
        "dock",
        "navigate",
        "purchase",
        "sell",
        "refuel",
        "negotiate/contract",
        "accept",
        "deliver",
        "fulfill",
    ],
)
def test_shared_mutation_boundary_blocks_unaware_automation(
    completed: dict[str, Any],
    action: str,
) -> None:
    run = completed["run"]
    completed["stop_after"] = "navigate"
    with pytest.raises(SafetyStop):
        earn_run(run, "X-A", reposition=True)
    completed["root"].joinpath("STOP").unlink()
    completed["posts"].clear()
    before = completed["store"].actions("r:a")
    path = (
        f"/my/contracts/C/{action}"
        if action in ("accept", "deliver", "fulfill")
        else f"/my/ships/P/{action}"
    )
    with pytest.raises(SafetyStop, match="open reposition"):
        run.mutate(path)
    assert completed["posts"] == []
    assert completed["store"].actions("r:a") == before


@pytest.mark.parametrize("ship", ["H", "P"])
def test_manual_move_cannot_move_reposition_ship_or_observer(
    completed: dict[str, Any],
    ship: str,
) -> None:
    run = completed["run"]
    completed["stop_after"] = "orbit"
    with pytest.raises(SafetyStop):
        earn_run(run, "X-A", reposition=True)
    completed["root"].joinpath("STOP").unlink()
    completed["posts"].clear()
    with pytest.raises(SafetyStop, match="open reposition"):
        run.navigate(ship, "X-A-1")
    assert completed["posts"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("hauler", "P"),
        ("source", "X-A-2"),
        ("destination", "X-A-1"),
        ("good", "COPPER"),
        ("original_position_id", 999999),
        ("original_position_id", 0),
        ("original_position_id", True),
        ("max_age", 0),
        ("max_age", -1),
        ("max_age", 86401),
        ("max_age", 1.5),
        ("max_age", None),
        ("source_return_required_fuel", -1),
        ("required_carried_fuel", -1),
        ("approach_fuel", False),
        ("units", 0),
    ],
)
@pytest.mark.parametrize("saved", [False, True])
def test_tampered_identity_and_malformed_bounds_never_write_or_move(
    completed: dict[str, Any],
    field: str,
    value: Any,
    saved: bool,
) -> None:
    run, store = completed["run"], completed["store"]
    plan = reposition_plan(run, "X-A")
    if saved:
        completed["stop_after"] = "navigate"
        with pytest.raises(SafetyStop):
            reposition_run(run, plan)
        completed["root"].joinpath("STOP").unlink()
        completed["posts"].clear()
        intent = next(
            p
            for p in store.latest("r:a", "position")
            if p["key"] == "reposition:H"
        )["data"]
        intent["plan"][field] = value
        store.observe("r:a", "position", "reposition:H", intent)
    else:
        plan[field] = value
    before = store.latest("r:a", "position")
    with pytest.raises(SafetyStop):
        if saved:
            earn_run(run, "X-OTHER")
        else:
            reposition_run(run, plan)
    assert completed["posts"] == []
    assert store.latest("r:a", "position") == before


def test_supplied_identity_not_silently_replaced_by_saved_plan(
    completed: dict[str, Any],
) -> None:
    run = completed["run"]
    plan = reposition_plan(run, "X-A")
    completed["stop_after"] = "orbit"
    with pytest.raises(SafetyStop):
        reposition_run(run, plan)
    completed["root"].joinpath("STOP").unlink()
    completed["posts"].clear()
    plan["source"] = "X-A-2"
    before = completed["store"].latest("r:a", "position")
    with pytest.raises(SafetyStop, match="identity"):
        reposition_run(run, plan)
    assert completed["posts"] == []
    assert completed["store"].latest("r:a", "position") == before


@pytest.mark.parametrize("evidence", ["original", "source", "buyer"])
@pytest.mark.parametrize("delay_at", ["navigation", "ship"])
def test_all_evidence_ages_checked_after_last_preparation_get(
    completed: dict[str, Any],
    evidence: str,
    delay_at: str,
) -> None:
    run: Session = completed["run"]
    completed["ships"][0]["nav"]["status"] = "IN_ORBIT"
    now = datetime.now(UTC)
    clock = now
    if evidence != "buyer":
        with completed["store"].db:
            completed["store"].db.execute(
                "UPDATE observations SET observed_at=? WHERE kind=? AND key=?",
                (
                    (now - timedelta(seconds=895)).isoformat(),
                    "position" if evidence == "original" else "market",
                    "trade:H" if evidence == "original" else "X-A-1",
                ),
            )
    original_navigation = run.navigation_plan
    original_ship = run.ship
    prepared = False

    def navigation(ship: dict[str, Any], destination: str) -> dict[str, Any]:
        nonlocal clock, prepared
        result = original_navigation(ship, destination)
        prepared = True
        if delay_at == "navigation":
            clock += timedelta(seconds=61 if evidence == "buyer" else 6)
        return result

    def ship(symbol: str) -> dict[str, Any]:
        nonlocal clock
        result = original_ship(symbol)
        if prepared and delay_at == "ship":
            clock += timedelta(seconds=61 if evidence == "buyer" else 6)
        return result

    with (
        patch("py_st.services.repositioning.datetime") as mocked_time,
        patch.object(run, "navigation_plan", side_effect=navigation) as nav,
        patch.object(run, "ship", side_effect=ship),
        patch.object(run, "navigate") as duplicate,
        pytest.raises(SafetyStop, match="evidence expired"),
    ):
        mocked_time.now.side_effect = lambda _: clock
        mocked_time.fromisoformat.side_effect = datetime.fromisoformat
        earn_run(run, "X-A", reposition=True)
    nav.assert_called_once()
    duplicate.assert_not_called()
    assert completed["posts"] == []


@pytest.mark.parametrize(
    "change", ["ship", "fuel", "observer", "contract", "credits"]
)
def test_navigation_preparation_changes_block_dispatch(
    completed: dict[str, Any],
    change: str,
) -> None:
    run: Session = completed["run"]
    completed["ships"][0]["nav"]["status"] = "IN_ORBIT"
    original = run.navigation_plan

    def navigation(ship: dict[str, Any], destination: str) -> dict[str, Any]:
        result = original(ship, destination)
        if change == "ship":
            completed["ships"][0]["nav"]["waypointSymbol"] = "X-A-0"
        elif change == "fuel":
            completed["ships"][0]["fuel"]["current"] -= 1
        elif change == "observer":
            completed["ships"][1]["nav"]["status"] = "IN_TRANSIT"
        elif change == "credits":
            completed["agent"]["credits"] = 0
        else:
            completed["contracts"].append(
                {"id": "C", "accepted": True, "fulfilled": False}
            )
        return result

    with (
        patch.object(run, "navigation_plan", side_effect=navigation),
        pytest.raises(SafetyStop, match="changed"),
    ):
        earn_run(run, "X-A", reposition=True)
    assert completed["posts"] == []


@pytest.mark.parametrize(
    "mode,limiter",
    [
        (mode, limiter)
        for mode in ("pacing", "retry")
        for limiter in ("buyer", "source", "original", "session")
    ]
    + [("timeout", "buyer"), ("arrival", "buyer")],
)
def test_real_transport_navigation_evidence_deadline(
    completed: dict[str, Any],
    mode: str,
    limiter: str,
) -> None:
    # Use the synthetic world's responses through real client/transport/Session
    # waits. Only clocks/sleep and HTTP I/O are substituted, not retry logic.
    completed["ships"][0]["nav"]["status"] = "IN_ORBIT"
    plan = reposition_plan(completed["run"], "X-A")
    completed["run"].close()
    store: Intelligence = completed["store"]
    response = completed["client"].request.side_effect
    start = datetime.now(UTC)
    clock = 0.0
    arrival: float | None = None
    dispatches: list[float] = []
    if limiter in ("source", "original"):
        with store.db:
            store.db.execute(
                "UPDATE observations SET observed_at=? WHERE kind=? AND key=?",
                (
                    (start - timedelta(seconds=895)).isoformat(),
                    "position" if limiter == "original" else "market",
                    "trade:H" if limiter == "original" else "X-A-1",
                ),
            )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal arrival
        path = request.url.path
        if path == "/":
            return httpx.Response(200, json={"resetDate": "r"})
        if request.method == "POST":
            assert path == "/my/ships/H/navigate"
            dispatches.append(clock)
            if mode == "retry":
                return httpx.Response(
                    429,
                    json={"error": {"code": 429}},
                    headers={"Retry-After": "61"},
                )
            if mode == "timeout":
                raise httpx.ReadTimeout("Lost navigation response")
        if path == "/my/ships/H" and arrival is not None:
            assert run.deadline == original_deadline
            if clock >= arrival:
                completed["ships"][0]["nav"]["status"] = "IN_ORBIT"
        data = response(
            request.method,
            path,
            body=json.loads(request.content) if request.content else None,
        )
        if request.method == "POST":
            arrival = clock + 90
            completed["ships"][0]["nav"].update(status="IN_TRANSIT")
            completed["ships"][0]["nav"]["route"]["arrival"] = (
                start + timedelta(seconds=arrival)
            ).isoformat()
        return httpx.Response(200, json={"data": data})

    def sleep(seconds: float) -> None:
        nonlocal clock
        clock += seconds

    client = SpaceTradersClient(
        "synthetic",
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://test"
        ),
    )
    client._transport._interval = 0
    with (
        patch(
            "py_st.services.repositioning.time.monotonic",
            side_effect=lambda: clock,
        ),
        patch("py_st.services.automation.time.sleep", side_effect=sleep),
        patch("py_st.services.repositioning.datetime") as evidence_time,
        patch("py_st.services.automation.datetime") as arrival_time,
    ):
        for mocked in (evidence_time, arrival_time):
            mocked.now.side_effect = lambda _: start + timedelta(seconds=clock)
            mocked.fromisoformat.side_effect = datetime.fromisoformat
        run = Session(client, store, execute=True, root=completed["root"])
        if limiter == "session":
            run.deadline = 3
        original_deadline = run.deadline
        begin_action = store.begin_action

        def begin(scope: str, path: str, body: Any) -> int:
            expected = {"buyer": 60, "source": 5, "original": 5, "session": 3}[
                limiter
            ]
            assert run.deadline == pytest.approx(expected)
            if mode == "pacing":
                client._transport._next_request = clock + 61
            return begin_action(scope, path, body)

        try:
            with patch.object(store, "begin_action", side_effect=begin):
                if mode == "arrival":
                    result = reposition_run(run, plan)
                    assert result["status"] == "closed"
                    assert clock >= 90 > 60
                else:
                    with pytest.raises(
                        httpx.ReadTimeout if mode == "timeout" else SafetyStop
                    ):
                        reposition_run(run, plan)
            assert run.deadline == original_deadline
            assert len(dispatches) == (0 if mode == "pacing" else 1)
            action = store.actions(run.scope)[0]
            assert action["path"] == "/my/ships/H/navigate"
            assert (
                action["status"]
                == {
                    "pacing": "not_sent",
                    "retry": "rejected",
                    "timeout": "pending",
                    "arrival": "succeeded",
                }[mode]
            )
            assert store.pending(run.scope) is (mode == "timeout")
            position = next(
                p
                for p in store.latest(run.scope, "position")
                if p["key"] == "reposition:H"
            )
            assert position["data"]["status"] == (
                "closed" if mode == "arrival" else "open"
            )
        finally:
            run.close()
            client.close()
