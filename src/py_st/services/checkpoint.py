"""Private, quiesced full-state checkpoints; never an authority transfer."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from py_st.services.flight_auth import validate_owner
from py_st.services.flight_queue import FlightQueue
from py_st.services.intelligence import Intelligence
from py_st.services.state_lease import StateLease
from py_st.services.stop_control import request_stop, stop_requested

DATABASES = ("flight.sqlite3", "intelligence.sqlite3")


def code_identity() -> str:
    """Restore with matching Python sources AND shipped frontend assets."""
    base = Path(__file__).parent.parent
    digest = hashlib.sha256()
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".html", ".js", ".css"}:
            name = path.relative_to(base).as_posix().encode()
            content = path.read_bytes()
            digest.update(len(name).to_bytes(8, "big"))
            digest.update(name)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    return digest.hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def files(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Checkpoint refuses symlinks and special files")
        if path.is_file() and path != root / "checkpoint.json":
            result[str(path.relative_to(root))] = file_hash(path)
    return result


def sync_tree(root: Path) -> None:
    for path in [*root.rglob("*"), root]:
        if path.is_file() or path.is_dir():
            fd = os.open(path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def validate_state(root: Path) -> dict[str, Any]:
    validate_owner(root)
    queue = FlightQueue(root, _checkpoint=True)
    try:
        store = Intelligence(
            root / ".state/intelligence.sqlite3", existing_only=True
        )
        try:
            if queue.scope not in store.scopes():
                raise ValueError("Managed scope missing from ledger")
            for db in (queue.db, store.db):
                rows = db.execute("PRAGMA integrity_check").fetchall()
                if len(rows) != 1 or rows[0][0] != "ok":
                    raise ValueError("SQLite integrity check failed")
            if queue.settings["mode"] == "demo":
                remote = sqlite3.connect(
                    (root / ".state/remote.sqlite3").as_uri() + "?mode=ro",
                    uri=True,
                )
                try:
                    world = json.loads(
                        remote.execute("SELECT data FROM world").fetchone()[0]
                    )
                    if not isinstance(world, dict):
                        raise ValueError("Invalid persistent demo world")
                finally:
                    remote.close()
            return dict(queue.settings)
        finally:
            store.close()
    finally:
        queue.close()


def checkpoint(root: Path, destination: Path) -> None:
    root = root.resolve(strict=True)
    destination = destination.resolve()
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("Checkpoint must be outside the canonical root")
    with StateLease(root, exclusive=True), ExitStack() as stack:
        settings = validate_state(root)
        databases = DATABASES + (
            ("remote.sqlite3",) if settings["mode"] == "demo" else ()
        )
        if not stop_requested(root) or not settings["paused"]:
            raise ValueError("Pause and STOP before checkpointing")
        # Also refuse active SQL writers from older application versions.
        for name in databases:
            db = sqlite3.connect(
                (root / ".state" / name).as_uri() + "?mode=rw",
                uri=True,
                timeout=0,
            )
            stack.callback(db.close)
            db.execute("BEGIN IMMEDIATE")
        destination.mkdir(mode=0o700)
        (destination / ".state").mkdir(mode=0o700)
        # Validate every entry before copying; SQLite sidecars are replaced by
        # complete SQLite backup images while both source DBs are write-locked.
        files(root / ".state")
        for source in (root / ".state").rglob("*"):
            relative = source.relative_to(root)
            target = destination / relative
            if source.is_dir():
                target.mkdir(mode=0o700, exist_ok=True)
            elif source.name not in {
                name + suffix
                for name in databases
                for suffix in ("", "-wal", "-shm", "-journal")
            }:
                shutil.copyfile(source, target)
                target.chmod(0o600)
        for name in databases:
            source_db = sqlite3.connect(
                (root / ".state" / name).as_uri() + "?mode=ro", uri=True
            )
            target_db = sqlite3.connect(destination / ".state" / name)
            try:
                source_db.backup(target_db)
            finally:
                target_db.close()
                source_db.close()
            (destination / ".state" / name).chmod(0o600)
        # Credentials are deliberately recovered through a separate private
        # channel; never copy the live token from canonical-root .env.
        for name in ("STOP", "HANDOFF_REQUIRED"):
            source = root / name
            if source.exists() or source.is_symlink():
                if source.is_symlink() or not source.is_file():
                    raise ValueError("Checkpoint requires regular state files")
                shutil.copyfile(source, destination / name)
                (destination / name).chmod(0o600)
        manifest = {
            "format": 1,
            "code": code_identity(),
            "source_root": str(root),
            "scope": settings["scope"],
            "mode": settings["mode"],
            "files": files(destination),
        }
        sync_tree(destination)
        fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        with (destination / "checkpoint.json").open("x") as output:
            json.dump(manifest, output, sort_keys=True)
        sync_tree(destination)


def restore(source: Path, target: Path) -> None:
    source = source.resolve(strict=True)
    if target.is_symlink():
        raise ValueError("Restore refuses symbolic-link targets")
    target = target.resolve()
    if target.is_mount():
        raise ValueError(
            "Restore target must be a directory beneath the state mount"
        )
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError("Restore target must be separate from checkpoint")
    if target.exists() and any(target.iterdir()):
        raise ValueError("Restore refuses nonempty targets")
    manifest_path = source / "checkpoint.json"
    if manifest_path.is_symlink():
        raise ValueError("Invalid checkpoint manifest")
    manifest = json.loads(manifest_path.read_text())
    if (
        not isinstance(manifest, dict)
        or any(
            not isinstance(manifest.get(key), str) or not manifest[key]
            for key in ("source_root", "scope", "mode")
        )
        or manifest["mode"] not in ("demo", "live")
        or manifest.get("format") != 1
        or manifest.get("code") != code_identity()
        or manifest.get("files") != files(source)
        or "STOP" not in manifest["files"]
        or ".env" in manifest["files"]
        or any(".state/" + name not in manifest["files"] for name in DATABASES)
    ):
        raise ValueError("Incomplete, altered or incompatible checkpoint")
    with tempfile.TemporaryDirectory(
        prefix=".restore-", dir=target.parent
    ) as temporary:
        staging = Path(temporary) / "state"
        staging.mkdir(mode=0o700)
        for name in manifest["files"]:
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid checkpoint path")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(source / relative, destination)
            destination.chmod(0o600)
        db = sqlite3.connect(staging / ".state/flight.sqlite3")
        try:
            row = db.execute("SELECT root,scope,mode FROM settings").fetchone()
            if row != (
                manifest["source_root"],
                manifest["scope"],
                manifest["mode"],
            ):
                raise ValueError("Checkpoint identity mismatch")
            with db:
                db.execute(
                    "UPDATE settings SET root=?, paused=1", (str(staging),)
                )
        finally:
            db.close()
        validate_state(staging)
        request_stop(staging)
        # Live restores are inspection-only until a separate authority review.
        if manifest["mode"] == "live":
            (staging / "HANDOFF_REQUIRED").touch(mode=0o600)
        db = sqlite3.connect(staging / ".state/flight.sqlite3")
        try:
            with db:
                db.execute("UPDATE settings SET root=?", (str(target),))
        finally:
            db.close()
        sync_tree(staging)
        if target.exists():
            target.rmdir()  # Atomic refusal if another actor populated it.
        staging.rename(target)
        fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
