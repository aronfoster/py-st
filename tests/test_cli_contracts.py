"""Unit tests for CLI contract commands with ship resolution."""

from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from py_st._generated.models import (
    Contract,
    ContractDeliverGood,
    ContractPayment,
    ContractTerms,
    ShipCargo,
    TradeSymbol,
)
from py_st._generated.models.Contract import Type as ContractType
from py_st.cli.contracts_cmd import (
    deliver_contract_cli,
    list_contracts,
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


def test_contracts_list_alignment() -> None:
    """Test contracts list has proper column alignment for mixed digits."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-VF50"

    now = datetime.now(UTC)
    future = now + timedelta(hours=3, minutes=12)

    # Create contracts with single and double-digit indexes
    payment = ContractPayment(onAccepted=1000, onFulfilled=5000)

    deliverable = ContractDeliverGood(
        tradeSymbol="SHIP_PARTS",
        destinationSymbol="X1-VF50-C37",
        unitsRequired=8,
        unitsFulfilled=8,
    )
    terms1 = ContractTerms(
        deadline=future, payment=payment, deliver=[deliverable]
    )
    contract1 = Contract(
        id="cmhd4r-123",
        factionSymbol="COSMIC",
        type=ContractType.PROCUREMENT,
        terms=terms1,
        accepted=True,
        fulfilled=False,
        expiration=future,
        deadlineToAccept=None,
    )

    deliverable2 = ContractDeliverGood(
        tradeSymbol="IRON_ORE",
        destinationSymbol="X1-VF50-H50",
        unitsRequired=10,
        unitsFulfilled=0,
    )
    terms2 = ContractTerms(
        deadline=now - timedelta(hours=2),
        payment=payment,
        deliver=[deliverable2],
    )
    contract2 = Contract(
        id="c8z12f-456",
        factionSymbol="COSMIC",
        type=ContractType.PROCUREMENT,
        terms=terms2,
        accepted=True,
        fulfilled=True,
        expiration=future,
        deadlineToAccept=None,
    )

    contracts_data = [contract1, contract2]

    # Act
    with (
        patch("py_st.cli.contracts_cmd._get_token") as mock_get_token,
        patch("py_st.cli.contracts_cmd.contracts.list_contracts") as mock_list,
        patch("py_st.cli.contracts_cmd.get_default_system") as mock_get_system,
        patch("py_st.cli.contracts_cmd.get_waypoint_index") as mock_wp_idx,
        patch("sys.stdout", new_callable=StringIO) as mock_stdout,
    ):
        mock_get_token.return_value = token
        mock_list.return_value = contracts_data
        mock_get_system.return_value = system_symbol
        mock_wp_idx.return_value = "w-12"

        list_contracts(
            token=token, verbose=False, json_output=False, stacked=False
        )

    # Assert
    output = mock_stdout.getvalue()
    lines = output.strip().split("\n")

    assert len(lines) == 3, "Expected header + 2 contract rows"

    header = lines[0]
    row1 = lines[1]
    row2 = lines[2]

    # Verify header content
    assert header.startswith("IDX  "), "Header should start with IDX"
    assert "ID6" in header, "Header should contain ID6"
    assert "T" in header, "Header should contain T"
    assert "A/F" in header, "Header should contain A/F"
    assert "DUE(REL)" in header, "Header should contain DUE(REL)"
    assert "DELIVER" in header, "Header should contain DELIVER"

    # Verify row content (note: contracts are sorted by ID)
    # "c8z12f-456" comes before "cmhd4r-123" alphabetically
    assert row1.startswith("c-0  "), "Row 1 should start with 'c-0  '"
    assert row2.startswith("c-1  "), "Row 2 should start with 'c-1  '"

    # Verify column alignment by checking positions
    idx_end = 5
    id6_start = idx_end + 1
    id6_end = id6_start + 7

    # Contracts are sorted alphabetically by ID
    assert (
        row1[id6_start:id6_end].strip() == "c8z12f"
    ), "Row 1 ID6 column misaligned"
    assert (
        row2[id6_start:id6_end].strip() == "cmhd4r"
    ), "Row 2 ID6 column misaligned"
