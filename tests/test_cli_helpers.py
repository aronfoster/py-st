"""Unit tests for CLI helper functions."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import typer

from py_st._generated.models import Ship, ShipNavStatus, Waypoint
from py_st.cli._helpers import (
    _format_time_remaining,
    format_ship_status,
    resolve_waypoint_id,
)
from tests.factories import ShipFactory, WaypointFactory


def test_format_time_remaining_arrived() -> None:
    """Test _format_time_remaining returns 'Arrived' for past times."""
    # Arrange
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    past_time = datetime(2025, 1, 1, 11, 55, 0, tzinfo=UTC)

    # Act
    with patch("py_st.cli._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        result = _format_time_remaining(past_time)

    # Assert
    assert (
        result == "Arrived"
    ), "Should return 'Arrived' when arrival time is in the past"


def test_format_time_remaining_minutes_and_seconds() -> None:
    """Test _format_time_remaining formats time with minutes and seconds."""
    # Arrange
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    future_time = datetime(2025, 1, 1, 12, 3, 45, tzinfo=UTC)

    # Act
    with patch("py_st.cli._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        result = _format_time_remaining(future_time)

    # Assert
    assert (
        result == "3m 45s"
    ), "Should format as 'Xm Ys' when time is minutes and seconds"


def test_format_time_remaining_only_seconds() -> None:
    """Test _format_time_remaining formats time with only seconds."""
    # Arrange
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    future_time = datetime(2025, 1, 1, 12, 0, 42, tzinfo=UTC)

    # Act
    with patch("py_st.cli._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        result = _format_time_remaining(future_time)

    # Assert
    assert (
        result == "42s"
    ), "Should format as 'Ys' when time is less than a minute"


def test_format_time_remaining_exactly_one_minute() -> None:
    """Test _format_time_remaining formats exactly 60 seconds as 1m 0s."""
    # Arrange
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    future_time = datetime(2025, 1, 1, 12, 1, 0, tzinfo=UTC)

    # Act
    with patch("py_st.cli._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        result = _format_time_remaining(future_time)

    # Assert
    assert result == "1m 0s", "Should format 60 seconds as '1m 0s', not '60s'"


def test_format_ship_status_docked() -> None:
    """Test format_ship_status for a docked ship."""
    # Arrange
    ship_data = ShipFactory.build_minimal()
    ship_data["nav"]["status"] = ShipNavStatus.DOCKED.value
    ship_data["nav"]["waypointSymbol"] = "X1-ABC-123"
    ship = Ship.model_validate(ship_data)

    # Act
    result = format_ship_status(ship)

    # Assert
    assert (
        result == "DOCKED at X1-ABC-123"
    ), "Should show DOCKED status with waypoint symbol"


def test_format_ship_status_in_orbit() -> None:
    """Test format_ship_status for a ship in orbit."""
    # Arrange
    ship_data = ShipFactory.build_minimal()
    ship_data["nav"]["status"] = ShipNavStatus.IN_ORBIT.value
    ship_data["nav"]["waypointSymbol"] = "X1-ABC-456"
    ship = Ship.model_validate(ship_data)

    # Act
    result = format_ship_status(ship)

    # Assert
    assert (
        result == "IN_ORBIT at X1-ABC-456"
    ), "Should show IN_ORBIT status with waypoint symbol"


def test_format_ship_status_in_transit() -> None:
    """Test format_ship_status for a ship in transit."""
    # Arrange
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    arrival_time = datetime(2025, 1, 1, 12, 5, 30, tzinfo=UTC)

    ship_data = ShipFactory.build_minimal()
    ship_data["nav"]["status"] = ShipNavStatus.IN_TRANSIT.value
    ship_data["nav"]["route"]["destination"]["symbol"] = "X1-DEF-789"
    ship_data["nav"]["route"]["arrival"] = arrival_time.isoformat()
    ship = Ship.model_validate(ship_data)

    # Act
    with patch("py_st.cli._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        result = format_ship_status(ship)

    # Assert
    assert (
        "IN_TRANSIT to X1-DEF-789" in result
    ), "Should show IN_TRANSIT status with destination"
    assert (
        "5m 30s" in result
    ), "Should include formatted time remaining in transit status"


def test_format_ship_status_in_transit_arrived() -> None:
    """Test format_ship_status for a ship that has arrived."""
    # Arrange
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    arrival_time = datetime(2025, 1, 1, 11, 59, 0, tzinfo=UTC)

    ship_data = ShipFactory.build_minimal()
    ship_data["nav"]["status"] = ShipNavStatus.IN_TRANSIT.value
    ship_data["nav"]["route"]["destination"]["symbol"] = "X1-GHI-999"
    ship_data["nav"]["route"]["arrival"] = arrival_time.isoformat()
    ship = Ship.model_validate(ship_data)

    # Act
    with patch("py_st.cli._helpers.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        result = format_ship_status(ship)

    # Assert
    assert (
        result == "IN_TRANSIT to X1-GHI-999 (Arrived)"
    ), "Should show 'Arrived' when ship has reached destination"


def test_resolve_waypoint_id_passthrough() -> None:
    """Test resolve_waypoint_id returns full symbol unchanged."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-ABC"
    wp_id_arg = "X1-ABC-A1"

    # Act
    result = resolve_waypoint_id(token, system_symbol, wp_id_arg)

    # Assert
    assert (
        result == "X1-ABC-A1"
    ), "Should return full waypoint symbol unchanged when input is not a digit"


def test_resolve_waypoint_id_index_lookup() -> None:
    """Test resolve_waypoint_id resolves index to waypoint symbol."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-ABC"
    wp_id_arg = "0"

    # Create mock waypoints (unsorted order)
    wp_data_1 = WaypointFactory.build_minimal(
        symbol="X1-ABC-C3", system_symbol="X1-ABC"
    )
    wp_data_2 = WaypointFactory.build_minimal(
        symbol="X1-ABC-A1", system_symbol="X1-ABC"
    )
    wp_data_3 = WaypointFactory.build_minimal(
        symbol="X1-ABC-B2", system_symbol="X1-ABC"
    )
    mock_waypoints = [
        Waypoint.model_validate(wp_data_1),
        Waypoint.model_validate(wp_data_2),
        Waypoint.model_validate(wp_data_3),
    ]

    # Act
    with patch(
        "py_st.cli._helpers.systems.list_waypoints"
    ) as mock_list_waypoints:
        mock_list_waypoints.return_value = mock_waypoints
        result = resolve_waypoint_id(token, system_symbol, wp_id_arg)

    # Assert
    assert (
        result == "X1-ABC-A1"
    ), "Should resolve index 0 to first waypoint after sorting by symbol"
    mock_list_waypoints.assert_called_once_with(
        token, system_symbol, traits=None
    )


def test_resolve_waypoint_id_out_of_bounds() -> None:
    """Test resolve_waypoint_id raises Exit for invalid index."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-ABC"
    wp_id_arg = "99"

    # Create mock waypoints
    wp_data = WaypointFactory.build_minimal(
        symbol="X1-ABC-A1", system_symbol="X1-ABC"
    )
    mock_waypoints = [Waypoint.model_validate(wp_data)]

    # Act & Assert
    with patch(
        "py_st.cli._helpers.systems.list_waypoints"
    ) as mock_list_waypoints:
        mock_list_waypoints.return_value = mock_waypoints
        with pytest.raises(typer.Exit) as exc_info:
            resolve_waypoint_id(token, system_symbol, wp_id_arg)

    assert (
        exc_info.value.exit_code == 1
    ), "Should exit with code 1 for invalid index"
    mock_list_waypoints.assert_called_once_with(
        token, system_symbol, traits=None
    )
