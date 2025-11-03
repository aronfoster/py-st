"""Unit tests for agent-related functions in services/agent.py."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from py_st._manual_models import RegisterAgentResponse
from py_st.services import agent
from tests.factories import RegisterAgentResponseDataFactory


@patch("py_st.services.agent.save_agent_token")
@patch("py_st.services.agent.cache.clear_cache")
@patch("py_st.services.agent.load_dotenv")
@patch("py_st.services.agent.os.getenv")
@patch("py_st.services.agent.SpaceTradersClient")
def test_register_new_agent_with_all_params(
    mock_client_class: Any,
    mock_getenv: Any,
    mock_load_dotenv: Any,
    mock_clear_cache: Any,
    mock_save_token: Any,
) -> None:
    """Test register_new_agent with all params provided."""
    # Arrange
    from py_st._manual_models import RegisterAgentResponseData

    response_data_dict = RegisterAgentResponseDataFactory.build_minimal()
    response_data = RegisterAgentResponseData.model_validate(
        response_data_dict
    )
    response = RegisterAgentResponse(data=response_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.agent.register_agent.return_value = response

    # Act
    result = agent.register_new_agent(
        account_token="account-token-123",
        symbol="TEST",
        faction="COSMIC",
        clear_cache_after=True,
    )

    # Assert
    assert result.agent.symbol == "FOO", "Should return agent data with symbol"
    assert (
        result.token == "test-agent-token-123"
    ), "Should return correct token"

    mock_client.agent.register_agent.assert_called_once_with(
        symbol="TEST", faction="COSMIC"
    )
    mock_save_token.assert_called_once_with("test-agent-token-123")
    mock_clear_cache.assert_called_once()


@patch("py_st.services.agent.save_agent_token")
@patch("py_st.services.agent.cache.clear_cache")
@patch("py_st.services.agent.load_dotenv")
@patch("py_st.services.agent.os.getenv")
@patch("py_st.services.agent.SpaceTradersClient")
def test_register_new_agent_from_env_vars(
    mock_client_class: Any,
    mock_getenv: Any,
    mock_load_dotenv: Any,
    mock_clear_cache: Any,
    mock_save_token: Any,
) -> None:
    """Test register_new_agent resolves params from env vars."""

    # Arrange
    def getenv_side_effect(key: str) -> str | None:
        env_vars = {
            "SPACETRADERS_ACCOUNT_TOKEN": "env-account-token",
            "DEFAULT_AGENT_SYMBOL": "ENV-AGENT",
            "DEFAULT_AGENT_FACTION": "ENV-FACTION",
        }
        return env_vars.get(key)

    mock_getenv.side_effect = getenv_side_effect

    from py_st._manual_models import RegisterAgentResponseData

    response_data_dict = RegisterAgentResponseDataFactory.build_minimal()
    response_data = RegisterAgentResponseData.model_validate(
        response_data_dict
    )
    response = RegisterAgentResponse(data=response_data)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.agent.register_agent.return_value = response

    # Act
    result = agent.register_new_agent()

    # Assert
    assert (
        result.token == "test-agent-token-123"
    ), "Should return correct token"
    mock_client.agent.register_agent.assert_called_once_with(
        symbol="ENV-AGENT", faction="ENV-FACTION"
    )
    mock_save_token.assert_called_once_with("test-agent-token-123")
    mock_clear_cache.assert_not_called()


@patch("py_st.services.agent.load_dotenv")
@patch("py_st.services.agent.os.getenv")
def test_register_new_agent_missing_account_token(
    mock_getenv: Any, mock_load_dotenv: Any
) -> None:
    """Test register_new_agent raises error if account token missing."""
    # Arrange
    mock_getenv.return_value = None

    # Act & Assert
    with pytest.raises(ValueError, match="Missing account token"):
        agent.register_new_agent()


@patch("py_st.services.agent.load_dotenv")
@patch("py_st.services.agent.os.getenv")
def test_register_new_agent_missing_symbol(
    mock_getenv: Any, mock_load_dotenv: Any
) -> None:
    """Test register_new_agent raises error if symbol missing."""

    # Arrange
    def getenv_side_effect(key: str) -> str | None:
        if key == "SPACETRADERS_ACCOUNT_TOKEN":
            return "account-token"
        return None

    mock_getenv.side_effect = getenv_side_effect

    # Act & Assert
    with pytest.raises(ValueError, match="Missing agent symbol"):
        agent.register_new_agent()


@patch("py_st.services.agent.load_dotenv")
@patch("py_st.services.agent.os.getenv")
def test_register_new_agent_missing_faction(
    mock_getenv: Any, mock_load_dotenv: Any
) -> None:
    """Test register_new_agent raises error if faction missing."""

    # Arrange
    def getenv_side_effect(key: str) -> str | None:
        env_vars = {
            "SPACETRADERS_ACCOUNT_TOKEN": "account-token",
            "DEFAULT_AGENT_SYMBOL": "TEST",
        }
        return env_vars.get(key)

    mock_getenv.side_effect = getenv_side_effect

    # Act & Assert
    with pytest.raises(ValueError, match="Missing faction"):
        agent.register_new_agent()
