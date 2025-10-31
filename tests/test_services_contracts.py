"""Unit tests for contract-related functions in services/contracts.py."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

from py_st._generated.models import Agent, Contract
from py_st.services import contracts
from tests.factories import AgentFactory, ContractFactory


@patch("py_st.services.contracts.cache.save_cache")
@patch("py_st.services.contracts.cache.load_cache")
@patch("py_st.services.contracts.SpaceTradersClient")
def test_list_contracts(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_contracts returns a list of Contract objects."""
    # Arrange
    mock_load_cache.return_value = {}

    contract1_data = ContractFactory.build_minimal()
    contract2_data = ContractFactory.build_minimal()
    contract2_data["id"] = "contract-2"

    contract1 = Contract.model_validate(contract1_data)
    contract2 = Contract.model_validate(contract2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.contracts.get_contracts.return_value = [contract1, contract2]

    # Act
    result = contracts.list_contracts("fake_token")

    # Assert
    assert isinstance(result, list), "Should return a list"
    assert len(result) == 2, "Should return 2 contracts"
    assert all(
        isinstance(c, Contract) for c in result
    ), "All items should be Contract objects"
    assert result[0].id == "contract-1", "First contract ID should match"
    assert result[1].id == "contract-2", "Second contract ID should match"

    mock_client.contracts.get_contracts.assert_called_once()


@patch("py_st.services.contracts.cache.save_cache")
@patch("py_st.services.contracts.cache.load_cache")
@patch("py_st.services.contracts.SpaceTradersClient")
def test_list_contracts_cache_hit(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_contracts returns cached data when cache is clean."""
    # Arrange
    now = datetime.now(UTC)

    contract1_data = ContractFactory.build_minimal()
    contract2_data = ContractFactory.build_minimal()
    contract2_data["id"] = "contract-2"

    cached_contracts = [contract1_data, contract2_data]

    mock_load_cache.return_value = {
        "contract_list": {
            "last_updated": now.isoformat(),
            "is_dirty": False,
            "data": cached_contracts,
        }
    }

    # Act
    result = contracts.list_contracts("fake_token")

    # Assert
    assert isinstance(result, list), "Should return list of contracts"
    assert len(result) == 2, "Should return 2 cached contracts"
    assert all(
        isinstance(c, Contract) for c in result
    ), "All items should be Contract objects"
    assert result[0].id == "contract-1", "First contract ID should match"
    assert result[1].id == "contract-2", "Second contract ID should match"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_not_called()
    mock_client_class.assert_not_called()


@patch("py_st.services.contracts.cache.save_cache")
@patch("py_st.services.contracts.cache.load_cache")
@patch("py_st.services.contracts.SpaceTradersClient")
def test_list_contracts_cache_miss_dirty(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_contracts fetches fresh data when cache is dirty."""
    # Arrange
    now = datetime.now(UTC)

    old_contract_data = ContractFactory.build_minimal()
    old_contract_data["id"] = "old-contract"

    mock_load_cache.return_value = {
        "contract_list": {
            "last_updated": now.isoformat(),
            "is_dirty": True,
            "data": [old_contract_data],
        }
    }

    new_contract1_data = ContractFactory.build_minimal()
    new_contract2_data = ContractFactory.build_minimal()
    new_contract2_data["id"] = "new-contract-2"

    new_contract1 = Contract.model_validate(new_contract1_data)
    new_contract2 = Contract.model_validate(new_contract2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.contracts.get_contracts.return_value = [
        new_contract1,
        new_contract2,
    ]

    # Act
    result = contracts.list_contracts("fake_token")

    # Assert
    assert isinstance(result, list), "Should return list of contracts"
    assert len(result) == 2, "Should return 2 fresh contracts"
    assert (
        result[0].id == "contract-1"
    ), "Should have new data, not old cached data"
    assert (
        result[1].id == "new-contract-2"
    ), "Should have new data, not old cached data"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_called_once()
    mock_client.contracts.get_contracts.assert_called_once()

    saved_cache = mock_save_cache.call_args[0][0]
    assert (
        saved_cache["contract_list"]["is_dirty"] is False
    ), "Saved cache should have is_dirty set to False"


@patch("py_st.services.contracts.cache.save_cache")
@patch("py_st.services.contracts.cache.load_cache")
@patch("py_st.services.contracts.SpaceTradersClient")
def test_list_contracts_cache_miss_not_found(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test list_contracts fetches data when cache entry doesn't exist."""
    # Arrange
    mock_load_cache.return_value = {}

    contract1_data = ContractFactory.build_minimal()
    contract2_data = ContractFactory.build_minimal()
    contract2_data["id"] = "contract-2"

    contract1 = Contract.model_validate(contract1_data)
    contract2 = Contract.model_validate(contract2_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.contracts.get_contracts.return_value = [contract1, contract2]

    # Act
    result = contracts.list_contracts("fake_token")

    # Assert
    assert isinstance(result, list), "Should return list of contracts"
    assert len(result) == 2, "Should return 2 contracts from API"
    assert result[0].id == "contract-1", "First contract ID should match"
    assert result[1].id == "contract-2", "Second contract ID should match"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_called_once()
    mock_client.contracts.get_contracts.assert_called_once()


@patch("py_st.services.contracts.cache.save_cache")
@patch("py_st.services.contracts.cache.load_cache")
@patch("py_st.services.contracts.SpaceTradersClient")
def test_accept_contract(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test accept_contract calls client and marks cache dirty."""
    # Arrange
    mock_load_cache.return_value = {
        "contract_list": {
            "last_updated": "2024-01-01T00:00:00Z",
            "is_dirty": False,
            "data": [],
        }
    }

    agent_data = AgentFactory.build_minimal()
    contract_data = ContractFactory.build_minimal()
    agent = Agent.model_validate(agent_data)
    contract = Contract.model_validate(contract_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.contracts.accept_contract.return_value = {
        "agent": agent,
        "contract": contract,
    }

    # Act
    result_agent, result_contract = contracts.accept_contract(
        "fake_token", "contract-1"
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert isinstance(
        result_contract, Contract
    ), "Should return Contract object"

    mock_client.contracts.accept_contract.assert_called_once_with("contract-1")

    mock_save_cache.assert_called_once()
    saved_cache = mock_save_cache.call_args[0][0]
    assert (
        saved_cache["contract_list"]["is_dirty"] is True
    ), "Should mark contract list cache as dirty"
    assert (
        saved_cache["contract_list"]["last_updated"] == "2024-01-01T00:00:00Z"
    ), "Should not update timestamp"


@patch("py_st.services.contracts.cache.save_cache")
@patch("py_st.services.contracts.cache.load_cache")
@patch("py_st.services.contracts.SpaceTradersClient")
def test_mark_contract_list_dirty_no_cache(
    mock_client_class: Any, mock_load_cache: Any, mock_save_cache: Any
) -> None:
    """Test contract-mutating operations skip dirty-flag when cache missing."""
    # Arrange
    mock_load_cache.return_value = {}

    agent_data = AgentFactory.build_minimal()
    contract_data = ContractFactory.build_minimal()
    agent = Agent.model_validate(agent_data)
    contract = Contract.model_validate(contract_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.contracts.accept_contract.return_value = {
        "agent": agent,
        "contract": contract,
    }

    # Act
    result_agent, result_contract = contracts.accept_contract(
        "fake_token", "contract-1"
    )

    # Assert
    assert isinstance(result_agent, Agent), "Should return Agent object"
    assert isinstance(
        result_contract, Contract
    ), "Should return Contract object"

    mock_load_cache.assert_called_once()
    mock_save_cache.assert_not_called()
