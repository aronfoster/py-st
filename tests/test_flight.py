"""Flight integration through the real queue, services and transport."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from py_st.cli.flight_cmd import flight_app
from py_st.client import APIError, SpaceTradersClient
from py_st.services.automation import SafetyStop, Session
from py_st.services.dashboard import dashboard_server
from py_st.services.flight_auth import save_password
from py_st.services.flight_demo import (
    SCOPE,
    create_demo,
    demo_client,
    scenario,
)
from py_st.services.flight_queue import FlightQueue, canonical_root
from py_st.services.flight_worker import FlightWorker, preview, trade_preview
from py_st.services.intelligence import Intelligence
from py_st.services.stop_control import request_stop

PASSWORD = "synthetic-owner-password"
TRIP: dict[str, Any] = {
    "kind": "trip",
    "ship": "SYNTHETIC-1",
    "destination": "X-DEMO-B2",
    "dock": True,
    "refuel": True,
}


def world(root: Path, **changes: Any) -> dict[str, Any]:
    with sqlite3.connect(root / ".state/remote.sqlite3") as db:
        state: dict[str, Any] = json.loads(
            db.execute("SELECT data FROM world").fetchone()[0]
        )
        state.update(changes)
        db.execute("UPDATE world SET data=?", (json.dumps(state),))
    return state


@pytest.fixture
def flight_root(tmp_path: Path) -> Path:
    create_demo(tmp_path)
    save_password(tmp_path, PASSWORD)
    queue = FlightQueue(tmp_path, create=True, scope=SCOPE, mode="demo")
    queue.control(False)
    queue.close()
    world(tmp_path, transit_seconds=0)
    return tmp_path


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Explicit offline browser suite",
)
@pytest.mark.parametrize("auxiliary", [True, False])
def test_browser_manual_guard_survives_submissions(
    flight_http: str, flight_root: Path, auxiliary: bool
) -> None:
    from playwright.sync_api import expect, sync_playwright

    # Arrange: freeze polling to expose guard overrides between ledger updates.
    queue = FlightQueue(flight_root)
    if auxiliary:
        queue.enqueue(SCOPE, uuid.uuid4().hex, TRIP)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.clock.install()
        page.goto(flight_http + "/#/explorer")
        page.locator("#owner-password").fill(PASSWORD)
        page.get_by_role("button", name="Log in", exact=True).click()
        page.locator("#explorer-ship").select_option("SYNTHETIC-1")
        page.locator("#waypoint-list button").filter(
            has_text="X-DEMO-B2"
        ).click()
        buttons = page.locator(
            "#flight-trip, #flight-orbit, #flight-dock, #flight-refuel"
        )

        # Act / Assert: inspection previews remain available without enqueuing.
        page.locator("#flight-preview").click()
        expect(page.locator("#flight-estimate")).to_contain_text(
            '"estimated": true'
        )
        assert len(queue.report()["commands"]) == int(auxiliary)
        if auxiliary:
            for button in buttons.all():
                expect(button).to_be_disabled()
            page.locator("#flight-refresh").click()
            expect(page.locator("#flight-message")).to_contain_text(
                "Command #"
            )
            expect(page.locator("#ship-ownership")).to_contain_text(
                "worker command"
            )
            assert not page.evaluate("window.ledgerUI.snapshot.submitting")
            for button in buttons.all():
                expect(button).to_be_disabled()
            expect(page.locator("#ship-ownership")).to_contain_text(
                "worker command"
            )
            assert len(queue.report()["commands"]) == 2
        else:
            held: list[Any] = []
            page.route(
                "**/api/flight",
                lambda route: (
                    held.append(route)
                    if route.request.method == "POST"
                    else route.continue_()
                ),
            )
            for attempt, status in enumerate((503, 503, 400)):
                page.locator(
                    "#flight-trip" if attempt == 0 else "#flight-retry"
                ).click()
                expect(page.locator("#ship-ownership")).to_contain_text(
                    "submission in progress"
                )
                for button in buttons.all():
                    expect(button).to_be_disabled()
                assert len(held) == attempt + 1
                request_id = held[-1].request.post_data_json["request_id"]
                assert (
                    request_id == held[0].request.post_data_json["request_id"]
                )
                held[-1].fulfill(
                    status=status, json={"error": f"Synthetic {attempt}"}
                )
                expect(page.locator("#flight-message")).to_contain_text(
                    f"Synthetic {attempt}"
                )
                assert not page.evaluate("window.ledgerUI.snapshot.submitting")
                if status == 503:
                    expect(page.locator("#ship-ownership")).to_contain_text(
                        "recover prior submission"
                    )
                    for button in buttons.all():
                        expect(button).to_be_disabled()
                else:
                    for button in buttons.all():
                        expect(button).to_be_enabled()
            assert queue.report()["commands"] == []
        browser.close()
    assert world(flight_root)["mutations"] == []
    queue.close()


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Explicit offline browser suite",
)
@pytest.mark.parametrize("width", [1440, 390])
def test_browser_pending_journal_and_historical_scope(
    flight_http: str, flight_root: Path, width: int
) -> None:
    from playwright.sync_api import expect, sync_playwright

    # Arrange: journal uncertainty independent of the current command queue.
    store = Intelligence(flight_root / ".state/intelligence.sqlite3")
    ship = store.latest(SCOPE, "ship")[0]
    store.observe("OLD:ARCHIVE", "ship", ship["key"], ship["data"])
    store.observe("OLD:ARCHIVE", "agent", "ARCHIVE", {"credits": 100000})
    store.begin_action(SCOPE, "/synthetic/unknown", {})
    store.close()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.add_init_script("""window.panelFlash = false;
            new MutationObserver(() => {
                if (document.querySelectorAll(
                    '#legacy-pages [data-page]:not([hidden])'
                ).length > 1) window.panelFlash = true;
            }).observe(document, {subtree:true, childList:true,
                attributes:true, attributeFilter:['hidden']});
        """)
        page.goto(flight_http + "/#/fleet")
        expect(page.locator("#page-title")).to_have_text("Fleet")
        assert not page.evaluate("window.panelFlash")
        assert page.evaluate("window.scrollY") == 0
        page.locator("#owner-password").fill(PASSWORD)
        page.get_by_role("button", name="Log in", exact=True).click()
        page.locator("#scope").select_option(SCOPE)
        page.get_by_role("navigation").get_by_role(
            "link", name="Explorer", exact=True
        ).click()
        page.locator("#explorer-ship").select_option("SYNTHETIC-1")

        # Act / Assert: the journal alone blocks all manual mutations.
        expect(page.locator("#ship-ownership")).to_contain_text(
            "pending mutation journal outcome"
        )
        for button in page.locator(
            "#flight-trip, #flight-orbit, #flight-dock, #flight-refuel"
        ).all():
            expect(button).to_be_disabled()
        certainty = page.locator(".ui-status").filter(
            has_text="Mutation certainty"
        )
        expect(certainty).to_contain_text("1 pending journal entries")
        page.locator("#scope").select_option("OLD:ARCHIVE")
        expect(page.locator("#credits")).to_have_text("100,000")
        expect(certainty).to_contain_text("Unknown")
        expect(certainty).not_to_contain_text("0 reconciliation required")
        expect(certainty).to_contain_text("0 pending journal entries")
        page.locator("#explorer-ship").select_option("SYNTHETIC-1")
        expect(page.locator("#ship-ownership")).to_contain_text(
            "historical scope"
        )
        page.reload()
        expect(page.locator("#page-title")).to_have_text("Explorer")
        assert not page.evaluate("window.panelFlash")
        expect(page.locator("[data-page]:not([hidden])")).to_have_count(1)
        browser.close()


@pytest.fixture
def runner(flight_root: Path) -> Iterator[FlightWorker]:
    with demo_client(flight_root) as client:
        client._transport._interval = 0
        worker = FlightWorker(flight_root, client)
        try:
            yield worker
        finally:
            worker.close()


def submit(worker: FlightWorker, payload: dict[str, Any]) -> int:
    return int(worker.queue.enqueue(SCOPE, uuid.uuid4().hex, payload)["id"])


def finish(worker: FlightWorker, command_id: int) -> dict[str, Any]:
    for _ in range(12):
        worker.tick()
        command = worker.queue.get(command_id)
        if command["status"] in (
            "completed",
            "blocked",
            "reconciliation_required",
        ):
            return command
    raise AssertionError(worker.queue.get(command_id))


def test_purchase_and_sale_refresh_authoritative_cash_and_cargo(
    runner: FlightWorker,
) -> None:
    # Arrange
    purchase = trade_preview(
        runner.store, SCOPE, "SYNTHETIC-1", "IRON_ORE", 5, "purchase"
    )
    assert purchase["feasible"]
    payload = {
        "ship": "SYNTHETIC-1",
        "good": "IRON_ORE",
        "waypoint": purchase["waypoint"],
    }

    # Act
    purchase_id = submit(
        runner,
        {
            **payload,
            "kind": "purchase",
            "units": 5,
            "quote": purchase["unit_price"],
            "observed_at": purchase["observed_at"],
        },
    )
    assert finish(runner, purchase_id)["status"] == "completed"
    sale = trade_preview(
        runner.store, SCOPE, "SYNTHETIC-1", "IRON_ORE", 2, "sell"
    )
    sale_id = submit(
        runner,
        {
            **payload,
            "kind": "sell",
            "units": 2,
            "quote": sale["unit_price"],
            "observed_at": sale["observed_at"],
        },
    )

    # Assert
    assert finish(runner, sale_id)["status"] == "completed"
    state = world(runner.root)
    assert state["agent"]["credits"] == 123216
    assert state["ships"][0]["cargo"]["units"] == 3
    assert state["mutations"][-2:] == [
        "/my/ships/SYNTHETIC-1/purchase",
        "/my/ships/SYNTHETIC-1/sell",
    ]


def test_trade_preview_rejects_capacity_and_unknown_price(
    runner: FlightWorker,
) -> None:
    # Arrange / Act
    too_large = trade_preview(
        runner.store, SCOPE, "SYNTHETIC-1", "IRON_ORE", 41, "purchase"
    )
    unknown = trade_preview(
        runner.store, SCOPE, "SYNTHETIC-1", "MISSING", 1, "purchase"
    )

    # Assert
    assert not too_large["feasible"]
    assert unknown["unit_price"] is None
    assert unknown["total_price"] is None
    assert not unknown["feasible"]


def test_complete_trip_fuel_cash_and_shared_observations(
    runner: FlightWorker,
) -> None:
    # Arrange: the actual guarded services operate a persistent synthetic API.
    command_id = submit(runner, TRIP)
    # Act
    command = finish(runner, command_id)
    state = world(runner.root)
    # Assert
    assert command["status"] == "completed", command
    assert state["mutations"] == [
        "/my/ships/SYNTHETIC-1/orbit",
        "/my/ships/SYNTHETIC-1/navigate",
        "/my/ships/SYNTHETIC-1/dock",
        "/my/ships/SYNTHETIC-1/refuel",
    ]
    assert state["agent"]["credits"] == 123384
    ship = runner.store.latest(SCOPE, "ship")[0]["data"]
    assert ship == state["ships"][0]
    assert ship["nav"]["waypointSymbol"] == "X-DEMO-B2"
    assert ship["nav"]["status"] == "DOCKED"
    assert ship["fuel"]["current"] == 100
    assert not runner.store.pending(SCOPE)


def test_duplicate_id_changed_payload_and_scope(runner: FlightWorker) -> None:
    request_id = uuid.uuid4().hex
    first = runner.queue.enqueue(SCOPE, request_id, TRIP)
    assert runner.queue.enqueue(SCOPE, request_id, TRIP)["id"] == first["id"]
    with pytest.raises(ValueError, match="different payload"):
        runner.queue.enqueue(
            SCOPE, request_id, TRIP | {"dock": False, "refuel": False}
        )
    with pytest.raises(ValueError, match="scope"):
        runner.queue.enqueue("OTHER:AGENT", uuid.uuid4().hex, TRIP)
    finish(runner, first["id"])
    assert len(world(runner.root)["mutations"]) == 4


def test_old_reconciliation_remains_visible(runner: FlightWorker) -> None:
    scenario(runner.root, "lost-response")
    command_id = submit(runner, TRIP)
    assert finish(runner, command_id)["status"] == "reconciliation_required"
    for _ in range(101):
        later = submit(runner, {"kind": "refresh", "system": "X-DEMO"})
        runner.queue.update(
            later, "completed", "Synthetic completed history", step=1
        )
    assert command_id in {c["id"] for c in runner.queue.report()["commands"]}


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "jump", "ship": "SYNTHETIC-1"},
        TRIP | {"dock": "true"},
        TRIP | {"ship": "../secret"},
        TRIP | {"extra": True},
        TRIP | {"dock": False},
    ],
)
def test_payload_validation(
    runner: FlightWorker, payload: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        submit(runner, payload)
    assert world(runner.root)["mutations"] == []


@pytest.mark.parametrize("step", range(5))
def test_worker_restart_preserves_trip(flight_root: Path, step: int) -> None:
    # Arrange / Act: terminate between steps, preserving fake remote state.
    with demo_client(flight_root) as client:
        client._transport._interval = 0
        first = FlightWorker(flight_root, client)
        command_id = submit(first, TRIP)
        for _ in range(step):
            first.tick()
        first.close()
    with demo_client(flight_root) as client:
        client._transport._interval = 0
        second = FlightWorker(flight_root, client)
        try:
            result = finish(second, command_id)
            assert result["status"] == "completed", result
        finally:
            second.close()
    assert len(world(flight_root)["mutations"]) == 4


@pytest.mark.parametrize("after_dispatch", [False, True])
def test_crash_at_journal_boundary(
    runner: FlightWorker, after_dispatch: bool
) -> None:
    command_id = submit(runner, TRIP)
    command = runner.queue.get(command_id)
    runner.queue.update(
        command_id, "dispatching", "Simulated process loss", before_action=0
    )
    if after_dispatch:
        runner.fresh()
        runner.mutate(command, "/my/ships/SYNTHETIC-1/orbit")
    result = finish(runner, command_id)
    assert result["status"] == "completed", result
    assert (
        world(runner.root)["mutations"].count("/my/ships/SYNTHETIC-1/orbit")
        == 1
    )


def test_stop_resume_during_trip_and_restart(flight_root: Path) -> None:
    with demo_client(flight_root) as client:
        client._transport._interval = 0
        worker = FlightWorker(flight_root, client)
        command_id = submit(worker, TRIP)
        worker.tick()
        request_stop(flight_root)
        worker.close()
    with demo_client(flight_root) as client:
        client._transport._interval = 0
        worker = FlightWorker(flight_root, client)
        try:
            assert worker.tick() is False
            assert len(world(flight_root)["mutations"]) == 1
            (flight_root / "STOP").unlink()
            worker.queue.control(False)
            assert finish(worker, command_id)["status"] == "completed"
        finally:
            worker.close()


def test_arrival_must_be_observed(runner: FlightWorker) -> None:
    world(runner.root, transit_seconds=3600)
    command_id = submit(runner, TRIP)
    for _ in range(4):
        runner.tick()
    assert runner.queue.get(command_id)["status"] == "in_transit"
    assert len(world(runner.root)["mutations"]) == 2


def test_transit_poll_is_deferred_without_api_calls(
    runner: FlightWorker,
) -> None:
    world(runner.root, transit_seconds=3600)
    command_id = submit(runner, TRIP)
    for _ in range(3):
        runner.tick()
    with patch.object(
        runner.client, "request", wraps=runner.client.request
    ) as send:
        for _ in range(30):
            assert runner.tick() is False
        send.assert_not_called()
    assert runner.queue.get(command_id)["status"] == "in_transit"
    request_stop(runner.root)
    assert runner.tick() is False
    assert runner.queue.report()["settings"]["worker_state"] == "paused"


def test_simple_step_does_not_duplicate_snapshot_reads(
    runner: FlightWorker,
) -> None:
    command_id = submit(runner, {"kind": "orbit", "ship": "SYNTHETIC-1"})
    with patch.object(
        runner.run, "refresh", wraps=runner.run.refresh
    ) as refresh:
        runner.tick()
        assert refresh.call_count == 1
    assert runner.queue.get(command_id)["status"] == "completed"


def test_dispatch_expiry_keeps_actionable_command_reason(
    runner: FlightWorker,
) -> None:
    mutate = runner.run.mutate

    def expired(
        path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        runner.dispatch_until = time.monotonic() - 1
        return mutate(path, body)

    with patch.object(runner.run, "mutate", side_effect=expired):
        result = finish(
            runner, submit(runner, {"kind": "orbit", "ship": "SYNTHETIC-1"})
        )
    assert result["status"] == "blocked"
    assert "evidence expired" in result["detail"]
    assert "replan" in result["detail"]
    assert not world(runner.root)["mutations"]


def test_deferred_arrival_survives_restart(flight_root: Path) -> None:
    world(flight_root, transit_seconds=3600)
    with demo_client(flight_root) as client:
        client._transport._interval = 0
        worker = FlightWorker(flight_root, client)
        command_id = submit(worker, TRIP)
        for _ in range(3):
            worker.tick()
        worker.close()
    with demo_client(flight_root) as client:
        client._transport._interval = 0
        worker = FlightWorker(flight_root, client)
        try:
            with patch.object(client, "request", wraps=client.request) as send:
                assert worker.tick() is False
                send.assert_not_called()
            command = worker.queue.get(command_id)
            evidence = command["evidence"] | {
                "arrival_poll_after": "2000-01-01T00:00:00+00:00"
            }
            worker.queue.update(
                command_id, "in_transit", "Due", evidence=evidence
            )
            worker.tick()
            assert worker.queue.get(command_id)["status"] == "in_transit"
            assert len(world(flight_root)["mutations"]) == 2
        finally:
            worker.close()


@pytest.mark.parametrize("status,code", [(401, None), (400, 4113)])
def test_setup_authentication_failure_persists_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    code: int | None,
) -> None:
    create_demo(tmp_path)
    client = SpaceTradersClient(
        "synthetic",
        httpx.Client(
            base_url="https://offline.invalid",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    status, json={"error": {"code": code}}
                )
            ),
        ),
    )
    monkeypatch.setenv("ST_STATE_ROOT", str(tmp_path))
    monkeypatch.setattr("py_st.cli.flight_cmd.live_client", lambda: client)
    monkeypatch.setattr(
        "py_st.cli.flight_cmd.getpass.getpass", lambda prompt: ""
    )
    result = CliRunner().invoke(flight_app, ["setup"])
    assert result.exit_code == 1
    assert (tmp_path / "STOP").exists()
    assert not (tmp_path / ".state/flight.sqlite3").exists()
    assert world(tmp_path)["mutations"] == []


def test_unknown_demo_waypoint_blocks_without_crashing(
    runner: FlightWorker,
) -> None:
    result = finish(
        runner, submit(runner, TRIP | {"destination": "X-DEMO-Z9"})
    )
    assert result["status"] == "blocked"
    assert not world(runner.root)["mutations"]
    assert finish(runner, submit(runner, TRIP))["status"] == "completed"


@pytest.mark.parametrize(
    "path",
    [
        "/my/ships/UNKNOWN",
        "/systems/X-DEMO/waypoints/X-DEMO-Z9",
        "/systems/X-DEMO/waypoints/X-DEMO-Z9/market",
    ],
)
def test_unknown_demo_resources_are_http_404(
    runner: FlightWorker, path: str
) -> None:
    with pytest.raises(APIError) as error:
        runner.client.request("GET", path)
    assert error.value.status == 404


def test_completed_history_is_not_validated_for_execution(
    runner: FlightWorker,
) -> None:
    historical = submit(runner, TRIP)
    runner.queue.update(historical, "completed", "Historical command", step=5)
    with runner.queue.db:
        runner.queue.db.execute(
            "UPDATE commands SET version=99,payload=? WHERE id=?",
            (json.dumps({"kind": "retired-command"}), historical),
        )
    active = submit(runner, {"kind": "orbit", "ship": "SYNTHETIC-1"})
    assert finish(runner, active)["status"] == "completed"


def test_worker_guard_explanation_reaches_legacy_cli() -> None:
    from py_st.cli._errors import handle_errors

    with (
        SpaceTradersClient("synthetic") as client,
        patch.object(client._client, "request") as send,
    ):

        @handle_errors
        def blocked() -> None:
            client.request("POST", "/my/ships/SHIP/orbit")

        import typer

        app = typer.Typer()
        app.command()(blocked)
        result = CliRunner().invoke(app, [])
        assert result.exit_code == 1
        assert "Use the flight worker" in result.output
        send.assert_not_called()


def test_unknown_outcome_blocks_replay_and_owner_review_cancels_steps(
    runner: FlightWorker,
) -> None:
    scenario(runner.root, "lost-response")
    command_id = submit(runner, TRIP)
    result = finish(runner, command_id)
    assert result["status"] == "reconciliation_required"
    assert runner.store.pending(SCOPE)
    for _ in range(3):
        runner.tick()
    assert len(world(runner.root)["mutations"]) == 1
    review = submit(
        runner,
        {
            "kind": "reconcile",
            "command": command_id,
            "explanation": "Observed SYNTHETIC-1 in orbit; no other effects.",
        },
    )
    assert finish(runner, review)["status"] == "completed"
    assert runner.queue.get(command_id)["status"] == "cancelled"
    assert not runner.store.pending(SCOPE)
    assert len(world(runner.root)["mutations"]) == 1


@pytest.mark.parametrize(
    "scenario_name,payload",
    [
        ("low-fuel", TRIP),
        ("low-funds", {"kind": "refuel", "ship": "SYNTHETIC-1"}),
    ],
)
def test_changed_fuel_and_funds_block(
    runner: FlightWorker, scenario_name: str, payload: dict[str, Any]
) -> None:
    command_id = submit(runner, payload)
    scenario(runner.root, scenario_name)
    assert finish(runner, command_id)["status"] == "blocked"
    assert not any(
        path.endswith(("navigate", "refuel"))
        for path in world(runner.root)["mutations"]
    )


def test_contract_reserves_block_spending_and_movement(
    runner: FlightWorker,
) -> None:
    world(
        runner.root,
        contracts=[{"id": "ACTIVE", "accepted": True, "fulfilled": False}],
    )
    result = finish(runner, submit(runner, TRIP))
    assert result["status"] == "blocked"
    assert "obligation reserve" in result["detail"]
    assert not world(runner.root)["mutations"]


def test_cross_system_trip_refused_before_orbit(runner: FlightWorker) -> None:
    result = finish(
        runner, submit(runner, TRIP | {"destination": "X-OTHER-A1"})
    )
    assert result["status"] == "blocked"
    assert not world(runner.root)["mutations"]


def test_lost_refuel_response_never_double_spends(
    runner: FlightWorker,
) -> None:
    command_id = submit(runner, TRIP)
    for _ in range(4):
        runner.tick()
    scenario(runner.root, "lost-response")
    assert finish(runner, command_id)["status"] == "reconciliation_required"
    for _ in range(4):
        runner.tick()
    state = world(runner.root)
    assert state["agent"]["credits"] == 123384
    assert sum(p.endswith("refuel") for p in state["mutations"]) == 1


def test_invalid_receipt_stays_pending(runner: FlightWorker) -> None:
    original = runner.client._transport._client._transport

    def broken(request: httpx.Request) -> httpx.Response:
        response = original.handle_request(request)
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"nav": None}})
        return response

    runner.client._transport._client._transport = httpx.MockTransport(broken)
    result = finish(runner, submit(runner, TRIP))
    assert result["status"] == "reconciliation_required"
    assert runner.store.pending(SCOPE)
    assert len(world(runner.root)["mutations"]) == 1


@pytest.mark.parametrize("status,code", [(401, None), (400, 4113)])
def test_auth_failure_persists_stop(
    runner: FlightWorker, status: int, code: int | None
) -> None:
    runner.client._transport._client._transport = httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": {"code": code}})
    )
    command_id = submit(runner, TRIP)
    runner.tick()
    assert (runner.root / "STOP").exists()
    assert runner.queue.report()["settings"]["paused"] == 1
    assert "Authentication/reset" in runner.queue.get(command_id)["detail"]
    assert not world(runner.root)["mutations"]


def test_reset_agent_mismatch_never_writes_new_scope(
    runner: FlightWorker,
) -> None:
    world(runner.root, agent={"symbol": "OTHER", "credits": 123456})
    submit(runner, TRIP)
    runner.tick()
    assert (runner.root / "STOP").exists()
    assert runner.store.scopes() == [SCOPE]
    assert not world(runner.root)["mutations"]


def test_stop_between_orbit_and_navigate_revalidates_fuel(
    runner: FlightWorker,
) -> None:
    command_id = submit(runner, TRIP)
    runner.tick()
    request_stop(runner.root)
    scenario(runner.root, "low-fuel")
    assert runner.tick() is False
    (runner.root / "STOP").unlink()
    assert finish(runner, command_id)["status"] == "blocked"
    assert len(world(runner.root)["mutations"]) == 1


def test_expired_dispatch_window_never_sends(runner: FlightWorker) -> None:
    command_id = submit(runner, TRIP)
    command = runner.queue.get(command_id)
    runner.fresh()
    runner.evidence_until = time.monotonic() - 1
    with pytest.raises(SafetyStop, match="expired"):
        runner.mutate(command, "/my/ships/SYNTHETIC-1/orbit")
    assert not world(runner.root)["mutations"]
    assert not runner.store.pending(SCOPE)


def test_schema_changed_under_active_worker_refused(
    runner: FlightWorker,
) -> None:
    submit(runner, TRIP)
    runner.queue.db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="schema"):
        runner.tick()
    assert not world(runner.root)["mutations"]


def test_host_scope_lock_across_different_roots(
    runner: FlightWorker, tmp_path: Path
) -> None:
    other = tmp_path / "second-checkout"
    other.mkdir()
    create_demo(other)
    queue = FlightQueue(other, create=True, scope=SCOPE, mode="demo")
    queue.close()
    with (
        demo_client(other) as client,
        pytest.raises(SafetyStop, match="Another worker"),
    ):
        FlightWorker(other, client)
    with pytest.raises(SafetyStop, match="automation session"):
        Session(runner.client, runner.store, root=runner.root)


def test_direct_live_client_cannot_mutate_without_worker() -> None:
    # Guard refuses before httpx dispatch; no real network is permitted here.
    with (
        SpaceTradersClient("synthetic") as client,
        patch.object(client._client, "request") as send,
    ):
        with pytest.raises(APIError):
            client.request("POST", "/my/ships/SHIP/orbit")
        send.assert_not_called()


@pytest.mark.parametrize(
    "sql",
    [
        "PRAGMA user_version=99",
        "UPDATE commands SET version=99",
        'UPDATE commands SET payload=\'{"kind":"jump"}\'',
        "UPDATE commands SET steps='[\"warp\"]'",
    ],
)
def test_incompatible_state_refused_before_dispatch(
    runner: FlightWorker, sql: str
) -> None:
    submit(runner, TRIP)
    runner.queue.db.execute(sql)
    runner.queue.db.commit()
    with pytest.raises(ValueError):
        check = FlightQueue(runner.root)
        check.close()
    assert not world(runner.root)["mutations"]


def test_missing_state_refused_and_preview_unknown(
    flight_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ST_STATE_ROOT", raising=False)
    with pytest.raises(ValueError, match="absolute"):
        canonical_root()
    store = Intelligence(
        flight_root / ".state/intelligence.sqlite3", read_only=True
    )
    try:
        result = preview(store, SCOPE, "unknown", "X-DEMO-B2")
        assert result["fuel"] is None and result["seconds"] is None
        assert not result["feasible"]
    finally:
        store.close()


def test_empty_replacement_ledger_refused(flight_root: Path) -> None:
    with sqlite3.connect(flight_root / ".state/intelligence.sqlite3") as db:
        db.execute("DELETE FROM observations")
    with (
        demo_client(flight_root) as client,
        pytest.raises(SafetyStop, match="agent history"),
    ):
        FlightWorker(flight_root, client)
    assert not world(flight_root)["mutations"]


def test_cli_worker_uses_canonical_root_from_another_directory(
    flight_root: Path,
) -> None:
    queue = FlightQueue(flight_root)
    command_id = queue.enqueue(
        SCOPE, uuid.uuid4().hex, {"kind": "orbit", "ship": "SYNTHETIC-1"}
    )["id"]
    queue.close()
    other = flight_root / "another-checkout"
    other.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "py_st", "flight", "worker", "--once"],
        cwd=other,
        env=os.environ
        | {
            "ST_STATE_ROOT": str(flight_root),
            "ST_LIVE_TESTS": "0",
            "ST_CACHE_DIR": str(flight_root / "cache"),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    queue = FlightQueue(flight_root)
    try:
        assert queue.get(command_id)["status"] == "completed"
    finally:
        queue.close()
    assert world(flight_root)["mutations"] == ["/my/ships/SYNTHETIC-1/orbit"]
    assert not (other / ".state").exists()


@pytest.fixture
def flight_http(flight_root: Path) -> Iterator[str]:
    server = dashboard_server(flight_root, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def login(client: httpx.Client, origin: str) -> str:
    page = client.get("/")
    match = re.search('nonce="([a-f0-9]+)"', page.text)
    assert match
    csrf = match.group(1)
    response = client.post(
        "/api/login",
        headers={"Origin": origin},
        json={"csrf": csrf, "password": PASSWORD},
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    return csrf


def test_successful_logins_do_not_consume_failure_budget(
    flight_http: str,
) -> None:
    with httpx.Client(base_url=flight_http) as client:
        for _ in range(6):
            csrf = login(client, flight_http)
        for attempt in range(6):
            response = client.post(
                "/api/login",
                headers={"Origin": flight_http},
                json={"csrf": csrf, "password": "incorrect"},
            )
            assert response.status_code == (401 if attempt < 5 else 429)


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Explicit offline browser suite",
)
def test_browser_preserves_review_draft_and_handles_auth_errors(
    flight_http: str,
    flight_root: Path,
) -> None:
    from playwright.sync_api import expect, sync_playwright

    queue = FlightQueue(flight_root)
    command = queue.enqueue(SCOPE, uuid.uuid4().hex, TRIP)
    queue.update(
        command["id"],
        "reconciliation_required",
        "Synthetic unknown",
        before_action=0,
        evidence={"id": 1},
    )
    queue.close()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        errors: list[str] = []
        reports: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: (
                reports.append(request.url)
                if "/api/report" in request.url
                else None
            ),
        )
        page.clock.install()
        page.goto(flight_http)
        expect(page.locator("#flight-login")).to_be_visible()
        page.clock.fast_forward(10000)
        expect(page.locator("#error")).to_be_empty()
        assert reports == []
        page.locator("#owner-password").fill(PASSWORD)
        page.get_by_role("button", name="Log in", exact=True).click()
        page.get_by_role("navigation").get_by_role(
            "link", name="Operations", exact=True
        ).click()
        textarea = page.get_by_role(
            "textbox", name=f"Outcome explanation for command {command['id']}"
        )
        draft = (
            "Observed my ship in orbit; still inspecting fuel and receipts."
        )
        textarea.fill(draft)
        textarea.press("ArrowLeft")
        original = textarea.element_handle()
        assert original is not None
        with page.expect_response(
            lambda response: response.url.endswith("/api/flight")
        ):
            page.clock.fast_forward(10000)
        original.wait_for_element_state("hidden")
        expect(textarea).to_have_value(draft)
        expect(textarea).to_be_focused()
        assert (
            textarea.evaluate("element => element.selectionStart")
            == len(draft) - 1
        )
        page.route(
            "**/api/logout",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"error": "Synthetic logout failure"}),
            ),
        )
        page.locator("#flight-logout").click()
        expect(page.locator("#flight-message")).to_contain_text(
            "Logout failed"
        )
        assert errors == []
        browser.close()


def test_authentication_csrf_and_durable_http_submission(
    flight_http: str, flight_root: Path
) -> None:
    with httpx.Client(base_url=flight_http) as client:
        assert client.get("/api/report").status_code == 401
        csrf = login(client, flight_http)
        body = {
            "csrf": csrf,
            "scope": SCOPE,
            "request_id": uuid.uuid4().hex,
            "payload": TRIP,
        }
        assert client.post("/api/flight", json=body).status_code == 403
        assert (
            client.post(
                "/api/flight",
                json=body | {"csrf": "wrong"},
                headers={"Origin": flight_http},
            ).status_code
            == 403
        )
        response = client.post(
            "/api/flight", json=body, headers={"Origin": flight_http}
        )
        assert response.status_code == 200
        assert PASSWORD not in client.get("/api/flight").text
        assert client.get("/.state/owner.json").status_code == 404
        command_id = response.json()["id"]
    # Closing the HTTP client leaves the independent queue intact.
    with demo_client(flight_root) as client:
        client._transport._interval = 0
        worker = FlightWorker(flight_root, client)
        try:
            assert finish(worker, command_id)["status"] == "completed"
        finally:
            worker.close()


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Explicit offline browser suite",
)
@pytest.mark.parametrize("width", [1440, 390])
def test_browser_trip(flight_http: str, flight_root: Path, width: int) -> None:
    from playwright.sync_api import sync_playwright

    stopped = threading.Event()
    errors: list[str] = []

    def work() -> None:
        with demo_client(flight_root) as client:
            client._transport._interval = 0
            worker = FlightWorker(flight_root, client)
            try:
                while not stopped.is_set():
                    worker.tick()
                    stopped.wait(0.1)
            except Exception as exc:
                errors.append(str(exc))
            finally:
                worker.close()

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome", headless=True
            )
            context = browser.new_context(
                viewport={"width": width, "height": 1000}
            )
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(flight_http)
            page.locator("#owner-password").fill(PASSWORD)
            page.get_by_role("button", name="Log in", exact=True).click()
            page.get_by_role("navigation").get_by_role(
                "link", name="Explorer", exact=True
            ).click()
            page.locator("#flight-controls").wait_for(state="visible")
            page.locator("#explorer-ship").select_option("SYNTHETIC-1")
            page.locator("#waypoint-list button").filter(
                has_text="X-DEMO-B2"
            ).click()
            page.locator("#flight-preview").click()
            from playwright.sync_api import expect

            expect(page.locator("#flight-estimate")).to_contain_text(
                '"estimated": true'
            )
            page.locator("#flight-trip").click()
            expect(page.locator("#flight-message")).to_contain_text(
                "Command #"
            )
            # Close/reopen the page while the separate worker continues.
            page.close()
            deadline = time.monotonic() + 15
            while (
                len(world(flight_root)["mutations"]) < 4
                and time.monotonic() < deadline
            ):
                time.sleep(0.1)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(flight_http)
            expect(page.locator("#flight-commands")).to_contain_text(
                "COMPLETED", timeout=15000
            )
            expect(page.locator("#fleet")).to_contain_text("Fuel 100/100")
            expect(page.locator("#credits")).to_have_text("123,384")
            page.get_by_role("navigation").get_by_role(
                "link", name="Fleet", exact=True
            ).click()
            expect(page.locator("#fleet")).to_be_visible()
            expect(page.locator("#explorer-ship")).to_have_value("SYNTHETIC-1")
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.screenshot(
                path=str(flight_root / f"flight-{width}.png"), full_page=True
            )
            browser.close()
    finally:
        stopped.set()
        thread.join(10)
    assert not errors, errors


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Explicit offline browser suite",
)
@pytest.mark.parametrize("width", [1440, 390])
def test_ui_shell_ownership_liveness_and_recovery(
    flight_http: str, flight_root: Path, width: int
) -> None:
    from playwright.sync_api import expect, sync_playwright

    # Arrange: a real queue has owned work; no worker or live API is running.
    queue = FlightQueue(flight_root)
    command = queue.enqueue(SCOPE, uuid.uuid4().hex, TRIP)
    queue.heartbeat("idle")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors: list[str] = []
        violations: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: (
                violations.append(message.text)
                if "Content Security Policy" in message.text
                else None
            ),
        )
        page.clock.install(time=datetime.now(UTC))
        page.goto(flight_http)
        page.locator("#owner-password").fill(PASSWORD)
        page.get_by_role("button", name="Log in", exact=True).click()
        expect(page.locator("#page-title")).to_have_text("Overview")
        expect(page.locator("#page-overview")).to_contain_text("SYNTHETIC-1")
        nav = page.get_by_role("navigation", name="Main navigation")
        expect(nav.get_by_role("link")).to_have_count(8)

        # Act / Assert: every previous panel remains reachable in its section.
        inventory = {
            "Explorer": ["map", "flight-controls"],
            "Fleet": ["fleet"],
            "Markets": ["market-select", "routes", "markets"],
            "Contracts": ["contracts", "contract-select"],
            "Automation": ["automation-runs", "plans"],
            "Reports": ["chart", "cash", "positions"],
            "Operations": ["flight-commands", "doctor-check", "journal"],
        }
        for name, ids in inventory.items():
            nav.get_by_role("link", name=name, exact=True).click()
            expect(page.locator("#page-title")).to_have_text(name)
            expect(
                nav.get_by_role("link", name=name, exact=True)
            ).to_have_attribute("aria-current", "page")
            for panel in ids:
                assert (
                    page.locator(f"#{panel}").evaluate(
                        "el => el.closest('[data-page]').dataset.page"
                    )
                    == name.lower()
                )
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), name
        nav.get_by_role("link", name="Explorer", exact=True).click()
        page.locator("#explorer-ship").select_option("SYNTHETIC-1")
        expect(page.locator("#ship-ownership")).to_contain_text(
            f"worker command #{command['id']}"
        )
        expect(page.locator("#flight-trip")).to_be_disabled()
        nav.get_by_role("link", name="Markets", exact=True).click()
        expect(page.locator("#explorer-ship")).to_have_value("SYNTHETIC-1")
        page.go_back()
        expect(page.locator("#page-title")).to_have_text("Explorer")
        expect(page.locator("#explorer-ship")).to_have_value("SYNTHETIC-1")

        # STOP and unknown outcome are independent. Doctor remains functional.
        queue.update(command["id"], "reconciliation_required", "Lost reply")
        page.locator("#pause").click()
        expect(page.locator("#state")).to_have_text("STOP REQUESTED")
        certainty = page.locator(".ui-status").filter(
            has_text="Mutation certainty"
        )
        expect(certainty).to_contain_text("1 reconciliation required")
        nav.get_by_role("link", name="Operations", exact=True).click()
        explanation = page.get_by_role(
            "textbox", name=f"Outcome explanation for command {command['id']}"
        )
        explanation.fill(
            "Observed ship evidence; still reviewing the receipt."
        )
        page.locator("#doctor-check").click()
        expect(page.locator("#doctor-status")).to_contain_text("unverified")
        nav.get_by_role("link", name="Overview", exact=True).click()
        expect(page.locator("#shared-ship-context")).to_be_hidden()

        # Fresh stored account evidence cannot stand in for a worker heartbeat.
        worker = page.locator(".ui-status").filter(has_text="Worker liveness")
        page.clock.fast_forward(20000)
        expect(worker).to_contain_text("Unknown · stale")
        expect(certainty).to_contain_text("1 reconciliation required")
        expect(
            page.locator(".ui-status").filter(has_text="Observation freshness")
        ).to_contain_text("recent stored, not live")
        page.route(
            "**/api/report?**",
            lambda route: route.fulfill(status=503, json={"error": "Offline"}),
        )
        page.locator("#refresh").click()
        expect(page.locator("#ui-root")).to_contain_text("Update unavailable")
        expect(certainty).to_contain_text("1 reconciliation required")
        page.screenshot(
            path=str(flight_root / f"overview-stale-{width}.png"),
            full_page=True,
        )
        nav.get_by_role("link", name="Operations", exact=True).click()
        expect(explanation).to_have_value(
            "Observed ship evidence; still reviewing the receipt."
        )
        page.screenshot(
            path=str(flight_root / f"operations-review-{width}.png"),
            full_page=True,
        )
        page.locator("#flight-logout").click()
        expect(page.locator("#flight-login")).to_be_visible()
        expect(page.locator("#ui-root")).not_to_contain_text("SYNTHETIC-1")
        assert not page.evaluate(
            "Object.keys(localStorage).some(k=>k.startsWith('selected-ship:'))"
        )
        assert not errors, errors
        assert not violations, violations
        browser.close()
    assert (flight_root / "STOP").exists()
    assert queue.get(command["id"])["status"] == "reconciliation_required"
    assert world(flight_root)["mutations"] == []
    queue.close()
