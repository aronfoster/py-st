"""Unit tests for CLI systems commands."""

from typing import Any
from unittest.mock import patch

from py_st._generated.models import Market, Shipyard
from tests.factories import MarketFactory, ShipyardFactory


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
