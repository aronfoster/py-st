"""Unit tests for the caching behavior of services.get_agent_info."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

from py_st import services
from py_st._generated.models import Agent
from tests.factories import AgentFactory


@patch("py_st.services.SpaceTradersClient")
@patch("py_st.services.cache.save_cache")
@patch("py_st.services.cache.load_cache")
def test_get_agent_info_cache_hit(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test get_agent_info returns cached data when cache is fresh."""
    # Create mock agent data using AgentFactory
    mock_agent_data = AgentFactory.build_minimal()

    # Calculate a recent timestamp (30 minutes ago)
    recent_timestamp = datetime.now(timezone.utc) - timedelta(minutes=30)
    recent_iso_timestamp = recent_timestamp.isoformat()

    # Prepare cached entry with recent data
    cached_entry = {
        "last_updated": recent_iso_timestamp,
        "data": mock_agent_data,
    }

    # Configure mock to return cached data
    mock_load_cache.return_value = {"agent_info": cached_entry}

    # Configure client to raise exception if called (shouldn't be called)
    mock_client_class.return_value.agent.get_agent.side_effect = RuntimeError(
        "API should not be called on cache hit"
    )

    # Call the function
    result = services.get_agent_info("fake_token")

    # Assert the result is an Agent instance matching mock data
    assert isinstance(result, Agent)
    assert result.symbol == mock_agent_data["symbol"]
    assert result.credits == mock_agent_data["credits"]
    assert result.headquarters == mock_agent_data["headquarters"]

    # Assert API was not called
    assert mock_client_class.return_value.agent.get_agent.call_count == 0

    # Assert cache was not saved (data was fresh)
    assert mock_save_cache.call_count == 0


@patch("py_st.services.SpaceTradersClient")
@patch("py_st.services.cache.save_cache")
@patch("py_st.services.cache.load_cache")
def test_get_agent_info_cache_miss_stale(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test get_agent_info fetches from API when cached data is stale."""
    # Create mock old agent data
    mock_old_agent_data = AgentFactory.build_minimal()
    mock_old_agent_data["credits"] = 100

    # Calculate a stale timestamp (2 hours ago)
    stale_timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
    stale_iso_timestamp = stale_timestamp.isoformat()

    # Prepare stale cached entry
    stale_cached_entry = {
        "last_updated": stale_iso_timestamp,
        "data": mock_old_agent_data,
    }

    # Configure mock to return stale cached data
    mock_load_cache.return_value = {"agent_info": stale_cached_entry}

    # Create mock new agent data
    mock_new_agent_data = AgentFactory.build_minimal()
    mock_new_agent_data["credits"] = 200
    mock_new_agent_object = Agent.model_validate(mock_new_agent_data)

    # Configure client to return new agent data
    mock_client_class.return_value.agent.get_agent.return_value = (
        mock_new_agent_object
    )

    # Call the function
    result = services.get_agent_info("fake_token")

    # Assert the result matches the new agent object
    assert isinstance(result, Agent)
    assert result.symbol == mock_new_agent_data["symbol"]
    assert result.credits == 200  # New credits, not old 100

    # Assert API was called once
    assert mock_client_class.return_value.agent.get_agent.call_count == 1

    # Assert cache was saved once
    assert mock_save_cache.call_count == 1

    # Check that save_cache was called with correct data
    saved_cache = mock_save_cache.call_args[0][0]
    assert "agent_info" in saved_cache
    assert "last_updated" in saved_cache["agent_info"]
    assert "data" in saved_cache["agent_info"]

    # Parse and verify timestamp is recent
    saved_timestamp = datetime.fromisoformat(
        saved_cache["agent_info"]["last_updated"]
    )
    time_diff = datetime.now(timezone.utc) - saved_timestamp
    assert time_diff < timedelta(seconds=5), "Saved timestamp should be recent"

    # Verify saved data matches new agent
    assert saved_cache["agent_info"]["data"]["credits"] == 200


@patch("py_st.services.SpaceTradersClient")
@patch("py_st.services.cache.save_cache")
@patch("py_st.services.cache.load_cache")
def test_get_agent_info_cache_miss_not_found(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test get_agent_info fetches from API when cache is empty."""
    # Configure mock to return empty cache
    mock_load_cache.return_value = {}

    # Create mock new agent data
    mock_new_agent_data = AgentFactory.build_minimal()
    mock_new_agent_data["credits"] = 300
    mock_new_agent_object = Agent.model_validate(mock_new_agent_data)

    # Configure client to return new agent data
    mock_client_class.return_value.agent.get_agent.return_value = (
        mock_new_agent_object
    )

    # Call the function
    result = services.get_agent_info("fake_token")

    # Assert the result matches the new agent object
    assert isinstance(result, Agent)
    assert result.symbol == mock_new_agent_data["symbol"]
    assert result.credits == 300

    # Assert API was called once
    assert mock_client_class.return_value.agent.get_agent.call_count == 1

    # Assert cache was saved once
    assert mock_save_cache.call_count == 1

    # Check that save_cache was called with correct data
    saved_cache = mock_save_cache.call_args[0][0]
    assert "agent_info" in saved_cache
    assert "last_updated" in saved_cache["agent_info"]
    assert "data" in saved_cache["agent_info"]

    # Parse and verify timestamp is recent
    saved_timestamp = datetime.fromisoformat(
        saved_cache["agent_info"]["last_updated"]
    )
    time_diff = datetime.now(timezone.utc) - saved_timestamp
    assert time_diff < timedelta(seconds=5), "Saved timestamp should be recent"


@patch("py_st.services.SpaceTradersClient")
@patch("py_st.services.cache.save_cache")
@patch("py_st.services.cache.load_cache")
def test_get_agent_info_cache_invalid_timestamp(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test get_agent_info handles invalid timestamp in cached data."""
    # Create mock agent data
    mock_agent_data = AgentFactory.build_minimal()

    # Prepare cached entry with invalid timestamp
    invalid_ts_entry = {
        "last_updated": "not-a-timestamp",
        "data": mock_agent_data,
    }

    # Configure mock to return invalid cached data
    mock_load_cache.return_value = {"agent_info": invalid_ts_entry}

    # Create mock new agent data
    mock_new_agent_data = AgentFactory.build_minimal()
    mock_new_agent_data["credits"] = 400
    mock_new_agent_object = Agent.model_validate(mock_new_agent_data)

    # Configure client to return new agent data
    mock_client_class.return_value.agent.get_agent.return_value = (
        mock_new_agent_object
    )

    # Call the function
    result = services.get_agent_info("fake_token")

    # Assert API was called (invalid timestamp triggers cache miss)
    assert mock_client_class.return_value.agent.get_agent.call_count == 1

    # Assert cache was saved
    assert mock_save_cache.call_count == 1

    # Assert correct agent returned
    assert isinstance(result, Agent)
    assert result.credits == 400


@patch("py_st.services.SpaceTradersClient")
@patch("py_st.services.cache.save_cache")
@patch("py_st.services.cache.load_cache")
def test_get_agent_info_cache_invalid_data(
    mock_load_cache: Any, mock_save_cache: Any, mock_client_class: Any
) -> None:
    """Test get_agent_info handles invalid agent data in cache."""
    # Calculate a recent timestamp
    recent_timestamp = datetime.now(timezone.utc) - timedelta(minutes=30)
    recent_iso_timestamp = recent_timestamp.isoformat()

    # Prepare cached entry with invalid data (missing required field)
    invalid_data_entry = {
        "last_updated": recent_iso_timestamp,
        "data": {"credits": 100},  # Missing required 'symbol' field
    }

    # Configure mock to return invalid cached data
    mock_load_cache.return_value = {"agent_info": invalid_data_entry}

    # Create mock new agent data
    mock_new_agent_data = AgentFactory.build_minimal()
    mock_new_agent_data["credits"] = 500
    mock_new_agent_object = Agent.model_validate(mock_new_agent_data)

    # Configure client to return new agent data
    mock_client_class.return_value.agent.get_agent.return_value = (
        mock_new_agent_object
    )

    # Call the function
    result = services.get_agent_info("fake_token")

    # Assert API was called (invalid data triggers cache miss)
    assert mock_client_class.return_value.agent.get_agent.call_count == 1

    # Assert cache was saved
    assert mock_save_cache.call_count == 1

    # Assert correct agent returned
    assert isinstance(result, Agent)
    assert result.credits == 500
