from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from py_st.client import APIError, SpaceTradersClient
from py_st.services.automation import SafetyStop, Session
from py_st.services.intelligence import Intelligence


def test_history_and_scope_isolation(tmp_path: Path) -> None:
    # Arrange
    store = Intelligence(tmp_path / "db")
    # Act
    store.observe("reset:a", "agent", "a", {"credits": 100})
    store.observe("reset:a", "agent", "a", {"credits": 110})
    store.observe("new:a", "agent", "a", {"credits": 200})
    # Assert
    assert store.report("reset:a")["credit_change"] == 10
    assert store.latest("new:a", "agent")[0]["data"]["credits"] == 200
    store.close()


@pytest.mark.parametrize("guard", ["stop", "dry", "budget", "pending"])
def test_mutation_guards(tmp_path: Path, guard: str) -> None:
    # Arrange
    client = MagicMock()
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=guard != "dry", root=tmp_path)
    run.scope = "r:a"
    if guard == "stop":
        (tmp_path / "STOP").touch()
    elif guard == "budget":
        run.remaining = 0
    elif guard == "pending":
        store.begin_action(run.scope, "/old", {})
    # Act
    with pytest.raises(SafetyStop):
        run.mutate("/my/ships/A/orbit")
    # Assert
    client.request.assert_not_called()
    run.close()
    store.close()


def test_uncertain_action_never_replayed(tmp_path: Path) -> None:
    # Arrange
    client = MagicMock()
    client.request.side_effect = httpx.ReadTimeout("uncertain")
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=True, root=tmp_path)
    run.scope = "r:a"
    # Act
    with pytest.raises(httpx.ReadTimeout):
        run.mutate("/my/ships/A/orbit")
    run.close()
    resumed = Session(client, store, execute=True, root=tmp_path)
    resumed.scope = "r:a"
    with pytest.raises(SafetyStop, match="Pending"):
        resumed.mutate("/my/ships/A/orbit")
    # Assert
    assert client.request.call_count == 1
    assert store.pending("r:a")
    resumed.close()
    store.close()


@pytest.mark.parametrize(
    "stage", ["initial", "cooldown", "rate_limit", "retry_pacing"]
)
@pytest.mark.parametrize("interruption", ["stop", "deadline", "interrupt"])
def test_interrupted_safe_wait_does_not_require_reconciliation(
    tmp_path: Path, stage: str, interruption: str
) -> None:
    # Arrange
    calls = []
    stopped = False
    waits = 0
    stop_at = {"initial": 1, "retry_pacing": 3}.get(stage, 2)
    status = 409 if stage == "cooldown" else 429

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if stopped:
            return httpx.Response(200, json={"data": {"ok": True}})
        return httpx.Response(
            status,
            json={"error": {"code": 4000}},
            headers={"Retry-After": "1"},
        )

    client = SpaceTradersClient(
        "test",
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://test"
        ),
    )
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=True, root=tmp_path)
    run.scope = "r:a"
    deadline = run.deadline

    def wait(seconds: float) -> None:
        nonlocal waits, stopped
        waits += 1
        if waits != stop_at:
            return
        stopped = True
        if interruption == "interrupt":
            raise KeyboardInterrupt()
        if interruption == "stop":
            (tmp_path / "STOP").touch()
        else:
            run.deadline = 0
        run.wait(0)

    client.set_wait(wait)
    try:
        # Act
        with patch("py_st.services.automation.cache.clear_cache"):
            with pytest.raises((SafetyStop, KeyboardInterrupt)):
                run.mutate("/my/ships/S/orbit")
            # Assert: all dispatched attempts were definitively rejected.
            assert len(calls) == (0 if stage == "initial" else 1)
            assert not store.pending(run.scope)
            action = store.actions(run.scope)[0]
            assert action["status"] == (
                "not_sent" if stage == "initial" else "rejected"
            )
            (tmp_path / "STOP").unlink(missing_ok=True)
            run.deadline = deadline
            client.set_wait(lambda _: None)
            run.mutate("/my/ships/S/orbit")
            assert store.actions(run.scope)[0]["status"] == "succeeded"
    finally:
        run.close()
        client.close()
        store.close()


@pytest.mark.parametrize("after_rejection", [False, True])
@pytest.mark.parametrize(
    "failure", ["timeout", "write", "server", "malformed", "stop", "interrupt"]
)
def test_dispatched_ambiguity_stays_pending_even_after_safe_retry(
    tmp_path: Path, after_rejection: bool, failure: str
) -> None:
    # Arrange
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if after_rejection and len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": 429}})
        if failure == "timeout":
            raise httpx.ReadTimeout("Response lost after dispatch")
        if failure == "write":
            raise httpx.WriteError("Possibly partial write")
        if failure == "stop":
            raise SafetyStop("Interruption inside network request")
        if failure == "interrupt":
            raise KeyboardInterrupt()
        if failure == "server":
            return httpx.Response(503, json={"error": {"message": "Unknown"}})
        return httpx.Response(
            200, content="broken", headers={"Content-Type": "application/json"}
        )

    client = SpaceTradersClient(
        "test",
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://test"
        ),
    )
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=True, root=tmp_path)
    run.scope = "r:a"
    client.set_wait(lambda _: None)
    try:
        # Act
        with patch("py_st.services.automation.cache.clear_cache"):
            with pytest.raises(
                (httpx.HTTPError, APIError, SafetyStop, KeyboardInterrupt)
            ):
                run.mutate("/my/ships/S/orbit")
            with pytest.raises(SafetyStop, match="Pending"):
                run.mutate("/my/ships/S/orbit")
        # Assert
        assert len(calls) == (2 if after_rejection else 1)
        assert store.pending(run.scope)
        assert store.actions(run.scope)[0]["status"] == "pending"
    finally:
        run.close()
        client.close()
        store.close()


def test_navigation_reserves_round_trip(tmp_path: Path) -> None:
    # Arrange
    client = MagicMock()
    client.request.side_effect = [
        {
            "nav": {
                "status": "DOCKED",
                "waypointSymbol": "X-A-1",
                "systemSymbol": "X-A",
                "flightMode": "CRUISE",
                "route": {"destination": {"x": 0, "y": 0}},
            },
            "fuel": {"capacity": 100, "current": 25},
        },
        {"x": 10, "y": 0},
    ]
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=True, root=tmp_path)
    run.scope = "r:a"
    # Act
    with pytest.raises(SafetyStop, match="round-trip"):
        run.navigate("A", "X-A-2")
    # Assert
    assert all(c.args[0] == "GET" for c in client.request.call_args_list)
    run.close()
    store.close()


def test_single_writer_lock(tmp_path: Path) -> None:
    # Arrange
    store = Intelligence(tmp_path / "db")
    run = Session(MagicMock(), store, root=tmp_path)
    # Act
    with pytest.raises(SafetyStop, match="active"):
        Session(MagicMock(), store, root=tmp_path)
    # Assert
    run.close()
    store.close()


def test_sparse_market_keeps_price_history_and_route_freshness(
    tmp_path: Path,
) -> None:
    # Arrange
    store = Intelligence(tmp_path / "db")
    for key, x, buy, sell in (("X-A-1", 0, 100, 80), ("X-A-2", 20, 300, 250)):
        store.observe(
            "r:a", "waypoint", key, {"systemSymbol": "X-A", "x": x, "y": 0}
        )
        store.observe(
            "r:a",
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
    store.observe("r:a", "market", "X-A-1", {"symbol": "X-A-1"})
    # Act
    routes = store.routes("r:a")
    # Assert
    assert routes[0]["net_estimate"] == 40 * 150 - 72
    assert not routes[0]["stale"]
    assert len(store.latest("r:a", "market", priced_only=True)) == 2
    assert store.latest("r:a", "market")[0]["data"] == {"symbol": "X-A-1"}
    with store.db:
        store.db.execute(
            "UPDATE observations SET observed_at='2000-01-01T00:00:00+00:00'"
        )
    assert store.routes("r:a")[0]["stale"]
    store.close()


def test_reconcile_requires_explicit_evidence_and_never_replays(
    tmp_path: Path,
) -> None:
    # Arrange
    store = Intelligence(tmp_path / "db")
    client = MagicMock()
    run = Session(client, store, root=tmp_path)
    run.scope = "r:a"
    action = store.begin_action(run.scope, "/my/ships/S/purchase", {})
    with patch.object(
        run, "refresh", return_value={"agent": {"credits": 100000}}
    ):
        # Act
        run.reconcile(action)
        assert store.pending(run.scope)
        with pytest.raises(SafetyStop, match="explanation"):
            run.reconcile(action, "yes")
        run.reconcile(
            action, "Fresh cargo and transaction history confirm purchase."
        )
    # Assert
    assert not store.pending(run.scope)
    assert store.actions(run.scope)[0]["status"] == "reviewed"
    client.request.assert_not_called()
    run.close()
    store.close()


def test_economics_and_online_backup_include_confirmed_journal(
    tmp_path: Path,
) -> None:
    # Arrange
    store = Intelligence(tmp_path / "db")
    store.observe("r:a", "agent", "a", {"credits": 100000})
    for kind, price in (("PURCHASE", 100), ("SELL", 250)):
        action = store.begin_action("r:a", "/my/ships/S/transaction", {})
        store.finish_action(
            action,
            "succeeded",
            {
                "transaction": {
                    "tradeSymbol": "IRON",
                    "type": kind,
                    "units": 1,
                    "totalPrice": price,
                }
            },
        )
    action = store.begin_action("r:a", "/my/contracts/C/fulfill", {})
    store.finish_action(
        action,
        "succeeded",
        {"contract": {"terms": {"payment": {"onFulfilled": 200}}}},
    )
    store.observe("r:a", "agent", "a", {"credits": 100350})
    # Act
    report = store.economics("r:a")
    store.backup(tmp_path / "backup.db")
    backup = Intelligence(tmp_path / "backup.db")
    # Assert
    assert report["journal_net_cash"] == 350
    assert report["unexplained_credit_change"] == 0
    assert backup.economics("r:a") == report
    with pytest.raises(ValueError, match="exists"):
        store.backup(tmp_path / "backup.db")
    backup.close()
    store.close()


@pytest.mark.parametrize(
    "path",
    [
        "/register",
        "/my/ships/S/jump",
        "/my/ships/S/warp",
        "/my/ships/S/scrap",
        "/my/ships/S/jettison",
        "/my/ships",
        "/my/ships/S/extract",
    ],
)
def test_unreviewed_mutations_cannot_enter_journal(
    tmp_path: Path, path: str
) -> None:
    # Arrange
    client = MagicMock()
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=True, root=tmp_path)
    run.scope = "r:a"
    # Act
    with pytest.raises(SafetyStop, match="allowlist"):
        run.mutate(path)
    # Assert
    assert store.actions(run.scope) == []
    client.request.assert_not_called()
    run.close()
    store.close()


def test_expired_wall_budget_interrupts_wait_without_sleep(
    tmp_path: Path,
) -> None:
    # Arrange
    store = Intelligence(tmp_path / "db")
    run = Session(MagicMock(), store, root=tmp_path)
    run.deadline = 0
    # Act
    with patch("py_st.services.automation.time.sleep") as sleep:
        with pytest.raises(SafetyStop, match="Wall-clock"):
            run.wait(60)
        # Assert
        sleep.assert_not_called()
    run.close()
    store.close()


@pytest.mark.parametrize(
    "mode,destination",
    [
        ("DRIFT", "X-A-2"),
        ("BURN", "X-A-2"),
        ("STEALTH", "X-A-2"),
        ("CRUISE", "X-B-1"),
    ],
)
def test_navigation_forbids_unsafe_modes_and_cross_system(
    tmp_path: Path,
    mode: str,
    destination: str,
) -> None:
    # Arrange
    client = MagicMock()
    client.request.return_value = {
        "nav": {
            "status": "DOCKED",
            "systemSymbol": "X-A",
            "waypointSymbol": "X-A-1",
            "flightMode": mode,
        }
    }
    store = Intelligence(tmp_path / "db")
    run = Session(client, store, execute=True, root=tmp_path)
    run.scope = "r:a"
    # Act
    with pytest.raises(SafetyStop):
        run.navigate("S", destination)
    # Assert
    assert client.request.call_count == 1
    assert store.actions(run.scope) == []
    run.close()
    store.close()
