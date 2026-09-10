"""CLI ledger authority tests use only synthetic child workspaces and APIs."""

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
import typer
from typer.testing import CliRunner

from py_st.cli import auto_cmd
from py_st.cli.app import app
from py_st.client import APIError
from py_st.services.automation import Session
from py_st.services.intelligence import Intelligence


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, Any]]:
    monkeypatch.chdir(tmp_path)
    client = MagicMock()
    client.__enter__.return_value = client
    client.status.return_value = {"resetDate": "r"}

    def request(method: str, path: str, **kwargs: Any) -> Any:
        assert method == "GET"
        if path == "/my/agent":
            return {"symbol": "a", "credits": 100000}
        assert path in ("/my/ships", "/my/contracts")
        return []

    client.request.side_effect = request
    with (
        patch.object(auto_cmd, "find_dotenv", return_value="") as find,
        patch.object(auto_cmd, "load_dotenv") as load,
        patch("py_st.cli.auto_cmd.os.environ", {"ST_TOKEN": "synthetic"}),
        patch.object(
            auto_cmd, "SpaceTradersClient", return_value=client
        ) as api,
    ):
        yield {
            "root": tmp_path,
            "database": tmp_path / ".state/intelligence.sqlite3",
            "client": client,
            "api": api,
            "find": find,
            "load": load,
        }


def seed(database: Path, scope: str = "r:a") -> None:
    store = Intelligence(database)
    try:
        symbol = scope.partition(":")[2]
        store.observe(scope, "agent", symbol, {"symbol": symbol, "credits": 1})
    finally:
        store.close()


def snapshot(database: Path) -> tuple[list[Any], list[Any]]:
    store = Intelligence(database, read_only=True)
    try:
        return (
            [
                tuple(row)
                for row in store.db.execute("SELECT * FROM observations")
            ],
            [tuple(row) for row in store.db.execute("SELECT * FROM actions")],
        )
    finally:
        store.close()


@pytest.mark.parametrize("execute", [False, True])
@pytest.mark.parametrize(
    "command",
    [
        ["pilot", "X-A", "--recover-contracts"],
        ["earn", "X-A"],
        ["scout", "X-A"],
        ["move", "a-1", "X-A-B"],
        ["contract", "a-1", "contract"],
        ["trade", "a-1", "X-A-B", "X-A-C", "FUEL"],
        ["refuel", "a-1"],
        ["negotiate", "a-1"],
        ["fleet"],
        [
            "abandon-procurement",
            "contract",
            "--reason",
            "Reviewed original intent",
        ],
    ],
)
def test_missing_cli_ledger_before_credentials(
    workspace: dict[str, Any], command: list[str], execute: bool
) -> None:
    with patch.object(auto_cmd, "Session") as session:
        result = CliRunner().invoke(
            app, ["auto", *command, *(["--execute"] if execute else [])]
        )
    assert result.exit_code != 0
    assert "authoritative workspace first" in result.output
    assert "genuinely" in result.output and "history" in result.output
    assert not workspace["database"].parent.exists()
    workspace["find"].assert_not_called()
    workspace["load"].assert_not_called()
    workspace["api"].assert_not_called()
    session.assert_not_called()


@pytest.mark.parametrize(
    "command", [["scan", "X-A"], ["mining", "a-1"], ["reconcile", "1"]]
)
def test_missing_get_only_cli_ledger(
    workspace: dict[str, Any], command: list[str]
) -> None:
    result = CliRunner().invoke(app, ["auto", *command])
    assert result.exit_code != 0
    assert "authoritative workspace first" in result.output
    assert not workspace["database"].parent.exists()
    workspace["find"].assert_not_called()
    workspace["api"].assert_not_called()


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (409, 4214, "APIError (HTTP 409, code 4214)"),
        (400, 4113, "APIError (HTTP 400, code 4113)"),
        (503, None, "APIError (HTTP 503)"),
        (None, 4214, "APIError (code 4214)"),
        (None, "private-token", "Stopped: APIError\n"),
        (None, {"credential": "private-token"}, "Stopped: APIError\n"),
        (True, True, "Stopped: APIError\n"),
    ],
)
def test_cli_errors_expose_only_numeric_api_metadata(
    workspace: dict[str, Any], status: Any, code: Any, expected: str
) -> None:
    # Arrange: server messages and payloads must never reach CLI output.
    seed(workspace["database"])
    before = snapshot(workspace["database"])
    workspace["client"].status.side_effect = APIError(
        "private-token in server message",
        status=status,
        payload={"error": {"code": code, "message": "private-token"}},
    )

    # Act
    result = CliRunner().invoke(app, ["auto", "mining", "a-1"])

    # Assert
    assert result.exit_code == 1
    assert expected in result.output
    assert "private-token" not in result.output
    assert (
        "HTTP True" not in result.output and "code True" not in result.output
    )
    assert snapshot(workspace["database"]) == before
    if code == 4113:
        assert "Owner must update ST_TOKEN" in result.output


@pytest.mark.parametrize(
    "kind,data,key",
    [
        ("empty", {}, "a"),
        ("market", {"symbol": "a"}, "a"),
        ("agent", {}, "a"),
        ("agent", {"symbol": "other"}, "a"),
        ("agent", {"symbol": "a"}, "other"),
        ("agent", [], "a"),
    ],
)
def test_unrecorded_agent_before_credentials(
    workspace: dict[str, Any], kind: str, data: Any, key: str
) -> None:
    store = Intelligence(workspace["database"])
    if kind != "empty":
        store.observe("r:a", kind, key, data)
    store.close()
    before = snapshot(workspace["database"])
    with pytest.raises(typer.Exit), auto_cmd.session(False, 60, 1):
        pytest.fail("unrecorded identity was accepted")
    assert snapshot(workspace["database"]) == before
    assert not workspace["database"].with_name("automation.lock").exists()
    workspace["find"].assert_not_called()
    workspace["api"].assert_not_called()


@pytest.mark.parametrize("execute", [False, True])
def test_matching_scope_preflight_is_nonrecording(
    workspace: dict[str, Any], execute: bool
) -> None:
    seed(workspace["database"], "other:b")
    seed(workspace["database"])
    before = snapshot(workspace["database"])
    with auto_cmd.session(execute, 60, 1) as run:
        assert run.scope == "r:a"
        assert not run.lock.closed
        assert run.remaining == 1
        assert snapshot(workspace["database"]) == before
    assert run.lock.closed
    workspace["client"].__exit__.assert_called_once()
    with pytest.raises(sqlite3.ProgrammingError):
        run.store.db.execute("SELECT 1")


@pytest.mark.parametrize(
    "error",
    [
        APIError("secret token", status=401),
        APIError("secret", status=400, payload={"error": {"code": 4113}}),
        httpx.ReadTimeout("secret token"),
    ],
)
def test_authentication_failure_never_records_or_bootstraps(
    workspace: dict[str, Any],
    error: Exception,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed(workspace["database"])
    before = snapshot(workspace["database"])
    workspace["client"].request.side_effect = error
    with pytest.raises(typer.Exit), auto_cmd.session(True, 60, 1):
        pytest.fail("failed authentication yielded")
    assert snapshot(workspace["database"]) == before
    assert "secret" not in capsys.readouterr().err
    workspace["client"].__exit__.assert_called_once()


@pytest.mark.parametrize(
    "status,agent",
    [
        ({"resetDate": "other"}, {"symbol": "a"}),
        ({"resetDate": "r"}, {"symbol": "b"}),
        ({}, {"symbol": "a"}),
        (None, {"symbol": "a"}),
        ({"resetDate": []}, {"symbol": "a"}),
        ({"resetDate": ""}, {"symbol": "a"}),
        ({"resetDate": "r"}, {}),
        ({"resetDate": "r"}, None),
        ({"resetDate": "r"}, {"symbol": 1}),
        ({"resetDate": "r"}, {"symbol": " "}),
    ],
)
def test_invalid_live_identity_does_not_write(
    workspace: dict[str, Any], status: Any, agent: Any
) -> None:
    seed(workspace["database"])
    store = Intelligence(workspace["database"])
    store.observe("r:b", "market", "b", {"symbol": "b"})
    store.close()
    before = snapshot(workspace["database"])
    workspace["client"].status.return_value = status
    workspace["client"].request.side_effect = None
    workspace["client"].request.return_value = agent
    with pytest.raises(typer.Exit), auto_cmd.session(False, 60, 1):
        pytest.fail("unrecorded or malformed identity yielded")
    assert snapshot(workspace["database"]) == before


@pytest.mark.parametrize("change", ["reset", "agent"])
def test_identity_change_after_preflight_fails_before_refresh_write(
    workspace: dict[str, Any], change: str
) -> None:
    seed(workspace["database"])
    before = snapshot(workspace["database"])
    with pytest.raises(typer.Exit), auto_cmd.session(True, 60, 1) as run:
        if change == "reset":
            workspace["client"].status.return_value = {"resetDate": "next"}
        else:
            workspace["client"].request.side_effect = None
            workspace["client"].request.return_value = {"symbol": "b"}
        run.refresh()
    assert snapshot(workspace["database"]) == before
    assert run.scope == "r:a"


def test_observe_deliberate_bootstrap_then_ordinary_cli(
    workspace: dict[str, Any],
) -> None:
    result = CliRunner().invoke(app, ["auto", "observe"])
    assert result.exit_code == 0, result.output
    store = Intelligence(workspace["database"], existing_only=True)
    assert store.latest("r:a", "agent")[0]["key"] == "a"
    store.close()
    result = CliRunner().invoke(app, ["auto", "fleet"])
    assert result.exit_code == 0, result.output
    assert "candidates" in result.output


def test_pending_history_remains_authoritative(
    workspace: dict[str, Any],
) -> None:
    seed(workspace["database"])
    store = Intelligence(workspace["database"])
    action = store.begin_action("r:a", "/my/ships/a-1/dock", {})
    store.close()
    before = snapshot(workspace["database"])
    with pytest.raises(typer.Exit), auto_cmd.session(True, 60, 1) as run:
        assert run.store.pending_action(run.scope, action)
        run.mutate("/my/ships/a-1/dock")
    assert snapshot(workspace["database"]) == before
    assert all(
        call.args[0] == "GET"
        for call in workspace["client"].request.call_args_list
    )


def test_lock_failure_closes_client_and_store(
    workspace: dict[str, Any],
) -> None:
    seed(workspace["database"])
    store = Intelligence(workspace["database"], existing_only=True)
    owner = Session(MagicMock(), store)
    rejected = Intelligence(workspace["database"], existing_only=True)
    try:
        with (
            patch.object(auto_cmd, "Intelligence", return_value=rejected),
            pytest.raises(typer.Exit),
            auto_cmd.session(False, 60, 1),
        ):
            pytest.fail("lock contention yielded")
        workspace["client"].__exit__.assert_called_once()
        workspace["client"].status.assert_not_called()
        with pytest.raises(sqlite3.ProgrammingError):
            rejected.db.execute("SELECT 1")
    finally:
        owner.close()
        store.close()


@pytest.mark.parametrize("failure", ["status", "agent", "stop", "deadline"])
def test_preflight_failure_closes_lock_and_leaves_scope_unset(
    workspace: dict[str, Any], failure: str
) -> None:
    seed(workspace["database"])
    store = Intelligence(workspace["database"], existing_only=True)
    run = Session(workspace["client"], store)
    if failure == "status":
        workspace["client"].status.side_effect = APIError("secret", status=401)
    elif failure == "agent":
        workspace["client"].request.side_effect = APIError(
            "secret", status=401
        )
    elif failure == "stop":
        workspace["root"].joinpath("STOP").touch()
    else:
        run.deadline = 0
    before = snapshot(workspace["database"])
    with (
        patch.object(auto_cmd, "Intelligence", return_value=store),
        patch.object(auto_cmd, "Session", return_value=run),
        pytest.raises(typer.Exit),
        auto_cmd.session(False, 60, 1),
    ):
        pytest.fail("failed preflight yielded")
    assert run.scope == ""
    assert run.lock.closed
    workspace["client"].__exit__.assert_called_once()
    with pytest.raises(sqlite3.ProgrammingError):
        store.db.execute("SELECT 1")
    assert snapshot(workspace["database"]) == before
    if failure in ("stop", "deadline"):
        workspace["client"].status.assert_not_called()


def test_missing_token_closes_store_before_session(
    workspace: dict[str, Any],
) -> None:
    seed(workspace["database"])
    store = Intelligence(workspace["database"], existing_only=True)
    with (
        patch.object(auto_cmd, "Intelligence", return_value=store),
        patch("py_st.cli.auto_cmd.os.environ", {}),
        pytest.raises(typer.BadParameter, match="ST_TOKEN"),
        auto_cmd.session(False, 60, 1),
    ):
        pytest.fail("missing credentials yielded")
    workspace["api"].assert_not_called()
    assert not workspace["database"].with_name("automation.lock").exists()
    with pytest.raises(sqlite3.ProgrammingError):
        store.db.execute("SELECT 1")


@pytest.mark.parametrize("invalid", ["schema", "json", "wal"])
def test_invalid_ledger_cli_is_safe_before_credentials(
    workspace: dict[str, Any], invalid: str
) -> None:
    seed(workspace["database"])
    store = Intelligence(workspace["database"])
    if invalid == "schema":
        store.db.execute("PRAGMA user_version=2")
    elif invalid == "json":
        with store.db:
            store.db.execute(
                "UPDATE observations SET data='secret invalid JSON'"
            )
    else:
        store.db.execute("PRAGMA journal_mode=DELETE")
    store.close()
    result = CliRunner().invoke(app, ["auto", "fleet"])
    assert result.exit_code != 0
    assert "secret" not in result.output
    assert str(workspace["database"]) not in result.output
    assert not workspace["database"].with_name("automation.lock").exists()
    workspace["find"].assert_not_called()
    workspace["api"].assert_not_called()


@pytest.mark.parametrize("version", [0, 2])
def test_existing_only_invalid_version_closes_connection(
    tmp_path: Path, version: int
) -> None:
    database = tmp_path / "invalid.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(f"PRAGMA user_version={version}")
    with (
        patch(
            "py_st.services.intelligence.sqlite3.connect",
            return_value=connection,
        ),
        pytest.raises(ValueError, match="schema version"),
    ):
        Intelligence(database, existing_only=True)
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_existing_only_missing_no_creation(tmp_path: Path) -> None:
    database = tmp_path / "absent/ledger.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        Intelligence(database, existing_only=True)
    assert not database.parent.exists()


def test_existing_only_requires_wal_and_full_sync(tmp_path: Path) -> None:
    database = tmp_path / "ledger ?#.sqlite3"
    seed(database)
    store = Intelligence(database, existing_only=True)
    assert store.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert store.db.execute("PRAGMA synchronous").fetchone()[0] == 2
    store.db.execute("PRAGMA journal_mode=DELETE")
    store.close()
    with pytest.raises(ValueError, match="WAL"):
        Intelligence(database, existing_only=True)


def test_existing_only_does_not_repair_missing_tables(tmp_path: Path) -> None:
    database = tmp_path / "invalid.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA user_version=1")
    with (
        patch(
            "py_st.services.intelligence.sqlite3.connect",
            return_value=connection,
        ),
        pytest.raises(sqlite3.OperationalError),
    ):
        Intelligence(database, existing_only=True)
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


@pytest.mark.parametrize(
    "invalid", ["zero-byte", "schema0", "actions", "observations", "version"]
)
def test_observe_never_repairs_existing_history(
    workspace: dict[str, Any], invalid: str
) -> None:
    database = workspace["database"]
    if invalid == "zero-byte":
        database.parent.mkdir()
        database.touch()
    else:
        seed(database)
        store = Intelligence(database)
        if invalid in ("actions", "observations"):
            store.db.execute(f"DROP TABLE {invalid}")
        else:
            version = 0 if invalid == "schema0" else 2
            store.db.execute(f"PRAGMA user_version={version}")
        store.close()
    before = database.read_bytes()
    statements: list[str] = []
    connections: list[sqlite3.Connection] = []
    connect = sqlite3.connect

    def tracked_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        connections.append(connection)
        return connection

    with patch(
        "py_st.services.intelligence.sqlite3.connect",
        side_effect=tracked_connect,
    ):
        result = CliRunner().invoke(app, ["auto", "observe"])

    assert result.exit_code != 0
    assert database.read_bytes() == before
    assert all(
        sql.startswith(("PRAGMA user_version", "SELECT")) for sql in statements
    )
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")
    assert not database.with_name("automation.lock").exists()
    workspace["find"].assert_not_called()
    workspace["load"].assert_not_called()
    workspace["api"].assert_not_called()


@pytest.mark.parametrize("pending", [False, True])
def test_observe_accepts_existing_v1_without_losing_history(
    workspace: dict[str, Any], pending: bool
) -> None:
    store = Intelligence(workspace["database"])
    if pending:
        store.observe("r:a", "agent", "a", {"symbol": "a", "credits": 1})
        store.begin_action("r:a", "/my/ships/a-1/dock", {})
    store.close()
    before = snapshot(workspace["database"])

    result = CliRunner().invoke(app, ["auto", "observe"])

    assert result.exit_code == 0, result.output
    after = snapshot(workspace["database"])
    assert after[0][: len(before[0])] == before[0]
    assert len(after[0]) == len(before[0]) + 1
    assert after[1] == before[1]
    store = Intelligence(workspace["database"], existing_only=True)
    assert store.latest("r:a", "agent")[0]["data"]["symbol"] == "a"
    assert store.pending("r:a") is pending
    store.close()


def test_observe_file_appearing_at_atomic_publish_is_not_repaired(
    workspace: dict[str, Any],
) -> None:
    database = workspace["database"]
    original_link = os.link
    claimed: list[bytes] = []

    def race(source: Path, target: Path) -> None:
        seed(database)
        store = Intelligence(database)
        store.db.execute("DROP TABLE actions")
        store.close()
        claimed.append(database.read_bytes())
        original_link(source, target)

    with patch("py_st.services.intelligence.os.link", side_effect=race):
        result = CliRunner().invoke(app, ["auto", "observe"])

    assert len(claimed) == 1
    assert result.exit_code != 0
    assert database.read_bytes() == claimed[0]
    workspace["find"].assert_not_called()
    workspace["api"].assert_not_called()


@pytest.mark.parametrize("failure", ["connect", "pragma", "schema"])
def test_new_ledger_failure_removes_temporary_database(
    tmp_path: Path, failure: str
) -> None:
    database = tmp_path / "new.sqlite3"
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = [0]
    error = sqlite3.OperationalError("synthetic failure")
    if failure == "pragma":
        connection.execute.side_effect = error
    elif failure == "schema":
        connection.executescript.side_effect = error

    with (
        patch(
            "py_st.services.intelligence.sqlite3.connect",
            side_effect=error if failure == "connect" else None,
            return_value=connection,
        ),
        pytest.raises(sqlite3.OperationalError, match="synthetic failure"),
    ):
        Intelligence(database, existing_or_create=True)

    assert not database.exists()
    assert list(tmp_path.iterdir()) == []
    if failure != "connect":
        connection.close.assert_called_once()
