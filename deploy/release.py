"""Pinned, operator-run single-host release. See docs/OPERATOR_RELEASE.md."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

VERSION = 1
BASE = Path("/opt/py-st")
DATA = Path("/srv/py-st")
ROOT = DATA / "state"
OPS = Path("/var/lib/py-st-deploy")
HOSTED_ENV = Path("/etc/py-st/hosted.env")
WORKER_GATE = Path("/etc/py-st/worker-armed")
USER = "py-st"
SERVICES = ("py-st-dashboard.service", "py-st-worker.service")
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
ASSETS = ("src/py_st/services/dashboard.html",)


class ReleaseError(Exception):
    """Expected refusal with an operator action."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ReleaseError(message)


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run(
    args: list[str], *, cwd: Path | None = None, timeout: int = 120
) -> str:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseError(f"{args[0]} unavailable or timed out") from exc
    if result.returncode:
        # Never echo subprocess output: pip, systemd and application errors may
        # include private paths or data. The phase and executable are enough.
        raise ReleaseError(f"{args[0]} exited {result.returncode}")
    return result.stdout.strip()


def prerequisites() -> None:
    require(
        sys.version_info[:2] == (3, 12),
        "Use Python 3.12 (python3.12 deploy/release.py ...)",
    )
    require(
        sys.platform == "linux" and platform.machine() == "x86_64",
        "Requires Linux x86_64, matching the py-st VM",
    )


def default_head(repo: Path) -> tuple[str, str]:
    output = run(["git", "ls-remote", "--symref", "origin", "HEAD"], cwd=repo)
    branch = re.search(r"^ref: refs/heads/([^\s]+)\s+HEAD$", output, re.M)
    commit = re.search(r"^([0-9a-f]{40})\s+HEAD$", output, re.M)
    require(
        branch is not None and commit is not None,
        "Remote default HEAD unavailable; check origin and retry",
    )
    assert branch is not None and commit is not None
    return branch.group(1), commit.group(1)


def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(
        name
        and not name.startswith("/")
        and "\\" not in name
        and all(part not in ("", ".", "..") for part in name.split("/"))
        and path.as_posix() == name
    )


def extract(
    archive: Path, target: Path, *, files: dict[str, str] | None = None
) -> None:
    seen: set[str] = set()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            name = member.name.rstrip("/")
            require(
                safe_name(name) and name not in seen,
                "Unsafe or duplicate archive member",
            )
            seen.add(name)
            require(
                member.isfile() or member.isdir(),
                "Archive has a symlink or special file",
            )
            if member.isdir():
                (target / name).mkdir(parents=True, exist_ok=True)
                continue
            require(
                files is None or name in files, "Unexpected archive member"
            )
            dest = target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            require(source is not None, "Unreadable archive member")
            assert source is not None
            with dest.open("xb") as output:
                shutil.copyfileobj(source, output)
            if files is not None:
                require(
                    sha256(dest) == files[name],
                    "Bundle member digest mismatch",
                )
    if files is not None:
        require(
            set(files) == {n for n in seen if (target / n).is_file()},
            "Bundle manifest incomplete",
        )


def source_snapshot(repo: Path, sha: str, target: Path) -> None:
    run(["git", "fetch", "--no-tags", "origin", sha], cwd=repo, timeout=180)
    require(
        run(["git", "rev-parse", "FETCH_HEAD"], cwd=repo) == sha,
        "Fetched SHA differs from selected default HEAD",
    )
    archive = target.parent / "source.tar.gz"
    with archive.open("wb") as output:
        result = subprocess.run(
            ["git", "archive", "--format=tar.gz", sha],
            cwd=repo,
            stdout=output,
            timeout=120,
            check=False,
        )
    require(result.returncode == 0, "Unable to archive pinned source")
    extract(archive, target)
    require(
        sha256(target / "deploy/release.py") == sha256(Path(__file__)),
        "Cloud Shell script differs from remote default; refresh checkout",
    )


def allowed_source(path: Path) -> bool:
    name = path.as_posix()
    return (
        name == "pyproject.toml"
        or name == "README.md"
        or (
            name.startswith("src/py_st/")
            and path.suffix
            in {".py", ".json", ".html", ".js", ".css", ".md", ".typed"}
        )
        or name
        in {
            "deploy/release.py",
            "deploy/requirements-py312.lock",
            "deploy/py-st-dashboard.service",
            "deploy/py-st-worker.service",
            "deploy/Caddyfile",
            "deploy/hosted.env.example",
            "docs/HOSTED_OPERATIONS.md",
        }
    )


def check_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        require(
            any(n.endswith("/services/dashboard.html") for n in names),
            "Wheel lacks dashboard HTML",
        )
        require(
            any(n.endswith("/services/ui/shell.js") for n in names),
            "Wheel lacks generated UI JavaScript",
        )
        require(
            any(n.endswith("/services/ui/shell.css") for n in names),
            "Wheel lacks generated UI CSS",
        )


def build(repo: Path, branch: str, sha: str, destination: Path) -> Path:
    scratch = repo / ".cache/nightly"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fos101-", dir=scratch) as tmp:
        temp = Path(tmp)
        source = temp / "source"
        source.mkdir()
        source_snapshot(repo, sha, source)
        wheels = temp / "wheels"
        wheels.mkdir()
        lock = source / "deploy/requirements-py312.lock"
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "-r",
                str(lock),
                "-d",
                str(wheels),
            ],
            timeout=300,
        )
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                str(source),
                "-w",
                str(wheels),
            ],
            timeout=300,
        )
        project_wheels = list(wheels.glob("py_st-*.whl"))
        require(len(project_wheels) == 1, "Expected exactly one py-st wheel")
        check_wheel(project_wheels[0])
        venv = temp / "verify"
        run([sys.executable, "-m", "venv", str(venv)])
        python = str(venv / "bin/python")
        run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(wheels),
                "-r",
                str(lock),
                "py-st",
            ],
            timeout=180,
        )
        run([python, "-m", "pip", "check"])
        run([python, "-m", "py_st", "flight", "serve", "--help"])
        run([python, "-m", "py_st", "flight", "inspect-state", "--help"])

        payload = temp / "payload"
        payload.mkdir()
        for item in source.rglob("*"):
            rel = item.relative_to(source)
            if item.is_file() and allowed_source(rel):
                out = payload / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, out)
        shutil.copytree(wheels, payload / "wheels")
        files = {
            p.relative_to(payload).as_posix(): sha256(p)
            for p in payload.rglob("*")
            if p.is_file()
        }
        manifest: dict[str, Any] = {
            "version": VERSION,
            "branch": branch,
            "sha": sha,
            "python": platform.python_version(),
            "platform": "linux-x86_64",
            "files": files,
        }
        (payload / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True) + "\n"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(".partial")
        try:
            with tarfile.open(partial, "w:gz") as archive:
                for item in sorted(payload.rglob("*")):
                    archive.add(
                        item,
                        arcname=item.relative_to(payload),
                        recursive=False,
                    )
            os.replace(partial, destination)
        finally:
            partial.unlink(missing_ok=True)
    return destination


def manifest_from(path: Path) -> dict[str, Any]:
    with tarfile.open(path, "r:gz") as archive:
        candidates = archive.getmembers()
        matches = [
            m for m in candidates if m.name == "manifest.json" and m.isfile()
        ]
        require(
            len(matches) == 1 and matches[0].size < 2_000_000,
            "Missing or oversized manifest",
        )
        data = archive.extractfile(matches[0])
        require(data is not None, "Unreadable manifest")
        assert data is not None
        try:
            manifest = json.load(data)
        except (ValueError, UnicodeError) as exc:
            raise ReleaseError("Malformed bundle manifest") from exc
    require(
        isinstance(manifest, dict)
        and manifest.get("version") == VERSION
        and isinstance(manifest.get("sha"), str)
        and SHA.fullmatch(manifest["sha"]) is not None
        and manifest.get("platform") == "linux-x86_64"
        and isinstance(manifest.get("branch"), str)
        and re.fullmatch(r"[A-Za-z0-9._/-]+", manifest["branch"]) is not None
        and isinstance(manifest.get("python"), str)
        and manifest["python"].startswith("3.12.")
        and isinstance(manifest.get("files"), dict)
        and all(
            isinstance(k, str)
            and safe_name(k)
            and (
                allowed_source(Path(k))
                or (k.startswith("wheels/") and k.endswith(".whl"))
            )
            and isinstance(v, str)
            and DIGEST.fullmatch(v) is not None
            for k, v in manifest["files"].items()
        ),
        "Invalid bundle manifest",
    )
    assert isinstance(manifest, dict)
    return manifest


def verify_archive(path: Path, manifest: dict[str, Any]) -> None:
    """Validate every member and digest before touching a release directory."""
    files = manifest["files"]
    seen: set[str] = set()
    total = 0
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            require(
                safe_name(name) and name not in seen,
                "Unsafe or duplicate archive member",
            )
            seen.add(name)
            require(
                member.isdir() or member.isfile(),
                "Archive has a symlink or special file",
            )
            if member.isdir():
                continue
            require(
                name == "manifest.json" or name in files,
                "Unexpected archive member",
            )
            total += member.size
            require(total < 1024**3, "Bundle expands beyond 1 GiB")
            if name != "manifest.json":
                source = archive.extractfile(member)
                require(source is not None, "Unreadable archive member")
                assert source is not None
                digest = hashlib.sha256()
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                require(
                    digest.hexdigest() == files[name],
                    "Bundle member digest mismatch",
                )
    require(
        {n for n in seen if n == "manifest.json" or n in files}
        == set(files) | {"manifest.json"},
        "Bundle manifest incomplete",
    )


def gcloud(
    project: str, zone: str, instance: str, *args: str, timeout: int = 180
) -> str:
    return run(
        [
            "gcloud",
            "compute",
            *args,
            "--project",
            project,
            "--zone",
            zone,
            "--tunnel-through-iap",
        ],
        timeout=timeout,
    )


def remote_command(
    project: str, zone: str, instance: str, command: str
) -> str:
    return gcloud(
        project, zone, instance, "ssh", instance, "--command", command
    )


def transfer(
    bundle: Path, digest: str, project: str, zone: str, instance: str
) -> None:
    home = remote_command(project, zone, instance, "printf '%s' \"$HOME\"")
    require(
        re.fullmatch(r"/(?:[A-Za-z0-9_.+-]+/?)+", home) is not None,
        "VM home path unsupported for gcloud scp; inspect account path",
    )
    manifest = manifest_from(bundle)
    stage = f"{home}/.local/share/py-st-deploy/incoming/{manifest['sha']}"
    script = Path(__file__).resolve()
    mkdir = f"umask 077; mkdir -p {shlex.quote(stage)}"
    remote_command(project, zone, instance, mkdir)
    local_paths = (bundle, script)
    for local in local_paths:
        gcloud(
            project,
            zone,
            instance,
            "scp",
            str(local),
            f"{instance}:{stage}/{local.name}.partial",
            timeout=300,
        )
    remote_command(
        project,
        zone,
        instance,
        " && ".join(
            f"mv {shlex.quote(stage+'/'+p.name+'.partial')} "
            f"{shlex.quote(stage+'/'+p.name)}"
            for p in local_paths
        ),
    )
    command = [
        "sudo",
        "python3.12",
        f"{stage}/{script.name}",
        "deploy",
        "--bundle",
        f"{stage}/{bundle.name}",
        "--sha256",
        digest,
    ]
    print("VM activation command: " + shlex.join(command))
    print(
        "VM status command: "
        + shlex.join(
            ["sudo", "python3.12", f"{stage}/{script.name}", "status"]
        )
    )


def prepare(args: argparse.Namespace) -> None:
    require(os.geteuid() != 0, "Run prepare without sudo")
    repo = Path(__file__).resolve().parent.parent
    branch, sha = default_head(repo)
    destination = repo / ".cache/nightly/releases" / sha / "release.tar.gz"
    if destination.exists():
        manifest = manifest_from(destination)
        verify_archive(destination, manifest)
        require(
            manifest["sha"] == sha and manifest["branch"] == branch,
            "Cached bundle mismatch; inspect/remove it and retry",
        )
    else:
        build(repo, branch, sha, destination)
    digest = sha256(destination)
    print(f"Prepared {branch} {sha} SHA256 {digest}: {destination}")
    if args.prepare_only:
        print(
            "Transfer retry: "
            + shlex.join(
                [
                    "python3.12",
                    str(Path(__file__).resolve()),
                    "transfer",
                    "--bundle",
                    str(destination),
                    "--sha256",
                    digest,
                    "--project",
                    args.project,
                    "--zone",
                    args.zone,
                    "--instance",
                    args.instance,
                ]
            )
        )
    else:
        try:
            transfer(
                destination, digest, args.project, args.zone, args.instance
            )
        except ReleaseError:
            print(
                "Transfer retry: "
                + shlex.join(
                    [
                        "python3.12",
                        str(Path(__file__).resolve()),
                        "transfer",
                        "--bundle",
                        str(destination),
                        "--sha256",
                        digest,
                        "--project",
                        args.project,
                        "--zone",
                        args.zone,
                        "--instance",
                        args.instance,
                    ]
                )
            )
            raise


def services() -> dict[str, str]:
    return {
        name: run(
            ["systemctl", "show", name, "--property=ActiveState", "--value"],
            timeout=15,
        )
        for name in SERVICES
    }


def current_sha() -> str | None:
    link = BASE / "current"
    if not link.is_symlink():
        return None
    target = link.resolve()
    return (
        target.name
        if target.parent == BASE / "releases" and SHA.fullmatch(target.name)
        else None
    )


def state_summary() -> dict[str, Any]:
    """Read only and minimal; validation belongs to the application probe."""
    summary: dict[str, Any] = {
        "stop": os.path.lexists(ROOT / "STOP"),
        "handoff": os.path.lexists(ROOT / "HANDOFF_REQUIRED"),
    }
    try:
        db = ROOT / ".state/flight.sqlite3"
        with sqlite3.connect(
            db.as_uri() + "?mode=ro", uri=True, timeout=2
        ) as connection:
            row = connection.execute(
                "SELECT paused, heartbeat, worker_state FROM settings "
                "WHERE id=1"
            ).fetchone()
            if row:
                summary.update(
                    paused=bool(row[0]), heartbeat=row[1], worker_state=row[2]
                )
            rows = connection.execute(
                "SELECT status, COUNT(*) FROM commands GROUP BY status"
            )
            counts = dict(rows)
            summary["queued"] = counts.get("queued", 0)
            summary["uncertain"] = sum(
                counts.get(n, 0)
                for n in (
                    "running",
                    "dispatching",
                    "in_transit",
                    "reconciliation_required",
                )
            )
    except (OSError, sqlite3.Error):
        summary["state"] = "unavailable"
    return summary


def observation() -> dict[str, Any]:
    result: dict[str, Any] = {"current_sha": current_sha()}
    try:
        result["services"] = services()
    except ReleaseError:
        result["services"] = {name: "unknown" for name in SERVICES}
    result["state"] = state_summary()
    return result


def save_receipt(receipt: dict[str, Any]) -> None:
    OPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = OPS / "receipt.json"
    receipt["updated_at"] = datetime.now(UTC).isoformat()
    receipt["observed"] = observation()
    fd, name = tempfile.mkstemp(dir=OPS, prefix="receipt.")
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(receipt, output, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
        directory = os.open(OPS, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def last_receipt() -> dict[str, Any] | None:
    path = OPS / "receipt.json"
    return json.loads(path.read_text()) if path.exists() else None


def status(json_output: bool) -> None:
    last = last_receipt()
    observed = observation()
    if json_output:
        print(
            json.dumps(
                {
                    "receipt": last,
                    "observed": observed,
                    "receipt_path": str(OPS / "receipt.json"),
                },
                sort_keys=True,
                indent=2,
            )
        )
    else:
        print(
            f"Current: {observed['current_sha']}; "
            f"services: {observed['services']}; "
            f"state: {observed['state']}"
        )
        print(
            f"Last receipt: {last.get('result') if last else 'none'} "
            f"({OPS / 'receipt.json'})"
        )


def unit_checks() -> None:
    for unit in SERVICES:
        expected = {
            "User": USER,
            "Group": USER,
            "WorkingDirectory": str(ROOT),
        }
        for field, value in expected.items():
            actual = run(
                ["systemctl", "show", unit, f"--property={field}", "--value"],
                timeout=15,
            )
            require(
                actual == value,
                f"{unit} {field} differs; inspect unit/drop-ins manually",
            )
        command = run(
            ["systemctl", "show", unit, "--property=ExecStart", "--value"],
            timeout=15,
        )
        expected_command = (
            "flight serve" if "dashboard" in unit else "flight worker"
        )
        require(
            str(BASE / "current/.venv/bin/python") in command
            and expected_command in command,
            f"{unit} ExecStart differs; inspect unit/drop-ins manually",
        )
        environment = run(
            ["systemctl", "show", unit, "--property=Environment", "--value"],
            timeout=15,
        )
        require(
            f"ST_STATE_ROOT={ROOT}" in environment,
            f"{unit} state-root environment differs; inspect unit/drop-ins",
        )
        if "dashboard" in unit:
            files = run(
                [
                    "systemctl",
                    "show",
                    unit,
                    "--property=EnvironmentFiles",
                    "--value",
                ],
                timeout=15,
            )
            require(
                str(HOSTED_ENV) in files,
                f"{unit} hosted environment file differs; inspect unit",
            )


def config() -> tuple[str, int]:
    path = HOSTED_ENV
    require(
        path.is_file() and not path.is_symlink(),
        "Missing hosted.env; inspect non-secret host configuration",
    )
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(
            separator == "="
            and key in {"ST_PUBLIC_ORIGIN", "PY_ST_BACKEND_PORT"}
            and key not in values,
            "Unexpected hosted.env field",
        )
        values[key] = value
    origin = values.get("ST_PUBLIC_ORIGIN", "")
    parsed = urlsplit(origin)
    require(
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and not parsed.username
        and not parsed.password,
        "Invalid ST_PUBLIC_ORIGIN in hosted.env",
    )
    port = values.get("PY_ST_BACKEND_PORT", "")
    require(
        port.isdecimal() and 1 <= int(port) <= 65535,
        "Invalid PY_ST_BACKEND_PORT in hosted.env",
    )
    return origin, int(port)


def preflight(bundle: Path, digest: str) -> tuple[dict[str, Any], str]:
    require(
        bundle.is_absolute() and bundle.is_file() and not bundle.is_symlink(),
        "Bundle must be an absolute regular file",
    )
    require(
        DIGEST.fullmatch(digest) is not None and sha256(bundle) == digest,
        "Bundle SHA256 mismatch; retransfer pinned artifact",
    )
    manifest = manifest_from(bundle)
    verify_archive(bundle, manifest)
    require(
        manifest["files"].get("deploy/release.py")
        == sha256(Path(__file__).resolve()),
        "Transferred entrypoint differs from bundle; retransfer same release",
    )
    require(
        (
            DATA.is_dir()
            and os.path.ismount(DATA)
            and ROOT.is_dir()
            and ROOT.resolve() == ROOT
        ),
        "Data mount/root differs; inspect /srv/py-st and fstab",
    )
    require(
        all(
            directory.is_dir()
            and directory.stat().st_uid == 0
            and not directory.stat().st_mode & 0o022
            for directory in (BASE, BASE / "releases")
        ),
        "Release directories must be administrator-owned and not writable "
        "by the runtime user; inspect /opt/py-st ownership",
    )
    import pwd

    uid = pwd.getpwnam(USER).pw_uid
    require(
        ROOT.stat().st_uid == uid,
        "State root owner differs; inspect ownership",
    )
    private = ROOT / ".env"
    require(
        private.is_file()
        and not private.is_symlink()
        and private.stat().st_uid == uid,
        "Private state credential missing or owner differs",
    )
    require(
        WORKER_GATE.is_file() and not (ROOT / "HANDOFF_REQUIRED").exists(),
        "Worker authority gate differs; inspect worker-armed/HANDOFF_REQUIRED",
    )
    prior = current_sha()
    require(
        prior is not None and (BASE / "current").is_symlink(),
        "Current symlink is not a versioned release; inspect manually",
    )
    assert prior is not None
    require(
        (BASE / "releases" / prior / ".venv/bin/python").is_file(),
        "Prior release interpreter missing; inspect manually",
    )
    unit_checks()
    config()
    gate = state_summary()
    require(
        gate.get("state") != "unavailable" and "paused" in gate,
        "Managed state unavailable; inspect initialized root, do not setup",
    )
    require(
        bool(gate.get("stop") and gate.get("paused")),
        "Pause in Operations, then rerun this same command",
    )
    require(
        all(v == "active" for v in services().values()),
        "Both services must be active before activation; inspect status",
    )
    free_release = shutil.disk_usage(BASE).free
    free_data = shutil.disk_usage(DATA).free
    state_size = sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file())
    require(
        free_release > bundle.stat().st_size * 3 + 256 * 1024**2
        and free_data > state_size * 2 + 64 * 1024**2,
        "Insufficient release/checkpoint space; free disk and retry",
    )
    return manifest, prior


def inspect(python: Path) -> dict[str, Any]:
    output = run(
        [
            "runuser",
            "-u",
            USER,
            "--",
            "env",
            f"ST_STATE_ROOT={ROOT}",
            str(python),
            "-m",
            "py_st",
            "flight",
            "inspect-state",
        ],
        cwd=ROOT,
        timeout=40,
    )
    try:
        data: dict[str, Any] = json.loads(output)
        require(
            data["stop"] and data["paused"],
            "State is not paused with STOP; pause in Operations",
        )
        return data
    except (ValueError, KeyError, TypeError) as exc:
        raise ReleaseError(
            "New-code state compatibility inspection failed"
        ) from exc


def stage(bundle: Path, manifest: dict[str, Any], digest: str) -> Path:
    sha = str(manifest["sha"])
    final = BASE / "releases" / sha
    marker = final / ".release.json"
    if final.exists():
        require(
            marker.is_file(),
            f"Partial release {final}; inspect it before removing manually",
        )
        record = json.loads(marker.read_text())
        require(
            record == {"sha": sha, "digest": digest},
            f"Existing release {final} differs; inspect manually",
        )
        inspect(final / ".venv/bin/python")
        return final
    final.mkdir(parents=True, mode=0o755)
    # Extract into the final path: virtual environments embed this exact path.
    expected = dict(manifest["files"])
    expected["manifest.json"] = sha256_manifest(bundle)
    extract(bundle, final, files=expected)
    python = final / ".venv/bin/python"
    run([sys.executable, "-m", "venv", str(final / ".venv")], timeout=90)
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(final / "wheels"),
            "-r",
            str(final / "deploy/requirements-py312.lock"),
            "py-st",
        ],
        timeout=180,
    )
    run([str(python), "-m", "pip", "check"])
    run([str(python), "-m", "py_st", "flight", "inspect-state", "--help"])
    inspect(python)
    marker.write_text(json.dumps({"sha": sha, "digest": digest}) + "\n")
    marker.chmod(0o644)
    return final


def sha256_manifest(bundle: Path) -> str:
    with tarfile.open(bundle, "r:gz") as archive:
        member = archive.getmember("manifest.json")
        source = archive.extractfile(member)
        require(source is not None, "Unreadable manifest")
        assert source is not None
        return hashlib.sha256(source.read()).hexdigest()


def stop_services() -> None:
    for service in SERVICES:
        run(["systemctl", "stop", service], timeout=65)
    require(
        all(value == "inactive" for value in services().values()),
        "Service still active; inspect processes and leases before restart",
    )


def checkpoint(previous: str, run_id: str) -> Path:
    parent = DATA / "checkpoints"
    parent.mkdir(mode=0o700, exist_ok=True)
    import pwd

    uid = pwd.getpwnam(USER).pw_uid
    if parent.stat().st_uid == 0:
        os.chown(parent, uid, uid)
    require(
        parent.stat().st_uid == uid and parent.stat().st_mode & 0o077 == 0,
        "Checkpoint parent owner/mode differs; inspect manually",
    )
    target = parent / f"{previous}-{run_id}"
    run(
        [
            "runuser",
            "-u",
            USER,
            "--",
            "env",
            f"ST_STATE_ROOT={ROOT}",
            str(BASE / "releases" / previous / ".venv/bin/python"),
            "-m",
            "py_st",
            "flight",
            "checkpoint",
            str(target),
        ],
        cwd=ROOT,
        timeout=180,
    )
    require(
        target.is_dir() and (target / "checkpoint.json").is_file(),
        "Checkpoint incomplete; inspect private checkpoint directory",
    )
    return target


def switch(target: Path) -> None:
    link = BASE / f".current-{uuid.uuid4().hex}"
    try:
        link.symlink_to(target)
        os.replace(link, BASE / "current")
    finally:
        link.unlink(missing_ok=True)


def start_services() -> None:
    for service in SERVICES:
        run(["systemctl", "start", service], timeout=45)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if all(state == "active" for state in services().values()):
            return
        time.sleep(1)
    raise ReleaseError(
        "Service not active; inspect systemctl status and "
        "worker ConditionPath/Restart result"
    )


def fresh_heartbeat(started: datetime) -> dict[str, Any]:
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        require(
            all(s == "active" for s in services().values()),
            "Service exited/restarted; inspect systemctl status",
        )
        data = inspect(BASE / "current/.venv/bin/python")
        stamp = data.get("heartbeat")
        if (
            stamp
            and datetime.fromisoformat(stamp) > started
            and (data.get("worker_state") == "paused")
        ):
            return data
        time.sleep(2)
    raise ReleaseError(
        "No new paused worker heartbeat after start; "
        "inspect worker ConditionPath and journal"
    )


def probe(origin: str, port: int) -> None:
    authority = urlsplit(origin).netloc
    for url, host, label in (
        (f"http://127.0.0.1:{port}/", authority, "loopback"),
        (origin + "/", None, "public HTTPS"),
    ):
        request = urllib.request.Request(
            url, headers={"Host": host} if host else {}
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                require(
                    response.status == 200,
                    f"{label} shell returned HTTP {response.status}",
                )
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ReleaseError(
                f"{label} shell unreachable; inspect "
                "proxy/DNS/TLS independently"
            ) from exc


def interrupted(_signum: int, _frame: Any) -> None:
    raise ReleaseError(
        "Interrupted; run status and inspect receipt before retry"
    )


def deploy(bundle: Path, digest: str) -> None:
    require(os.geteuid() == 0, "Run VM deploy with sudo")
    os.umask(0o022)
    OPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(
        OPS.stat().st_uid == 0 and OPS.stat().st_mode & 0o077 == 0,
        "Operations directory ownership/mode differs; inspect manually",
    )
    with (OPS / "deploy.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReleaseError(
                "Another deployment holds the host lock"
            ) from exc
        prior_receipt = last_receipt()
        if (
            prior_receipt
            and prior_receipt.get("result") == "incomplete"
            and (
                prior_receipt.get("phase")
                in {
                    "stop",
                    "checkpoint",
                    "compatibility",
                    "switch",
                    "start",
                    "heartbeat",
                    "http",
                }
            )
        ):
            raise ReleaseError(
                "Prior activation incomplete; run status, "
                "inspect services/checkpoint, then recover manually"
            )
        manifest = manifest_from(bundle)
        sha = manifest["sha"]
        require(
            manifest["files"].get("deploy/release.py")
            == sha256(Path(__file__).resolve()),
            "Transferred entrypoint differs from bundle; retransfer",
        )
        if (
            current_sha() == sha
            and prior_receipt
            and (
                prior_receipt.get("result") == "success"
                and prior_receipt.get("bundle_digest") == digest
            )
        ):
            final = BASE / "releases" / sha
            require(
                json.loads((final / ".release.json").read_text())
                == {"sha": sha, "digest": digest},
                "Release marker differs; inspect installed release",
            )
            require(
                all(s == "active" for s in services().values()),
                "Installed release has inactive service; inspect status",
            )
            require(
                state_summary().get("heartbeat") is not None,
                "Installed release has no heartbeat; inspect status",
            )
            print(f"Already deployed {sha}; no service change")
            return
        receipt: dict[str, Any] = {
            "version": VERSION,
            "run_id": uuid.uuid4().hex,
            "started_at": datetime.now(UTC).isoformat(),
            "phase": "preflight",
            "result": "incomplete",
            "source_branch": manifest.get("branch"),
            "source_sha": sha,
            "previous_sha": current_sha(),
            "bundle_digest": digest,
            "checkpoint": None,
            "error_category": None,
        }
        previous_handler = signal.signal(signal.SIGTERM, interrupted)
        previous_interrupt = signal.signal(signal.SIGINT, interrupted)
        try:
            save_receipt(receipt)
            verified, previous = preflight(bundle, digest)
            require(
                verified == manifest,
                "Bundle manifest changed during preflight",
            )
            receipt["previous_sha"] = previous
            receipt["phase"] = "stage"
            save_receipt(receipt)
            target = stage(bundle, manifest, digest)
            # Recheck the application gate just before downtime.
            inspect(target / ".venv/bin/python")
            require(
                all(s == "active" for s in services().values()),
                "Service state changed before downtime; inspect status",
            )
            receipt["phase"] = "stop"
            save_receipt(receipt)
            stop_services()
            receipt["phase"] = "checkpoint"
            save_receipt(receipt)
            receipt["checkpoint"] = str(
                DATA / "checkpoints" / f"{previous}-{receipt['run_id']}"
            )
            save_receipt(receipt)
            checkpoint_path = checkpoint(previous, receipt["run_id"])
            receipt["phase"] = "compatibility"
            save_receipt(receipt)
            inspect(target / ".venv/bin/python")
            receipt["phase"] = "switch"
            save_receipt(receipt)
            switch(target)
            receipt["phase"] = "start"
            save_receipt(receipt)
            start_time = datetime.now(UTC)
            start_services()
            receipt["phase"] = "heartbeat"
            save_receipt(receipt)
            fresh_heartbeat(start_time)
            receipt["phase"] = "http"
            save_receipt(receipt)
            origin, port = config()
            probe(origin, port)
            receipt["phase"] = "complete"
            receipt["result"] = "success"
            save_receipt(receipt)
            print(
                f"Deployed {sha} from {previous}; checkpoint {checkpoint_path}"
            )
            status(False)
            print(
                "Log in again; verify Explorer destination → detail → "
                "preview; resume deliberately when ready."
            )
        except (ReleaseError, OSError, ValueError, KeyboardInterrupt) as exc:
            receipt["error_category"] = type(exc).__name__
            save_receipt(receipt)
            reason = (
                str(exc)
                if isinstance(exc, ReleaseError)
                else type(exc).__name__
            )
            print(
                f"Incomplete phase={receipt['phase']}: {reason}",
                file=sys.stderr,
            )
            status(False)
            if receipt["phase"] in {"stop", "checkpoint", "compatibility"}:
                print(
                    "If both services are safely stopped and STOP/desired "
                    "pause "
                    "remain, explicitly restart the old release: "
                    "sudo systemctl start py-st-dashboard.service "
                    "py-st-worker.service; verify a fresh paused heartbeat.",
                    file=sys.stderr,
                )
            else:
                print(
                    "Keep STOP; inspect service journal and the private "
                    "checkpoint. Do not restore state automatically.",
                    file=sys.stderr,
                )
            raise ReleaseError(
                "Deployment incomplete; see status above"
            ) from None
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
            signal.signal(signal.SIGINT, previous_interrupt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "transfer"):
        command = sub.add_parser(name)
        command.add_argument("--project", required=True)
        command.add_argument("--zone", required=True)
        command.add_argument("--instance", required=True)
        if name == "prepare":
            command.add_argument("--prepare-only", action="store_true")
        else:
            command.add_argument("--bundle", type=Path, required=True)
            command.add_argument("--sha256", required=True)
    activation = sub.add_parser("deploy")
    activation.add_argument("--bundle", type=Path, required=True)
    activation.add_argument("--sha256", required=True)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        prerequisites()
        if args.command == "prepare":
            prepare(args)
        elif args.command == "transfer":
            require(
                args.bundle.is_file() and sha256(args.bundle) == args.sha256,
                "Retry artifact digest mismatch",
            )
            transfer(
                args.bundle,
                args.sha256,
                args.project,
                args.zone,
                args.instance,
            )
        elif args.command == "deploy":
            deploy(args.bundle, args.sha256)
        else:
            require(os.geteuid() == 0, "Run status with sudo")
            status(args.json)
    except ReleaseError as exc:
        print(f"Release error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
