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
from py_st.services.procurement_recovery import abandon_procurement
from py_st.services.remote_procurement import remote_contract_run
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


@pytest.mark.parametrize("field", ["accepted", "fulfilled"])
@pytest.mark.parametrize("value", ["false", 1, None])
def test_remote_invalid_flags_preserve_recovery_intent(
    remote: tuple[Any, ...], field: str, value: Any
) -> None:
    # Arrange: a saved accepted position must never close on a truthy non-bool.
    run, _, contract, _, _, _, posts = remote
    run.remaining = 1
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C", "X-A-S")
    contract[field] = value
    before = run.store.latest(run.scope, "position")
    count = len(posts)
    run.remaining = 30

    # Act / Assert: exercise the remote loop's own admission.
    with pytest.raises(SafetyStop, match="flags"):
        remote_contract_run(run, "S", "C", "X-A-S")
    assert run.store.latest(run.scope, "position") == before
    assert len(posts) == count


@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize(
    "change", ["cargo", "fuel", "observer", "terms", "obligation", "position"]
)
def test_remote_acquisition_rechecks_eligibility_after_quotes(
    remote: tuple[Any, ...], accepted: bool, change: str
) -> None:
    # Arrange: mutate fake state while market observation is in progress.
    run, _, contract, ship, probe, _, posts = remote
    if accepted:
        run.remaining = 1
        with pytest.raises(SafetyStop, match="budget"):
            contract_run(run, "S", "C", "X-A-S")
        run.remaining = 30
        ship["nav"]["status"] = "DOCKED"
    request = run.client.request.side_effect
    changed = False
    count = len(posts)

    def observe(method: str, path: str, **kwargs: Any) -> Any:
        nonlocal changed
        if path == "/systems/X-A/waypoints/X-A-S/market" and not changed:
            changed = True
            if change == "cargo":
                ship["cargo"].update(
                    units=1, inventory=[{"symbol": "EQUIPMENT", "units": 1}]
                )
            elif change == "fuel":
                ship["fuel"]["current"] = 1
            elif change == "observer":
                probe["nav"]["waypointSymbol"] = "X-A-OTHER"
            elif change == "terms":
                contract["terms"]["payment"]["onFulfilled"] = 0
            elif change == "position":
                run.store.observe(
                    run.scope, "position", "trade:OTHER", {"status": "open"}
                )
        result = request(method, path, **kwargs)
        if changed and change == "obligation" and path == "/my/contracts":
            result.append(
                {"id": "OTHER", "accepted": True, "fulfilled": False}
            )
        return result

    run.client.request.side_effect = observe

    # Act / Assert: no acceptance, preparation or goods spending after drift.
    with pytest.raises(SafetyStop):
        remote_contract_run(run, "S", "C", "X-A-S")
    assert changed
    assert len(posts) == count


@pytest.mark.parametrize(
    "limiter,stage",
    [
        ("quote", "accept"),
        ("expiry", "accept"),
        ("lead", "accept"),
        ("actual", "deliver"),
        ("actual", "fulfill"),
    ],
)
@pytest.mark.parametrize("retry", [False, True])
def test_remote_transport_stops_at_acquisition_evidence_deadline(
    remote: tuple[Any, ...], limiter: str, stage: str, retry: bool
) -> None:
    # Arrange: real transport waits against a fake clock and HTTP peer.
    old, _, contract, _, _, _, posts = remote
    if stage != "accept":
        old.remaining = 7 if stage == "deliver" else 8
        with pytest.raises(SafetyStop, match="budget"):
            contract_run(old, "S", "C", "X-A-S")
    count = len(posts)
    old.close()
    start = datetime(2098, 1, 1, tzinfo=UTC)
    clock = 0.0
    contract["deadlineToAccept"] = (
        start + timedelta(seconds=5 if limiter == "expiry" else 3600)
    ).isoformat()
    contract["terms"]["deadline"] = (
        start
        + timedelta(seconds={"lead": 3816, "actual": 65}.get(limiter, 7200))
    ).isoformat()
    response = old.client.request.side_effect
    dispatches = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, json={"resetDate": "r"})
        if request.method == "POST":
            dispatches.append(request.url.path)
            return httpx.Response(
                429,
                json={"error": {"code": 429}},
                headers={"Retry-After": "71"},
            )
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
            "py_st.services.remote_procurement.time.monotonic",
            side_effect=lambda: clock,
        ),
        patch("py_st.services.automation.time.sleep", side_effect=sleep),
        patch(
            "py_st.services.remote_procurement.datetime", wraps=datetime
        ) as now,
    ):
        now.now.side_effect = lambda _: start + timedelta(seconds=clock)
        client._transport._interval = 0
        run = Session(client, old.store, execute=True, root=old.root)
        budget = run.deadline
        store: Intelligence = old.store
        begin_action = store.begin_action

        def begin(scope: str, path: str, body: Any) -> int:
            if not retry:
                client._transport._next_request = clock + 71
            return begin_action(scope, path, body)

        try:
            # Act
            with (
                patch.object(old.store, "begin_action", side_effect=begin),
                pytest.raises(SafetyStop),
            ):
                remote_contract_run(run, "S", "C", "X-A-S")

            # Assert: no stale dispatch or retry, with resumable local intent.
            assert clock == pytest.approx(
                {"quote": 60, "actual": 65}.get(limiter, 5)
            )
            assert dispatches == (
                [f"/my/contracts/C/{stage}"] if retry else []
            )
            assert old.store.actions("r:A")[0]["status"] == (
                "rejected" if retry else "not_sent"
            )
            assert not old.store.pending("r:A")
            assert run.deadline == budget
            assert len(posts) == count
            position = old.store.latest("r:A", "position")[0]["data"]
            assert position["status"] == "open"
        finally:
            run.close()


@pytest.mark.parametrize("change", ["obligation", "destination"])
def test_remote_refreshes_obligations_after_navigation(
    remote: tuple[Any, ...], change: str
) -> None:
    # Arrange: acquire cargo, then change evidence during the navigation POST.
    run, _, contract, _, _, _, posts = remote
    run.remaining = 4
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C", "X-A-S")
    run.remaining = 30
    request = run.client.request.side_effect
    navigated = False
    count = len(posts)

    def changed(method: str, path: str, **kwargs: Any) -> Any:
        nonlocal navigated
        result = request(method, path, **kwargs)
        if path.endswith("/navigate") and method == "POST":
            navigated = True
            if change == "destination":
                delivery = contract["terms"]["deliver"][0]
                delivery["destinationSymbol"] = "X-A-OTHER"
        if navigated and change == "obligation" and path == "/my/contracts":
            result.append(
                {"id": "OTHER", "accepted": True, "fulfilled": False}
            )
        return result

    run.client.request.side_effect = changed

    # Act / Assert: confirm arrival, then reobserve before dock or delivery.
    with pytest.raises(SafetyStop):
        remote_contract_run(run, "S", "C", "X-A-S")
    assert navigated
    assert [p.rsplit("/", 1)[-1] for p, _ in posts[count:]] == [
        "orbit",
        "navigate",
    ]


@pytest.mark.parametrize("change", ["false_completion", "negative", "bool"])
def test_remote_conflicting_progress_never_releases_saved_intent(
    remote: tuple[Any, ...], change: str
) -> None:
    run, _, contract, _, _, _, posts = remote
    run.remaining = 1
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C", "X-A-S")
    run.remaining = 30
    if change == "false_completion":
        contract["fulfilled"] = True
    else:
        contract["terms"]["deliver"][0]["unitsFulfilled"] = (
            -1 if change == "negative" else True
        )
    before = run.store.latest(run.scope, "position")
    count = len(posts)

    with pytest.raises(SafetyStop, match="progress|quantities"):
        remote_contract_run(run, "S", "C", "X-A-S")
    assert run.store.latest(run.scope, "position") == before
    assert len(posts) == count


def test_remote_arrival_polling_discards_pre_wait_contract(
    remote: tuple[Any, ...],
) -> None:
    run, _, contract, ship, _, _, posts = remote
    run.remaining = 4
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C", "X-A-S")
    run.remaining = 30
    ship["nav"]["status"] = "IN_TRANSIT"
    request = run.client.request.side_effect
    count = len(posts)

    def arrive(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/my/ships/S":
            ship["nav"].update(status="IN_ORBIT", waypointSymbol="X-A-D")
            contract["terms"]["deliver"][0]["destinationSymbol"] = "X-A-OTHER"
        return request(method, path, **kwargs)

    run.client.request.side_effect = arrive

    with pytest.raises(SafetyStop, match="terms changed"):
        remote_contract_run(run, "S", "C", "X-A-S")
    assert len(posts) == count
    assert ship["cargo"]["units"] == 26


@pytest.mark.parametrize("market_kind", ["source", "fuel"])
@pytest.mark.parametrize(
    "change", ["duplicate", "boolean_price", "boolean_volume", "fractional"]
)
def test_remote_requires_unique_positive_integer_quotes(
    remote: tuple[Any, ...], market_kind: str, change: str
) -> None:
    run, _, _, _, _, markets, posts = remote
    waypoint, good = (
        ("X-A-S", "EQUIPMENT")
        if market_kind == "source"
        else ("X-A-D", "FUEL")
    )
    goods = markets[waypoint]["tradeGoods"]
    quote = next(q for q in goods if q["symbol"] == good)
    if change == "duplicate":
        goods.append(quote | {"purchasePrice": 999_999})
    elif change == "boolean_price":
        quote["purchasePrice"] = True
    elif change == "boolean_volume":
        quote["tradeVolume"] = True
    else:
        quote["purchasePrice"] = 1.5

    with pytest.raises(SafetyStop, match="quote|price/volume"):
        remote_contract_run(run, "S", "C", "X-A-S")
    assert posts == []
    assert run.store.latest("r:A", "position") == []


@pytest.mark.parametrize(
    "change", ["closed", "unknown", "contract", "missing_contract", "strategy"]
)
def test_remote_saved_intent_cannot_regain_authority_from_invalid_identity(
    remote: tuple[Any, ...], change: str
) -> None:
    run, _, _, _, _, _, posts = remote
    run.remaining = 1
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C", "X-A-S")
    run.remaining = 30
    position = run.store.latest(run.scope, "position")[0]["data"]
    if change == "closed":
        position.update(status="closed", stage="fulfilled")
    elif change == "unknown":
        position["status"] = "review"
    elif change == "contract":
        position["plan"]["contract"] = "OTHER"
    elif change == "missing_contract":
        position["plan"].pop("contract")
    else:
        position["strategy"] = "unrecognized"
    run.store.observe(run.scope, "position", "procurement:C", position)
    before = run.store.latest(run.scope, "position")
    count = len(posts)

    with pytest.raises(SafetyStop, match="identity/status"):
        remote_contract_run(run, "S", "C", "X-A-S")
    assert run.store.latest(run.scope, "position") == before
    assert len(posts) == count


def test_remote_dryrun_costs_full_obligation_without_mutating(
    remote: tuple[Any, ...],
) -> None:
    run, _, _, _, _, _, posts = remote
    run.execute = False
    plan = contract_run(run, "S", "C", "X-A-S")
    assert plan["feasible"]
    assert plan["purchase_batches"] == 2
    assert plan["full_refill_credit_reserve"] == 420
    assert plan["protected_credits"] == 116212
    assert plan["conservative_net"] == 87526
    assert not posts
    assert not run.store.latest(run.scope, "position")


@pytest.mark.parametrize("capacity", [400, 401])
@pytest.mark.parametrize("fuel_price", [72, 73])
def test_remote_reserved_refill_funds_recovery_at_original_ceiling(
    remote: tuple[Any, ...], capacity: int, fuel_price: int
) -> None:
    # Arrange
    run, agent, contract, ship, _, markets, posts = remote
    run.execute = False
    ship["fuel"]["capacity"] = capacity
    markets["X-A-D"]["tradeGoods"][1]["purchasePrice"] = fuel_price
    plan = contract_run(run, "S", "C", "X-A-S")
    contract.update(accepted=True, fulfilled=True)
    ship["nav"]["waypointSymbol"] = "X-A-D"
    ship["fuel"]["current"] = 0
    markets["X-A-D"]["tradeGoods"][1]["purchasePrice"] = plan[
        "fuel_price_ceiling"
    ]
    # No assumed fulfillment income finances this reserve boundary.
    agent["credits"] = 51000 + plan["full_refill_credit_reserve"]

    # Act
    refill = refuel_run(run, "S")

    # Assert
    assert (
        refill["maximum_estimated_cost"] == plan["full_refill_credit_reserve"]
    )
    assert posts == []


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
        "unknown_position",
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
    elif guard == "unknown_position":
        run.store.observe("r:A", "position", "unknown", {"status": "review"})
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


@pytest.mark.parametrize("changed_destination", [False, True])
def test_remote_abandonment_cannot_reopen_on_resume(
    remote: tuple[Any, ...], changed_destination: bool
) -> None:
    # Arrange: no acceptance was ever dispatched.
    run, _, contract, _, _, _, posts = remote
    run.remaining = 0
    with pytest.raises(SafetyStop, match="budget"):
        contract_run(run, "S", "C", "X-A-S")
    abandon_procurement(
        run,
        "C",
        execute=True,
        reason="Operator abandoned the unaccepted procurement plan.",
    )
    run.remaining = 30
    if changed_destination:
        contract["terms"]["deliver"][0]["destinationSymbol"] = "X-A-S"
    before = run.store.latest(run.scope, "position")

    # Act / Assert
    with pytest.raises(SafetyStop, match="Abandoned procurement"):
        contract_run(run, "S", "C")
    assert posts == []
    assert run.store.latest(run.scope, "position") == before
