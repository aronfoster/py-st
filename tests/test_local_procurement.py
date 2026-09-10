import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from py_st.client import SpaceTradersClient
from py_st.services.automation import SafetyStop, Session
from py_st.services.intelligence import Intelligence
from py_st.services.local_procurement import local_contract_run
from py_st.services.strategies import (
    contract_run,
    fleet_run,
    refuel_run,
    trade_run,
)


@pytest.fixture
def local(tmp_path: Path) -> Iterator[dict[str, Any]]:
    agent = {"symbol": "A", "credits": 100_000}
    contract = {
        "id": "C",
        "accepted": False,
        "fulfilled": False,
        "deadlineToAccept": "2099-01-01T00:00:00Z",
        "terms": {
            "deadline": "2099-01-02T00:00:00Z",
            "payment": {"onAccepted": 10_000, "onFulfilled": 20_000},
            "deliver": [
                {
                    "tradeSymbol": good,
                    "destinationSymbol": "X-A-M",
                    "unitsRequired": units,
                    "unitsFulfilled": 0,
                }
                for good, units in (("IRON", 5), ("COPPER", 3))
            ],
        },
    }
    ship = {
        "symbol": "S",
        "nav": {
            "systemSymbol": "X-A",
            "waypointSymbol": "X-A-M",
            "status": "IN_ORBIT",
            "flightMode": "CRUISE",
        },
        "cargo": {"capacity": 3, "units": 0, "inventory": []},
    }
    market = {
        "symbol": "X-A-M",
        "tradeGoods": [
            {"symbol": good, "purchasePrice": price, "tradeVolume": 2}
            for good, price in (("IRON", 100), ("COPPER", 200))
        ],
    }
    data: dict[str, Any] = {
        "agent": agent,
        "contract": contract,
        "ship": ship,
        "market": market,
        "posts": [],
        "contracts": [contract],
        "unknown": "",
    }

    def request(method: str, path: str, **kwargs: Any) -> Any:
        if method == "GET":
            if path == "/my/agent":
                result = data["agent"]
            elif path == "/my/ships":
                result = [data["ship"]]
            elif path == "/my/contracts":
                result = data["contracts"]
            elif path == "/my/ships/S":
                result = data["ship"]
            elif path == "/systems/X-A/waypoints/X-A-M/market":
                result = data["market"]
            else:
                raise AssertionError(path)
            return deepcopy(result)
        assert method == "POST"
        position = data["store"].latest("r:A", "position")[0]["data"]
        assert position["status"] == "open"
        assert position["plan"]["strategy"] == "local-multi"
        assert set(position["plan"]["purchase_ceilings"]) == {"IRON", "COPPER"}
        action = path.rsplit("/", 1)[-1]
        body = kwargs.get("body") or {}
        data["posts"].append((action, body))
        c = data["contract"]
        cargo = data["ship"]["cargo"]
        if action == "accept":
            assert not c["accepted"]
            c["accepted"] = True
            data["agent"]["credits"] += c["terms"]["payment"]["onAccepted"]
        elif action == "dock":
            data["ship"]["nav"]["status"] = "DOCKED"
        elif action == "purchase":
            good, units = body["symbol"], body["units"]
            quote = next(
                q for q in data["market"]["tradeGoods"] if q["symbol"] == good
            )
            assert 0 < units <= quote["tradeVolume"]
            assert cargo["units"] + units <= cargo["capacity"]
            cargo["units"] += units
            cargo["inventory"].append({"symbol": good, "units": units})
            data["agent"]["credits"] -= units * quote["purchasePrice"]
        elif action == "deliver":
            term = next(
                t
                for t in c["terms"]["deliver"]
                if t["tradeSymbol"] == body["tradeSymbol"]
            )
            term["unitsFulfilled"] += body["units"]
            assert term["unitsFulfilled"] <= term["unitsRequired"]
            cargo["units"] -= body["units"]
            cargo["inventory"] = [
                g
                for g in cargo["inventory"]
                if g["symbol"] != body["tradeSymbol"]
            ]
        elif action == "fulfill":
            assert all(
                t["unitsFulfilled"] == t["unitsRequired"]
                for t in c["terms"]["deliver"]
            )
            assert not c["fulfilled"]
            c["fulfilled"] = True
            data["agent"]["credits"] += c["terms"]["payment"]["onFulfilled"]
        else:
            raise AssertionError(f"Forbidden operation: {action}")
        if data["unknown"] == action:
            raise TimeoutError("response lost after dispatch")
        return {"agent": deepcopy(data["agent"]), "contract": deepcopy(c)}

    client = MagicMock()
    client.status.return_value = {"resetDate": "r"}
    client.request.side_effect = request
    store = Intelligence(tmp_path / "ledger.sqlite3")
    data.update(
        client=client,
        store=store,
        root=tmp_path,
        run=Session(client, store, execute=True, root=tmp_path),
    )
    with patch("py_st.services.automation.cache.clear_cache"):
        yield data
    data["run"].close()
    store.close()


def restart(data: dict[str, Any]) -> Session:
    data["run"].close()
    run = Session(
        data["client"], data["store"], execute=True, root=data["root"]
    )
    data["run"] = run
    return run


def test_existing_contract_entrypoint_runs_multi_good_workflow(
    local: dict[str, Any],
) -> None:
    # Act
    result = contract_run(local["run"], "S", "C")
    repeated = contract_run(restart(local), "S", "C")

    # Assert
    assert result["status"] == repeated["status"] == "fulfilled"
    assert len(local["posts"]) == 13
    assert local["agent"]["credits"] == 128_900


def test_completed_external_contract_needs_no_execution_plan(
    local: dict[str, Any],
) -> None:
    # Arrange: a fulfilled contract is a no-op unless an intent needs recovery.
    local["contract"].update(accepted=True, fulfilled=True)
    for term in local["contract"]["terms"]["deliver"]:
        term["unitsFulfilled"] = term["unitsRequired"]

    # Act
    result = contract_run(local["run"], "S", "C")

    # Assert
    assert result == {"status": "already fulfilled", "contract": "C"}
    assert local["posts"] == []
    assert local["store"].latest("r:A", "position") == []


@pytest.mark.parametrize("during_quote", [False, True])
@pytest.mark.parametrize("dispatcher", [False, True])
def test_duplicate_contract_identity_cannot_authorize_purchase(
    local: dict[str, Any], during_quote: bool, dispatcher: bool
) -> None:
    # Arrange: conflicting observations must not select the first row.
    duplicate = deepcopy(local["contract"])
    duplicate["accepted"] = True
    request = local["client"].request.side_effect

    def changed(method: str, path: str, **kwargs: Any) -> Any:
        if during_quote and path.endswith("/market"):
            local["contracts"].append(deepcopy(duplicate))
        return request(method, path, **kwargs)

    if not during_quote:
        local["contracts"].append(duplicate)
    local["client"].request.side_effect = changed

    # Act / Assert
    with pytest.raises(SafetyStop, match="uniquely present"):
        runner = contract_run if dispatcher else local_contract_run
        runner(local["run"], "S", "C")
    assert local["posts"] == []
    assert local["store"].latest("r:A", "position") == []


@pytest.mark.parametrize(
    "change", ["terms", "delivery", "payment", "nav", "cargo", "inventory"]
)
def test_malformed_multi_good_evidence_has_recovery_error(
    local: dict[str, Any], change: str
) -> None:
    # Arrange: incomplete observations must produce an actionable SafetyStop.
    if change == "terms":
        local["contract"]["terms"] = None
    elif change == "delivery":
        local["contract"]["terms"]["deliver"][0] = None
    elif change == "payment":
        local["contract"]["terms"]["payment"] = None
    elif change in ("nav", "cargo"):
        local["ship"][change] = None
    else:
        local["ship"]["cargo"]["inventory"] = None

    # Act / Assert
    with pytest.raises(SafetyStop, match="Invalid"):
        local_contract_run(local["run"], "S", "C")
    assert local["posts"] == []
    assert local["store"].latest("r:A", "position") == []


@pytest.mark.parametrize("field", ["accepted", "fulfilled"])
@pytest.mark.parametrize("value", ["false", 1, None])
def test_invalid_contract_flags_do_not_close_execution_intent(
    local: dict[str, Any], field: str, value: Any
) -> None:
    # Arrange: all deliveries are complete, but fulfillment is not established.
    local["run"].remaining = 1
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(local["run"], "S", "C")
    for term in local["contract"]["terms"]["deliver"]:
        term["unitsFulfilled"] = term["unitsRequired"]
    local["contract"][field] = value
    before = local["store"].latest("r:A", "position")
    posts = len(local["posts"])

    # Act / Assert
    with pytest.raises(SafetyStop, match="flags"):
        contract_run(restart(local), "S", "C")
    assert local["store"].latest("r:A", "position") == before
    assert len(local["posts"]) == posts


@pytest.mark.parametrize("during_quote", [False, True])
def test_malformed_other_obligation_is_not_treated_as_fulfilled(
    local: dict[str, Any], during_quote: bool
) -> None:
    # Arrange
    other = {"id": "OTHER", "accepted": True, "fulfilled": "false"}
    request = local["client"].request.side_effect

    def changed(method: str, path: str, **kwargs: Any) -> Any:
        result = request(method, path, **kwargs)
        if path.endswith("/market"):
            local["contracts"].append(other)
        return result

    if during_quote:
        local["client"].request.side_effect = changed
    else:
        local["contracts"].append(other)

    # Act / Assert
    with pytest.raises(SafetyStop, match="flags"):
        contract_run(local["run"], "S", "C")
    assert local["posts"] == []


def test_dispatch_uses_saved_strategy_before_changed_term_shortcut(
    local: dict[str, Any],
) -> None:
    # Arrange: a saved multi-good intent must not become a single-good run.
    local["run"].remaining = 1
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(local["run"], "S", "C")
    local["contract"]["terms"]["deliver"].pop()
    before = len(local["posts"])

    # Act / Assert
    with pytest.raises(SafetyStop, match="multiple goods"):
        contract_run(restart(local), "S", "C")
    assert len(local["posts"]) == before


@pytest.mark.parametrize("operation", ["fleet", "trade", "refuel"])
@pytest.mark.parametrize("ship", ["S", "ANOTHER"])
def test_unaccepted_intent_protects_account_wide_funds(
    local: dict[str, Any], operation: str, ship: str
) -> None:
    # Arrange: a known pre-acceptance stop still reserves all the goods.
    run = local["run"]
    run.remaining = 0
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C")
    before = local["store"].latest("r:A", "position")
    assert not local["contract"]["accepted"]
    assert not local["store"].pending("r:A")
    run.remaining = 30

    # Act / Assert: no navigation/docking/spending by unrelated workflows.
    with pytest.raises(SafetyStop, match="nonclosed procurement"):
        if operation == "fleet":
            fleet_run(run)
        elif operation == "trade":
            trade_run(run, ship, "X-A-M", "X-A-D", "IRON")
        else:
            refuel_run(run, ship)
    assert local["posts"] == []
    assert local["store"].latest("r:A", "position") == before


@pytest.mark.parametrize("stop_after", range(1, 14))
def test_new_session_resumes_after_every_action(
    local: dict[str, Any], stop_after: int
) -> None:
    # Arrange: 1 acceptance + 1 dock + 5 purchases/deliveries + 1 fulfill.
    local["run"].remaining = stop_after
    if stop_after < 13:
        with pytest.raises(SafetyStop, match="budget"):
            local_contract_run(local["run"], "S", "C")
    else:
        local_contract_run(local["run"], "S", "C")
    original = local["store"].latest("r:A", "position")[0]["data"]["plan"]
    before = local["agent"]["credits"]
    # Act: a new Session shares only synthetic API state and the ledger.
    result = local_contract_run(restart(local), "S", "C")
    # Assert: no known success is replayed and original ceilings survive.
    assert result["status"] == "fulfilled"
    assert (
        result["session_credit_change"] == local["agent"]["credits"] - before
    )
    assert result["plan"] == original
    assert local["agent"]["credits"] == 128_900
    assert len(local["posts"]) == 13
    assert (
        local["store"].latest("r:A", "position")[0]["data"]["status"]
        == "closed"
    )


def test_dry_run_full_reserve_and_batches(local: dict[str, Any]) -> None:
    local["run"].execute = False
    plan = local_contract_run(local["run"], "S", "C")
    assert plan["protected_credits"] == 52_320
    assert plan["remaining_goods_reserve"] == 1320
    assert plan["goods"]["IRON"] == {
        "remaining": 5,
        "held": 0,
        "to_buy": 5,
        "purchase_batches": 3,
    }
    assert plan["goods"]["COPPER"]["purchase_batches"] == 2
    assert plan["travel_fuel_reserve"] == 0
    assert not local["posts"]
    assert not local["store"].latest("r:A", "position")


@pytest.mark.parametrize(
    "guard",
    [
        "funds",
        "profit",
        "other",
        "unknown_position",
        "pending",
        "moving",
        "mode",
        "location",
        "source",
        "untracked",
        "excess",
        "duplicate",
        "destination",
        "negative",
        "overfulfilled",
        "boolean",
        "expiry",
        "deadline",
        "missing_quote",
        "duplicate_quote",
        "accepted_plan",
    ],
)
def test_pre_mutation_guards(local: dict[str, Any], guard: str) -> None:
    c, s = local["contract"], local["ship"]
    term = c["terms"]["deliver"][1]
    source = ""
    if guard == "funds":
        local["agent"]["credits"] = 52_319
    elif guard == "profit":
        c["terms"]["payment"] = {"onAccepted": 0, "onFulfilled": 1}
    elif guard == "other":
        local["contracts"].append(c | {"id": "OTHER", "accepted": True})
    elif guard == "unknown_position":
        local["store"].observe("r:A", "position", "unknown:S", {})
    elif guard == "pending":
        local["store"].begin_action("r:A", "/my/contracts/C/accept", {})
    elif guard == "moving":
        s["nav"]["status"] = "IN_TRANSIT"
    elif guard == "mode":
        s["nav"]["flightMode"] = "DRIFT"
    elif guard == "location":
        s["nav"]["waypointSymbol"] = "X-A-X"
    elif guard == "source":
        source = "X-A-X"
    elif guard in ("untracked", "excess"):
        s["cargo"].update(
            capacity=10,
            units=6,
            inventory=[
                {
                    "symbol": "FOOD" if guard == "untracked" else "IRON",
                    "units": 6,
                }
            ],
        )
    elif guard == "duplicate":
        term["tradeSymbol"] = "IRON"
    elif guard == "destination":
        term["destinationSymbol"] = "X-A-X"
    elif guard == "negative":
        term["unitsRequired"] = -1
    elif guard == "overfulfilled":
        term["unitsFulfilled"] = 4
    elif guard == "boolean":
        term["unitsRequired"] = True
    elif guard == "expiry":
        c["deadlineToAccept"] = "2000-01-01T00:00:00Z"
    elif guard == "deadline":
        c["terms"]["deadline"] = (
            datetime.now(UTC) + timedelta(minutes=30)
        ).isoformat()
    elif guard == "missing_quote":
        local["market"]["tradeGoods"].pop()
    elif guard == "duplicate_quote":
        local["market"]["tradeGoods"].append(local["market"]["tradeGoods"][0])
    else:
        c["accepted"] = True
    with pytest.raises(SafetyStop):
        local_contract_run(local["run"], "S", "C", source)
    assert not local["posts"]


@pytest.mark.parametrize(
    "action", ["accept", "dock", "purchase", "deliver", "fulfill"]
)
def test_unknown_outcome_blocks_new_session(
    local: dict[str, Any], action: str
) -> None:
    local["unknown"] = action
    with pytest.raises(TimeoutError):
        local_contract_run(local["run"], "S", "C")
    posts = deepcopy(local["posts"])
    with pytest.raises(SafetyStop, match="pending"):
        local_contract_run(restart(local), "S", "C")
    assert local["posts"] == posts
    assert local["store"].pending("r:A")


@pytest.mark.parametrize(
    "change",
    ["ship", "source", "required", "payment", "deadline", "price", "funds"],
)
def test_original_plan_and_whole_reserve_survive_restart(
    local: dict[str, Any], change: str
) -> None:
    local["run"].remaining = 2
    with pytest.raises(SafetyStop, match="budget"):
        local_contract_run(local["run"], "S", "C")
    source, ship = "", "S"
    if change == "ship":
        ship = "OTHER"
    elif change == "source":
        source = "X-A-X"
    elif change == "required":
        local["contract"]["terms"]["deliver"][1]["unitsRequired"] += 1
    elif change == "payment":
        local["contract"]["terms"]["payment"]["onFulfilled"] += 1
    elif change == "deadline":
        local["contract"]["terms"]["deadline"] = "2099-02-01T00:00:00Z"
    elif change == "price":
        local["market"]["tradeGoods"][1]["purchasePrice"] = 241
    else:
        local["agent"]["credits"] = 52_319
    with pytest.raises(SafetyStop):
        local_contract_run(restart(local), ship, "C", source)
    assert len(local["posts"]) == 2


def test_completion_first_without_quotes_or_liquidity(
    local: dict[str, Any],
) -> None:
    local["run"].remaining = 11  # Last purchase, before delivery/fulfillment.
    with pytest.raises(SafetyStop, match="budget"):
        local_contract_run(local["run"], "S", "C")
    local["market"].pop("tradeGoods")
    local["agent"]["credits"] = 0
    result = local_contract_run(restart(local), "S", "C")
    assert result["status"] == "fulfilled"
    assert [a for a, _ in local["posts"][-2:]] == ["deliver", "fulfill"]


def test_owned_goods_allocated_once_without_quotes(
    local: dict[str, Any],
) -> None:
    local["ship"]["cargo"].update(
        capacity=10,
        units=8,
        inventory=[
            {"symbol": "IRON", "units": 2},
            {"symbol": "IRON", "units": 3},
            {"symbol": "COPPER", "units": 3},
        ],
    )
    local["market"].pop("tradeGoods")
    result = local_contract_run(local["run"], "S", "C")
    assert result["status"] == "fulfilled"
    assert [b["units"] for a, b in local["posts"] if a == "deliver"] == [5, 3]
    assert not any(a == "purchase" for a, _ in local["posts"])


def test_accepted_obligation_not_rejected_for_negative_future_profit(
    local: dict[str, Any],
) -> None:
    local["contract"]["terms"]["payment"] = {
        "onAccepted": 10_000,
        "onFulfilled": 1,
    }
    local["run"].remaining = 1
    with pytest.raises(SafetyStop, match="budget"):
        local_contract_run(local["run"], "S", "C")
    assert (
        local_contract_run(restart(local), "S", "C")["status"] == "fulfilled"
    )


@pytest.mark.parametrize(
    "change",
    ["price", "funds", "contract", "position", "mode", "movement", "cargo"],
)
def test_docking_rechecks_before_purchase(
    local: dict[str, Any],
    change: str,
) -> None:
    original = local["client"].request.side_effect

    def request(method: str, path: str, **kwargs: Any) -> Any:
        result = original(method, path, **kwargs)
        if method == "POST" and path.endswith("/dock"):
            if change == "price":
                local["market"]["tradeGoods"][1]["purchasePrice"] = 241
            elif change == "funds":
                local["agent"]["credits"] = 52_319
            elif change == "contract":
                local["contracts"].append(local["contract"] | {"id": "OTHER"})
            elif change == "position":
                local["store"].observe("r:A", "position", "unknown:P", {})
            elif change == "mode":
                local["ship"]["nav"]["flightMode"] = "BURN"
            elif change == "movement":
                local["ship"]["nav"]["status"] = "IN_TRANSIT"
            else:
                local["ship"]["cargo"].update(
                    units=1, inventory=[{"symbol": "FOOD", "units": 1}]
                )
        return result

    local["client"].request.side_effect = request
    with pytest.raises(SafetyStop):
        local_contract_run(local["run"], "S", "C")
    assert [a for a, _ in local["posts"]] == ["accept", "dock"]


@pytest.mark.parametrize("expired", [False, True])
def test_completion_uses_actual_deadline_not_acquisition_margin(
    local: dict[str, Any], expired: bool
) -> None:
    local["run"].remaining = 11
    with pytest.raises(SafetyStop, match="budget"):
        local_contract_run(local["run"], "S", "C")
    deadline = datetime.fromisoformat(local["contract"]["terms"]["deadline"])
    now = (
        deadline + timedelta(seconds=1)
        if expired
        else deadline - timedelta(minutes=30)
    )
    local["market"].pop("tradeGoods")
    with patch(
        "py_st.services.local_procurement.datetime", wraps=datetime
    ) as clock:
        clock.now.return_value = now
        if expired:
            with pytest.raises(SafetyStop, match="deadline expired"):
                local_contract_run(restart(local), "S", "C")
            assert len(local["posts"]) == 11
        else:
            assert (
                local_contract_run(restart(local), "S", "C")["status"]
                == "fulfilled"
            )


def test_wall_clock_stop_after_purchase_preserves_recovery(
    local: dict[str, Any],
) -> None:
    original = local["client"].request.side_effect
    clock = 0.0
    local["run"].deadline = 600

    def request(method: str, path: str, **kwargs: Any) -> Any:
        nonlocal clock
        result = original(method, path, **kwargs)
        if method == "POST" and path.endswith("/purchase"):
            clock = 601
        return result

    local["client"].request.side_effect = request
    with (
        patch(
            "py_st.services.local_procurement.time.monotonic",
            side_effect=lambda: clock,
        ),
        pytest.raises(SafetyStop, match="Wall-clock"),
    ):
        local_contract_run(local["run"], "S", "C")
    local["client"].request.side_effect = original
    assert not local["store"].pending("r:A")
    assert (
        local_contract_run(restart(local), "S", "C")["status"] == "fulfilled"
    )
    assert len(local["posts"]) == 13


def test_unknown_own_position_is_not_overwritten(
    local: dict[str, Any],
) -> None:
    local["store"].observe("r:A", "position", "procurement:C", {})
    with pytest.raises(SafetyStop, match="Original"):
        local_contract_run(local["run"], "S", "C")
    assert not local["posts"]


def test_partial_owned_delivery_precedes_missing_other_quote(
    local: dict[str, Any],
) -> None:
    local["run"].remaining = 3
    with pytest.raises(SafetyStop, match="budget"):
        local_contract_run(local["run"], "S", "C")
    local["market"].pop("tradeGoods")
    with pytest.raises(SafetyStop, match="acquisition"):
        local_contract_run(restart(local), "S", "C")
    assert local["posts"][-1] == (
        "deliver",
        {
            "shipSymbol": "S",
            "tradeSymbol": "IRON",
            "units": 2,
        },
    )
    assert local["ship"]["cargo"]["units"] == 0


def test_expiry_during_market_get_prevents_acceptance(
    local: dict[str, Any],
) -> None:
    original = local["client"].request.side_effect
    with patch(
        "py_st.services.local_procurement.datetime", wraps=datetime
    ) as clock:
        clock.now.return_value = datetime(2098, 12, 31, tzinfo=UTC)

        def request(method: str, path: str, **kwargs: Any) -> Any:
            result = original(method, path, **kwargs)
            if path.endswith("/market"):
                clock.now.return_value = datetime(2099, 1, 1, tzinfo=UTC)
            return result

        local["client"].request.side_effect = request
        with pytest.raises(SafetyStop, match="evidence expired"):
            local_contract_run(local["run"], "S", "C")
    assert not local["posts"]


@pytest.mark.parametrize("stage", ["accept", "purchase"])
@pytest.mark.parametrize("during", ["market", "agent"])
@pytest.mark.parametrize(
    "change", ["mode", "nav", "cargo", "other", "credits", "terms", "position"]
)
def test_post_quote_revalidation(
    local: dict[str, Any], stage: str, during: str, change: str
) -> None:
    # Arrange: inject after returning evidence, not before the initial refresh.
    if stage == "purchase":
        local["run"].remaining = 2
        with pytest.raises(SafetyStop, match="budget"):
            local_contract_run(local["run"], "S", "C")
        restart(local)
    before = deepcopy(local["posts"])
    original = local["client"].request.side_effect
    agent_reads = 0
    injected = False

    def request(method: str, path: str, **kwargs: Any) -> Any:
        nonlocal agent_reads, injected
        result = original(method, path, **kwargs)
        if path == "/my/agent":
            agent_reads += 1
        trigger = (
            path.endswith("/market")
            if during == "market"
            else (path == "/my/agent" and agent_reads == 2)
        )
        if not injected and trigger:
            injected = True
            if change == "mode":
                local["ship"]["nav"]["flightMode"] = "DRIFT"
            elif change == "nav":
                local["ship"]["nav"]["status"] = "IN_TRANSIT"
            elif change == "cargo":
                local["ship"]["cargo"].update(
                    units=1, inventory=[{"symbol": "IRON", "units": 1}]
                )
            elif change == "other":
                local["contracts"].append(
                    local["contract"] | {"id": "OTHER", "accepted": True}
                )
            elif change == "credits":
                local["agent"]["credits"] = 52_319
            elif change == "terms":
                local["contract"]["terms"]["deliver"][1]["unitsRequired"] += 1
            else:
                local["store"].observe("r:A", "position", "unknown:P", {})
        return result

    local["client"].request.side_effect = request
    # Act/Assert: no stale acceptance or purchase, including stale credit GETs.
    with pytest.raises(SafetyStop):
        local_contract_run(local["run"], "S", "C")
    assert injected
    assert local["posts"] == before
    if stage == "accept":
        assert not any(
            p["key"] == "procurement:C"
            for p in local["store"].latest("r:A", "position")
        )


def test_revalidation_ignores_cooldown_and_route_metadata(
    local: dict[str, Any],
) -> None:
    original = local["client"].request.side_effect

    def request(method: str, path: str, **kwargs: Any) -> Any:
        result = original(method, path, **kwargs)
        if path.endswith("/market"):
            local["ship"]["cooldown"] = {"remainingSeconds": 12}
            local["ship"]["nav"]["route"] = {"arrival": "2099-01-01T00:00:00Z"}
        elif path == "/my/ships/S":
            local["ship"]["cooldown"] = {"remainingSeconds": 11}
        return result

    local["client"].request.side_effect = request
    assert local_contract_run(local["run"], "S", "C")["status"] == "fulfilled"


def test_local_batches_deliver_each_purchase_not_full_loads(
    local: dict[str, Any],
) -> None:
    local["contract"]["terms"]["deliver"][0]["unitsRequired"] = 80
    local["ship"]["cargo"]["capacity"] = 40
    local["market"]["tradeGoods"][0]["tradeVolume"] = 30
    local["run"].execute = False
    plan = local_contract_run(local["run"], "S", "C")
    assert plan["goods"]["IRON"]["purchase_batches"] == 3
    local["run"].execute = True
    local_contract_run(local["run"], "S", "C")
    assert [
        b["units"]
        for a, b in local["posts"]
        if a == "purchase" and b["symbol"] == "IRON"
    ] == [30, 30, 20]
    assert [a for a, _ in local["posts"]][2:8] == ["purchase", "deliver"] * 3


@pytest.mark.parametrize("mode", ["pacing", "retry", "timeout", "success"])
@pytest.mark.parametrize(
    "stage,limiter",
    [
        ("accept", "quote"),
        ("purchase", "quote"),
        ("dock", "quote"),
        ("accept", "expiry"),
        ("accept", "lead"),
        ("purchase", "lead"),
        ("dock", "lead"),
        ("deliver", "actual"),
        ("fulfill", "actual"),
        ("completion-dock", "actual"),
        ("accept", "session"),
    ],
)
def test_transport_waits_cannot_outlive_evidence(
    local: dict[str, Any], mode: str, stage: str, limiter: str
) -> None:
    # Arrange: the real transport paces/retries; only its HTTP peer is fake.
    start = datetime(2098, 1, 1, tzinfo=UTC)
    clock = 0.0
    deadline_seconds = {"lead": 3605, "actual": 5}.get(limiter, 7200)
    local["contract"]["terms"]["deadline"] = (
        start + timedelta(seconds=deadline_seconds)
    ).isoformat()
    local["contract"]["deadlineToAccept"] = (
        start + timedelta(seconds=5 if limiter == "expiry" else 3600)
    ).isoformat()
    stop = {
        "accept": 0,
        "dock": 1,
        "purchase": 2,
        "deliver": 3,
        "fulfill": 12,
        "completion-dock": 3,
    }[stage]
    if stop:
        local["run"].remaining = stop
        with pytest.raises(SafetyStop, match="budget"):
            local_contract_run(local["run"], "S", "C")
    if stage == "completion-dock":
        local["ship"]["nav"]["status"] = "IN_ORBIT"
    local["run"].close()
    response = local["client"].request.side_effect
    dispatches = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, json={"resetDate": "r"})
        if request.method == "POST":
            dispatches.append(request.url.path)
            if mode == "retry":
                return httpx.Response(
                    429,
                    json={"error": {"code": 429}},
                    headers={"Retry-After": "61"},
                )
            if mode == "timeout":
                raise httpx.ReadTimeout("Lost mutation response")
        return httpx.Response(
            200,
            json={
                "data": response(
                    request.method,
                    request.url.path,
                    body=(
                        json.loads(request.content)
                        if request.content
                        else None
                    ),
                )
            },
        )

    def sleep(seconds: float) -> None:
        nonlocal clock
        clock += seconds

    with (
        SpaceTradersClient(
            "synthetic",
            client=httpx.Client(
                transport=httpx.MockTransport(handler), base_url="https://test"
            ),
        ) as client,
        patch(
            "py_st.services.local_procurement.time.monotonic",
            side_effect=lambda: clock,
        ),
        patch("py_st.services.automation.time.sleep", side_effect=sleep),
        patch(
            "py_st.services.local_procurement.datetime", wraps=datetime
        ) as now,
    ):
        now.now.side_effect = lambda _: start + timedelta(seconds=clock)
        client._transport._interval = 0
        run = Session(client, local["store"], execute=True, root=local["root"])
        local["run"] = run
        run.remaining = 1
        if limiter == "session":
            run.deadline = 3
        original_deadline = run.deadline
        store: Intelligence = local["store"]
        begin_action = store.begin_action
        caps = []

        def begin(scope: str, path: str, body: Any) -> int:
            caps.append(run.deadline)
            if mode == "pacing":
                client._transport._next_request = clock + 61
            elif mode == "success":
                client._transport._next_request = clock + 1
            return begin_action(scope, path, body)

        # Act: pace/retry within the cap; restore it on success and failure.
        with patch.object(store, "begin_action", side_effect=begin):
            if mode == "success" and stage == "fulfill":
                assert (
                    local_contract_run(run, "S", "C")["status"] == "fulfilled"
                )
            else:
                with pytest.raises(
                    httpx.ReadTimeout if mode == "timeout" else SafetyStop
                ):
                    local_contract_run(run, "S", "C")
        # Assert: known nondispatch/rejection, not unknown or a blind replay.
        target = (
            "ships/S"
            if stage in ("dock", "completion-dock", "purchase")
            else "contracts/C"
        )
        assert dispatches == (
            []
            if mode == "pacing"
            else [f"/my/{target}/{stage.removeprefix('completion-')}"]
        )
        expected = {"quote": 60, "session": 3}.get(limiter, 5)
        assert caps == [pytest.approx(expected)]
        elapsed = {"success": 1, "timeout": 0}.get(mode, expected)
        assert clock == pytest.approx(elapsed)
        assert run.deadline == original_deadline
        assert store.pending("r:A") is (mode == "timeout")
        assert (
            store.actions("r:A")[0]["status"]
            == {
                "pacing": "not_sent",
                "retry": "rejected",
                "timeout": "pending",
                "success": "succeeded",
            }[mode]
        )
