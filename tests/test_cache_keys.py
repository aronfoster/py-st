"""Tests for cache_keys helper functions."""

from __future__ import annotations

import re
from pathlib import Path

from py_st.services.cache_keys import (
    key_for_agent,
    key_for_contract_list,
    key_for_market,
    key_for_ship_list,
    key_for_shipyard,
    key_for_waypoints,
)


def test_key_for_agent() -> None:
    """Test key_for_agent returns correct constant."""
    # Arrange & Act
    result = key_for_agent()

    # Assert
    assert result == "agent_info", "Agent key should be 'agent_info'"


def test_key_for_ship_list() -> None:
    """Test key_for_ship_list returns correct constant."""
    # Arrange & Act
    result = key_for_ship_list()

    # Assert
    assert result == "ship_list", "Ship list key should be 'ship_list'"


def test_key_for_contract_list() -> None:
    """Test key_for_contract_list returns correct constant."""
    # Arrange & Act
    result = key_for_contract_list()

    # Assert
    assert (
        result == "contract_list"
    ), "Contract list key should be 'contract_list'"


def test_key_for_waypoints() -> None:
    """Test key_for_waypoints formats system symbol correctly."""
    # Arrange
    system_symbol = "X1-ABC"

    # Act
    result = key_for_waypoints(system_symbol)

    # Assert
    assert (
        result == "waypoints_X1-ABC"
    ), "Waypoints key should include system symbol"


def test_key_for_waypoints_different_system() -> None:
    """Test key_for_waypoints with different system symbol."""
    # Arrange
    system_symbol = "X1-ZZ9"

    # Act
    result = key_for_waypoints(system_symbol)

    # Assert
    assert (
        result == "waypoints_X1-ZZ9"
    ), "Waypoints key should format system symbol correctly"


def test_key_for_market() -> None:
    """Test key_for_market formats waypoint symbol correctly."""
    # Arrange
    waypoint_symbol = "X1-ABC-1"

    # Act
    result = key_for_market(waypoint_symbol)

    # Assert
    assert (
        result == "market_X1-ABC-1"
    ), "Market key should include waypoint symbol"


def test_key_for_market_different_waypoint() -> None:
    """Test key_for_market with different waypoint symbol."""
    # Arrange
    waypoint_symbol = "X1-ZZ9-XY"

    # Act
    result = key_for_market(waypoint_symbol)

    # Assert
    assert (
        result == "market_X1-ZZ9-XY"
    ), "Market key should format waypoint symbol correctly"


def test_key_for_shipyard() -> None:
    """Test key_for_shipyard formats waypoint symbol correctly."""
    # Arrange
    waypoint_symbol = "X1-ABC-1"

    # Act
    result = key_for_shipyard(waypoint_symbol)

    # Assert
    assert (
        result == "shipyard_X1-ABC-1"
    ), "Shipyard key should include waypoint symbol"


def test_key_for_shipyard_different_waypoint() -> None:
    """Test key_for_shipyard with different waypoint symbol."""
    # Arrange
    waypoint_symbol = "X1-ZZ9-XY"

    # Act
    result = key_for_shipyard(waypoint_symbol)

    # Assert
    assert (
        result == "shipyard_X1-ZZ9-XY"
    ), "Shipyard key should format waypoint symbol correctly"


def test_schema_documents_all_cache_types() -> None:
    """
    Test that SCHEMA.md documents all cache key types used in code.

    This is a lightweight drift check to ensure the schema documentation
    stays in sync with the actual cache keys defined in cache_keys.py.
    """
    # Arrange
    schema_path = Path(__file__).parent.parent / "cache" / "SCHEMA.md"
    assert schema_path.exists(), "cache/SCHEMA.md should exist"

    with open(schema_path, encoding="utf-8") as f:
        schema_content = f.read()

    # Expected cache key patterns (base names without parameters)
    expected_keys = [
        "agent_info",
        "ship_list",
        "contract_list",
        "waypoints_",  # waypoints_{system_symbol}
        "market_",  # market_{waypoint_symbol}
        "shipyard_",  # shipyard_{waypoint_symbol}
    ]

    # Act & Assert
    for key in expected_keys:
        assert (
            key in schema_content
        ), f"SCHEMA.md should document cache key '{key}'"


def test_all_key_functions_exist() -> None:
    """
    Test that all key helper functions documented in SCHEMA.md exist.

    This ensures that the cache_keys module has all the helpers
    mentioned in the documentation.
    """
    # Arrange
    schema_path = Path(__file__).parent.parent / "cache" / "SCHEMA.md"
    assert schema_path.exists(), "cache/SCHEMA.md should exist"

    with open(schema_path, encoding="utf-8") as f:
        schema_content = f.read()

    # Look for function references in the SCHEMA.md
    # Pattern matches: key_for_* function names
    function_pattern = r"key_for_\w+"
    documented_functions = set(re.findall(function_pattern, schema_content))

    # Expected functions from cache_keys module
    expected_functions = {
        "key_for_agent",
        "key_for_ship_list",
        "key_for_contract_list",
        "key_for_waypoints",
        "key_for_market",
        "key_for_shipyard",
    }

    # Act & Assert
    assert expected_functions == documented_functions, (
        f"Expected functions {expected_functions} to match documented "
        f"functions {documented_functions}"
    )
