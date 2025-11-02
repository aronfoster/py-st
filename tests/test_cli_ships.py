"""Unit tests for ship CLI commands."""

from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from py_st._generated.models import ShipCargo, TradeSymbol
from py_st.cli.ships_cmd import ships_app
from py_st.client import APIError
from tests.factories import ShipFactory

runner = CliRunner()


@patch("py_st.cli.ships_cmd.ships.transfer_cargo")
@patch("py_st.cli.ships_cmd.resolve_ship_id")
@patch("py_st.cli.ships_cmd._get_token")
def test_transfer_cargo_resolves_ship_indices(
    mock_get_token: Any, mock_resolve_ship_id: Any, mock_transfer: Any
) -> None:
    """Test transfer-cargo resolves s-0 and s-1 to full symbols."""
    # Arrange
    mock_get_token.return_value = "fake_token"
    mock_resolve_ship_id.side_effect = ["SHIP-1", "SHIP-2"]

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo_data["inventory"] = [
        {
            "symbol": "FUEL",
            "units": 5,
            "name": "Fuel",
            "description": "Fuel for ships",
        }
    ]
    cargo = ShipCargo.model_validate(cargo_data)
    mock_transfer.return_value = cargo

    # Act
    result = runner.invoke(
        ships_app, ["transfer-cargo", "s-0", "s-1", "FUEL", "10"]
    )

    # Assert
    assert result.exit_code == 0, f"CLI should succeed: {result.output}"
    mock_resolve_ship_id.assert_any_call("fake_token", "s-0")
    mock_resolve_ship_id.assert_any_call("fake_token", "s-1")
    mock_transfer.assert_called_once_with(
        "fake_token", "SHIP-1", "SHIP-2", TradeSymbol.FUEL, 10
    )
    assert "SHIP-1" in result.output, "Should show resolved from_ship"
    assert "SHIP-2" in result.output, "Should show resolved to_ship"
    assert "FUEL" in result.output, "Should show trade symbol"


@patch("py_st.cli.ships_cmd.resolve_ship_id")
@patch("py_st.cli.ships_cmd._get_token")
def test_transfer_cargo_same_ship_error(
    mock_get_token: Any, mock_resolve_ship_id: Any
) -> None:
    """Test transfer-cargo exits with error when source == destination."""
    # Arrange
    mock_get_token.return_value = "fake_token"
    mock_resolve_ship_id.return_value = "SHIP-1"

    # Act
    result = runner.invoke(
        ships_app, ["transfer-cargo", "s-0", "s-0", "FUEL", "10"]
    )

    # Assert
    assert (
        result.exit_code == 1
    ), "Should exit with error when source == destination"
    assert (
        "Source and destination must differ" in result.output
    ), "Should show error message"


@patch("py_st.cli.ships_cmd._get_token")
def test_transfer_cargo_negative_units_error(mock_get_token: Any) -> None:
    """Test transfer-cargo exits with error when units <= 0."""
    # Arrange
    mock_get_token.return_value = "fake_token"

    # Act
    result = runner.invoke(
        ships_app, ["transfer-cargo", "s-0", "s-1", "FUEL", "0"]
    )

    # Assert
    assert result.exit_code == 1, "Should exit with error when units <= 0"
    assert (
        "Units must be positive" in result.output
    ), "Should show error message"


@patch("py_st.cli.ships_cmd._get_token")
def test_transfer_cargo_negative_units_error_negative(
    mock_get_token: Any,
) -> None:
    """Test transfer-cargo exits with error when units is negative."""
    # Arrange
    mock_get_token.return_value = "fake_token"

    # Act
    result = runner.invoke(
        ships_app, ["transfer-cargo", "s-0", "s-1", "FUEL", "-5"]
    )

    # Assert
    assert result.exit_code == 2, "Typer returns exit code 2 for invalid arg"


@patch("py_st.cli.ships_cmd.ships.transfer_cargo")
@patch("py_st.cli.ships_cmd.resolve_ship_id")
@patch("py_st.cli.ships_cmd._get_token")
def test_transfer_cargo_api_error(
    mock_get_token: Any, mock_resolve_ship_id: Any, mock_transfer: Any
) -> None:
    """Test transfer-cargo handles API errors gracefully."""
    # Arrange
    mock_get_token.return_value = "fake_token"
    mock_resolve_ship_id.side_effect = ["SHIP-1", "SHIP-2"]
    mock_transfer.side_effect = APIError("Insufficient cargo capacity")

    # Act
    result = runner.invoke(
        ships_app, ["transfer-cargo", "s-0", "s-1", "FUEL", "10"]
    )

    # Assert
    assert result.exit_code == 1, "Should exit with error on API failure"
    assert (
        "Insufficient cargo capacity" in result.output
    ), "Should show API error message"


@patch("py_st.cli.ships_cmd.ships.transfer_cargo")
@patch("py_st.cli.ships_cmd.resolve_ship_id")
@patch("py_st.cli.ships_cmd._get_token")
def test_transfer_cargo_with_full_ship_symbols(
    mock_get_token: Any, mock_resolve_ship_id: Any, mock_transfer: Any
) -> None:
    """Test transfer-cargo works with full ship symbols."""
    # Arrange
    mock_get_token.return_value = "fake_token"
    mock_resolve_ship_id.side_effect = ["SHIP-FULL-1", "SHIP-FULL-2"]

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    cargo_data["inventory"] = [
        {
            "symbol": "IRON_ORE",
            "units": 15,
            "name": "Iron Ore",
            "description": "Raw iron ore",
        }
    ]
    cargo = ShipCargo.model_validate(cargo_data)
    mock_transfer.return_value = cargo

    # Act
    result = runner.invoke(
        ships_app,
        ["transfer-cargo", "SHIP-FULL-1", "SHIP-FULL-2", "IRON_ORE", "20"],
    )

    # Assert
    assert result.exit_code == 0, f"CLI should succeed: {result.output}"
    mock_transfer.assert_called_once_with(
        "fake_token",
        "SHIP-FULL-1",
        "SHIP-FULL-2",
        TradeSymbol.IRON_ORE,
        20,
    )
    assert "SHIP-FULL-1" in result.output, "Should show from_ship symbol"
    assert "SHIP-FULL-2" in result.output, "Should show to_ship symbol"
