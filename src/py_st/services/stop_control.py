"""Shared filesystem STOP semantics for live sessions and offline controls."""

from pathlib import Path


def stop_requested(root: Path) -> bool:
    """Any STOP directory entry counts, including a dangling symbolic link."""
    try:
        (root / "STOP").lstat()
    except FileNotFoundError:
        return False
    return True


def request_stop(root: Path) -> None:
    """Create STOP atomically; never follow or modify an existing entry."""
    try:
        with (root / "STOP").open("x"):
            pass
    except FileExistsError:
        pass
