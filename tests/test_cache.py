"""Unit tests for the cache module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from py_st import cache
from tests.factories import CacheFactory


@pytest.fixture
def mock_cache_paths(tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary cache directory and file paths."""
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "data.json"
    return cache_dir, cache_file


def test_load_cache_file_not_found(tmp_path: Path) -> None:
    """Test load_cache returns {} when file doesn't exist."""
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "data.json"

    with (
        patch.object(cache, "CACHE_DIR", cache_dir),
        patch.object(cache, "CACHE_FILE", cache_file),
    ):
        result = cache.load_cache()
        assert result == {}


def test_load_cache_invalid_json(tmp_path: Path) -> None:
    """Test load_cache returns {} for invalid JSON."""
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "data.json"
    cache_dir.mkdir(parents=True)

    invalid_json = CacheFactory.build_invalid_json_string()
    cache_file.write_text(invalid_json)

    with (
        patch.object(cache, "CACHE_DIR", cache_dir),
        patch.object(cache, "CACHE_FILE", cache_file),
    ):
        result = cache.load_cache()
        assert result == {}


def test_load_cache_success(tmp_path: Path) -> None:
    """Test load_cache successfully loads valid cache data."""
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "data.json"
    cache_dir.mkdir(parents=True)

    valid_data = CacheFactory.build_valid_cache_data()
    cache_file.write_text(json.dumps(valid_data))

    with (
        patch.object(cache, "CACHE_DIR", cache_dir),
        patch.object(cache, "CACHE_FILE", cache_file),
    ):
        result = cache.load_cache()
        assert result == valid_data


def test_save_cache_creates_directory_and_file(
    tmp_path: Path,
) -> None:
    """Test save_cache creates directory and file."""
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "data.json"

    test_data = CacheFactory.build_valid_cache_data()

    with (
        patch.object(cache, "CACHE_DIR", cache_dir),
        patch.object(cache, "CACHE_FILE", cache_file),
    ):
        cache.save_cache(test_data)

        assert cache_dir.exists()
        assert cache_dir.is_dir()
        assert cache_file.exists()
        assert cache_file.is_file()


def test_save_cache_writes_correct_content(tmp_path: Path) -> None:
    """Test save_cache writes correct JSON content."""
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "data.json"

    test_data = CacheFactory.build_valid_cache_data()

    with (
        patch.object(cache, "CACHE_DIR", cache_dir),
        patch.object(cache, "CACHE_FILE", cache_file),
    ):
        cache.save_cache(test_data)

        loaded_data = json.loads(cache_file.read_text())
        assert loaded_data == test_data


def test_save_cache_overwrites_existing_content(
    tmp_path: Path,
) -> None:
    """Test save_cache overwrites existing data."""
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "data.json"

    data_a = CacheFactory.build_valid_cache_data()
    data_b = {"new": "data"}

    with (
        patch.object(cache, "CACHE_DIR", cache_dir),
        patch.object(cache, "CACHE_FILE", cache_file),
    ):
        cache.save_cache(data_a)
        cache.save_cache(data_b)

        result = cache.load_cache()
        assert result == data_b


def test_save_cache_handles_datetime(tmp_path: Path) -> None:
    """Test save_cache handles datetime objects by converting
    to string."""
    cache_dir = tmp_path / ".cache"
    cache_file = cache_dir / "data.json"

    datetime_data = CacheFactory.build_data_with_datetime()

    with (
        patch.object(cache, "CACHE_DIR", cache_dir),
        patch.object(cache, "CACHE_FILE", cache_file),
    ):
        cache.save_cache(datetime_data)

        assert cache_file.exists()

        loaded_data = json.loads(cache_file.read_text())
        assert "timestamp" in loaded_data
        assert isinstance(loaded_data["timestamp"], str)
