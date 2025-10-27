"""
Utility functions for loading and saving data to a simple
JSON-based file cache.
"""

import json
import logging
from pathlib import Path

# Define cache location inside the src directory
CACHE_DIR = Path(__file__).parent.parent / ".cache"
CACHE_FILE = CACHE_DIR / "data.json"


def load_cache() -> dict:
    """Load cache data from the JSON file.

    Returns:
        dict: The cached data, or an empty dictionary if the
            cache doesn't exist or fails to load.
    """
    if not CACHE_FILE.exists():
        return {}

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logging.warning("Failed to load cache: %s", e)
        return {}


def save_cache(data: dict) -> None:
    """Save data to the JSON cache file.

    Args:
        data: The dictionary to save to the cache.
    """
    try:
        # Ensure cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Serialize to JSON with pretty formatting
        json_data = json.dumps(data, indent=2, default=str)

        # Write to file
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(json_data)
    except (TypeError, OSError) as e:
        logging.error("Failed to save cache: %s", e)
