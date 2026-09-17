"""Offline hosted HTTP boundary and quiesced full-state recovery."""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import ssl
import subprocess
import threading
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from typer.testing import CliRunner

from py_st.cli.flight_cmd import flight_app
from py_st.services import checkpoint as checkpoint_module
from py_st.services.checkpoint import checkpoint, restore
from py_st.services.flight_auth import save_password
from py_st.services.flight_demo import SCOPE, create_demo, demo_client
from py_st.services.flight_queue import FlightQueue
from py_st.services.flight_worker import FlightWorker
from py_st.services.hosted_config import PublicOrigin
from py_st.services.hosted_server import hosted_server
from py_st.services.state_lease import StateLease
from py_st.services.stop_control import request_stop

PASSWORD = "synthetic-hosted-owner"
ORIGIN = "https://game.example:8443"


@pytest.fixture
def managed(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    create_demo(root)
    save_password(root, PASSWORD)
    queue = FlightQueue(root, create=True, scope=SCOPE, mode="demo")
    queue.close()
    request_stop(root)
    return root


@pytest.mark.parametrize(
    ("value", "canonical"),
    [
        ("https://game.example", "https://game.example"),
        ("https://GAME.example:443", "https://game.example"),
        (ORIGIN, ORIGIN),
        ("https://127.0.0.1:8443", "https://127.0.0.1:8443"),
        ("https://[::1]:8443", "https://[::1]:8443"),
        ("https://[2001:db8::1]:443", "https://[2001:db8::1]"),
    ],
)
def test_origin(value: str, canonical: str) -> None:
    assert PublicOrigin.parse(value).origin == canonical


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://game.example",
        "https://u:p@game.example",
        "https://*.example",
        "https://example/",
        "https://example/path",
        "https://example?",
        "https://example#",
        "https://example:",
        "https://example:0",
        "https://example:65536",
        "https://example:0443",
        "https://[::1]evil",
        "https://::1",
        "https://[fe80::1%25eth0]",
        "https://127.1",
        "https://0177.0.0.1",
        "https://2130706433",
        "https://example\\evil",
        "https://example\n",
        "https://foo..bar",
        "https://-foo.example",
        "https://foo_.example",
        "https://é.example",
    ],
)
def test_reject_origin(value: str) -> None:
    with pytest.raises(ValueError):
        PublicOrigin.parse(value)


def test_explicit_hosted_never_falls_back(
    managed: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ST_STATE_ROOT", str(managed))
    monkeypatch.delenv("ST_PUBLIC_ORIGIN", raising=False)
    result = CliRunner().invoke(flight_app, ["serve", "--hosted"])
    assert result.exit_code != 0
    assert "HTTPS origin" in result.output


@pytest.fixture
def backend(managed: Path) -> Iterator[httpx.Client]:
    server = hosted_server(managed, ORIGIN, 0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.effective_port}",
            headers={"Host": "game.example:8443", "Origin": ORIGIN},
            trust_env=False,
        ) as client:
            yield client
    finally:
        server.close()
        thread.join(5)


def sign_in(client: httpx.Client) -> tuple[str, str]:
    match = re.search('nonce="([a-f0-9]+)"', client.get("/").text)
    assert match
    csrf = match[1]
    response = client.post(
        "/api/login", json={"csrf": csrf, "password": PASSWORD}
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert all(
        flag in cookie for flag in ("Secure", "HttpOnly", "SameSite=Strict")
    )
    # Tests connect to the loopback backend; browser tests use real TLS.
    client.headers["Cookie"] = cookie.split(";", 1)[0]
    return csrf, cookie


def test_auth_host_origin_csrf_logout(backend: httpx.Client) -> None:
    for path in (
        "/api/report",
        "/api/flight",
        "/api/doctor",
        "/api/sources",
        "/api/market-history",
    ):
        assert backend.get(path).status_code == 401
    assert (
        backend.get(
            "/",
            headers={
                "Host": "evil.example",
                "X-Forwarded-Host": "game.example:8443",
            },
        ).status_code
        == 403
    )
    csrf, _ = sign_in(backend)
    assert backend.get("/api/flight").status_code == 200
    for origin in ("http://game.example:8443", "https://evil.example", "null"):
        response = backend.post(
            "/api/control",
            headers={"Origin": origin, "X-Forwarded-Proto": "https"},
            json={"csrf": csrf, "action": "resume"},
        )
        assert response.status_code == 403
    assert (
        backend.post(
            "/api/control", json={"csrf": "wrong", "action": "resume"}
        ).status_code
        == 403
    )
    response = backend.post("/api/logout", json={"csrf": csrf})
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
    assert backend.get("/api/flight").status_code == 401


def test_lost_state_never_becomes_anonymous(
    backend: httpx.Client, managed: Path
) -> None:
    sign_in(backend)
    (managed / ".state/flight.sqlite3").rename(
        managed / ".state/retained.sqlite3"
    )
    assert backend.get("/api/report").status_code == 401
    assert not (managed / ".state/flight.sqlite3").exists()


@pytest.mark.parametrize(
    "damage", ["ledger", "owner", "blank", "malformed", "schema"]
)
def test_startup_refusal(managed: Path, damage: str) -> None:
    if damage == "ledger":
        (managed / ".state/flight.sqlite3").unlink()
    elif damage in ("owner", "blank", "malformed"):
        (managed / ".state/owner.json").unlink()
        if damage == "blank":
            save_password(managed, "")
        elif damage == "malformed":
            (managed / ".state/owner.json").write_text("{}")
    else:
        with sqlite3.connect(managed / ".state/flight.sqlite3") as db:
            db.execute("PRAGMA user_version=999")
    with pytest.raises((ValueError, OSError, sqlite3.Error)):
        hosted_server(managed, ORIGIN, 0)


@pytest.mark.parametrize("existing", [False, True])
def test_checkpoint_restore_and_integrity(
    managed: Path, tmp_path: Path, existing: bool
) -> None:
    backup = tmp_path / "backup"
    checkpoint(managed, backup)
    restored = tmp_path / "restored"
    if existing:
        restored.mkdir()
    restore(backup, restored)
    queue = FlightQueue(restored)
    try:
        assert queue.settings["paused"] == 1
        assert queue.scope == SCOPE
    finally:
        queue.close()
    assert (restored / "STOP").is_file()
    with pytest.raises(ValueError):
        restore(backup, restored)
    (backup / ".state/owner.json").write_text("{}")
    with pytest.raises(ValueError):
        restore(backup, tmp_path / "altered")


def test_restore_rejects_mount_before_copying(
    managed: Path, tmp_path: Path
) -> None:
    backup = tmp_path / "backup"
    checkpoint(managed, backup)
    target = tmp_path / "data-mount"
    target.mkdir()
    with (
        patch.object(Path, "is_mount", return_value=True),
        pytest.raises(ValueError, match="beneath the state mount"),
    ):
        restore(backup, target)
    assert target.is_dir()
    assert not list(target.iterdir())
    assert not list(tmp_path.glob(".restore-*"))


def test_checkpoint_excludes_token_and_preserves_handoff(
    managed: Path, tmp_path: Path
) -> None:
    (managed / ".env").write_text("ST_TOKEN=synthetic-never-live\n")
    (managed / "HANDOFF_REQUIRED").write_text("Retain authority review\n")
    backup, target = tmp_path / "backup", tmp_path / "restored"
    checkpoint(managed, backup)
    manifest = json.loads((backup / "checkpoint.json").read_text())
    assert ".env" not in manifest["files"]
    assert not (backup / ".env").exists()
    restore(backup, target)
    assert not (target / ".env").exists()
    assert (target / "HANDOFF_REQUIRED").read_text() == (
        "Retain authority review\n"
    )
    assert (target / "STOP").is_file()
    queue = FlightQueue(target)
    try:
        with pytest.raises(ValueError, match="authority"):
            queue.control(False)
    finally:
        queue.close()


@pytest.mark.parametrize("name", ["app.py", "page.html", "ui.js", "ui.css"])
def test_release_identity_covers_sources_and_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    package = tmp_path / "py_st"
    services = package / "services"
    services.mkdir(parents=True)
    monkeypatch.setattr(
        checkpoint_module, "__file__", str(services / "checkpoint.py")
    )
    asset = services / name
    asset.write_text("before")
    before = checkpoint_module.code_identity()
    asset.write_text("after")
    assert checkpoint_module.code_identity() != before
    after = checkpoint_module.code_identity()
    (services / "cache.pyc").write_bytes(b"ignored cache")
    assert checkpoint_module.code_identity() == after


@pytest.mark.parametrize(
    "error", [KeyboardInterrupt, OSError, BlockingIOError]
)
def test_lease_preserves_interrupts_and_closes_descriptor(
    tmp_path: Path, error: type[BaseException]
) -> None:
    expected = ValueError if error is BlockingIOError else error
    with (
        patch("py_st.services.state_lease.fcntl.flock", side_effect=error),
        patch("py_st.services.state_lease.os.close", wraps=os.close) as close,
    ):
        with pytest.raises(expected):
            StateLease(tmp_path)
        close.assert_called_once()


def test_runtime_lock_covers_project_requirements() -> None:
    root = Path(__file__).resolve().parents[1]
    pins = {}
    for line in (
        (root / "deploy/requirements-py312.lock").read_text().splitlines()
    ):
        if line and not line.startswith("#"):
            name, version = line.split("==")
            pins[canonicalize_name(name)] = version
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    for text in project["dependencies"]:
        requirement = Requirement(text)
        version = pins[canonicalize_name(requirement.name)]
        assert version in requirement.specifier, text


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "OPTIONS"])
def test_adapter_rejects_unsupported_methods(
    backend: httpx.Client, method: str
) -> None:
    response = backend.request(method, "/api/control")
    assert response.status_code == 405
    assert response.json() == {}
    assert response.headers["cache-control"] == "no-store"


def test_waitress_request_limits(backend: httpx.Client) -> None:
    assert backend.post("/api/login", content=b"x" * 65537).status_code == 413
    assert (
        backend.get("/", headers={"X-Oversized": "x" * 17000}).status_code
        == 431
    )
    assert backend.get("/").status_code == 200


def test_checkpoint_refuses_running_server(
    backend: httpx.Client, managed: Path, tmp_path: Path
) -> None:
    assert backend.get("/").status_code == 200
    with pytest.raises(ValueError, match="in use"):
        checkpoint(managed, tmp_path / "backup")


def test_incomplete_manifest(managed: Path, tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    checkpoint(managed, backup)
    manifest = json.loads((backup / "checkpoint.json").read_text())
    manifest["code"] = "wrong"
    (backup / "checkpoint.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        restore(backup, tmp_path / "restored")


@pytest.mark.parametrize("damage", ["missing", "schema", "unpaused", "writer"])
def test_checkpoint_refusals(
    managed: Path, tmp_path: Path, damage: str
) -> None:
    db = sqlite3.connect(managed / ".state/flight.sqlite3")
    try:
        if damage == "missing":
            (managed / ".state/intelligence.sqlite3").unlink()
        elif damage == "schema":
            db.execute("PRAGMA user_version=99")
        elif damage == "unpaused":
            (managed / "STOP").unlink()
        else:
            db.execute("BEGIN IMMEDIATE")
        with pytest.raises((ValueError, OSError, sqlite3.Error)):
            checkpoint(managed, tmp_path / "backup")
    finally:
        db.close()


def test_unknown_and_live_handoff_survive_restore(
    managed: Path, tmp_path: Path
) -> None:
    queue = FlightQueue(managed)
    try:
        command = queue.enqueue(
            SCOPE,
            "synthetic-request-0001",
            {"kind": "orbit", "ship": "SYNTHETIC-1"},
        )
        queue.update(
            command["id"], "reconciliation_required", "Synthetic lost response"
        )
        with queue.db:
            queue.db.execute("UPDATE settings SET mode='live'")
    finally:
        queue.close()
    backup, target = tmp_path / "backup", tmp_path / "restored"
    checkpoint(managed, backup)
    restore(backup, target)
    queue = FlightQueue(target)
    try:
        assert queue.get(command["id"])["status"] == "reconciliation_required"
        assert queue.settings["paused"] == 1
        assert (target / "HANDOFF_REQUIRED").is_file()
        with pytest.raises(ValueError, match="authority"):
            queue.control(False)
    finally:
        queue.close()


@pytest.fixture
def tls_stack(managed: Path, tmp_path: Path) -> Iterator[tuple[str, Path]]:
    binary = os.environ.get("CADDY_TEST_BINARY")
    if not binary:
        pytest.skip("Set CADDY_TEST_BINARY for actual reverse-proxy TLS proof")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"https://127.0.0.1:{port}"
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=isolated-offline-test",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    server = hosted_server(managed, origin, 0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    config = tmp_path / "Caddyfile"
    config.write_text(
        "{\n admin off\n auto_https off\n}\n"
        + origin
        + " {\n bind 127.0.0.1\n"
        + f"tls {cert} {key}\nrequest_body {{\n max_size 64KB\n}}\n"
        + f"reverse_proxy 127.0.0.1:{server.effective_port}\n}}\n"
    )
    with (tmp_path / "caddy.log").open("w") as log:
        proxy = subprocess.Popen(
            [binary, "run", "--config", str(config), "--adapter", "caddyfile"],
            stdout=log,
            stderr=log,
            env=os.environ
            | {
                "XDG_DATA_HOME": str(tmp_path / "data"),
                "XDG_CONFIG_HOME": str(tmp_path / "config"),
            },
        )
        try:
            context = ssl.create_default_context(cafile=str(cert))
            with httpx.Client(verify=context, trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get(origin).status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.05)
                else:
                    pytest.fail(
                        "Caddy did not become ready; inspect caddy.log"
                    )
            yield origin, cert
        finally:
            proxy.terminate()
            proxy.wait(timeout=10)
            server.close()
            thread.join(5)


def test_real_https_proxy(tls_stack: tuple[str, Path]) -> None:
    origin, cert = tls_stack
    with httpx.Client(
        base_url=origin,
        verify=ssl.create_default_context(cafile=str(cert)),
        trust_env=False,
        headers={"Origin": origin},
    ) as client:
        csrf, _ = sign_in(client)
        client.headers.pop("Cookie")
        # Unlike backend-only tests, the cookie jar sends Secure over TLS.
        assert client.get("/api/flight").status_code == 200
        wrong_host = client.get(
            "/api/flight", headers={"Host": "evil.example"}
        )
        # Caddy's unmatched virtual host has an empty default response;
        # it must never reach the application or expose authenticated data.
        assert not wrong_host.content
        assert (
            client.post("/api/logout", json={"csrf": csrf}).status_code == 200
        )
        assert client.get("/api/flight").status_code == 401


@pytest.mark.skipif(
    os.environ.get("DASHBOARD_BROWSER_TESTS") != "1",
    reason="Explicit actual-browser offline proof",
)
@pytest.mark.parametrize("width", [1440, 390])
def test_https_browser_flight(
    tls_stack: tuple[str, Path], managed: Path, width: int
) -> None:
    from playwright.sync_api import expect, sync_playwright

    origin, _ = tls_stack
    stopped = threading.Event()
    errors: list[str] = []

    def work() -> None:
        try:
            with demo_client(managed) as client:
                client._transport._interval = 0
                worker = FlightWorker(managed, client)
                try:
                    while not stopped.is_set():
                        worker.tick()
                        stopped.wait(0.1)
                finally:
                    worker.close()
        except Exception as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            # Private test certificate only; never installs a system CA.
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": width, "height": 1000},
            )
            page = context.new_page()
            page.goto(origin)
            page.locator("#owner-password").fill(PASSWORD)
            page.get_by_role("button", name="Log in", exact=True).click()
            page.get_by_role(
                "button", name="Resume worker", exact=True
            ).click()
            page.get_by_role("navigation").get_by_role(
                "link", name="Explorer", exact=True
            ).click()
            page.locator("#explorer-ship").select_option("SYNTHETIC-1")
            page.locator("#waypoint-list button").filter(
                has_text="X-DEMO-B2"
            ).click()
            page.locator("#flight-preview").click()
            expect(page.locator("#flight-estimate")).to_contain_text(
                '"estimated": true'
            )
            page.locator("#flight-trip").click()
            expect(page.locator("#flight-message")).to_contain_text(
                "Command #"
            )
            page.close()
            page = context.new_page()
            page.goto(origin)
            expect(page.locator("#flight-commands")).to_contain_text(
                "COMPLETED", timeout=20000
            )
            expect(page.locator("#credits")).to_have_text("123,384")
            page.get_by_role("navigation").get_by_role(
                "link", name="Fleet", exact=True
            ).click()
            expect(page.locator("#fleet")).to_contain_text("Fuel 100/100")
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.screenshot(
                path=str(managed / f"https-flight-{width}.png"), full_page=True
            )
            browser.close()
    finally:
        stopped.set()
        thread.join(10)
    assert not errors, errors
