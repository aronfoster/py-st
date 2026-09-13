"""Offline reset-night rehearsal through the CLI and real HTTP client stack."""

import os
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from py_st import cache, env
from py_st.cli.app import app
from py_st.client.client import close_shared_client
from tests.factories import RegisterAgentResponseDataFactory

runner = CliRunner()
REGISTER = ["agent", "register", "--symbol", "NEW", "--faction", "COSMIC"]
VERIFY = [
    "agent",
    "verify-registration",
    "--symbol",
    "NEW",
    "--faction",
    "COSMIC",
]
# Deliberately synthetic, non-credential sentinels only.
ACCOUNT = "synthetic-account-credential"
TOKEN = "synthetic-new-agent-credential"
OLD = "synthetic-old-agent-credential"


@pytest.fixture(autouse=True)
def isolated_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    # Arrange: no real dotenv, cache, shared session or runtime state access.
    close_shared_client()
    monkeypatch.chdir(tmp_path)
    for key in (
        "SPACETRADERS_ACCOUNT_TOKEN",
        "DEFAULT_AGENT_SYMBOL",
        "DEFAULT_AGENT_FACTION",
        "ST_TOKEN",
        "ST_STATE_ROOT",
    ):
        # Record absent keys too: load_dotenv writes outside monkeypatch.
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(cache, "CACHE_FILE", tmp_path / ".cache/data.json")

    def refuse_network(
        transport: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        raise AssertionError("Unexpected HTTP request in offline rehearsal")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse_network)
    yield
    close_shared_client()


@pytest.fixture
def starter() -> dict[str, Any]:
    data = RegisterAgentResponseDataFactory.build_minimal()
    data["token"] = TOKEN
    data["agent"].update(
        symbol="NEW", startingFaction="COSMIC", shipCount=2, credits=175000
    )
    command = data["ships"][0]
    command["symbol"] = "NEW-1"
    command["registration"].update(name="NEW-1", role="COMMAND")
    probe = deepcopy(command)
    probe["symbol"] = "NEW-2"
    probe["registration"].update(name="NEW-2", role="SATELLITE")
    data["ships"].append(probe)
    data["contract"].update(factionSymbol="COSMIC", accepted=False)
    return data


def install_peer(
    monkeypatch: pytest.MonkeyPatch, starter: dict[str, Any]
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def handler(
        transport: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v2/register":
            assert request.method == "POST"
            assert request.headers["Authorization"] == f"Bearer {ACCOUNT}"
            assert request.content == b'{"symbol":"NEW","faction":"COSMIC"}'
            return httpx.Response(201, json={"data": starter})
        assert request.method == "GET"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        payloads = {
            "/v2/my/agent": starter["agent"],
            "/v2/my/ships": starter["ships"],
            "/v2/my/contracts": [starter["contract"]],
        }
        return httpx.Response(200, json={"data": payloads[request.url.path]})

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handler)
    return requests


@pytest.mark.parametrize("source", ["flags", "environment", "dotenv"])
def test_register_then_verify(
    source: str,
    starter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange: cached previous-reset identities and durable evidence.
    Path(".env").write_text(f"# keep me\nST_TOKEN='{OLD}'\n", encoding="utf-8")
    Path("runtime-evidence").write_text("previous scope", encoding="utf-8")
    cache.save_cache(
        {"agent_info": {"old": True}, "ships": [], "contracts": []}
    )
    requests = install_peer(monkeypatch, starter)
    args = REGISTER
    if source == "flags":
        args = [*REGISTER, "--account-token", ACCOUNT]
    elif source == "environment":
        monkeypatch.setenv("ST_STATE_ROOT", str(Path.cwd()))
        monkeypatch.setenv("SPACETRADERS_ACCOUNT_TOKEN", ACCOUNT)
        monkeypatch.setenv("DEFAULT_AGENT_SYMBOL", "new")
        monkeypatch.setenv("DEFAULT_AGENT_FACTION", "cosmic")
        args = ["agent", "register"]
    else:
        with Path(".env").open("a", encoding="utf-8") as stream:
            stream.write(
                f"SPACETRADERS_ACCOUNT_TOKEN='{ACCOUNT}'\n"
                "DEFAULT_AGENT_SYMBOL=NEW\nDEFAULT_AGENT_FACTION=COSMIC\n"
                f"ST_STATE_ROOT='{Path.cwd()}'\n"
            )
        args = ["agent", "register"]
    monkeypatch.setenv("ST_TOKEN", OLD)

    # Act: owner invokes registration, then the separate read-only smoke path.
    registered = runner.invoke(app, args)
    verified = runner.invoke(app, VERIFY)

    # Assert: saved credential wins over the old exported token.
    assert registered.exit_code == 0, registered.output
    assert "Verification pending" in registered.output
    assert verified.exit_code == 0, verified.output
    assert "Verified agent NEW" in verified.output
    assert "175000" in verified.output
    assert "NEW-1: COMMAND" in verified.output
    assert "NEW-2: SATELLITE" in verified.output
    assert "accepted=False" in verified.output
    assert [r.url.path for r in requests] == [
        "/v2/register",
        "/v2/my/agent",
        "/v2/my/ships",
        "/v2/my/contracts",
    ]
    assert env.saved_agent_token() == TOKEN
    assert os.environ["ST_TOKEN"] == OLD
    assert "# keep me" in Path(".env").read_text(encoding="utf-8")
    assert not cache.CACHE_FILE.exists()
    assert Path("runtime-evidence").read_text() == "previous scope"
    for secret in (ACCOUNT, TOKEN, OLD):
        assert secret not in registered.output + verified.output + caplog.text


@pytest.mark.parametrize(
    "failure", [400, 401, 409, 500, 4113, "timeout", "bad"]
)
def test_api_failure_preserves_local_identity(
    failure: int | str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    original = f"ST_TOKEN='{OLD}'\n"
    Path(".env").write_text(original, encoding="utf-8")
    Path("runtime-evidence").write_text("pending operation", encoding="utf-8")
    cache.save_cache({"agent_info": {"symbol": "OLD"}})
    previous_cache = cache.CACHE_FILE.read_bytes()
    calls = []

    def handler(
        transport: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(ACCOUNT, request=request)
        if failure == "bad":
            return httpx.Response(201, json={"data": {"token": TOKEN}})
        return httpx.Response(
            400 if failure == 4113 else int(failure),
            json={"error": {"message": ACCOUNT, "code": failure}},
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handler)

    # Act
    result = runner.invoke(app, [*REGISTER, "--account-token", ACCOUNT, "-v"])

    # Assert: even server messages, parse errors and timeout text stay private.
    assert result.exit_code == 1
    assert "Previous saved token" in result.output
    assert len(calls) == 1
    assert Path(".env").read_text(encoding="utf-8") == original
    assert cache.CACHE_FILE.read_bytes() == previous_cache
    assert Path("runtime-evidence").read_text() == "pending operation"
    for secret in (ACCOUNT, TOKEN, OLD):
        assert secret not in result.output + caplog.text


@pytest.mark.parametrize("failure", ["cache", "persistence"])
def test_local_activation_failure_is_explicit(
    failure: str,
    starter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    original = f"ST_TOKEN='{OLD}'\n"
    Path(".env").write_text(original, encoding="utf-8")
    cache.save_cache({"agent_info": "old"})
    requests = install_peer(monkeypatch, starter)
    if failure == "cache":
        cache.CACHE_FILE.unlink()
        cache.CACHE_FILE.mkdir()  # unlink must fail, rather than be swallowed.
    else:

        def fail_replace(source: Path, target: Path) -> None:
            raise PermissionError(TOKEN)

        monkeypatch.setattr(os, "replace", fail_replace)

    # Act
    result = runner.invoke(app, [*REGISTER, "--account-token", ACCOUNT])

    # Assert
    assert result.exit_code == 1
    assert "registered remotely" in result.output
    assert "Do not register again" in result.output
    assert "account dashboard" in result.output
    assert Path(".env").read_text(encoding="utf-8") == original
    assert len(requests) == 1
    assert "Token saved" not in result.output
    assert TOKEN not in result.output + caplog.text


@pytest.mark.parametrize(
    "args, message, code",
    [
        (["agent", "register"], "Missing account token", 1),
        (
            ["agent", "register", "--account-token", ACCOUNT],
            "Missing agent symbol",
            1,
        ),
        (
            [
                "agent",
                "register",
                "--account-token",
                ACCOUNT,
                "--symbol",
                "NEW",
            ],
            "Missing faction",
            1,
        ),
        ([*REGISTER, "--account-token", ACCOUNT, "--symbol", "X"], "3-14", 1),
        (
            [*REGISTER, "--account-token", ACCOUNT, "--faction", "INVALID"],
            "Unknown faction",
            1,
        ),
        ([*REGISTER, "--clear-cache"], "No such option", 2),
        (["agent", "verify-registration"], "Missing option", 2),
    ],
)
def test_cli_validation(args: list[str], message: str, code: int) -> None:
    # Act
    result = runner.invoke(app, args)

    # Assert: offline refusal fixture ensures no accidental dispatch.
    assert result.exit_code == code
    assert message in result.output


@pytest.mark.parametrize(
    "failure",
    [
        "missing-token",
        "identity",
        "faction",
        "ships",
        "contracts",
        "command",
        "auth",
        "timeout",
    ],
)
def test_verification_failure_is_read_only_and_actionable(
    failure: str,
    starter: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Arrange
    if failure != "missing-token":
        env.save_agent_token(TOKEN)
    if failure == "identity":
        starter["agent"]["symbol"] = "OTHER"
    elif failure == "faction":
        starter["agent"]["startingFaction"] = "VOID"
    elif failure == "ships":
        starter["ships"] = []
    elif failure == "contracts":
        starter["contract"]["factionSymbol"] = "VOID"
    elif failure == "command":
        starter["ships"][0]["registration"]["role"] = "SATELLITE"
    requests = install_peer(monkeypatch, starter)
    if failure in ("auth", "timeout"):

        def fail_get(
            transport: httpx.HTTPTransport, request: httpx.Request
        ) -> httpx.Response:
            requests.append(request)
            if failure == "timeout":
                raise httpx.ReadTimeout(TOKEN, request=request)
            return httpx.Response(401, json={"error": {"message": TOKEN}})

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fail_get)
    cache.save_cache({"agent_info": "stale"})
    previous = cache.CACHE_FILE.read_bytes()

    # Act
    result = runner.invoke(app, VERIFY)

    # Assert
    assert result.exit_code == 1
    assert "verification failed" in result.output
    reasons = {
        "missing-token": "Saved ST_TOKEN is missing or unreadable",
        "identity": "does not match the expected identity",
        "faction": "does not match the expected identity",
        "ships": "Fleet is empty or its count/ownership is inconsistent",
        "contracts": "No starting-faction contract",
        "command": "No COMMAND ship",
        "auth": "Authentication/reset check failed",
        "timeout": "Agent identity request failed",
    }
    assert reasons[failure] in result.output
    assert "Do not register again" in result.output
    assert all(r.method == "GET" for r in requests)
    assert cache.CACHE_FILE.read_bytes() == previous
    assert TOKEN not in result.output + caplog.text


@pytest.mark.parametrize("existing", [False, True])
def test_token_persistence(existing: bool) -> None:
    # Arrange
    if existing:
        Path(".env").write_text(
            f"# preserved\nOTHER='value'\nST_TOKEN='{OLD}'\n", encoding="utf-8"
        )

    # Act
    env.save_agent_token(TOKEN)

    # Assert
    assert env.saved_agent_token() == TOKEN
    assert Path(".env").stat().st_mode & 0o777 == 0o600
    contents = Path(".env").read_text(encoding="utf-8")
    assert OLD not in contents
    if existing:
        assert "# preserved\nOTHER='value'\n" in contents
    assert list(Path.cwd().iterdir()) == [Path.cwd() / ".env"]


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["set-key", "replace"])
def test_failed_persistence_does_not_truncate_or_create_env(
    existing: bool, failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    original = f"ST_TOKEN='{OLD}'\n"
    if existing:
        Path(".env").write_text(original, encoding="utf-8")
    if failure == "set-key":
        monkeypatch.setattr(
            env, "set_key", lambda *a: (None, "ST_TOKEN", TOKEN)
        )
    else:

        def fail_replace(source: Path, target: Path) -> None:
            raise PermissionError("Synthetic persistence failure")

        monkeypatch.setattr(os, "replace", fail_replace)

    # Act
    with pytest.raises(OSError):
        env.save_agent_token(TOKEN)

    # Assert
    assert Path(".env").exists() == existing
    if existing:
        assert Path(".env").read_text(encoding="utf-8") == original
    assert not list(Path.cwd().glob("tmp*"))


def test_invalid_dotenv_fails_before_dispatch() -> None:
    # Arrange
    Path(".env").write_bytes(b"ST_TOKEN=\xff")

    # Act
    result = runner.invoke(app, [*REGISTER, "--account-token", ACCOUNT])

    # Assert: the default HTTP refusal fixture guards against dispatch.
    assert result.exit_code == 1
    assert "no request was sent" in result.output
    assert ACCOUNT not in result.output
    assert Path(".env").read_bytes() == b"ST_TOKEN=\xff"


def test_working_directory_env_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: a parent token must neither satisfy verification nor be edited.
    original = f"ST_TOKEN='{OLD}'\n"
    parent = Path.cwd() / ".env"
    parent.write_text(original, encoding="utf-8")
    child = Path.cwd() / "child"
    child.mkdir()
    monkeypatch.chdir(child)

    # Act & Assert
    with pytest.raises(ValueError, match="No saved ST_TOKEN"):
        env.saved_agent_token()
    env.save_agent_token(TOKEN)
    assert env.saved_agent_token() == TOKEN
    assert parent.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("token", ["", "  "])
def test_empty_token_cannot_replace_previous_identity(token: str) -> None:
    # Arrange
    env.save_agent_token(OLD)

    # Act
    with pytest.raises(ValueError, match="empty agent token"):
        env.save_agent_token(token)

    # Assert
    assert env.saved_agent_token() == OLD


@pytest.mark.parametrize("args", [REGISTER, VERIFY])
@pytest.mark.parametrize("source", ["environment", "dotenv"])
@pytest.mark.parametrize(
    "root_kind", ["other", "relative", "missing", "empty"]
)
def test_registration_requires_worker_root_before_any_request(
    args: list[str],
    source: str,
    root_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: another managed root with its own token and durable evidence.
    worker_root = Path.cwd() / "worker"
    worker_root.mkdir()
    worker_env = worker_root / ".env"
    worker_env.write_text(f"ST_TOKEN='{OLD}'\n", encoding="utf-8")
    evidence = worker_root / "runtime-evidence"
    evidence.write_text("pending operation", encoding="utf-8")
    values = {
        "other": str(worker_root),
        "relative": ".",
        "missing": str(Path.cwd() / "missing"),
        "empty": "",
    }
    config = f"ST_TOKEN='{TOKEN}'\nSPACETRADERS_ACCOUNT_TOKEN='{ACCOUNT}'\n"
    if source == "environment":
        monkeypatch.setenv("ST_STATE_ROOT", values[root_kind])
    else:
        config += f"ST_STATE_ROOT='{values[root_kind]}'\n"
    Path(".env").write_text(config, encoding="utf-8")
    # A relative cache path must not be cleared in the wrong directory either.
    monkeypatch.setattr(cache, "CACHE_DIR", Path(".cache"))
    monkeypatch.setattr(cache, "CACHE_FILE", Path(".cache/data.json"))
    cache.save_cache({"agent_info": "previous identity"})
    previous_cache = cache.CACHE_FILE.read_bytes()

    # Act: the default HTTP refusal fixture ensures no request is dispatched.
    result = runner.invoke(app, args)

    # Assert
    assert result.exit_code == 1
    assert "ST_STATE_ROOT" in result.output
    assert Path(".env").read_text(encoding="utf-8") == config
    assert worker_env.read_text(encoding="utf-8") == f"ST_TOKEN='{OLD}'\n"
    assert evidence.read_text(encoding="utf-8") == "pending operation"
    assert cache.CACHE_FILE.read_bytes() == previous_cache
    for secret in (ACCOUNT, TOKEN, OLD):
        assert secret not in result.output


def test_resolved_worker_root_alias_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: the same physical root may be addressed through a symlink.
    alias = Path.cwd() / "root-alias"
    alias.symlink_to(Path.cwd(), target_is_directory=True)
    monkeypatch.setenv("ST_STATE_ROOT", str(alias))

    # Act
    env.save_agent_token(TOKEN)

    # Assert
    assert env.saved_agent_token() == TOKEN
