"""Utility functions for managing environment variables."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import dotenv_values, set_key


def registration_env_path() -> Path:
    """Require the worker's configured root to match registration's cwd."""
    env_path = Path.cwd() / ".env"
    root_value = os.environ.get("ST_STATE_ROOT")
    if root_value is None:
        try:
            root_value = dotenv_values(env_path).get("ST_STATE_ROOT")
        except (OSError, ValueError):
            raise ValueError(
                "Cannot read the working directory's .env. Fix its encoding "
                "or permissions; no request was sent."
            ) from None
    if root_value is not None:
        try:
            root = Path(root_value)
            if (
                not root.is_absolute()
                or root.resolve(strict=True) != Path.cwd()
            ):
                raise ValueError
        except (OSError, ValueError, RuntimeError):
            raise ValueError(
                "Registration requires the working directory to match "
                "the absolute ST_STATE_ROOT. Run from the configured "
                "worker root; no request was sent."
            ) from None
    return env_path


def save_agent_token(token: str) -> None:
    """Atomically replace ST_TOKEN in the working directory's private .env.

    A failed write leaves the previous file intact. Never update the process
    environment: other processes must be restarted deliberately by the owner.
    """
    if not token.strip():
        raise ValueError("Cannot save an empty agent token")
    env_path = registration_env_path()
    original = (
        env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    )
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=env_path.parent,
        prefix="tmp.registration-",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(original, encoding="utf-8")
        success, _, _ = set_key(temporary, "ST_TOKEN", token)
        if not success:
            raise OSError("Token persistence failed")
        temporary.chmod(0o600)
        with temporary.open("rb") as stream_read:
            os.fsync(stream_read.fileno())
        os.replace(temporary, env_path)
    finally:
        temporary.unlink(missing_ok=True)


def saved_agent_token() -> str:
    """Read the local saved credential, ignoring environment overrides."""
    token = dotenv_values(registration_env_path(), interpolate=False).get(
        "ST_TOKEN"
    )
    if not token:
        raise ValueError("No saved ST_TOKEN in the working directory's .env")
    return token
