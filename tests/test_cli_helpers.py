"""Unit tests for CLI helper functions."""

from datetime import UTC, datetime
from unittest.mock import patch

from py_st._generated.models import Ship, ShipNavStatus
from py_st.cli._helpers import _format_time_remaining, format_ship_status
from tests.factories import ShipFactory


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
