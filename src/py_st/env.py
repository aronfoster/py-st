"""Utility functions for managing environment variables."""

from __future__ import annotations

from pathlib import Path

from dotenv import find_dotenv, set_key


def save_agent_token(token: str) -> None:
    """
    Save the agent token to the .env file.

    Args:
        token: The agent token to save.
    """
    env_file = find_dotenv()
    if not env_file:
        env_file = ".env"

    env_path = Path(env_file)
    set_key(env_path, "ST_TOKEN", token)
