"""Synthetic offline doctor evidence; never use the runtime ledger."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from py_st.cli import auto_cmd
from py_st.services.doctor import diagnose
from py_st.services.intelligence import Intelligence

NOW = datetime(2026, 9, 8, tzinfo=UTC)
SCOPE = "reset:AGENT"


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[Intelligence]:
    store = Intelligence(tmp_path / "ledger.sqlite3")
    for kind, data in (
        ("agent", {"symbol": "AGENT", "credits": 100000}),
        ("ship", {"symbol": "AGENT-1"}),
        ("contract", {"accepted": True, "fulfilled": True}),
    ):
        store.observe(SCOPE, kind, "AGENT" if kind == "agent" else kind, data)
    with store.db:
        store.db.execute(
            "UPDATE observations SET observed_at=?", (NOW.isoformat(),)
        )
    yield store
    store.close()


def report(
    store: Intelligence, tmp_path: Path, **kwargs: Any
) -> dict[str, Any]:
    return diagnose(
        tmp_path / "ledger.sqlite3", SCOPE, root=tmp_path, now=NOW, **kwargs
    )


def codes(result: dict[str, Any]) -> list[str]:
    assert result["live_scope_verified"] is False
    assert result["execution_authorized"] is False
    assert result["process_state"] == "unknown"
    return [f["code"] for f in result["findings"]]


def test_fresh_wal_no_writes_or_auth(
    ledger: Intelligence, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Doctor attempted live/auth/lock access")

    for name in (
        "session",
        "Session",
        "SpaceTradersClient",
        "load_dotenv",
        "find_dotenv",
    ):
        monkeypatch.setattr(auto_cmd, name, forbidden)
    monkeypatch.setattr("py_st.services.automation.fcntl.flock", forbidden)
    assert Path(str(tmp_path / "ledger.sqlite3") + "-wal").stat().st_size > 0
    before = ledger.db.total_changes
    result = report(ledger, tmp_path)
    assert codes(result) == []
    assert result["exit_code"] == 0
    assert ledger.db.total_changes == before
    monkeypatch.setattr(
        auto_cmd, "diagnose", lambda *a, **k: diagnose(*a, now=NOW, **k)
    )
    monkeypatch.chdir(tmp_path)
    cli = CliRunner().invoke(
        auto_cmd.auto_app,
        ["doctor", "--scope", SCOPE, "--database", "ledger.sqlite3"],
    )
    assert cli.exit_code == 0
    assert json.loads(cli.stdout) == result


@pytest.mark.parametrize("scope", ["", "bad", "a:b:c", " :b", "other:AGENT"])
def test_scope(ledger: Intelligence, tmp_path: Path, scope: str) -> None:
    result = diagnose(
        tmp_path / "ledger.sqlite3", scope, root=tmp_path, now=NOW
    )
    assert result["exit_code"] == 2
    assert "unavailable" in codes(result)


def test_stop_cwd_unchanged_and_pending_all(
    ledger: Intelligence, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stop = tmp_path / "STOP"
    stop.write_bytes(b"owner stop\n")
    before = stop.stat()
    first = ledger.begin_action(SCOPE, "/uncertain", {})
    for status in ("succeeded", "rejected", "not_sent", "reconciled") * 51:
        action = ledger.begin_action(SCOPE, "/old", {})
        ledger.finish_action(action, status, {})
    second = ledger.begin_action(SCOPE, "/uncertain", {})
    ledger.begin_action("other:AGENT", "/foreign", {})
    monkeypatch.chdir(tmp_path)
    result = diagnose(tmp_path / "ledger.sqlite3", SCOPE, now=NOW)
    assert codes(result) == ["stop_present", "pending_actions"]
    assert [a["id"] for a in result["findings"][1]["actions"]] == [
        first,
        second,
    ]
    assert stop.read_bytes() == b"owner stop\n"
    assert stop.stat().st_mtime_ns == before.st_mtime_ns
    assert not (tmp_path / ".state").exists()


def test_missing_db(tmp_path: Path) -> None:
    path = tmp_path / "absent" / "ledger.sqlite3"
    assert diagnose(path, SCOPE, root=tmp_path)["exit_code"] == 2
    assert not path.parent.exists()


@pytest.mark.parametrize(
    "stamp,expected",
    [
        (NOW - timedelta(seconds=900), "fresh"),
        (NOW - timedelta(seconds=901), "stale"),
        (NOW + timedelta(seconds=1), "invalid_timestamp"),
        (NOW.replace(tzinfo=None), "invalid_timestamp"),
        ("bad", "invalid_timestamp"),
    ],
)
def test_freshness_boundary(
    ledger: Intelligence, tmp_path: Path, stamp: datetime | str, expected: str
) -> None:
    with ledger.db:
        ledger.db.execute(
            "UPDATE observations SET observed_at=?", (str(stamp),)
        )
    result = report(ledger, tmp_path)
    assert result["exit_code"] == (0 if expected == "fresh" else 1)
    assert all(
        r["state"] == expected
        for rows in result["freshness"].values()
        for r in rows
    )


def test_absent_contract_not_fresh_empty(
    ledger: Intelligence, tmp_path: Path
) -> None:
    with ledger.db:
        ledger.db.execute("DELETE FROM observations WHERE kind='contract'")
    result = report(ledger, tmp_path)
    assert codes(result) == ["contract_freshness"]
    assert result["exit_code"] == 1


@pytest.mark.parametrize("change", ["missing", "symbol", "key"])
def test_doctor_explains_invalid_recorded_agent_identity(
    ledger: Intelligence, tmp_path: Path, change: str
) -> None:
    # Arrange: freshness alone is insufficient for live ledger admission.
    if change == "key":
        with ledger.db:
            ledger.db.execute(
                "UPDATE observations SET key='OTHER' WHERE kind='agent'"
            )
    else:
        data: dict[str, Any] = {"credits": 100000}
        if change == "symbol":
            data["symbol"] = "OTHER"
        ledger.observe(SCOPE, "agent", "AGENT", data)
        with ledger.db:
            ledger.db.execute(
                "UPDATE observations SET observed_at=? WHERE kind='agent'",
                (NOW.isoformat(),),
            )

    # Act / Assert
    result = report(ledger, tmp_path)
    assert codes(result) == ["agent_identity_unknown"]
    assert result["exit_code"] == 1


@pytest.mark.parametrize(
    "keys,status,expected",
    [
        (["trade:A"], "open", "trade_recovery"),
        (["reposition:A"], "open", "reposition_recovery"),
        (["procurement:C"], "open", "procurement_recovery"),
        (["contract:A"], "open", "unknown_or_multiple_positions"),
        (["trade:A"], "weird", "unknown_or_multiple_positions"),
        (["trade:A", "reposition:B"], "open", "unknown_or_multiple_positions"),
        (["trade:A"], "closed", None),
    ],
)
def test_positions(
    ledger: Intelligence,
    tmp_path: Path,
    keys: list[str],
    status: str,
    expected: str | None,
) -> None:
    for key in keys:
        ledger.observe(SCOPE, "position", key, {"status": status})
    result = report(ledger, tmp_path)
    assert codes(result) == ([expected] if expected else [])


@pytest.mark.parametrize(
    "status",
    ["running", "stopped", "interrupted", "failed", "completed", "unknown"],
)
def test_pilot_record_not_liveness(
    ledger: Intelligence, tmp_path: Path, status: str
) -> None:
    ledger.observe(SCOPE, "automation_run", "z-old", {"status": "failed"})
    ledger.observe(
        SCOPE,
        "automation_run",
        "a-new",
        {
            "status": status,
            "resume_command": "danger --execute",
            "resume_instructions": "danger",
        },
    )
    result = report(ledger, tmp_path)
    assert result["last_pilot"]["key"] == "a-new"
    assert result["last_pilot"]["recorded_status"] == status
    assert result["last_pilot"]["process_state"] == "unknown"
    assert result["exit_code"] == (0 if status == "completed" else 1)
    assert "danger" not in json.dumps(result)
    assert "resume_command" not in json.dumps(result)
    codes(result)


def test_accepted_and_incomplete_contract(
    ledger: Intelligence, tmp_path: Path
) -> None:
    ledger.observe(
        SCOPE, "contract", "active", {"accepted": True, "fulfilled": False}
    )
    ledger.observe(SCOPE, "contract", "unknown", {})
    assert codes(report(ledger, tmp_path))[:2] == [
        "accepted_contracts",
        "contract_state_unknown",
    ]


@pytest.mark.parametrize(
    "status",
    [
        {"resume_command": "saved --execute"},
        float("nan"),
        float("inf"),
        float("-inf"),
        "saved --execute",
        ["completed"],
        None,
    ],
)
def test_invalid_pilot_status_is_safe_unknown(
    ledger: Intelligence,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: Any,
) -> None:
    ledger.observe(SCOPE, "automation_run", "run", {"status": status})

    result = report(ledger, tmp_path)

    assert result["last_pilot"]["recorded_status"] == "unknown"
    assert result["exit_code"] == 1
    assert codes(result) == ["pilot_record_requires_review"]
    encoded = json.dumps(result, allow_nan=False)
    assert "saved" not in encoded
    assert "resume_command" not in encoded
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        auto_cmd, "diagnose", lambda *a, **k: diagnose(*a, now=NOW, **k)
    )
    cli = CliRunner().invoke(
        auto_cmd.auto_app,
        ["doctor", "--scope", SCOPE, "--database", "ledger.sqlite3"],
    )
    assert cli.exit_code == 1
    assert json.dumps(json.loads(cli.stdout), allow_nan=False) == encoded


@pytest.mark.parametrize(
    "mode,expected", [("fresh", 0), ("stop", 1), ("missing", 2)]
)
def test_cli_exits(
    ledger: Intelligence,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    with ledger.db:
        ledger.db.execute(
            "UPDATE observations SET observed_at=?",
            (datetime.now(UTC).isoformat(),),
        )
    if mode == "stop":
        (tmp_path / "STOP").touch()
    path = tmp_path / (
        "missing.sqlite3" if mode == "missing" else "ledger.sqlite3"
    )
    result = CliRunner().invoke(
        auto_cmd.auto_app,
        ["doctor", "--scope", SCOPE, "--database", str(path)],
    )
    assert result.exit_code == expected, result.output
    assert json.loads(result.stdout)["exit_code"] == expected
    assert len(result.stdout.splitlines()) == 1


def test_cli_requires_explicit_scope() -> None:
    assert CliRunner().invoke(auto_cmd.auto_app, ["doctor"]).exit_code == 2


def test_consistent_transaction(
    ledger: Intelligence, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Intelligence.pending_actions

    def concurrent_write(
        reader: Intelligence, scope: str
    ) -> list[dict[str, Any]]:
        assert reader.db.in_transaction
        ledger.observe(SCOPE, "position", "trade:new", {"status": "open"})
        return original(reader, scope)

    monkeypatch.setattr(Intelligence, "pending_actions", concurrent_write)
    assert codes(report(ledger, tmp_path)) == []
    assert ledger.latest(SCOPE, "position")
