"""Unit tests for CLI systems commands."""

from io import StringIO
from typing import Any
from unittest.mock import patch

from py_st._generated.models import (
    Market,
    Shipyard,
    Waypoint,
    WaypointTraitSymbol,
    WaypointType,
)
from tests.factories import MarketFactory, ShipyardFactory, WaypointFactory


@patch("py_st.cli.systems_cmd.resolve_waypoint_id")
@patch("py_st.cli.systems_cmd.get_default_system")
@patch("py_st.cli.systems_cmd.systems.get_market")
@patch("py_st.cli.systems_cmd._get_token")
def test_get_market_cli_calls_with_force_refresh(
    mock_get_token: Any,
    mock_get_market: Any,
    mock_get_default_system: Any,
    mock_resolve_waypoint_id: Any,
) -> None:
    """Test market CLI command calls get_market with force_refresh=True."""
    # Arrange
    mock_get_token.return_value = "fake_token"
    mock_get_default_system.return_value = "X1-ABC"
    mock_resolve_waypoint_id.return_value = "X1-ABC-1"

    market_data = MarketFactory.build_minimal()
    market = Market.model_validate(market_data)
    mock_get_market.return_value = market

    # Import and invoke CLI command
    from py_st.cli.systems_cmd import get_market_cli

    # Act
    get_market_cli(waypoint_symbol="X1-ABC-1", system_symbol="X1-ABC")

    # Assert
    mock_get_market.assert_called_once_with(
        "fake_token", "X1-ABC", "X1-ABC-1", force_refresh=True
    )


@patch("py_st.cli.systems_cmd.resolve_waypoint_id")
@patch("py_st.cli.systems_cmd.get_default_system")
@patch("py_st.cli.systems_cmd.systems.get_shipyard")
@patch("py_st.cli.systems_cmd._get_token")
def test_get_shipyard_cli_calls_with_force_refresh(
    mock_get_token: Any,
    mock_get_shipyard: Any,
    mock_get_default_system: Any,
    mock_resolve_waypoint_id: Any,
) -> None:
    """Test shipyard CLI command calls get_shipyard with force_refresh=True."""
    # Arrange
    mock_get_token.return_value = "fake_token"
    mock_get_default_system.return_value = "X1-ABC"
    mock_resolve_waypoint_id.return_value = "X1-ABC-1"

    shipyard_data = ShipyardFactory.build_minimal()
    shipyard = Shipyard.model_validate(shipyard_data)
    mock_get_shipyard.return_value = shipyard

    # Import and invoke CLI command
    from py_st.cli.systems_cmd import get_shipyard_cli

    # Act
    get_shipyard_cli(waypoint_symbol="X1-ABC-1", system_symbol="X1-ABC")

    # Assert
    mock_get_shipyard.assert_called_once_with(
        "fake_token", "X1-ABC", "X1-ABC-1", force_refresh=True
    )


def test_waypoints_list_alignment() -> None:
    """Test waypoints list has proper index and type alignment."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-VF50"

    # Create waypoints with single, double, and triple-digit indexes
    waypoint_data = [
        WaypointFactory.build_minimal(
            symbol="X1-VF50-B15",
            system_symbol=system_symbol,
            waypoint_type=WaypointType.ASTEROID,
            traits=[WaypointTraitSymbol.COMMON_METAL_DEPOSITS],
        ),
        WaypointFactory.build_minimal(
            symbol="X1-VF50-CD5Z",
            system_symbol=system_symbol,
            waypoint_type=WaypointType.ENGINEERED_ASTEROID,
            traits=[
                WaypointTraitSymbol.MINERAL_DEPOSITS,
                WaypointTraitSymbol.MICRO_GRAVITY_ANOMALIES,
            ],
        ),
    ]

    # Add 8 more waypoints to get to index 9 (10 total)
    for i in range(8):
        waypoint_data.insert(
            0,
            WaypointFactory.build_minimal(
                symbol=f"X1-VF50-W{i}",
                system_symbol=system_symbol,
                waypoint_type=WaypointType.PLANET,
                traits=[],
            ),
        )

    waypoints = [Waypoint.model_validate(w) for w in waypoint_data]

    # Act
    with (
        patch("py_st.cli.systems_cmd._get_token") as mock_get_token,
        patch("py_st.cli.systems_cmd.get_default_system") as mock_get_system,
        patch(
            "py_st.cli.systems_cmd.systems.list_waypoints"
        ) as mock_list_waypoints,
        patch("sys.stdout", new_callable=StringIO) as mock_stdout,
    ):
        mock_get_token.return_value = token
        mock_get_system.return_value = system_symbol
        mock_list_waypoints.return_value = waypoints

        from py_st.cli.systems_cmd import list_waypoints

        list_waypoints(
            system_symbol=system_symbol,
            traits=[],
            token=token,
            verbose=False,
            json_output=False,
        )

    # Assert
    output = mock_stdout.getvalue()
    lines = output.strip().split("\n")

    assert len(lines) == 10, "Expected 10 waypoint rows"

    # Get rows with indexes 8 and 9
    row_8 = lines[8]
    row_9 = lines[9]

    # With 10 waypoints (0-9), max_idx_width is 1
    # So format is: "[{i:>1}]" which gives "[8]", "[9]"
    assert row_8.startswith("[8]"), "Index 8 should be '[8]'"
    assert row_9.startswith("[9]"), "Index 9 should be '[9]'"

    # Extract the index portion from both rows (3 chars: "[X]")
    idx_8 = row_8[:3]
    idx_9 = row_9[:3]

    # Verify they have the same total width
    assert len(idx_8) == len(idx_9), "Index columns should have same width"

    # Verify the bracket position aligns
    assert idx_8.index("]") == idx_9.index(
        "]"
    ), "Closing bracket should align vertically"

    # Verify waypoint symbol starts at same position
    # Format is: "[idx] symbol (type) Traits: ..."
    # Position 3 is the space after "]"
    assert row_8[3] == row_9[3] == " ", "Space after bracket should align"

    # Verify type column alignment by checking "Traits:" position
    # This ensures types are padded correctly
    traits_pos_8 = row_8.index("Traits:")
    traits_pos_9 = row_9.index("Traits:")

    assert (
        traits_pos_8 == traits_pos_9
    ), "Traits column should align vertically"
