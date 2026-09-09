"""Synthetic smoke-tool guards; no browser or operator state is accessed."""

import fcntl
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def smoke() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "tools/check_dashboard.py"
    spec = importlib.util.spec_from_file_location("dashboard_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), (["--bad"], 2)])
def test_arguments_without_runtime_access(
    smoke: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    code: int,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Argument parsing accessed runtime state")

    for name in ("cwd", "resolve", "exists", "is_file", "open"):
        monkeypatch.setattr(Path, name, forbidden)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(SystemExit) as exc:
        smoke.main(arguments)
    assert exc.value.code == code


def test_missing_ledger_creates_nothing(
    smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="Existing ledger required"):
        smoke.main(["--read-only"])
    assert list(tmp_path.iterdir()) == []


def test_default_refuses_existing_stop(
    smoke: ModuleType, tmp_path: Path
) -> None:
    stop = tmp_path / "STOP"
    stop.write_text("operator pause")
    with pytest.raises(RuntimeError, match="Preserve existing STOP"):
        smoke.main(["--root", str(tmp_path)])
    assert stop.read_text() == "operator pause"
    assert not (tmp_path / ".state").exists()


@pytest.fixture
def harness(
    smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, MagicMock, MagicMock, MagicMock]:
    # Only disposable synthetic files and mocked browser/server operations.
    state = tmp_path / ".state"
    state.mkdir()
    (state / "intelligence.sqlite3").touch()
    api = MagicMock()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    browser = api.sync_playwright.return_value.__enter__.return_value
    context = browser.chromium.launch.return_value.new_context.return_value
    page = context.new_page.return_value
    server = MagicMock(server_port=8765)
    monkeypatch.setattr(
        "py_st.services.dashboard.dashboard_server", lambda root, port: server
    )
    monkeypatch.setattr(smoke, "Thread", MagicMock())
    monkeypatch.setattr(smoke, "check_read_only", MagicMock())
    return tmp_path, context, page, server


@pytest.mark.parametrize("paused", [False, True])
def test_read_only_preserves_stop_and_uses_unique_captures(
    smoke: ModuleType,
    harness: tuple[Path, MagicMock, MagicMock, MagicMock],
    paused: bool,
) -> None:
    root, context, page, server = harness
    stop = root / "STOP"
    if paused:
        stop.write_text("operator pause")
    for _ in range(2):
        smoke.main(["--read-only", "--root", str(root)])
    assert stop.exists() == paused
    if paused:
        assert stop.read_text() == "operator pause"
    page.get_by_role.assert_not_called()
    paths = [call.kwargs["path"] for call in page.screenshot.call_args_list]
    assert len(set(paths)) == 4
    assert all("dashboard-product-readonly-" in path for path in paths)
    assert [
        call.args[0]["width"] for call in page.set_viewport_size.call_args_list
    ] == [1440, 390, 1440, 390]
    server.shutdown.assert_called()
    server.server_close.assert_called()
    route_handler = context.route.call_args.args[1]
    for method, url, denied in (
        ("GET", "http://127.0.0.1:8765/api/report", False),
        ("POST", "http://127.0.0.1:8765/api/control", True),
        ("POST", "http://127.0.0.1:8765/api/contract-model", True),
        ("GET", "https://example.invalid/", True),
    ):
        route = MagicMock()
        route.request.method, route.request.url = method, url
        route_handler(route)
        assert route.abort.called == denied
        assert route.continue_.called != denied


def test_active_automation_refused(
    smoke: ModuleType, harness: tuple[Path, MagicMock, MagicMock, MagicMock]
) -> None:
    root, context, _, server = harness
    with (root / ".state/automation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="Automation active"):
            smoke.main(["--read-only", "--root", str(root)])
    context.new_page.assert_not_called()
    server.serve_forever.assert_not_called()


@pytest.mark.parametrize("paused", [False, True])
def test_operator_stop_change_is_not_undone_even_on_failure(
    smoke: ModuleType,
    harness: tuple[Path, MagicMock, MagicMock, MagicMock],
    paused: bool,
) -> None:
    root, _, _, server = harness
    stop = root / "STOP"
    if paused:
        stop.touch()

    def operator_change(*args: Any) -> None:
        if paused:
            stop.unlink()
        else:
            stop.write_text("new operator pause")
        raise ValueError("browser failed")

    smoke.check_read_only.side_effect = operator_change
    with pytest.raises(RuntimeError, match="STOP existence changed"):
        smoke.main(["--read-only", "--root", str(root)])
    assert stop.exists() != paused
    server.server_close.assert_called_once()
    with (root / ".state/automation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_attempted_post_is_aborted_and_fails_smoke(
    smoke: ModuleType, harness: tuple[Path, MagicMock, MagicMock, MagicMock]
) -> None:
    root, context, _, _ = harness
    route = MagicMock()
    route.request.method = "POST"
    route.request.url = "http://127.0.0.1:8765/api/control"
    smoke.check_read_only.side_effect = (
        lambda *args: context.route.call_args.args[1](route)
    )
    with pytest.raises(AssertionError, match="POST"):
        smoke.main(["--read-only", "--root", str(root)])
    route.abort.assert_called()
    route.continue_.assert_not_called()


@pytest.mark.parametrize("has_data", [False, True])
def test_stored_data_assertions(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, has_data: bool
) -> None:
    api = MagicMock()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    page = MagicMock()
    report = {
        "scopes": ["r:a"],
        "scope": "r:a",
        "paused": True,
        "credits": [{"credits": 123456}] if has_data else [],
        "ships": (
            [{"data": {"symbol": "A-1", "nav": {"waypointSymbol": "X-A"}}}]
            if has_data
            else []
        ),
        "prices": (
            [
                {
                    "key": "X-A",
                    "observed_at": "2026-01-01T00:00:00Z",
                    "data": {"tradeGoods": [{"symbol": "FUEL"}]},
                }
            ]
            if has_data
            else []
        ),
    }
    pending = page.expect_response.return_value.__enter__.return_value
    pending.value.json.return_value = report
    smoke.check_read_only(page, "http://127.0.0.1:8765")
    api.expect.return_value.to_have_text.assert_any_call(
        "123,456" if has_data else "--"
    )
    page.get_by_role.assert_not_called()
    page.evaluate.assert_called_once()
    if has_data:
        api.expect.return_value.to_contain_text.assert_any_call("FUEL / X-A:")


def test_default_still_clicks_pause_and_clear(
    smoke: ModuleType, harness: tuple[Path, MagicMock, MagicMock, MagicMock]
) -> None:
    root, context, page, _ = harness
    stop = root / "STOP"

    def click() -> None:
        if stop.exists():
            stop.unlink()
        else:
            stop.touch()

    page.get_by_role.return_value.click.side_effect = click
    smoke.main(["--root", str(root)])
    assert [
        call.kwargs["name"] for call in page.get_by_role.call_args_list
    ] == [
        "Pause automation",
        "Clear stop",
    ]
    context.route.assert_not_called()
    assert not stop.exists()
