"""Unit tests for CLI helper functions."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import typer

from py_st._generated.models import (
    Agent,
    Contract,
    Ship,
    ShipNavStatus,
    Waypoint,
)
from py_st.cli._helpers import (
    _format_time_remaining,
    format_ship_status,
    get_default_system,
    resolve_contract_id,
    resolve_ship_id,
    resolve_waypoint_id,
)
from tests.factories import (
    AgentFactory,
    ContractFactory,
    ShipFactory,
    WaypointFactory,
)


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
    assert result == "X1-ABC-A1", (
        "Should return full waypoint symbol unchanged when input is "
        "not prefixed"
    )


def test_resolve_waypoint_id_plain_digit_passthrough() -> None:
    """Test resolve_waypoint_id treats plain digits as symbols."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-ABC"
    wp_id_arg = "0"

    # Act
    result = resolve_waypoint_id(token, system_symbol, wp_id_arg)

    # Assert
    assert (
        result == "0"
    ), "Should pass through plain digit as symbol, not resolve as index"


def test_resolve_waypoint_id_index_lookup() -> None:
    """Test resolve_waypoint_id resolves prefixed index to waypoint symbol."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-ABC"
    wp_id_arg = "w-0"

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
    ), "Should resolve w-0 to first waypoint after sorting by symbol"
    mock_list_waypoints.assert_called_once_with(
        token, system_symbol, traits=None
    )


def test_resolve_waypoint_id_uppercase_prefix() -> None:
    """Test resolve_waypoint_id handles uppercase W- prefix."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-ABC"
    wp_id_arg = "W-1"

    # Create mock waypoints
    wp_data_1 = WaypointFactory.build_minimal(
        symbol="X1-ABC-A1", system_symbol="X1-ABC"
    )
    wp_data_2 = WaypointFactory.build_minimal(
        symbol="X1-ABC-B2", system_symbol="X1-ABC"
    )
    mock_waypoints = [
        Waypoint.model_validate(wp_data_1),
        Waypoint.model_validate(wp_data_2),
    ]

    # Act
    with patch(
        "py_st.cli._helpers.systems.list_waypoints"
    ) as mock_list_waypoints:
        mock_list_waypoints.return_value = mock_waypoints
        result = resolve_waypoint_id(token, system_symbol, wp_id_arg)

    # Assert
    assert (
        result == "X1-ABC-B2"
    ), "Should resolve uppercase W-1 to second waypoint after sorting"
    mock_list_waypoints.assert_called_once_with(
        token, system_symbol, traits=None
    )


def test_resolve_waypoint_id_out_of_bounds() -> None:
    """Test resolve_waypoint_id raises Exit for invalid prefixed index."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-ABC"
    wp_id_arg = "w-99"

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


def test_resolve_waypoint_id_invalid_prefix_format() -> None:
    """Test resolve_waypoint_id treats w-abc as a symbol (not an index)."""
    # Arrange
    token = "test-token"
    system_symbol = "X1-ABC"
    wp_id_arg = "w-abc"

    # Act
    result = resolve_waypoint_id(token, system_symbol, wp_id_arg)

    # Assert
    assert (
        result == "w-abc"
    ), "Should pass through w-abc as symbol since it's not w-<digits>"


def test_resolve_ship_id_passthrough() -> None:
    """Test resolve_ship_id returns full symbol unchanged."""
    # Arrange
    token = "test-token"
    ship_id_arg = "MY-SHIP-1"

    # Act
    result = resolve_ship_id(token, ship_id_arg)

    # Assert
    assert (
        result == "MY-SHIP-1"
    ), "Should return full ship symbol unchanged when input is not prefixed"


def test_resolve_ship_id_plain_digit_passthrough() -> None:
    """Test resolve_ship_id treats plain digits as symbols."""
    # Arrange
    token = "test-token"
    ship_id_arg = "0"

    # Act
    result = resolve_ship_id(token, ship_id_arg)

    # Assert
    assert (
        result == "0"
    ), "Should pass through plain digit as symbol, not resolve as index"


def test_resolve_ship_id_index_lookup() -> None:
    """Test resolve_ship_id resolves prefixed index to ship symbol."""
    # Arrange
    token = "test-token"
    ship_id_arg = "s-0"

    # Create mock ships (unsorted order)
    ship_data_1 = ShipFactory.build_minimal()
    ship_data_1["symbol"] = "MY-SHIP-C"
    ship_data_2 = ShipFactory.build_minimal()
    ship_data_2["symbol"] = "MY-SHIP-A"
    ship_data_3 = ShipFactory.build_minimal()
    ship_data_3["symbol"] = "MY-SHIP-B"
    mock_ships = [
        Ship.model_validate(ship_data_1),
        Ship.model_validate(ship_data_2),
        Ship.model_validate(ship_data_3),
    ]

    # Act
    with patch("py_st.cli._helpers.ships.list_ships") as mock_list_ships:
        mock_list_ships.return_value = mock_ships
        result = resolve_ship_id(token, ship_id_arg)

    # Assert
    assert (
        result == "MY-SHIP-A"
    ), "Should resolve s-0 to first ship after sorting by symbol"
    mock_list_ships.assert_called_once_with(token)


def test_resolve_ship_id_uppercase_prefix() -> None:
    """Test resolve_ship_id handles uppercase S- prefix."""
    # Arrange
    token = "test-token"
    ship_id_arg = "S-1"

    # Create mock ships
    ship_data_1 = ShipFactory.build_minimal()
    ship_data_1["symbol"] = "MY-SHIP-A"
    ship_data_2 = ShipFactory.build_minimal()
    ship_data_2["symbol"] = "MY-SHIP-B"
    mock_ships = [
        Ship.model_validate(ship_data_1),
        Ship.model_validate(ship_data_2),
    ]

    # Act
    with patch("py_st.cli._helpers.ships.list_ships") as mock_list_ships:
        mock_list_ships.return_value = mock_ships
        result = resolve_ship_id(token, ship_id_arg)

    # Assert
    assert (
        result == "MY-SHIP-B"
    ), "Should resolve uppercase S-1 to second ship after sorting"
    mock_list_ships.assert_called_once_with(token)


def test_resolve_ship_id_out_of_bounds() -> None:
    """Test resolve_ship_id raises Exit for invalid prefixed index."""
    # Arrange
    token = "test-token"
    ship_id_arg = "s-99"

    # Create mock ships
    ship_data = ShipFactory.build_minimal()
    ship_data["symbol"] = "MY-SHIP-A"
    mock_ships = [Ship.model_validate(ship_data)]

    # Act & Assert
    with patch("py_st.cli._helpers.ships.list_ships") as mock_list_ships:
        mock_list_ships.return_value = mock_ships
        with pytest.raises(typer.Exit) as exc_info:
            resolve_ship_id(token, ship_id_arg)

    assert (
        exc_info.value.exit_code == 1
    ), "Should exit with code 1 for invalid index"
    mock_list_ships.assert_called_once_with(token)


def test_resolve_ship_id_invalid_prefix_format() -> None:
    """Test resolve_ship_id treats s-abc as a symbol (not an index)."""
    # Arrange
    token = "test-token"
    ship_id_arg = "s-abc"

    # Act
    result = resolve_ship_id(token, ship_id_arg)

    # Assert
    assert (
        result == "s-abc"
    ), "Should pass through s-abc as symbol since it's not s-<digits>"


def test_get_default_system() -> None:
    """Test get_default_system parses system from standard HQ symbol."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent_data["headquarters"] = "X1-TEST-A1"
    mock_agent = Agent.model_validate(agent_data)

    # Act
    with patch("py_st.cli._helpers.agent.get_agent_info") as mock_get_agent:
        mock_get_agent.return_value = mock_agent
        result = get_default_system("fake_token")

    # Assert
    assert (
        result == "X1-TEST"
    ), "Should correctly parse the system from a standard HQ waypoint symbol"


def test_get_default_system_complex_symbol() -> None:
    """Test get_default_system parses system with multiple hyphens."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent_data["headquarters"] = "X1-LONG-SYSTEM-NAME-A123"
    mock_agent = Agent.model_validate(agent_data)

    # Act
    with patch("py_st.cli._helpers.agent.get_agent_info") as mock_get_agent:
        mock_get_agent.return_value = mock_agent
        result = get_default_system("fake_token")

    # Assert
    assert (
        result == "X1-LONG-SYSTEM-NAME"
    ), "Should correctly parse a system with multiple hyphens"


def test_get_default_system_no_headquarters() -> None:
    """Test get_default_system raises Exit when headquarters is None."""
    # Arrange
    # Use model_construct to bypass validation and set headquarters to None
    mock_agent = Agent.model_construct(
        accountId=None,
        symbol="TEST",
        headquarters=None,
        credits=100,
        startingFaction="COSMIC",
        shipCount=1,
    )

    # Act & Assert
    with patch("py_st.cli._helpers.agent.get_agent_info") as mock_get_agent:
        mock_get_agent.return_value = mock_agent
        with pytest.raises(typer.Exit) as exc_info:
            get_default_system("fake_token")

    assert (
        exc_info.value.exit_code == 1
    ), "Should exit with code 1 when headquarters is None"


def test_get_default_system_empty_headquarters() -> None:
    """Test get_default_system raises Exit when headquarters is empty."""
    # Arrange
    # Use model_construct to bypass validation and set headquarters to ""
    mock_agent = Agent.model_construct(
        accountId=None,
        symbol="TEST",
        headquarters="",
        credits=100,
        startingFaction="COSMIC",
        shipCount=1,
    )

    # Act & Assert
    with patch("py_st.cli._helpers.agent.get_agent_info") as mock_get_agent:
        mock_get_agent.return_value = mock_agent
        with pytest.raises(typer.Exit) as exc_info:
            get_default_system("fake_token")

    assert (
        exc_info.value.exit_code == 1
    ), "Should exit with code 1 when headquarters is empty string"


def test_get_default_system_malformed_symbol() -> None:
    """Test get_default_system raises Exit for malformed symbol."""
    # Arrange
    agent_data = AgentFactory.build_minimal()
    agent_data["headquarters"] = "MALFORMED"
    mock_agent = Agent.model_validate(agent_data)

    # Act & Assert
    with patch("py_st.cli._helpers.agent.get_agent_info") as mock_get_agent:
        mock_get_agent.return_value = mock_agent
        with pytest.raises(typer.Exit) as exc_info:
            get_default_system("fake_token")

    assert (
        exc_info.value.exit_code == 1
    ), "Should exit with code 1 when headquarters has no hyphens"


def test_resolve_contract_id_passthrough() -> None:
    """Test resolve_contract_id returns full ID unchanged."""
    # Arrange
    token = "test-token"
    contract_id_arg = "my-contract-123"

    # Act
    result = resolve_contract_id(token, contract_id_arg)

    # Assert
    assert (
        result == "my-contract-123"
    ), "Should return full contract ID unchanged when input is not prefixed"


def test_resolve_contract_id_plain_digit_passthrough() -> None:
    """Test resolve_contract_id treats plain digits as IDs."""
    # Arrange
    token = "test-token"
    contract_id_arg = "0"

    # Act
    result = resolve_contract_id(token, contract_id_arg)

    # Assert
    assert (
        result == "0"
    ), "Should pass through plain digit as ID, not resolve as index"


def test_resolve_contract_id_index_lookup() -> None:
    """Test resolve_contract_id resolves prefixed index to contract ID."""
    # Arrange
    token = "test-token"
    contract_id_arg = "c-0"

    contract_data_1 = ContractFactory.build_minimal()
    contract_data_1["id"] = "contract-c"
    contract_data_2 = ContractFactory.build_minimal()
    contract_data_2["id"] = "contract-a"
    contract_data_3 = ContractFactory.build_minimal()
    contract_data_3["id"] = "contract-b"
    mock_contracts = [
        Contract.model_validate(contract_data_1),
        Contract.model_validate(contract_data_2),
        Contract.model_validate(contract_data_3),
    ]

    # Act
    with patch(
        "py_st.cli._helpers.contracts.list_contracts"
    ) as mock_list_contracts:
        mock_list_contracts.return_value = mock_contracts
        result = resolve_contract_id(token, contract_id_arg)

    # Assert
    assert (
        result == "contract-a"
    ), "Should resolve c-0 to first contract after sorting by id"
    mock_list_contracts.assert_called_once_with(token)


def test_resolve_contract_id_uppercase_prefix() -> None:
    """Test resolve_contract_id handles uppercase C- prefix."""
    # Arrange
    token = "test-token"
    contract_id_arg = "C-1"

    contract_data_1 = ContractFactory.build_minimal()
    contract_data_1["id"] = "contract-a"
    contract_data_2 = ContractFactory.build_minimal()
    contract_data_2["id"] = "contract-b"
    mock_contracts = [
        Contract.model_validate(contract_data_1),
        Contract.model_validate(contract_data_2),
    ]

    # Act
    with patch(
        "py_st.cli._helpers.contracts.list_contracts"
    ) as mock_list_contracts:
        mock_list_contracts.return_value = mock_contracts
        result = resolve_contract_id(token, contract_id_arg)

    # Assert
    assert (
        result == "contract-b"
    ), "Should resolve uppercase C-1 to second contract after sorting"
    mock_list_contracts.assert_called_once_with(token)


def test_resolve_contract_id_out_of_bounds() -> None:
    """Test resolve_contract_id raises Exit for invalid prefixed index."""
    # Arrange
    token = "test-token"
    contract_id_arg = "c-99"

    contract_data = ContractFactory.build_minimal()
    contract_data["id"] = "contract-a"
    mock_contracts = [Contract.model_validate(contract_data)]

    # Act & Assert
    with patch(
        "py_st.cli._helpers.contracts.list_contracts"
    ) as mock_list_contracts:
        mock_list_contracts.return_value = mock_contracts
        with pytest.raises(typer.Exit) as exc_info:
            resolve_contract_id(token, contract_id_arg)

    assert (
        exc_info.value.exit_code == 1
    ), "Should exit with code 1 for invalid index"
    mock_list_contracts.assert_called_once_with(token)


def test_resolve_contract_id_invalid_prefix_format() -> None:
    """Test resolve_contract_id treats c-abc as an ID (not an index)."""
    # Arrange
    token = "test-token"
    contract_id_arg = "c-abc"

    # Act
    result = resolve_contract_id(token, contract_id_arg)

    # Assert
    assert (
        result == "c-abc"
    ), "Should pass through c-abc as ID since it's not c-<digits>"
