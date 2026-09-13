"""Services for agent-related operations."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from py_st import cache
from py_st._generated.models import Agent, Contract, FactionSymbol, Ship
from py_st._manual_models import RegisterAgentResponseData
from py_st.client.client import get_client as SpaceTradersClient
from py_st.client.transport import APIError
from py_st.env import (
    registration_env_path,
    save_agent_token,
    saved_agent_token,
)
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


class RegistrationError(RuntimeError):
    """Credential-free owner recovery guidance."""


def register_new_agent(
    account_token: str | None = None,
    symbol: str | None = None,
    faction: str | None = None,
) -> RegisterAgentResponseData:
    """
    Register a new agent using the account token.

    Resolves account_token, symbol, and faction from environment
    variables if not provided. Validates required fields, registers
    the agent, invalidates legacy cache, then atomically saves the token to
    the working directory's .env. Stop other application processes first.

    Args:
        account_token: Account token (reads from
            SPACETRADERS_ACCOUNT_TOKEN env var if not provided).
        symbol: Agent symbol (reads from DEFAULT_AGENT_SYMBOL
            env var if not provided).
        faction: Faction (reads from DEFAULT_AGENT_FACTION
            env var if not provided).

    Returns:
        The registration response data (contains agent, contract,
        faction, ship, and token).

    Raises:
        ValueError: If account_token, symbol, or faction is missing.
    """
    env_path = registration_env_path()
    try:
        load_dotenv(env_path)
    except (OSError, ValueError):
        raise RegistrationError(
            "Cannot read the working directory's .env. Fix its encoding "
            "or permissions before registration; no request was sent."
        ) from None

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

    resolved_symbol = resolved_symbol.strip().upper()
    resolved_faction = resolved_faction.strip().upper()
    if not 3 <= len(resolved_symbol) <= 14:
        raise ValueError("Agent symbol must be 3-14 characters.")
    # New upstream factions require regenerating the local model enum.
    if resolved_faction not in {f.value for f in FactionSymbol}:
        raise ValueError(
            "Unknown faction; choose an official faction symbol. If it was "
            "recently added upstream, regenerate the local models first."
        )

    try:
        client = SpaceTradersClient(token=resolved_account_token)
        response = client.agent.register_agent(
            symbol=resolved_symbol, faction=resolved_faction
        )
    except (APIError, httpx.HTTPError, ValueError) as exc:
        # API messages and validation errors can contain credentials/payloads.
        if isinstance(exc, APIError) and exc.authentication_failed:
            guidance = "Check the account token and reset/account status."
        else:
            guidance = (
                "Check the account dashboard for an existing pilot before "
                "retrying; the remote outcome may be unknown."
            )
        raise RegistrationError(
            "Registration not completed locally. Previous saved token, "
            f"cache and runtime state are unchanged. {guidance} "
            "See docs/REGISTRATION.md."
        ) from None

    try:
        # Never publish a new identity while the unscoped cache can survive.
        cache.clear_cache(strict=True)
        save_agent_token(response.data.token)
    except (OSError, ValueError):
        raise RegistrationError(
            "Pilot registered remotely, but local activation failed. "
            "The previous saved token is unchanged; cache may be cleared. "
            "Do not register again. Fix .env/cache permissions, regenerate "
            "this pilot's agent token in the account dashboard and save it "
            "privately. Follow docs/REGISTRATION.md before resuming."
        ) from None

    return response.data


def verify_registration(
    symbol: str, faction: str
) -> tuple[Agent, list[Ship], list[Contract]]:
    """Read saved-token identity and starter state, bypassing cache."""
    reason = (
        "Registration directory check failed. Run from the absolute "
        "ST_STATE_ROOT configured for the worker."
    )
    try:
        registration_env_path()
        reason = "Saved ST_TOKEN is missing or unreadable."
        client = SpaceTradersClient(token=saved_agent_token())
        reason = "Agent identity request failed."
        current = client.agent.get_agent()
        if (
            current.symbol != symbol.upper()
            or current.startingFaction != faction.upper()
        ):
            reason = (
                "Agent symbol/faction does not match the expected identity."
            )
            raise ValueError("Identity mismatch")
        reason = "Fleet request failed."
        ships = client.ships.get_ships()
        reason = "Contracts request failed."
        contracts = client.contracts.get_contracts()
        if (
            not ships
            or len(ships) != current.shipCount
            or any(
                not s.symbol.startswith(f"{current.symbol}-") for s in ships
            )
        ):
            reason = "Fleet is empty or its count/ownership is inconsistent."
            raise ValueError("Fleet mismatch")
        if not any(s.registration.role.value == "COMMAND" for s in ships):
            reason = "No COMMAND ship was found."
            raise ValueError("Missing command ship")
        if not any(
            c.factionSymbol == current.startingFaction for c in contracts
        ):
            reason = "No starting-faction contract was found."
            raise ValueError("Missing starting contract")
    except (APIError, httpx.HTTPError, OSError, ValueError) as exc:
        if isinstance(exc, APIError) and exc.authentication_failed:
            reason = (
                "Authentication/reset check failed (HTTP 401 or code 4113)."
            )
        raise RegistrationError(
            f"Registration verification failed: {reason} "
            "Keep gameplay stopped. "
            "Check the working directory's .env, expected symbol/faction "
            "and account dashboard/reset status. Recover the existing "
            "pilot's token if needed, then rerun agent verify-registration. "
            "Do not register again. See docs/REGISTRATION.md."
        ) from None
    return current, ships, contracts
