"""Services for agent-related operations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from py_st import cache
from py_st._generated.models import Agent
from py_st._manual_models import RegisterAgentResponseData
from py_st.client import SpaceTradersClient
from py_st.env import save_agent_token
from py_st.services.cache_keys import key_for_agent

# Cache configuration for agent info
CACHE_STALENESS_THRESHOLD = timedelta(hours=1)


def get_agent_info(token: str) -> Agent:
    """
    Fetches agent data from the API with caching.

    Checks the cache first and returns cached data if it's fresh
    (less than 1 hour old). Otherwise, fetches from the API and
    updates the cache.
    """
    # Load cache
    full_cache = cache.load_cache()

    # Check for cached entry
    cached_entry = full_cache.get(key_for_agent())
    if cached_entry is not None and isinstance(cached_entry, dict):
        try:
            # Try to parse timestamp
            last_updated_str = cached_entry.get("last_updated")
            if last_updated_str is None or not isinstance(
                last_updated_str, str
            ):
                raise ValueError("Missing or invalid last_updated")

            # Parse ISO format timestamp
            last_updated = datetime.fromisoformat(last_updated_str)

            # Ensure timezone-aware (assume UTC if naive)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=UTC)

            # Check if cache is fresh
            if datetime.now(UTC) - last_updated < CACHE_STALENESS_THRESHOLD:
                # Try to parse agent data
                agent = Agent.model_validate(cached_entry["data"])
                return agent

        except (ValueError, ValidationError, KeyError) as e:
            logging.warning("Invalid cache entry for agent info: %s", e)

    # Cache miss or stale - fetch from API
    client = SpaceTradersClient(token=token)
    agent = client.agent.get_agent()

    # Update cache
    now_utc = datetime.now(UTC)
    now_iso = now_utc.isoformat()
    new_entry = {
        "last_updated": now_iso,
        "data": agent.model_dump(mode="json"),
    }
    full_cache[key_for_agent()] = new_entry
    cache.save_cache(full_cache)

    return agent


def register_new_agent(
    account_token: str, symbol: str | None, faction: str | None
) -> RegisterAgentResponseData:
    """
    Register a new agent using the account token.

    Creates a temporary client with the account token, calls the
    registration endpoint, extracts and saves the new agent token
    to .env, and returns the registration response data.

    Args:
        account_token: The master account token for registration.
        symbol: The desired agent symbol (callsign), or None.
        faction: The desired faction, or None.

    Returns:
        The registration response data (contains agent, contract,
        faction, ship, and token).
    """
    client = SpaceTradersClient(token=account_token)
    response = client.agent.register_agent(symbol=symbol, faction=faction)

    save_agent_token(response.data.token)

    return response.data
