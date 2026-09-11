import json
import os
import re
import sqlite3
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from py_st.services.contract_planning import plan_contract_procurement
from py_st.services.contract_sources import contract_sources
from py_st.services.dashboard import dashboard_server
from py_st.services.doctor import diagnose
from py_st.services.intelligence import Intelligence
from py_st.services.market_history import market_history


def test_dashboard_shared_data_and_guarded_control(tmp_path: Path) -> None:
    # Arrange
    store = Intelligence(tmp_path / ".state/intelligence.sqlite3")
    store.observe("r:a", "agent", "a", {"credits": 175000})
    store.close()
    server = dashboard_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with httpx.Client(base_url=origin) as client:
            # Act
            page = client.get("/")
            match = re.search('nonce="([a-f0-9]+)"', page.text)
            assert match is not None
            csrf = match.group(1)
            assert all(
                marker not in page.text
                for marker in ("__UI_SCRIPT__", "__UI_STYLE__", "__NONCE__")
            )
            assert re.findall('nonce="([a-f0-9]+)"', page.text) == [csrf, csrf]
            scripts = re.findall(
                r'<script nonce="[^"]+">(.*?)</script>', page.text, re.DOTALL
            )
            assert len(scripts) == 2
            assert "Mutation certainty" in scripts[1]
            assert ".ui-nav" in page.text
            data = client.get("/api/report").json()
            denied = client.post(
                "/api/control", json={"action": "pause", "csrf": csrf}
            )
            hostile = client.get("/api/report", headers={"Host": "evil.test"})
            paused = client.post(
                "/api/control",
                headers={"Origin": origin},
                json={"action": "pause", "csrf": csrf},
            )
            # Assert
            assert data["credits"][0]["credits"] == 175000
            assert denied.status_code == hostile.status_code == 403
            assert paused.json()["paused"]
            assert (tmp_path / "STOP").exists()
            assert (
                "frame-ancestors 'none'"
                in page.headers["Content-Security-Policy"]
            )
            assert client.get("/.env").status_code == 404
            resumed = client.post(
                "/api/control",
                headers={"Origin": origin},
                json={"action": "resume", "csrf": csrf},
            )
            assert not resumed.json()["paused"]
            assert not (tmp_path / "STOP").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_dashboard_embeds_only_escaped_raw_text_terminators(
    tmp_path: Path,
) -> None:
    # Arrange: valid JS less-than/regex syntax must not be blanket-escaped.
    import py_st.services.dashboard as dashboard

    template = Path(dashboard.__file__).with_name("dashboard.html")
    (tmp_path / "dashboard.html").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )
    assets = tmp_path / "ui"
    assets.mkdir()
    expression = 'const comparison=1</re/.test("é");'
    (assets / "shell.js").write_text(
        'const text="</ScRiPt><!--é";' + expression, encoding="utf-8"
    )
    (assets / "shell.css").write_text(
        'p::after { content: "</StYlE></other>é"; }', encoding="utf-8"
    )
    with patch.object(dashboard, "__file__", str(tmp_path / "dashboard.py")):
        server = dashboard_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Act: exercise response composition and UTF-8 HTTP encoding.
        response = httpx.get(f"http://127.0.0.1:{server.server_port}/")
        # Assert: only HTML raw-text terminators/comment opener are rewritten.
        assert response.status_code == 200
        assert expression in response.text
        assert r"<\/ScRiPt>\x3c!--é" in response.text
        assert r"<\/StYlE></other>é" in response.text
        assert "</ScRiPt>" not in response.text
        assert "</StYlE>" not in response.text
        assert response.text.count("</script>") == 2
        assert response.text.count("</style>") == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def desk_ledger(tmp_path: Path) -> Path:
    """Synthetic observations only; never copy the operator's ledger."""
    store = Intelligence(tmp_path / ".state/intelligence.sqlite3")
    contract: dict[str, Any] = {
        "id": "C<script>alert(1)</script>",
        "accepted": False,
        "fulfilled": False,
        "deadlineToAccept": "2099-01-01T00:00:00Z",
        "terms": {
            "deadline": "2099-01-02T00:00:00Z",
            "payment": {"onAccepted": 100, "onFulfilled": 10000},
            "deliver": [
                {
                    "tradeSymbol": "ORE",
                    "destinationSymbol": "X-A-D",
                    "unitsRequired": 45,
                    "unitsFulfilled": 0,
                }
            ],
        },
    }
    store.observe("r:a", "contract", contract["id"], contract, "synthetic")
    for key, fulfilled in (("SECOND", False), ("FINISHED", True)):
        store.observe(
            "r:a",
            "contract",
            key,
            contract | {"id": key, "fulfilled": fulfilled},
            "synthetic",
        )
    store.observe(
        "r:a", "agent", "a", {"symbol": "a", "credits": 200000}, "synthetic"
    )
    store.observe(
        "r:b", "agent", "b", {"symbol": "b", "credits": 100000}, "synthetic"
    )
    store.observe(
        "r:a",
        "automation_run",
        "PILOT-A",
        {
            "system": "X-A",
            "execute": False,
            "status": "completed",
            "completed_steps": 1,
            "steps": 10,
            "actions_used": 0,
            "action_limit": 100,
            "outcome": "dry run",
            "last_decision": {"status": "dry run"},
            "resume_instructions": "Review before restarting",
            "resume_command": "python -m py_st auto pilot X-A",
        },
        "synthetic",
    )
    store.observe(
        "r:a",
        "ship",
        "A-1",
        {
            "symbol": "A-1",
            "nav": {
                "waypointSymbol": "X-A-D",
                "status": "DOCKED",
                "flightMode": "CRUISE",
                "route": {},
            },
            "fuel": {"current": 100, "capacity": 100},
            "cargo": {"units": 2, "capacity": 22, "inventory": []},
            "cooldown": {"remainingSeconds": 0},
        },
        "synthetic",
    )
    market = {
        "exports": [{"symbol": "ORE"}],
        "tradeGoods": [
            {"symbol": "ORE", "purchasePrice": 10, "tradeVolume": 7}
        ],
    }
    for key in ("X-A-CURRENT", "X-A-OLD", "X-A-HISTORY", "X-A-UNKNOWN"):
        store.observe("r:a", "market", key, market, "synthetic")
    with store.db:
        store.db.execute(
            "UPDATE observations SET observed_at=? WHERE key='X-A-OLD'",
            ((datetime.now(UTC) - timedelta(hours=2)).isoformat(),),
        )
        store.db.execute("DELETE FROM observations WHERE key='X-A-UNKNOWN'")
    for key in ("X-A-OLD", "X-A-HISTORY", "X-A-UNKNOWN"):
        store.observe(
            "r:a",
            "market",
            key,
            {"exports": [{"symbol": "ORE"}]},
            "synthetic",
        )
    store.close()
    return tmp_path


@pytest.fixture
def desk_http(desk_ledger: Path) -> Iterator[httpx.Client]:
    server = dashboard_server(desk_ledger, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with httpx.Client(
            base_url=origin, headers={"Origin": origin}
        ) as client:
            yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def model_body(client: httpx.Client) -> dict[str, Any]:
    match = re.search('nonce="([a-f0-9]+)"', client.get("/").text)
    assert match
    report = client.get("/api/report?scope=r:a").json()
    return {
        "csrf": match.group(1),
        "model": {
            "contract": report["contracts"][0]["data"],
            "credits": report["agents"][0]["data"]["credits"],
            "ship_capacity": 20,
            "quotes": [
                {
                    "source": "X-A-CURRENT",
                    "destination": "X-A-D",
                    "trade_symbol": "ORE",
                    "purchase_price": 10,
                    "trade_volume": 7,
                    "fuel_cost": 4,
                    "travel_seconds": 30,
                }
            ],
        },
    }


@pytest.mark.parametrize("target_exists", [False, True])
def test_stop_symlink_is_a_sentinel_not_a_write_target(
    desk_http: httpx.Client, desk_ledger: Path, target_exists: bool
) -> None:
    # Arrange: STOP remains a request even if its symlink target moved.
    target = desk_ledger / "owner-note"
    if target_exists:
        target.write_text("preserve this note")
    before = target.stat().st_mtime_ns if target_exists else None
    stop = desk_ledger / "STOP"
    stop.symlink_to(target)
    csrf = model_body(desk_http)["csrf"]

    # Act / Assert: report agrees with doctor; pause never follows the link.
    assert desk_http.get("/api/report?scope=r:a").json()["paused"] is True
    findings = desk_http.get("/api/doctor?scope=r:a").json()["findings"]
    assert any(f["code"] == "stop_present" for f in findings)
    response = desk_http.post(
        "/api/control", json={"action": "pause", "csrf": csrf}
    )
    assert response.json()["paused"] is True
    assert stop.is_symlink()
    assert target.exists() is target_exists
    if target_exists:
        assert target.read_text() == "preserve this note"
        assert target.stat().st_mtime_ns == before
    response = desk_http.post(
        "/api/control", json={"action": "resume", "csrf": csrf}
    )
    assert response.json()["paused"] is False
    assert not stop.is_symlink()
    assert target.exists() is target_exists


def test_stop_control_reports_filesystem_failure_without_clearing(
    desk_http: httpx.Client, desk_ledger: Path
) -> None:
    stop = desk_ledger / "STOP"
    stop.mkdir()
    csrf = model_body(desk_http)["csrf"]

    response = desk_http.post(
        "/api/control", json={"action": "resume", "csrf": csrf}
    )

    assert response.status_code == 503
    assert response.json() == {"error": "STOP control unavailable"}
    assert stop.is_dir()
    assert desk_http.get("/api/report?scope=r:a").json()["paused"] is True


def test_desk_shared_services_read_only(
    desk_http: httpx.Client,
    desk_ledger: Path,
) -> None:
    database = desk_ledger / ".state/intelligence.sqlite3"
    before = database.read_bytes()
    connect = sqlite3.connect
    transport_request = httpx.HTTPTransport.handle_request
    statements: list[str] = []

    def read_only(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        assert args[0].endswith("?mode=ro") and kwargs["uri"]
        db: sqlite3.Connection = connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    def local_request(
        transport: httpx.HTTPTransport,
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url.host == "127.0.0.1"
        return transport_request(transport, request)

    with (
        patch("sqlite3.connect", side_effect=read_only),
        patch("httpx.HTTPTransport.handle_request", new=local_request),
        patch("py_st.services.automation.Session", side_effect=AssertionError),
        patch("py_st.client.SpaceTradersClient", side_effect=AssertionError),
        patch("dotenv.load_dotenv", side_effect=AssertionError),
        patch("dotenv.find_dotenv", side_effect=AssertionError),
        patch("pathlib.Path.open", side_effect=AssertionError),
    ):
        body = model_body(desk_http)
        contract = body["model"]["contract"]["id"]
        result = desk_http.get(
            "/api/sources", params={"scope": "r:a", "contract": contract}
        ).json()
        expected = contract_sources(
            database,
            "r:a",
            contract,
            now=datetime.fromisoformat(result["evaluated_at"]),
        )
        assert result == expected
        sources = result["deliveries"][0]["sources"]
        assert [s["quote_status"] for s in sources] == [
            "fresh",
            "fresh_historical",
            "stale",
            "missing",
        ]
        assert sources[2]["quote_age_seconds"] >= 7200
        assert sources[2]["purchase_price"] is None
        assert sources[3]["quote_observed_at"] is None
        with patch("sqlite3.connect", side_effect=AssertionError):
            response = desk_http.post("/api/contract-model", json=body)
        assert response.status_code == 200
        expected_model = plan_contract_procurement(**body["model"])
        actual = response.json()
        assert (
            abs(
                actual.pop("deadline_seconds")
                - expected_model.pop("deadline_seconds")
            )
            <= 1
        )
        assert actual == expected_model
        assert actual["execution_authorized"] is False
        assert actual["steps"][0]["purchase_batches"] == 7
        diagnosis = desk_http.get("/api/doctor?scope=r:a")
        assert diagnosis.status_code == 200
        assert diagnosis.json() == diagnose(database, "r:a", root=desk_ledger)
        history = desk_http.get(
            "/api/market-history?scope=r:a&waypoint=X-A-OLD&good=ORE"
        )
        assert history.status_code == 200
        data = history.json()
        assert data == market_history(
            database,
            "r:a",
            "X-A-OLD",
            "ORE",
            now=datetime.fromisoformat(data["evaluated_at"]),
        )
        assert data["points"][0]["stale"]
        assert data["points"][0]["visibility"] == "retained_history"
        assert not (desk_ledger / "STOP").exists()
    assert database.read_bytes() == before
    assert all(
        s.startswith(("SELECT", "WITH", "BEGIN", "PRAGMA user_version"))
        for s in statements
    )


@pytest.mark.parametrize(
    "query",
    [
        "",
        "scope=bad&contract=SECOND",
        "scope=r:z&contract=SECOND",
        "scope=r:b&contract=SECOND",
        "scope=r:a&contract=missing",
        "scope=r:a&scope=r:b&contract=SECOND",
        "scope=r:a&contract=SECOND&database=/etc/passwd",
    ],
)
def test_sources_invalid_query(desk_http: httpx.Client, query: str) -> None:
    assert desk_http.get("/api/sources?" + query).status_code == 400


@pytest.mark.parametrize(
    "query",
    [
        "",
        "scope=r:a",
        "scope=r:b&waypoint=X-A-OLD&good=ORE",
        "scope=r:z&waypoint=X-A-OLD&good=ORE",
        "scope=r:a&waypoint=X-A-OLD&good=",
        *[
            "scope=r:a&waypoint=X-A-OLD&good=ORE&" + extra
            for extra in (
                "limit=0",
                "limit=101",
                "limit=",
                "limit=1.5",
                "limit=-1",
                "limit=+1",
                "limit=50&limit=1",
                "scope=r:b",
                "good=FUEL",
                "waypoint=X-A-CURRENT",
                "database=/etc/passwd",
                "root=/tmp",
                "execute=true",
                "csrf=secret",
            )
        ],
    ],
)
def test_market_history_query_guards(
    desk_http: httpx.Client, query: str
) -> None:
    assert desk_http.get("/api/market-history?" + query).status_code == 400


def test_market_history_get_only_host_and_empty(
    desk_http: httpx.Client,
) -> None:
    url = "/api/market-history?scope=r:a&waypoint=X-A-CURRENT&good=ORE"
    response = desk_http.get(url)
    assert response.status_code == 200  # No auth/CSRF required for local GET.
    assert response.json()["limit"] == 50
    assert response.json()["points"][0]["sell_price"] is None
    assert desk_http.get(url, headers={"Host": "evil.test"}).status_code == 403
    assert desk_http.post("/api/market-history", json={}).status_code == 404
    assert (
        desk_http.get(url.replace("good=ORE", "good=FUEL")).json()["points"]
        == []
    )


@pytest.mark.parametrize(
    "query",
    [
        "",
        "scope=",
        "scope=bad",
        "scope=r:unknown",
        "scope=r:a&scope=r:b",
        "scope=r:a&root=/tmp",
        "scope=r:a&database=/etc/passwd",
        "scope=r:a&db=/etc/passwd",
        "scope=r:a&max_age=1",
        "scope=r:a&execute=true",
    ],
)
def test_doctor_invalid_query(desk_http: httpx.Client, query: str) -> None:
    assert desk_http.get("/api/doctor?" + query).status_code == 400


@pytest.mark.parametrize("stopped", [False, True])
def test_doctor_shared_result_and_host(
    desk_http: httpx.Client, desk_ledger: Path, stopped: bool
) -> None:
    # Arrange: r:a has fresh complete records and no pending exposure.
    if stopped:
        (desk_ledger / "STOP").touch()
    database = desk_ledger / ".state/intelligence.sqlite3"
    before = database.read_bytes()
    expected = diagnose(database, "r:a", root=desk_ledger)

    # Act / Assert: both successful diagnostic outcomes use HTTP 200.
    with patch("py_st.services.dashboard.diagnose", wraps=diagnose) as shared:
        response = desk_http.get("/api/doctor?scope=r:a")
        shared.assert_called_once_with(database, "r:a", root=desk_ledger)
        assert response.status_code == 200
        assert response.json() == expected
        assert expected["exit_code"] == int(stopped)
        assert (
            desk_http.get(
                "/api/doctor?scope=r:a", headers={"Host": "evil.test"}
            ).status_code
            == 403
        )
        assert shared.call_count == 1
    assert database.read_bytes() == before
    assert (desk_ledger / "STOP").exists() == stopped


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract", None),
        ("contract", {"terms": []}),
        ("quotes", {}),
        ("quotes", [None]),
        ("ship_capacity", True),
        ("credits", -1),
        ("price_margin", "NaN"),
        ("database", "/etc/passwd"),
    ],
)
def test_model_invalid_payload(
    desk_http: httpx.Client,
    field: str,
    value: Any,
) -> None:
    body = model_body(desk_http)
    body["model"][field] = value
    response = desk_http.post("/api/contract-model", json=body)
    assert response.status_code == 400
    assert response.json()["error"]


@pytest.mark.parametrize("field", ["fuel_cost", "travel_seconds"])
@pytest.mark.parametrize("value", [None, -1, True, "0"])
def test_model_requires_explicit_route_costs(
    desk_http: httpx.Client,
    field: str,
    value: Any,
) -> None:
    body = model_body(desk_http)
    body["model"]["quotes"][0][field] = value
    assert desk_http.post("/api/contract-model", json=body).status_code == 400


def test_model_http_guards(desk_http: httpx.Client) -> None:
    body = model_body(desk_http)
    url = "/api/contract-model"
    for headers in (
        {"Origin": ""},
        {"Origin": "https://evil.test"},
        {"Host": "evil.test"},
    ):
        assert (
            desk_http.post(url, headers=headers, json=body).status_code == 403
        )
    for csrf in ("", "incorrect"):
        assert (
            desk_http.post(url, json=body | {"csrf": csrf}).status_code == 403
        )
    for content in (b"", b"{", b"x" * 65537, b"\xff"):
        assert desk_http.post(url, content=content).status_code == 400
    assert desk_http.post(url, content=json.dumps(body)).status_code == 400
    assert (
        desk_http.get(
            "/api/sources?scope=r:a&contract=SECOND", headers={"Host": "evil"}
        ).status_code
        == 403
    )
    assert desk_http.get("/api/report?scope=unknown").status_code == 400


def test_model_infeasible_is_not_http_error(desk_http: httpx.Client) -> None:
    body = model_body(desk_http)
    body["model"]["credits"] = 0
    response = desk_http.post("/api/contract-model", json=body)
    assert response.status_code == 200
    assert response.json()["feasible"] is False
    assert response.json()["reasons"] == [
        "Insufficient credits for goods, fuel, and reserves"
    ]
    assert response.json()["execution_authorized"] is False


def test_report_exports_scoped_pilot_progress(desk_http: httpx.Client) -> None:
    # Arrange / Act
    first = desk_http.get("/api/report?scope=r:a").json()
    other = desk_http.get("/api/report?scope=r:b").json()

    # Assert
    assert first["automation_runs"][0]["key"] == "PILOT-A"
    assert first["automation_runs"][0]["data"]["outcome"] == "dry run"
    assert other["automation_runs"] == []


def test_fresh_dashboard_does_not_create_ledger(tmp_path: Path) -> None:
    server = dashboard_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}"
        ) as client:
            assert client.get("/").status_code == 200
            assert client.get("/api/report").json() == {
                "scopes": [],
                "paused": False,
            }
            assert (
                client.get("/api/sources?scope=r:a&contract=C").status_code
                == 400
            )
            diagnosis = client.get("/api/doctor?scope=r:a")
            assert diagnosis.status_code == 400
            assert diagnosis.json()["exit_code"] == 2
            assert diagnosis.json()["findings"][0]["code"] == "unavailable"
            assert (
                client.get(
                    "/api/market-history?scope=r:a&waypoint=X-A-M&good=ORE"
                ).status_code
                == 400
            )
        assert not (tmp_path / ".state").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Opt-in synthetic Chrome verification",
)
@pytest.mark.parametrize("width", [1440, 390])
def test_market_desk_browser(
    desk_http: httpx.Client, desk_ledger: Path, width: int
) -> None:
    browser_api = pytest.importorskip("playwright.sync_api")
    database = desk_ledger / ".state/intelligence.sqlite3"
    store = Intelligence(database)
    now = datetime.now(UTC)
    timestamps = []
    for minutes in (60, 50, 10):
        timestamp = (now - timedelta(minutes=minutes)).isoformat()
        timestamps.append(timestamp)
        store.observe(
            "r:a",
            "market",
            "X-A-TREND",
            {
                "exports": [],
                "tradeGoods": [
                    {
                        "symbol": "ORE",
                        "purchasePrice": minutes,
                        "sellPrice": minutes + 2,
                        "tradeVolume": 7,
                        "supply": "<script>bad()</script>",
                        "activity": "WEAK",
                    },
                    {"symbol": "FUEL", "purchasePrice": 10, "tradeVolume": 3},
                ],
            },
            "synthetic",
        )
        with store.db:
            store.db.execute(
                "UPDATE observations SET observed_at=? "
                "WHERE id=(SELECT MAX(id) FROM observations)",
                (timestamp,),
            )
    store.observe(
        "r:a", "market", "X-A-TREND", {"exports": []}, "synthetic-advert"
    )
    store.close()
    before = database.read_bytes()
    with browser_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors: list[str] = []
            requests: list[Any] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request))
            page.goto(str(desk_http.base_url))
            page.get_by_role("navigation").get_by_role(
                "link", name="Markets", exact=True
            ).click()
            page.locator("#scope").select_option("r:a")
            browser_api.expect(
                page.locator("#market-select option")
            ).to_have_count(5)
            page.get_by_label("Cached market", exact=True).select_option(
                "X-A-TREND"
            )
            page.get_by_label("Good history", exact=True).select_option("ORE")
            status = page.locator("#market-status")
            history = page.locator("#market-history")
            browser_api.expect(status).to_contain_text("3 cached observations")
            browser_api.expect(page.locator("#market-asof")).to_contain_text(
                "Retained history"
            )
            browser_api.expect(page.locator("#market-asof")).to_contain_text(
                timestamps[-1]
            )
            browser_api.expect(history).to_contain_text(
                "<script>bad()</script>"
            )
            assert (
                page.locator(
                    "#market-history script, #market-prices script"
                ).count()
                == 0
            )
            assert history.locator("tr").count() == 3
            assert (
                history.locator("tr").first.locator("td").first.inner_text()
                == timestamps[0]
            )
            xs = page.locator("#market-trend circle").evaluate_all(
                "nodes=>nodes.slice(0,3).map(n=>Number(n.getAttribute('cx')))"
            )
            assert (xs[1] - xs[0]) / (xs[2] - xs[0]) == pytest.approx(0.2)
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )
            with page.expect_response("**/api/market-history?**"):
                page.get_by_role("button", name="Refresh ledger").click()
            assert page.locator("#market-select").input_value() == "X-A-TREND"
            assert page.locator("#good-select").input_value() == "ORE"

            # A late success after good change and a late error after A->B->A.
            held: list[Any] = []
            page.route(
                "**/api/market-history?**", lambda route: held.append(route)
            )
            page.locator("#good-select").select_option("FUEL")
            page.wait_for_timeout(100)
            assert len(held) == 1
            page.locator("#good-select").select_option("ORE")
            page.wait_for_timeout(100)
            assert len(held) == 2
            held[0].fulfill(
                json=desk_http.get(
                    "/api/market-history?scope=r:a&waypoint=X-A-TREND&good=FUEL"
                ).json()
            )
            browser_api.expect(history).to_be_empty()
            browser_api.expect(status).to_have_text(
                "Loading cached history..."
            )
            page.locator("#scope").select_option("r:b")
            browser_api.expect(
                page.locator("#market-select option")
            ).to_have_count(1)
            browser_api.expect(history).to_be_empty()
            browser_api.expect(status).to_contain_text("No detailed markets")
            page.locator("#scope").select_option("r:a")
            browser_api.expect(
                page.locator("#market-select option")
            ).to_have_count(5)
            held[1].fulfill(status=503, json={"error": "OLD ERROR"})
            page.wait_for_timeout(100)
            browser_api.expect(status).not_to_contain_text("OLD ERROR")
            assert page.locator("#market-select").input_value() == ""
            page.unroute("**/api/market-history?**")
            page.locator("#market-select").select_option("X-A-CURRENT")
            page.locator("#good-select").select_option("ORE")
            browser_api.expect(status).to_contain_text("1 cached observations")
            browser_api.expect(status).to_contain_text("At least two")
            browser_api.expect(history).to_contain_text("unknown")
            browser_api.expect(page.locator("#market-trend")).to_be_hidden()
            # Report timestamps must not become fresh through Date.parse's
            # permissive timezone/calendar parsing.
            report = desk_http.get("/api/report?scope=r:a").json()
            detail = next(
                r for r in report["prices"] if r["key"] == "X-A-CURRENT"
            )
            page.route(
                "**/api/report?**", lambda route: route.fulfill(json=report)
            )
            for timestamp, label in (
                (now.replace(tzinfo=None).isoformat(), "INVALID timestamp"),
                ("2026-02-30T12:00:00Z", "INVALID timestamp"),
                ((now + timedelta(days=1)).isoformat(), "FUTURE timestamp"),
            ):
                detail["observed_at"] = timestamp
                with page.expect_response("**/api/market-history?**"):
                    page.get_by_role("button", name="Refresh ledger").click()
                browser_api.expect(
                    page.locator("#market-asof")
                ).to_contain_text(label)
            assert all(r.method == "GET" for r in requests)
            assert not errors, errors
        finally:
            browser.close()
    assert database.read_bytes() == before
    assert not (desk_ledger / "STOP").exists()


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Opt-in synthetic Chrome verification",
)
@pytest.mark.parametrize("width", [1440, 390])
def test_market_basic_iso_browser(
    desk_http: httpx.Client, desk_ledger: Path, width: int
) -> None:
    browser_api = pytest.importorskip("playwright.sync_api")
    database = desk_ledger / ".state/intelligence.sqlite3"
    store = Intelligence(database)
    start = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    timestamps = [
        start.strftime("%Y%m%dT%H%M%S%z"),
        (start + timedelta(minutes=30)).isoformat(),
    ]
    for timestamp in timestamps:
        store.observe(
            "r:a",
            "market",
            "X-A-BASIC",
            {
                "exports": [],
                "tradeGoods": [
                    {
                        "symbol": "ORE",
                        "purchasePrice": 20,
                        "sellPrice": 10,
                        "tradeVolume": 7,
                    }
                ],
            },
            "synthetic",
        )
        with store.db:
            store.db.execute(
                "UPDATE observations SET observed_at=? "
                "WHERE id=(SELECT MAX(id) FROM observations)",
                (timestamp,),
            )
    store.close()
    with browser_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(str(desk_http.base_url))
            page.get_by_role("navigation").get_by_role(
                "link", name="Markets", exact=True
            ).click()
            page.locator("#scope").select_option("r:a")
            page.get_by_label("Cached market", exact=True).select_option(
                "X-A-BASIC"
            )
            with page.expect_response("**/api/market-history?**") as response:
                page.get_by_label("Good history", exact=True).select_option(
                    "ORE"
                )
            data = response.value.json()
            assert [p["observed_at_ms"] for p in data["points"]] == [
                start.timestamp() * 1000,
                (start + timedelta(minutes=30)).timestamp() * 1000,
            ]
            browser_api.expect(
                page.locator("#market-history")
            ).to_contain_text(timestamps[0])
            browser_api.expect(
                page.locator("#market-trend circle")
            ).to_have_count(4)
            assert page.locator("#market-trend circle").evaluate_all(
                "nodes=>nodes.map(n=>Number(n.getAttribute('cx')))"
            ) == [20, 580, 20, 580]

            # Malformed response times remain table-only gaps, including a
            # JSON number that overflows to Infinity in JavaScript.
            data["points"][1:1] = [
                data["points"][0] | {"observed_at_ms": value}
                for value in (None, "bad", 1e100, "NONFINITE")
            ]
            page.route(
                "**/api/market-history?**",
                lambda route: route.fulfill(
                    content_type="application/json",
                    body=json.dumps(data).replace('"NONFINITE"', "1e400"),
                ),
            )
            page.get_by_role("button", name="Refresh ledger").click()
            browser_api.expect(page.locator("#market-status")).to_contain_text(
                "4 observations have invalid plotting times"
            )
            browser_api.expect(
                page.locator("#market-trend circle")
            ).to_have_count(4)
            assert page.locator("#market-trend circle").evaluate_all(
                "nodes=>nodes.every(n=>['cx','cy'].every("
                "a=>Number.isFinite(Number(n.getAttribute(a)))))"
            )
            paths = page.locator("#market-trend path").evaluate_all(
                "nodes=>nodes.map(n=>n.getAttribute('d'))"
            )
            assert all(p.count("M") == 2 and "L" not in p for p in paths)
            assert all("NaN" not in p and "Infinity" not in p for p in paths)
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )
            assert not errors, errors
        finally:
            browser.close()


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Opt-in synthetic Chrome verification",
)
@pytest.mark.parametrize("width", [1440, 390])
def test_doctor_browser(
    desk_http: httpx.Client, desk_ledger: Path, width: int
) -> None:
    # Arrange: STOP and unresolved actions belong only to this fixture.
    browser_api = pytest.importorskip("playwright.sync_api")
    stop = desk_ledger / "STOP"
    stop.write_text("synthetic owner stop")
    database = desk_ledger / ".state/intelligence.sqlite3"
    store = Intelligence(database)
    action = store.begin_action("r:a", "/synthetic/<script>bad()</script>", {})
    store.close()
    before = database.read_bytes()
    with browser_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            errors: list[str] = []
            requests: list[Any] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request))
            page.goto(str(desk_http.base_url))
            page.locator("#scope").select_option("r:a")
            browser_api.expect(page.locator("#state")).to_have_text(
                "STOP REQUESTED"
            )
            assert not any("/api/doctor" in r.url for r in requests)

            # Act / Assert: real shared findings, with STOP left intact.
            page.get_by_role("navigation").get_by_role(
                "link", name="Operations", exact=True
            ).click()
            button = page.get_by_role("button", name="Check recorded safety")
            button.click()
            findings = page.locator("#doctor-findings")
            status = page.locator("#doctor-status")
            browser_api.expect(findings).to_contain_text("stop present")
            browser_api.expect(findings).to_contain_text(f"Pending #{action}")
            browser_api.expect(status).to_contain_text("readiness unverified")
            browser_api.expect(status).to_contain_text(
                "process liveness unknown"
            )
            assert "--execute" not in findings.inner_text()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )

            # Hold responses to verify request versions and A -> B -> A.
            held: list[Any] = []
            page.route("**/api/doctor?**", lambda route: held.append(route))
            button.click()
            browser_api.expect(status).to_contain_text("Checking recorded")
            button.click()
            page.wait_for_timeout(100)
            assert len(held) == 2
            synthetic = desk_http.get("/api/doctor?scope=r:a").json()
            synthetic["findings"] = [
                {
                    "code": "pending_actions",
                    "next_step": "Never replay.",
                    "actions": [
                        {
                            "id": "<b>pending</b>",
                            "path": "/<script>bad()</script>",
                        }
                    ],
                    "procurement": {
                        "status": "recorded",
                        "next_step": "Review owned cargo; not live readiness.",
                        "goods": [
                            {
                                "good": "<script>IRON</script>",
                                "required": 10,
                                "delivered": 4,
                                "held": 3,
                                "to_acquire": 3,
                                "excess": 0,
                            }
                        ],
                        "observations": {"ship": "2026-09-10T00:02:00Z"},
                        "deadlines": {
                            "delivery": {"state": "unknown", "at": None}
                        },
                    },
                }
            ]
            held[1].fulfill(json=synthetic)
            browser_api.expect(findings).to_contain_text(
                "Pending #<b>pending</b> / /<script>bad()</script>"
            )
            browser_api.expect(findings).to_contain_text(
                "<script>IRON</script>: 4/10 delivered / 3 held / "
                "3 to acquire / 0 excess"
            )
            browser_api.expect(findings).to_contain_text(
                "ship observed: 2026-09-10T00:02:00Z"
            )
            browser_api.expect(findings).to_contain_text(
                "delivery deadline: unknown / unknown"
            )
            assert findings.locator("script, b").count() == 0
            held[0].fulfill(status=503, json={"error": "OLD ERROR"})
            page.wait_for_timeout(100)
            browser_api.expect(status).not_to_contain_text("OLD ERROR")
            button.click()
            page.wait_for_timeout(100)
            assert len(held) == 3
            page.locator("#scope").select_option("r:b")
            browser_api.expect(status).to_be_empty()
            browser_api.expect(findings).to_be_empty()
            page.locator("#scope").select_option("r:a")
            held[2].fulfill(json=synthetic)
            page.wait_for_timeout(100)
            browser_api.expect(status).to_be_empty()
            browser_api.expect(findings).to_be_empty()
            assert all(r.method == "GET" for r in requests)
            assert not errors, errors
        finally:
            browser.close()
    assert stop.read_text() == "synthetic owner stop"
    assert database.read_bytes() == before
    assert (
        diagnose(database, "r:a", root=desk_ledger)["findings"][1]["actions"][
            0
        ]["id"]
        == action
    )


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Opt-in synthetic Chrome verification",
)
def test_contract_desk_browser(
    desk_http: httpx.Client,
    desk_ledger: Path,
) -> None:
    browser_api = pytest.importorskip("playwright.sync_api")
    store = Intelligence(desk_ledger / ".state/intelligence.sqlite3")
    try:
        ship = store.latest("r:a", "ship")[0]["data"]
        store.observe(
            "r:b", "ship", "B-1", ship | {"symbol": "B-1"}, "synthetic"
        )
        store.observe("r:a", "plan", "A-plan", {}, "synthetic")
        store.observe(
            "r:a",
            "position",
            "A-position",
            {
                "status": "open",
                "plan": {"good": "ORE", "destination": "X-A-D"},
            },
            "synthetic",
        )
        store.observe(
            "r:a",
            "position",
            "procurement:C-MULTI",
            {
                "status": "open",
                "stage": "acquiring",
                "plan": {
                    "strategy": "local-multi",
                    "destination": "X-A-D",
                    "purchase_ceilings": {"IRON": 120, "COPPER": 240},
                },
                "goods": {
                    "IRON": {"remaining": 5, "held": 2, "to_buy": 3},
                    "COPPER": {"remaining": 3, "held": 0, "to_buy": 3},
                },
            },
            "synthetic",
        )
        store.observe(
            "r:a",
            "position",
            "unknown-intent",
            {"status": "review", "goods": {"UNKNOWN": None}},
        )
        store.observe(
            "r:a",
            "position",
            "reposition:A-1",
            {
                "status": "open",
                "plan": {
                    "good": "IRON",
                    "source": "X-A-S",
                    "destination": "X-A-D",
                },
            },
        )
        store.observe(
            "r:a",
            "waypoint",
            "X-A-D",
            {"x": 0, "y": 0, "traits": [{"symbol": "MARKETPLACE"}]},
            "synthetic",
        )
        action = store.begin_action("r:a", "/synthetic/a", {})
        store.finish_action(
            action,
            "succeeded",
            {
                "transaction": {
                    "tradeSymbol": "ORE",
                    "type": "PURCHASE",
                    "units": 1,
                    "totalPrice": 10,
                }
            },
        )
        action = store.begin_action("r:b", "/synthetic/b", {})
        store.finish_action(action, "rejected", {})
    finally:
        store.close()
    with browser_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            for width in (1440, 390):
                page = browser.new_page(
                    viewport={"width": width, "height": 900}
                )
                errors: list[str] = []
                page.on(
                    "pageerror",
                    lambda error, errors=errors: errors.append(str(error)),
                )
                page.goto(str(desk_http.base_url))
                page.get_by_role("navigation").get_by_role(
                    "link", name="Contracts", exact=True
                ).click()
                page.locator("#scope").select_option("r:a")
                browser_api.expect(page.locator("#positions")).to_contain_text(
                    "procurement:C-MULTI / IRON, COPPER -> X-A-D"
                )
                browser_api.expect(page.locator("#positions")).to_contain_text(
                    "IRON: 5 remaining / 2 held / 3 to acquire"
                )
                browser_api.expect(page.locator("#positions")).to_contain_text(
                    "reposition:A-1 / IRON -> X-A-S"
                )
                browser_api.expect(page.locator("#positions")).to_contain_text(
                    "UNRECOGNIZED POSITION: unknown-intent"
                )
                browser_api.expect(
                    page.locator("#positions")
                ).not_to_contain_text("undefined")
                browser_api.expect(
                    page.locator("#contract-select option")
                ).to_have_count(3)
                page.locator("#contract-select").select_option(
                    "C<script>alert(1)</script>"
                )
                browser_api.expect(
                    page.locator("#model-editor")
                ).to_be_visible()
                browser_api.expect(page.locator("#sources")).to_contain_text(
                    "HISTORICAL detail; current visibility unknown"
                )
                browser_api.expect(page.locator("#sources")).to_contain_text(
                    "STALE detail"
                )
                draft = json.loads(page.locator("#model-input").input_value())
                assert draft["credits"] == 200000
                assert draft["ship_capacity"] == 20
                assert all(
                    q["fuel_cost"] is None and q["travel_seconds"] is None
                    for q in draft["quotes"]
                )
                # Build and calculate without editing JSON, then keep the
                # independent advanced-editor regression below.
                requests: list[str] = []
                page.on(
                    "request",
                    lambda request, *, requests=requests: (
                        requests.append(request.url)
                        if request.url.endswith("/api/contract-model")
                        else None
                    ),
                )
                build = page.get_by_role(
                    "button", name="Build draft from form"
                )
                assert (
                    page.locator(
                        "#builder-routes input[type=checkbox]:checked"
                    ).count()
                    == 0
                )
                assert page.get_by_label(
                    "Credits (required)"
                ).input_value() == ("200000")
                assert (
                    page.get_by_label(
                        "Free cargo units (required)"
                    ).input_value()
                    == "20"
                )
                build.click()
                browser_api.expect(
                    page.locator("#builder-error")
                ).to_contain_text("Select at least one source")
                unknown = page.get_by_role(
                    "checkbox", name="X-A-UNKNOWN / ORE -> X-A-D", exact=True
                )
                unknown.check()
                unknown_route = page.locator(".builder-route").filter(
                    has=unknown
                )
                assert (
                    unknown_route.get_by_label(
                        "Purchase price per unit (required)"
                    ).input_value()
                    == ""
                )
                build.click()
                browser_api.expect(
                    page.locator("#builder-error")
                ).to_contain_text(
                    "Purchase price per unit (required) is missing"
                )
                browser_api.expect(
                    unknown_route.get_by_label(
                        "Purchase price per unit (required)"
                    )
                ).to_be_focused()
                unknown.uncheck()
                selected = page.get_by_role(
                    "checkbox", name="X-A-CURRENT / ORE -> X-A-D", exact=True
                )
                selected.check()
                route = page.locator(".builder-route").filter(has=selected)
                assert (
                    route.get_by_label(
                        "Purchase price per unit (required)"
                    ).input_value()
                    == "10"
                )
                assert (
                    route.get_by_label(
                        "Trade volume per batch (required)"
                    ).input_value()
                    == "7"
                )
                for field in (
                    "Fuel credits per trip (required)",
                    "Travel seconds per trip (required)",
                ):
                    entry = route.get_by_label(field)
                    assert entry.input_value() == ""
                    build.click()
                    browser_api.expect(
                        page.locator("#builder-error")
                    ).to_contain_text(field + " is missing")
                    browser_api.expect(entry).to_be_focused()
                    entry.fill("0")
                page.get_by_label("Credits (required)").fill("-1")
                build.click()
                browser_api.expect(
                    page.get_by_label("Credits (required)")
                ).to_be_focused()
                page.get_by_label("Credits (required)").fill("190000")
                page.get_by_label("Free cargo units (required)").fill("15")
                route.get_by_label("Purchase price per unit (required)").fill(
                    "11"
                )
                route.get_by_label("Trade volume per batch (required)").fill(
                    "5"
                )
                available = route.get_by_label(
                    "Available units (optional; blank = unbounded)"
                )
                available.fill("-1")
                build.click()
                browser_api.expect(available).to_be_focused()
                available.fill("")
                assert (
                    json.loads(page.locator("#model-input").input_value())
                    == draft
                )
                assert not requests
                build.click()
                built = json.loads(page.locator("#model-input").input_value())
                assert built["credits"] == 190000
                assert built["ship_capacity"] == 15
                assert built["quotes"] == [
                    {
                        "source": "X-A-CURRENT",
                        "destination": "X-A-D",
                        "trade_symbol": "ORE",
                        "purchase_price": 11,
                        "trade_volume": 5,
                        "fuel_cost": 0,
                        "travel_seconds": 0,
                    }
                ]
                assert not requests
                with page.expect_response("**/api/report?scope=r%3Aa"):
                    page.get_by_role("button", name="Refresh ledger").click()
                browser_api.expect(selected).to_be_checked()
                assert (
                    route.get_by_label(
                        "Fuel credits per trip (required)"
                    ).input_value()
                    == "0"
                )
                assert (
                    json.loads(page.locator("#model-input").input_value())
                    == built
                )
                page.get_by_role(
                    "button", name="Calculate offline model"
                ).click()
                browser_api.expect(
                    page.locator("#model-result")
                ).to_contain_text("9 purchase batches")
                browser_api.expect(
                    page.locator("#model-result")
                ).to_contain_text("Execution authorized: false")
                page.screenshot(
                    path=str(desk_ledger / f"contract-builder-{width}.png"),
                    full_page=True,
                )
                available.fill("30")
                assert (
                    json.loads(page.locator("#model-input").input_value())
                    == built
                )
                build.click()
                page.get_by_role(
                    "button", name="Calculate offline model"
                ).click()
                browser_api.expect(
                    page.locator("#model-result")
                ).to_contain_text("Missing 15 units of ORE capacity")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                )
                page.get_by_role(
                    "button",
                    name="Reset draft from cached evidence",
                    exact=True,
                ).click()
                assert (
                    json.loads(page.locator("#model-input").input_value())
                    == draft
                )
                assert (
                    page.locator(
                        "#builder-routes input[type=checkbox]:checked"
                    ).count()
                    == 0
                )
                assert (
                    route.get_by_label(
                        "Fuel credits per trip (required)"
                    ).input_value()
                    == ""
                )
                page.get_by_role(
                    "button", name="Calculate offline model"
                ).click()
                browser_api.expect(
                    page.locator("#model-error")
                ).to_contain_text("explicit")
                draft["quotes"] = [
                    draft["quotes"][0]
                    | {
                        "fuel_cost": 4,
                        "travel_seconds": 30,
                    }
                ]
                page.locator("#model-input").fill(json.dumps(draft))
                page.get_by_role(
                    "button", name="Calculate offline model"
                ).click()
                browser_api.expect(
                    page.locator("#model-result")
                ).to_contain_text("7 purchase batches")
                browser_api.expect(
                    page.locator("#model-result")
                ).to_contain_text("Execution authorized: false")
                with page.expect_response("**/api/report?scope=r%3Aa"):
                    page.get_by_role("button", name="Refresh ledger").click()
                assert (
                    json.loads(page.locator("#model-input").input_value())
                    == draft
                )
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= innerWidth"
                )
                assert page.locator("#contracts script").count() == 0
                browser_api.expect(page.locator("#fleet")).to_contain_text(
                    "A-1"
                )
                browser_api.expect(
                    page.locator("#automation-runs")
                ).to_contain_text("X-A / DRY RUN / recorded COMPLETED")
                browser_api.expect(
                    page.locator("#automation-runs")
                ).to_contain_text(
                    "1/10 returned decisions; 0/100 actions used"
                )
                browser_api.expect(page.locator("#journal")).to_contain_text(
                    "/synthetic/a"
                )
                browser_api.expect(page.locator("#export")).to_have_attribute(
                    "href", "/api/report?scope=r%3Aa"
                )
                page.screenshot(
                    path=str(desk_ledger / f"contract-desk-{width}.png"),
                    full_page=True,
                )
                # Late model/report/source responses cannot restore old state.
                models: list[Any] = []
                reports: list[Any] = []
                page.route(
                    "**/api/contract-model",
                    lambda route, *, models=models: models.append(route),
                )
                page.route(
                    "**/api/report?scope=r%3Aa",
                    lambda route, *, reports=reports: reports.append(route),
                )
                page.get_by_role(
                    "button", name="Calculate offline model"
                ).click()
                page.get_by_role("button", name="Refresh ledger").click()
                held: list[Any] = []
                page.route(
                    "**/api/sources?**",
                    lambda route, *, held=held: held.append(route),
                )
                page.locator("#contract-select").select_option("SECOND")
                page.wait_for_function(
                    "document.querySelector('#desk-status').textContent"
                    ".includes('Loading cached')"
                )
                incoming: list[Any] = []
                page.route(
                    "**/api/report?scope=r%3Ab",
                    lambda route, *, incoming=incoming: incoming.append(route),
                )
                page.locator("#scope").select_option("r:b")
                for phase in ("pending", "failed", "late old responses"):
                    if phase == "failed":
                        assert incoming
                        incoming[0].fulfill(
                            status=503, json={"error": "Synthetic unavailable"}
                        )
                        browser_api.expect(
                            page.locator("#error")
                        ).to_have_text("Synthetic unavailable")
                        browser_api.expect(
                            page.locator("#desk-status")
                        ).to_contain_text("Refresh ledger to retry")
                    elif phase == "late old responses":
                        assert held and models and reports
                        held[0].fulfill(
                            json=desk_http.get(
                                "/api/sources?scope=r:a&contract=SECOND"
                            ).json()
                        )
                        reports[0].fulfill(
                            json=desk_http.get("/api/report?scope=r:a").json()
                        )
                        models[0].fulfill(
                            json=plan_contract_procurement(**draft)
                        )
                        page.wait_for_timeout(100)
                    assert page.locator("#scope").input_value() == "r:b"
                    for metric in ("credits", "profit", "reserve", "coverage"):
                        browser_api.expect(
                            page.locator(f"#{metric}")
                        ).to_have_text("--")
                    for panel in (
                        "chart",
                        "map",
                        "fleet",
                        "contracts",
                        "plans",
                        "routes",
                        "cash",
                        "audit",
                        "positions",
                        "markets",
                        "journal",
                        "contract-select",
                        "sources",
                        "model-ship",
                        "snapshot",
                        "snapshot-json",
                        "model-result",
                        "builder-routes",
                        "builder-error",
                        "builder-status",
                        "automation-runs",
                    ):
                        assert (
                            page.locator(f"#{panel}").text_content() == ""
                        ), (phase, panel)
                    assert page.locator("#model-input").input_value() == ""
                    assert page.locator("#builder-credits").input_value() == ""
                    assert (
                        page.locator("#builder-capacity").input_value() == ""
                    )
                    browser_api.expect(
                        page.locator("#model-editor")
                    ).to_be_hidden()
                    assert (
                        page.locator("#export").get_attribute("href") is None
                    )
                    browser_api.expect(
                        page.locator("#export")
                    ).to_have_attribute("aria-disabled", "true")
                    browser_api.expect(page.locator("#state")).to_have_text(
                        "STOP CLEAR"
                    )
                # A successful explicit retry restores only the new scope.
                page.unroute("**/api/report?scope=r%3Ab")
                with page.expect_response("**/api/report?scope=r%3Ab"):
                    page.get_by_role("button", name="Refresh ledger").click()
                browser_api.expect(page.locator("#credits")).to_have_text(
                    "100,000"
                )
                browser_api.expect(page.locator("#profit")).to_have_text("0")
                browser_api.expect(page.locator("#reserve")).to_have_text(
                    "50,000"
                )
                browser_api.expect(page.locator("#coverage")).to_have_text(
                    "0 / 0"
                )
                browser_api.expect(page.locator("#fleet")).to_contain_text(
                    "B-1"
                )
                browser_api.expect(page.locator("#fleet")).not_to_contain_text(
                    "A-1"
                )
                browser_api.expect(page.locator("#journal")).to_contain_text(
                    "/synthetic/b"
                )
                browser_api.expect(
                    page.locator("#journal")
                ).not_to_contain_text("/synthetic/a")
                browser_api.expect(page.locator("#export")).to_have_attribute(
                    "href", "/api/report?scope=r%3Ab"
                )
                assert (
                    page.locator("#export").get_attribute("aria-disabled")
                    is None
                )
                assert (
                    desk_http.get(
                        page.locator("#export").get_attribute("href")
                    ).json()["scope"]
                    == "r:b"
                )
                browser_api.expect(page.locator("#error")).to_be_empty()
                browser_api.expect(
                    page.locator("#desk-status")
                ).to_contain_text("No unfulfilled contracts")
                assert page.locator("#scope").input_value() == "r:b"
                browser_api.expect(
                    page.locator("#automation-runs")
                ).to_contain_text("No recorded pilot runs")
                assert page.locator("#model-result").inner_text() == ""
                assert not errors, errors
                page.close()
        finally:
            browser.close()
    assert not (desk_ledger / "STOP").exists()


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Opt-in synthetic Chrome verification",
)
@pytest.mark.parametrize("width", [1440, 390])
def test_desk_uses_source_contract_snapshot(
    desk_http: httpx.Client,
    desk_ledger: Path,
    width: int,
) -> None:
    browser_api = pytest.importorskip("playwright.sync_api")
    store = Intelligence(desk_ledger / ".state/intelligence.sqlite3")
    try:
        contract = next(
            r["data"]
            for r in store.latest("r:a", "contract")
            if r["key"] == "SECOND"
        )
        contract["terms"]["deliver"][0]["unitsRequired"] = 10
        store.observe("r:a", "contract", "SECOND", contract, "synthetic-offer")
        earlier_report = desk_http.get("/api/report?scope=r:a").json()
        with browser_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome", headless=True
            )
            try:
                page = browser.new_page(
                    viewport={"width": width, "height": 900}
                )
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                # Keep the displayed report at offered 10, including any
                # background refresh. Sources uses the real synthetic ledger.
                page.route(
                    "**/api/report?**",
                    lambda route: route.fulfill(json=earlier_report),
                )
                page.goto(str(desk_http.base_url))
                page.get_by_role("navigation").get_by_role(
                    "link", name="Contracts", exact=True
                ).click()
                browser_api.expect(
                    page.locator("#contract-select option")
                ).to_have_count(3)
                browser_api.expect(
                    page.locator('#contract-select option[value="SECOND"]')
                ).to_have_text("SECOND / offered")
                contract["accepted"] = True
                delivery = contract["terms"]["deliver"][0]
                for fulfilled in (5, 7):
                    delivery["unitsFulfilled"] = fulfilled
                    store.observe(
                        "r:a",
                        "contract",
                        "SECOND",
                        contract,
                        "synthetic-progress",
                    )
                    observation = next(
                        r
                        for r in store.latest("r:a", "contract")
                        if r["key"] == "SECOND"
                    )
                    with page.expect_response("**/api/sources?**") as response:
                        if fulfilled == 5:
                            page.locator("#contract-select").select_option(
                                "SECOND"
                            )
                        else:
                            page.get_by_role(
                                "button", name="Reload sources and reset draft"
                            ).click()
                    sources = response.value.json()
                    assert sources["contract_observation"] == observation
                    remaining = 10 - fulfilled
                    browser_api.expect(
                        page.locator("#sources")
                    ).to_contain_text(f"ORE: {remaining} remaining")
                    initial = json.loads(
                        page.locator("#model-input").input_value()
                    )
                    assert initial["contract"] == observation["data"]
                    assert initial["contract"]["accepted"] is True
                    assert (
                        initial["contract"]["terms"]["deliver"][0][
                            "unitsFulfilled"
                        ]
                        == fulfilled
                    )
                    evidence = json.loads(
                        page.locator("#snapshot-json").text_content()
                    )
                    assert evidence["contract"] == observation
                    assert evidence["agent"] == earlier_report["agents"][0]
                    assert evidence["ship"] == earlier_report["ships"][0]
                    browser_api.expect(
                        page.locator("#snapshot")
                    ).to_contain_text(observation["observed_at"])
                    browser_api.expect(
                        page.locator("#snapshot")
                    ).to_contain_text("may be older than the contract")
                    assert initial["credits"] == 200000
                    assert (
                        page.locator(
                            "#builder-routes input[type=checkbox]:checked"
                        ).count()
                        == 0
                    )
                    browser_api.expect(
                        page.locator("#model-result")
                    ).to_be_empty()
                    selected = page.get_by_role(
                        "checkbox",
                        name="X-A-CURRENT / ORE -> X-A-D",
                        exact=True,
                    )
                    selected.check()
                    route = page.locator(".builder-route").filter(has=selected)
                    for field in (
                        "Fuel credits per trip (required)",
                        "Travel seconds per trip (required)",
                    ):
                        assert route.get_by_label(field).input_value() == ""
                        route.get_by_label(field).fill("0")
                    page.get_by_label("Credits (required)").fill("190000")
                    page.get_by_role(
                        "button", name="Build draft from form"
                    ).click()
                    built = json.loads(
                        page.locator("#model-input").input_value()
                    )
                    assert built["contract"] == observation["data"]
                    with page.expect_response(
                        "**/api/contract-model"
                    ) as response:
                        page.get_by_role(
                            "button", name="Calculate offline model"
                        ).click()
                    model = response.value.json()
                    assert model["accepted"] is True
                    assert model["remaining_units"] == remaining
                    # The 100 acceptance credits were already paid.
                    assert model["future_revenue"] == 10000
                    assert model["execution_authorized"] is False
                    browser_api.expect(
                        page.locator("#model-result")
                    ).to_contain_text("Future revenue 10,000")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        store.close()
    assert not (desk_ledger / "STOP").exists()
