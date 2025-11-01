"""Unit tests for CLI contract commands with ship resolution."""

from unittest.mock import patch

from py_st._generated.models import Contract, ShipCargo, TradeSymbol
from py_st.cli.contracts_cmd import (
    deliver_contract_cli,
    negotiate_contract_cli,
)
from tests.factories import ContractFactory, ShipFactory


def test_negotiate_contract_cli_resolves_ship_index() -> None:
    """Test negotiate command resolves s-<idx> to ship symbol."""
    # Arrange
    token = "test-token"
    ship_symbol_arg = "s-0"
    resolved_ship = "MY-SHIP-A"

    contract_data = ContractFactory.build_minimal()
    mock_contract = Contract.model_validate(contract_data)

    # Act
    with (
        patch("py_st.cli.contracts_cmd._get_token") as mock_get_token,
        patch("py_st.cli.contracts_cmd.resolve_ship_id") as mock_resolve,
        patch(
            "py_st.cli.contracts_cmd.contracts.negotiate_contract"
        ) as mock_negotiate,  # noqa: E501
        patch("builtins.print"),
    ):
        mock_get_token.return_value = token
        mock_resolve.return_value = resolved_ship
        mock_negotiate.return_value = mock_contract

        negotiate_contract_cli(
            ship_symbol=ship_symbol_arg, token=token, verbose=False
        )

    # Assert
    mock_resolve.assert_called_once_with(token, ship_symbol_arg)
    mock_negotiate.assert_called_once_with(token, resolved_ship)


def test_negotiate_contract_cli_accepts_full_ship_symbol() -> None:
    """Test negotiate command passes through full ship symbol."""
    # Arrange
    token = "test-token"
    ship_symbol = "MY-SHIP-FULL"

    contract_data = ContractFactory.build_minimal()
    mock_contract = Contract.model_validate(contract_data)

    # Act
    with (
        patch("py_st.cli.contracts_cmd._get_token") as mock_get_token,
        patch("py_st.cli.contracts_cmd.resolve_ship_id") as mock_resolve,
        patch(
            "py_st.cli.contracts_cmd.contracts.negotiate_contract"
        ) as mock_negotiate,  # noqa: E501
        patch("builtins.print"),
    ):
        mock_get_token.return_value = token
        mock_resolve.return_value = ship_symbol
        mock_negotiate.return_value = mock_contract

        negotiate_contract_cli(
            ship_symbol=ship_symbol, token=token, verbose=False
        )

    # Assert
    mock_resolve.assert_called_once_with(token, ship_symbol)
    mock_negotiate.assert_called_once_with(token, ship_symbol)


def test_deliver_contract_cli_resolves_both_indices() -> None:
    """Test deliver command resolves both c-<idx> and s-<idx>."""
    # Arrange
    token = "test-token"
    contract_id_arg = "c-0"
    ship_symbol_arg = "s-1"
    trade_symbol = TradeSymbol.IRON_ORE
    units = 10

    resolved_contract = "contract-abc123"
    resolved_ship = "MY-SHIP-B"

    contract_data = ContractFactory.build_minimal()
    mock_contract = Contract.model_validate(contract_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    mock_cargo = ShipCargo.model_validate(cargo_data)

    # Act
    with (
        patch("py_st.cli.contracts_cmd._get_token") as mock_get_token,
        patch(
            "py_st.cli.contracts_cmd.resolve_contract_id"
        ) as mock_resolve_contract,
        patch("py_st.cli.contracts_cmd.resolve_ship_id") as mock_resolve_ship,
        patch(
            "py_st.cli.contracts_cmd.contracts.deliver_contract"
        ) as mock_deliver,  # noqa: E501
        patch("builtins.print"),
    ):
        mock_get_token.return_value = token
        mock_resolve_contract.return_value = resolved_contract
        mock_resolve_ship.return_value = resolved_ship
        mock_deliver.return_value = (mock_contract, mock_cargo)

        deliver_contract_cli(
            contract_id=contract_id_arg,
            ship_symbol=ship_symbol_arg,
            trade_symbol=trade_symbol,
            units=units,
            token=token,
            verbose=False,
        )

    # Assert
    mock_resolve_contract.assert_called_once_with(token, contract_id_arg)
    mock_resolve_ship.assert_called_once_with(token, ship_symbol_arg)
    mock_deliver.assert_called_once_with(
        token, resolved_contract, resolved_ship, trade_symbol.value, units
    )


def test_deliver_contract_cli_accepts_full_symbols() -> None:
    """Test deliver command passes through full contract and ship symbols."""
    # Arrange
    token = "test-token"
    contract_id = "contract-full-id"
    ship_symbol = "MY-SHIP-FULL"
    trade_symbol = TradeSymbol.IRON_ORE
    units = 10

    contract_data = ContractFactory.build_minimal()
    mock_contract = Contract.model_validate(contract_data)

    ship_data = ShipFactory.build_minimal()
    cargo_data = ship_data["cargo"]
    mock_cargo = ShipCargo.model_validate(cargo_data)

    # Act
    with (
        patch("py_st.cli.contracts_cmd._get_token") as mock_get_token,
        patch(
            "py_st.cli.contracts_cmd.resolve_contract_id"
        ) as mock_resolve_contract,
        patch("py_st.cli.contracts_cmd.resolve_ship_id") as mock_resolve_ship,
        patch(
            "py_st.cli.contracts_cmd.contracts.deliver_contract"
        ) as mock_deliver,  # noqa: E501
        patch("builtins.print"),
    ):
        mock_get_token.return_value = token
        mock_resolve_contract.return_value = contract_id
        mock_resolve_ship.return_value = ship_symbol
        mock_deliver.return_value = (mock_contract, mock_cargo)

        deliver_contract_cli(
            contract_id=contract_id,
            ship_symbol=ship_symbol,
            trade_symbol=trade_symbol,
            units=units,
            token=token,
            verbose=False,
        )

    # Assert
    mock_resolve_contract.assert_called_once_with(token, contract_id)
    mock_resolve_ship.assert_called_once_with(token, ship_symbol)
    mock_deliver.assert_called_once_with(
        token, contract_id, ship_symbol, trade_symbol.value, units
    )
