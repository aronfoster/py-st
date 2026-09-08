"""
Utility functions for loading and saving data to a simple
JSON-based file cache.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, cast

CACHE_DIR = Path(os.environ.get("ST_CACHE_DIR", ".cache"))
CACHE_FILE = CACHE_DIR / "data.json"


def load_cache() -> dict[str, Any]:
    """Load cache data from the JSON file.

    Returns:
        dict[str, Any]: The cached data, or an empty dictionary
            if the cache doesn't exist or fails to load.
    """
    if not CACHE_FILE.exists():
        return {}

    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Cache root must be an object")
            return cast(dict[str, Any], data)
    except (ValueError, OSError) as e:
        logging.warning("Failed to load cache: %s", e)
        return {}


def save_cache(data: dict[str, Any]) -> None:
    """Save data to the JSON cache file.

    Args:
        data: The dictionary to save to the cache.
    """
    try:
        # Ensure cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Serialize to JSON with pretty formatting
        json_data = json.dumps(data, indent=2, default=str)

        # Replace on the same filesystem so readers never see partial JSON.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CACHE_DIR, delete=False
        ) as f:
            temporary = Path(f.name)
            try:
                f.write(json_data)
                f.flush()
                os.fsync(f.fileno())
                os.replace(temporary, CACHE_FILE)
            finally:
                temporary.unlink(missing_ok=True)
    except (TypeError, OSError) as e:
        logging.error("Failed to save cache: %s", e)


def clear_cache() -> None:
    """Remove the cache file if it exists."""
    if CACHE_FILE.exists():
        try:
            CACHE_FILE.unlink()
        except OSError as e:
            logging.error("Failed to clear cache: %s", e)
