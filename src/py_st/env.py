"""Utility functions for managing environment variables."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import dotenv_values, set_key


def save_agent_token(token: str) -> None:
    """Atomically replace ST_TOKEN in the working directory's private .env.

    A failed write leaves the previous file intact. Never update the process
    environment: other processes must be restarted deliberately by the owner.
    """
    if not token.strip():
        raise ValueError("Cannot save an empty agent token")
    env_path = Path.cwd() / ".env"
    original = (
        env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    )
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=env_path.parent, delete=False
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
    token = dotenv_values(Path.cwd() / ".env", interpolate=False).get(
        "ST_TOKEN"
    )
    if not token:
        raise ValueError("No saved ST_TOKEN in the working directory's .env")
    return token
