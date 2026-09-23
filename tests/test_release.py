"""Offline release rehearsal: all host and cloud boundaries are synthetic."""

from __future__ import annotations

import hashlib
import io
import json
import os
import pwd
import shlex
import sqlite3
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from deploy import release
from py_st.cli.flight_cmd import flight_app
from py_st.services.flight_auth import save_password
from py_st.services.flight_demo import SCOPE, create_demo
from py_st.services.flight_queue import FlightQueue
from py_st.services.stop_control import request_stop

OLD = "a" * 40
NEW = "b" * 40
SECRET = "secret-canary-never-print"


def bundle(
    path: Path,
    *,
    member: str = "deploy/release.py",
    content: bytes = b"print('release')\n",
) -> tuple[Path, str]:
    manifest = {
        "version": 1,
        "branch": "master",
        "sha": NEW,
        "python": "3.12.14",
        "platform": "linux-x86_64",
        "files": {member: hashlib.sha256(content).hexdigest()},
    }
    with tarfile.open(path, "w:gz") as archive:
        for name, data in (
            (member, content),
            ("manifest.json", json.dumps(manifest).encode()),
        ):
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return path, release.sha256(path)


def test_default_head_pins_sha_for_master_and_renamed_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for branch in ("master", "main", "renamed"):
        calls: list[list[str]] = []

        def fake(
            args: list[str],
            *,
            name: str = branch,
            seen: list[list[str]] = calls,
            **_kwargs: Any,
        ) -> str:
            seen.append(args)
            return f"ref: refs/heads/{name}\tHEAD\n{NEW}\tHEAD"

        monkeypatch.setattr(release, "run", fake)
        assert release.default_head(tmp_path) == (branch, NEW)
        assert calls == [["git", "ls-remote", "--symref", "origin", "HEAD"]]


def test_archive_rejects_corruption_traversal_and_symlink(
    tmp_path: Path,
) -> None:
    path, _ = bundle(tmp_path / "valid.tar.gz")
    release.verify_archive(path, release.manifest_from(path))
    bad, _ = bundle(tmp_path / "corrupt.tar.gz", content=b"mismatch")
    info = release.manifest_from(bad)
    info["files"]["deploy/release.py"] = "0" * 64
    with pytest.raises(release.ReleaseError, match="digest"):
        release.verify_archive(bad, info)
    for name in ("../escape", "/absolute", "wheels/../../escape"):
        unsafe, _ = bundle(
            tmp_path / f"unsafe-{len(name)}.tar.gz", member=name
        )
        with pytest.raises(release.ReleaseError, match="manifest"):
            release.manifest_from(unsafe)
    linked = tmp_path / "linked.tar.gz"
    with tarfile.open(linked, "w:gz") as archive:
        entry = tarfile.TarInfo("bad")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "/etc/shadow"
        archive.addfile(entry)
    with pytest.raises(release.ReleaseError):
        release.extract(linked, tmp_path / "extract")


def test_inspect_state_sanitizes_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "state"
    root.mkdir()
    create_demo(root)
    save_password(root, "synthetic-owner")
    (root / ".env").write_text("ST_TOKEN=" + SECRET)
    queue = FlightQueue(root, create=True, scope=SCOPE, mode="demo")
    queue.heartbeat("paused")
    queue.close()
    request_stop(root)
    monkeypatch.setenv("ST_STATE_ROOT", str(root))
    opened: list[str] = []
    original = sqlite3.connect

    def read_only_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        if "flight.sqlite3" in str(database) or "intelligence.sqlite3" in str(
            database
        ):
            opened.append(str(database))
        return original(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", read_only_connect)

    result = CliRunner().invoke(flight_app, ["inspect-state"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["paused"] is True
    assert SECRET not in result.stdout
    assert "digest" not in result.stdout
    assert len(opened) == 3 and all("?mode=ro" in uri for uri in opened)


def test_read_only_inspect_never_creates_missing_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "state"
    root.mkdir()
    create_demo(root)
    save_password(root, "synthetic-owner")
    queue = FlightQueue(root, create=True, scope=SCOPE, mode="demo")
    queue.close()
    (root / ".state-lease").unlink()
    monkeypatch.setenv("ST_STATE_ROOT", str(root))
    result = CliRunner().invoke(flight_app, ["inspect-state"])
    assert result.exit_code != 0
    assert not (root / ".state-lease").exists()


def test_wheel_asset_gate_rejects_missing_javascript(tmp_path: Path) -> None:
    wheel = tmp_path / "py_st-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("py_st/services/dashboard.html", "<main></main>")
        archive.writestr("py_st/services/ui/shell.css", "body {}")
    with pytest.raises(release.ReleaseError, match="JavaScript"):
        release.check_wheel(wheel)


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    base = tmp_path / "opt"
    data = tmp_path / "data"
    root = data / "state"
    ops = tmp_path / "ops"
    for directory in (base / "releases" / OLD, root, ops):
        directory.mkdir(parents=True)
    old_python = base / "releases" / OLD / ".venv/bin/python"
    old_python.parent.mkdir(parents=True)
    old_python.touch()
    ops.chmod(0o700)
    (base / "current").symlink_to(base / "releases" / OLD)
    (root / ".env").write_text("ST_TOKEN=" + SECRET)
    (root / "STOP").touch()
    gate = ops / "worker-armed"
    gate.touch()
    monkeypatch.setattr(release, "WORKER_GATE", gate)
    monkeypatch.setattr(release, "BASE", base)
    monkeypatch.setattr(release, "DATA", data)
    monkeypatch.setattr(release, "ROOT", root)
    monkeypatch.setattr(release, "OPS", ops)
    # Synthetic directories belong to the runner, whereas production requires
    # uid 0. Preserve the real mode/owner checks against this test owner.
    monkeypatch.setattr(release, "ADMIN_UID", os.getuid())
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    active = {name: "active" for name in release.SERVICES}
    monkeypatch.setattr(release, "services", lambda: active.copy())
    monkeypatch.setattr(
        release,
        "state_summary",
        lambda: {
            "stop": True,
            "paused": True,
            "heartbeat": datetime.now(UTC).isoformat(),
            "worker_state": "paused",
            "queued": 2,
            "uncertain": 1,
        },
    )
    return SimpleNamespace(
        base=base, data=data, root=root, ops=ops, active=active, events=[]
    )


def rehearse(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    failure: str | None = None,
) -> tuple[Path, str]:
    path, digest = bundle(
        host.ops / "bundle.tar.gz",
        content=Path(release.__file__).read_bytes(),
    )
    target = host.base / "releases" / NEW
    target.mkdir()
    new_python = target / ".venv/bin/python"
    new_python.parent.mkdir(parents=True)
    new_python.touch()
    (target / ".release.json").write_text(
        json.dumps({"sha": NEW, "digest": digest})
    )

    def step(name: str, result: Any = None) -> Any:
        host.events.append(name)
        if failure == name:
            raise release.ReleaseError(f"synthetic {name} failure")
        return result

    monkeypatch.setattr(
        release,
        "preflight",
        lambda _a, _b: step("preflight", (release.manifest_from(path), OLD)),
    )
    monkeypatch.setattr(
        release, "stage", lambda _a, _b, _c: step("stage", target)
    )
    monkeypatch.setattr(
        release,
        "inspect",
        lambda _p: step("inspect", {"stop": True, "paused": True}),
    )
    monkeypatch.setattr(release, "stop_services", lambda: step("stop"))
    monkeypatch.setattr(
        release,
        "checkpoint",
        lambda _p, _r: step(
            "checkpoint", host.data / "checkpoints" / "synthetic"
        ),
    )
    real_switch = release.switch
    monkeypatch.setattr(
        release, "switch", lambda p: (step("switch"), real_switch(p))
    )
    monkeypatch.setattr(release, "start_services", lambda: step("start"))
    monkeypatch.setattr(
        release,
        "fresh_heartbeat",
        lambda _t: step("heartbeat", {"worker_state": "paused"}),
    )
    monkeypatch.setattr(
        release, "config", lambda: ("https://example.com", 8765)
    )
    monkeypatch.setattr(release, "probe", lambda _a, _b: step("http"))
    return path, digest


def test_success_and_repeat_preserve_pause_and_private_state(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path, digest = rehearse(host, monkeypatch)
    release.deploy(path, digest)
    receipt = release.last_receipt()
    assert receipt is not None
    assert receipt["result"] == "success"
    assert receipt["previous_sha"] == OLD
    assert host.events == [
        "preflight",
        "stage",
        "inspect",
        "stop",
        "checkpoint",
        "inspect",
        "switch",
        "start",
        "heartbeat",
        "http",
    ]
    assert release.current_sha() == NEW
    assert (host.root / "STOP").exists()
    assert (host.root / ".env").read_text() == "ST_TOKEN=" + SECRET
    assert SECRET not in json.dumps(receipt) + capsys.readouterr().out
    release.deploy(path, digest)
    assert len(host.events) == 10
    assert "Already deployed" in capsys.readouterr().out


def test_same_sha_refuses_stale_heartbeat(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, digest = rehearse(host, monkeypatch)
    release.deploy(path, digest)
    monkeypatch.setattr(
        release,
        "state_summary",
        lambda: {
            "stop": True,
            "paused": True,
            "worker_state": "paused",
            "heartbeat": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    with pytest.raises(release.ReleaseError, match="stale"):
        release.deploy(path, digest)
    receipt = release.last_receipt()
    assert receipt is not None and receipt["result"] == "success"


def test_recover_acknowledge_preserves_receipt_and_allows_explicit_retry(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, digest = rehearse(host, monkeypatch, "checkpoint")
    with pytest.raises(release.ReleaseError, match="incomplete"):
        release.deploy(path, digest)
    failed = release.last_receipt()
    assert failed is not None
    run_id = failed["run_id"]
    with pytest.raises(release.ReleaseError, match="matching incomplete"):
        release.acknowledge("0" * 32)
    host.active[release.SERVICES[1]] = "inactive"
    with pytest.raises(release.ReleaseError, match="Recovery not verified"):
        release.acknowledge(run_id)
    host.active[release.SERVICES[1]] = "active"
    host.ops.joinpath("worker-armed").unlink()
    with pytest.raises(release.ReleaseError, match="Recovery not verified"):
        release.acknowledge(run_id)
    host.ops.joinpath("worker-armed").touch()
    release.acknowledge(run_id)
    recovered = release.last_receipt()
    assert recovered is not None and recovered["result"] == "recovered"
    assert recovered["failure_observed"] == failed["observed"]
    history = host.ops / "runs" / f"{run_id}.json"
    assert json.loads(history.read_text())["result"] == "recovered"
    monkeypatch.setattr(
        release,
        "checkpoint",
        lambda _p, _r: host.data / "checkpoints" / "retry",
    )
    release.deploy(path, digest)
    retried = release.last_receipt()
    assert retried is not None and retried["result"] == "success"
    assert retried["run_id"] != run_id
    assert history.is_file()


def test_acknowledge_old_release_without_inspector_after_compatibility_failure(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, digest = rehearse(host, monkeypatch)
    inspected: list[Path] = []

    def inspect_release(python: Path) -> dict[str, bool]:
        inspected.append(python)
        if NEW in python.parts and len(inspected) > 1:
            raise release.ReleaseError("new release rejects persisted state")
        return {"stop": True, "paused": True}

    monkeypatch.setattr(release, "inspect", inspect_release)
    with pytest.raises(release.ReleaseError, match="incomplete"):
        release.deploy(path, digest)
    failed = release.last_receipt()
    assert failed is not None and failed["phase"] == "compatibility"
    assert release.current_sha() == OLD
    before_ack = inspected.copy()
    release.acknowledge(failed["run_id"])
    assert inspected == before_ack
    recovered = release.last_receipt()
    assert recovered is not None and recovered["result"] == "recovered"


def test_lost_output_after_success_keeps_success_receipt(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, digest = rehearse(host, monkeypatch)

    def broken_output(_json: bool) -> None:
        raise BrokenPipeError("SSH terminal disconnected")

    monkeypatch.setattr(release, "status", broken_output)
    release.deploy(path, digest)
    receipt = release.last_receipt()
    assert receipt is not None and receipt["result"] == "success"
    assert receipt["error_category"] is None


def test_acknowledge_current_new_release_still_inspects_it(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, digest = rehearse(host, monkeypatch, "http")
    with pytest.raises(release.ReleaseError, match="incomplete"):
        release.deploy(path, digest)
    failed = release.last_receipt()
    assert failed is not None and release.current_sha() == NEW
    inspected: list[Path] = []

    def inspected_release(python: Path) -> dict[str, bool]:
        inspected.append(python)
        return {"stop": True, "paused": True}

    monkeypatch.setattr(release, "inspect", inspected_release)
    release.acknowledge(failed["run_id"])
    assert inspected == [host.base / "releases" / NEW / ".venv/bin/python"]


def test_bad_bundle_digest_exits_before_manifest_parse(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = host.ops / "truncated.tar.gz"
    path.write_bytes(b"truncated transfer")
    monkeypatch.setattr(
        release,
        "manifest_from",
        lambda _p: pytest.fail("Malformed bundle must not be parsed"),
    )
    with pytest.raises(release.ReleaseError, match="SHA256 mismatch"):
        release.deploy(path, "0" * 64)
    assert release.last_receipt() is None


def test_corrupt_receipt_fails_with_manual_guidance(
    host: SimpleNamespace,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for record in ("{incomplete", '{"run_id":"bad","result":"unknown"}'):
        (host.ops / "receipt.json").write_text(record)
        with pytest.raises(release.ReleaseError, match="inspect it manually"):
            release.status(False)
        output = capsys.readouterr().out
        assert f"Current: {OLD}" in output
        assert "Last receipt: unreadable" in output
        with pytest.raises(release.ReleaseError, match="inspect it manually"):
            release.status(True)
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["observed"]["current_sha"] == OLD
        assert "inspect it manually" in parsed["receipt_error"]


def test_stage_failure_removes_new_partial_release(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, digest = bundle(host.ops / "bundle.tar.gz")
    manifest = release.manifest_from(path)
    target = host.base / "releases" / NEW

    def failed_install(*_args: Any, **_kwargs: Any) -> str:
        raise release.ReleaseError("synthetic pip failure")

    monkeypatch.setattr(release, "run", failed_install)
    with pytest.raises(release.ReleaseError, match="pip failure"):
        release.stage(path, manifest, digest)
    assert not target.exists()


@pytest.mark.parametrize(
    "failure",
    [
        "preflight",
        "stage",
        "checkpoint",
        "inspect",
        "switch",
        "start",
        "heartbeat",
        "http",
    ],
)
def test_failure_retains_evidence_and_never_resumes(
    host: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    path, digest = rehearse(host, monkeypatch, failure)
    with pytest.raises(release.ReleaseError, match="incomplete"):
        release.deploy(path, digest)
    receipt = release.last_receipt()
    assert receipt is not None and receipt["result"] == "incomplete"
    assert release.current_sha() == (
        NEW if failure in {"start", "heartbeat", "http"} else OLD
    )
    assert (host.root / "STOP").exists()
    assert SECRET not in json.dumps(receipt) + str(capsys.readouterr())
    assert "restore" not in host.events
    if failure in {"checkpoint", "switch", "start", "heartbeat", "http"}:
        with pytest.raises(release.ReleaseError, match="Prior activation"):
            release.deploy(path, digest)


def test_stale_heartbeat_never_passes(
    host: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        release,
        "inspect",
        lambda _p: {
            "stop": True,
            "paused": True,
            "heartbeat": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "worker_state": "paused",
        },
    )
    times = iter((0, 50))
    monkeypatch.setattr(time, "monotonic", lambda: next(times))
    with pytest.raises(release.ReleaseError, match="heartbeat"):
        release.fresh_heartbeat(datetime.now(UTC))


def test_preflight_rejects_mount_pause_and_authority_before_downtime(
    host: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest = bundle(
        host.ops / "preflight.tar.gz",
        content=Path(release.__file__).read_bytes(),
    )
    hosted = host.ops / "hosted.env"
    hosted.write_text(
        "ST_PUBLIC_ORIGIN=https://example.com\n" "PY_ST_BACKEND_PORT=8765\n"
    )
    armed = host.ops / "worker-armed"
    armed.touch()
    monkeypatch.setattr(release, "HOSTED_ENV", hosted)
    monkeypatch.setattr(release, "WORKER_GATE", armed)
    monkeypatch.setattr(release, "unit_checks", lambda: None)
    monkeypatch.setattr(os.path, "ismount", lambda _p: True)
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda _u: SimpleNamespace(pw_uid=host.root.stat().st_uid),
    )
    assert release.preflight(path, digest)[1] == OLD
    monkeypatch.setattr(release, "ADMIN_UID", os.getuid() + 1)
    with pytest.raises(release.ReleaseError, match="administrator-owned"):
        release.preflight(path, digest)
    monkeypatch.setattr(release, "ADMIN_UID", os.getuid())
    with pytest.raises(release.ReleaseError, match="SHA256"):
        release.preflight(path, "0" * 64)
    monkeypatch.setattr(os.path, "ismount", lambda _p: False)
    with pytest.raises(release.ReleaseError, match="mount/root"):
        release.preflight(path, digest)
    monkeypatch.setattr(os.path, "ismount", lambda _p: True)
    armed.unlink()
    with pytest.raises(release.ReleaseError, match="authority gate"):
        release.preflight(path, digest)
    armed.touch()
    monkeypatch.setattr(
        release, "state_summary", lambda: {"stop": False, "paused": False}
    )
    with pytest.raises(release.ReleaseError, match="Pause in Operations"):
        release.preflight(path, digest)
    assert release.current_sha() == OLD


def test_receipt_directory_requires_admin_owner(
    host: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest = bundle(
        host.ops / "owner.tar.gz",
        content=Path(release.__file__).read_bytes(),
    )
    monkeypatch.setattr(release, "ADMIN_UID", os.getuid() + 1)
    with pytest.raises(release.ReleaseError, match="Operations directory"):
        release.deploy(path, digest)
    assert release.last_receipt() is None


def test_transfer_uses_pinned_private_directory_and_quoted_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact, digest = bundle(tmp_path / "bundle with space.tar.gz")
    calls: list[tuple[str, ...]] = []

    def fake(_project: str, _zone: str, *args: str, **_kwargs: Any) -> str:
        calls.append(args)
        if args[:1] == ("ssh",) and "sha256sum" in args[-1]:
            return (
                f"{digest}  bundle\n"
                f"{release.sha256(Path(release.__file__))}  script"
            )
        return (
            "/home/operator"
            if args[:1] == ("ssh",) and any("printf" in a for a in args)
            else ""
        )

    monkeypatch.setattr(release, "gcloud", fake)
    release.transfer(artifact, digest, "proj", "zone", "instance")
    output = capsys.readouterr().out
    assert f"/incoming/{NEW}/release.py" in output
    assert "'" in output  # shell quotes the bundle path with spaces
    assert "systemd-run" in output and "--wait" in output
    assert sum(call[0] == "scp" for call in calls) == 2
    assert (
        shlex.quote(
            f"/home/operator/.local/share/py-st-deploy/incoming/"
            f"{NEW}/bundle with space.tar.gz.partial"
        )
        in calls[-2][-1]
    )
    monkeypatch.setattr(release, "gcloud", lambda *_a, **_kw: "/home/o;bad")
    with pytest.raises(release.ReleaseError, match="home path"):
        release.transfer(artifact, digest, "proj", "zone", "instance")


def test_transfer_rejects_remote_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact, digest = bundle(tmp_path / "release.tar.gz")
    monkeypatch.setattr(
        release,
        "gcloud",
        lambda _project, _zone, *args, **_kw: (
            "/home/operator"
            if "printf" in args[-1]
            else (
                "0" * 64 + "  damaged\n" + "0" * 64 + "  script"
                if "sha256sum" in args[-1]
                else ""
            )
        ),
    )
    with pytest.raises(release.ReleaseError, match="Remote bundle"):
        release.transfer(artifact, digest, "proj", "zone", "instance")
    assert "VM activation command" not in capsys.readouterr().out


def test_condition_skipped_worker_and_public_failure_are_distinct(
    host: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "run", lambda *_a, **_kw: "")
    host.active[release.SERVICES[1]] = "inactive"
    times = iter((0, 36))
    monkeypatch.setattr(time, "monotonic", lambda: next(times))
    with pytest.raises(release.ReleaseError, match="ConditionPath"):
        release.start_services()

    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    def urlopen(request: Any, timeout: int) -> Response:
        assert timeout == 10
        if request.full_url.startswith("https:"):
            raise urllib.error.URLError("synthetic TLS error")
        assert request.get_header("Host") == "example.com"
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(release.ReleaseError, match="public HTTPS"):
        release.probe("https://example.com", 8765)


def test_checkpoint_runs_old_interpreter_and_keeps_private_evidence(
    host: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        pwd,
        "getpwnam",
        lambda _u: SimpleNamespace(
            pw_uid=host.root.stat().st_uid,
            pw_gid=host.root.stat().st_gid,
        ),
    )

    def fake(args: list[str], **_kwargs: Any) -> str:
        calls.append(args)
        target = Path(args[-1])
        target.mkdir()
        (target / "checkpoint.json").write_text("synthetic private evidence")
        return ""

    monkeypatch.setattr(release, "run", fake)
    target = release.checkpoint(OLD, "synthetic-run")
    assert str(host.base / "releases" / OLD / ".venv/bin/python") in calls[0]
    assert "flight" in calls[0] and "checkpoint" in calls[0]
    assert target.is_dir()
    assert (host.root / ".env").read_text() == "ST_TOKEN=" + SECRET
