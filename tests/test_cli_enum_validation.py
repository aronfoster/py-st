"""Tests for CLI enum argument validation."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from py_st._generated.models import (
    ShipNavFlightMode,
)
from py_st.cli.contracts_cmd import contracts_app
from py_st.cli.ships_cmd import ships_app
from py_st.cli.systems_cmd import systems_app
from tests.factories import ContractFactory, ShipFactory

runner = CliRunner()


def test_ships_flight_mode_accepts_valid_enum_value() -> None:
    """Test flight-mode command accepts valid ShipNavFlightMode."""
    # Arrange
    token = "test-token"
    ship_symbol = "s-0"
    resolved_ship = "MY-SHIP-A"
    flight_mode = "CRUISE"

    mock_nav = {"flightMode": flight_mode}

    # Act
    with (
        patch("py_st.cli.ships_cmd._get_token") as mock_get_token,
        patch("py_st.cli.ships_cmd.resolve_ship_id") as mock_resolve,
        patch("py_st.cli.ships_cmd.ships.set_flight_mode") as mock_set_fm,
        patch("builtins.print"),
    ):
        mock_get_token.return_value = token
        mock_resolve.return_value = resolved_ship
        mock_set_fm.return_value = type(
            "MockNav", (), {"model_dump": lambda self, mode: mock_nav}
        )()

        result = runner.invoke(
            ships_app, ["flight-mode", ship_symbol, flight_mode]
        )

    # Assert
    assert result.exit_code == 0, (
        f"Command should succeed with valid enum value. "
        f"Output: {result.stdout}"
    )
    mock_set_fm.assert_called_once_with(
        token, resolved_ship, ShipNavFlightMode.CRUISE
    )


def test_ships_flight_mode_accepts_another_valid_enum_value() -> None:
    """Test flight-mode command accepts BURN mode."""
    # Arrange
    token = "test-token"
    ship_symbol = "s-0"
    resolved_ship = "MY-SHIP-A"
    flight_mode = "BURN"

    mock_nav = {"flightMode": flight_mode}

    # Act
    with (
        patch("py_st.cli.ships_cmd._get_token") as mock_get_token,
        patch("py_st.cli.ships_cmd.resolve_ship_id") as mock_resolve,
        patch("py_st.cli.ships_cmd.ships.set_flight_mode") as mock_set_fm,
        patch("builtins.print"),
    ):
        mock_get_token.return_value = token
        mock_resolve.return_value = resolved_ship
        mock_set_fm.return_value = type(
            "MockNav", (), {"model_dump": lambda self, mode: mock_nav}
        )()

        result = runner.invoke(
            ships_app, ["flight-mode", ship_symbol, flight_mode]
        )

    # Assert
    assert result.exit_code == 0, (
        f"Command should succeed with valid enum value. "
        f"Output: {result.stdout}"
    )
    mock_set_fm.assert_called_once_with(
        token, resolved_ship, ShipNavFlightMode.BURN
    )


def test_ships_flight_mode_rejects_invalid_enum_value() -> None:
    """Test flight-mode command rejects invalid mode."""
    # Arrange
    ship_symbol = "s-0"
    invalid_mode = "INVALID_MODE"

    # Act
    result = runner.invoke(
        ships_app, ["flight-mode", ship_symbol, invalid_mode]
    )

    # Assert
    assert result.exit_code != 0, "Command should fail with invalid enum value"
    output = result.stdout + (result.stderr or "")
    assert "Invalid value" in output or "invalid choice" in (
        output.lower()
    ), "Should show validation error for invalid enum"


def test_contracts_deliver_accepts_valid_trade_symbol() -> None:
    """Test deliver command accepts valid TradeSymbol."""
    # Arrange
    token = "test-token"
    contract_id = "c-0"
    ship_symbol = "s-0"
    trade_symbol = "IRON_ORE"
    units = "10"

    resolved_contract = "contract-abc123"
    resolved_ship = "MY-SHIP-A"

    contract_data = ContractFactory.build_minimal()
    ship_data = ShipFactory.build_minimal()

    # Act
    with (
        patch("py_st.cli.contracts_cmd._get_token") as mock_get_token,
        patch("py_st.cli.contracts_cmd.resolve_contract_id") as mock_resolve_c,
        patch("py_st.cli.contracts_cmd.resolve_ship_id") as mock_resolve_s,
        patch(
            "py_st.cli.contracts_cmd.contracts.deliver_contract"
        ) as mock_deliver,
        patch("builtins.print"),
    ):
        mock_get_token.return_value = token
        mock_resolve_c.return_value = resolved_contract
        mock_resolve_s.return_value = resolved_ship
        mock_deliver.return_value = (
            type("C", (), {"model_dump": lambda s, mode: contract_data})(),
            type(
                "Cg", (), {"model_dump": lambda s, mode: ship_data["cargo"]}
            )(),
        )

        result = runner.invoke(
            contracts_app,
            ["deliver", contract_id, ship_symbol, trade_symbol, units],
        )

    # Assert
    assert result.exit_code == 0, (
        f"Command should succeed with valid trade symbol. "
        f"Output: {result.stdout}"
    )
    mock_deliver.assert_called_once_with(
        token, resolved_contract, resolved_ship, "IRON_ORE", 10
    )


def test_contracts_deliver_rejects_invalid_trade_symbol() -> None:
    """Test deliver command rejects invalid TradeSymbol."""
    # Arrange
    contract_id = "c-0"
    ship_symbol = "s-0"
    invalid_symbol = "INVALID_TRADE_GOOD"
    units = "10"

    # Act
    result = runner.invoke(
        contracts_app,
        ["deliver", contract_id, ship_symbol, invalid_symbol, units],
    )

    # Assert
    assert (
        result.exit_code != 0
    ), "Command should fail with invalid trade symbol"
    output = result.stdout + (result.stderr or "")
    assert "Invalid value" in output or "invalid choice" in (
        output.lower()
    ), "Should show validation error for invalid trade symbol"


def test_systems_waypoints_trait_accepts_valid_trait_symbol() -> None:
    """Test waypoints command accepts valid WaypointTraitSymbol."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-TEST"
    trait = "MARKETPLACE"

    # Act
    with (
        patch("py_st.cli.systems_cmd._get_token") as mock_get_token,
        patch("py_st.cli.systems_cmd.get_default_system") as mock_get_system,
        patch("py_st.cli.systems_cmd.systems.list_waypoints") as mock_list_wp,
        patch("builtins.print"),
    ):
        mock_get_token.return_value = token
        mock_get_system.return_value = system_symbol
        mock_list_wp.return_value = [
            type(
                "W",
                (),
                {
                    "symbol": type("S", (), {"root": "X1-TEST-A"})(),
                    "type": type("T", (), {"value": "PLANET"})(),
                    "traits": [
                        type(
                            "Tr",
                            (),
                            {
                                "symbol": type(
                                    "TS", (), {"value": ("MARKETPLACE")}
                                )()
                            },
                        )()
                    ],
                },
            )()
        ]

        result = runner.invoke(systems_app, ["waypoints", "--trait", trait])

    # Assert
    assert result.exit_code == 0, (
        f"Command should succeed with valid trait symbol. "
        f"Output: {result.stdout}"
    )
    mock_list_wp.assert_called_once_with(token, system_symbol, ["MARKETPLACE"])


def test_systems_waypoints_trait_rejects_invalid_trait_symbol() -> None:
    """Test waypoints command rejects invalid WaypointTraitSymbol."""
    # Arrange
    invalid_trait = "INVALID_TRAIT"

    # Act
    result = runner.invoke(
        systems_app, ["waypoints", "--trait", invalid_trait]
    )

    # Assert
    assert (
        result.exit_code != 0
    ), "Command should fail with invalid trait symbol"
    output = result.stdout + (result.stderr or "")
    assert "Invalid value" in output or "invalid choice" in (
        output.lower()
    ), "Should show validation error for invalid trait symbol"
