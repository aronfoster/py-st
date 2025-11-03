"""Services for agent-related operations."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
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
    account_token: str | None = None,
    symbol: str | None = None,
    faction: str | None = None,
    clear_cache_after: bool = False,
) -> RegisterAgentResponseData:
    """
    Register a new agent using the account token.

    Resolves account_token, symbol, and faction from environment
    variables if not provided. Validates required fields, registers
    the agent, saves the token to .env, and optionally clears cache.

    Args:
        account_token: Account token (reads from
            SPACETRADERS_ACCOUNT_TOKEN env var if not provided).
        symbol: Agent symbol (reads from DEFAULT_AGENT_SYMBOL
            env var if not provided).
        faction: Faction (reads from DEFAULT_AGENT_FACTION
            env var if not provided).
        clear_cache_after: Whether to clear cache after registration.

    Returns:
        The registration response data (contains agent, contract,
        faction, ship, and token).

    Raises:
        ValueError: If account_token, symbol, or faction is missing.
    """
    load_dotenv()

    resolved_account_token = account_token or os.getenv(
        "SPACETRADERS_ACCOUNT_TOKEN"
    )
    if not resolved_account_token:
        raise ValueError(
            "Missing account token. Set --account-token or "
            "SPACETRADERS_ACCOUNT_TOKEN env var."
        )

    resolved_symbol = symbol or os.getenv("DEFAULT_AGENT_SYMBOL")
    if not resolved_symbol:
        raise ValueError(
            "Missing agent symbol. Set --symbol or "
            "DEFAULT_AGENT_SYMBOL env var."
        )

    resolved_faction = faction or os.getenv("DEFAULT_AGENT_FACTION")
    if not resolved_faction:
        raise ValueError(
            "Missing faction. Set --faction or "
            "DEFAULT_AGENT_FACTION env var."
        )

    client = SpaceTradersClient(token=resolved_account_token)
    response = client.agent.register_agent(
        symbol=resolved_symbol, faction=resolved_faction
    )

    save_agent_token(response.data.token)

    if clear_cache_after:
        cache.clear_cache()

    return response.data
