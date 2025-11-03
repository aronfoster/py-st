from __future__ import annotations

import json
import logging
import os

import typer
from dotenv import load_dotenv

from .. import cache
from ..client.transport import APIError
from ..services import agent
from .options import SHOW_OPTION, TOKEN_OPTION, VERBOSE_OPTION, _get_token

agent_app: typer.Typer = typer.Typer(help="Manage agent information.")


@agent_app.command("info")
def agent_info(
    show: bool = SHOW_OPTION,
    token: str | None = TOKEN_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Query and print agent info.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    if show:
        agent_info_data = agent.get_agent_info(t)
        print(json.dumps(agent_info_data.model_dump(mode="json"), indent=2))


@agent_app.command("register")
def register(
    account_token: str | None = typer.Option(
        None,
        "--account-token",
        help=(
            "Account token. Reads from SPACETRADERS_ACCOUNT_TOKEN "
            "env var if not provided."
        ),
    ),
    symbol: str | None = typer.Option(
        None,
        "--symbol",
        help=(
            "Agent symbol. Reads from DEFAULT_AGENT_SYMBOL "
            "env var if not provided."
        ),
    ),
    faction: str | None = typer.Option(
        None,
        "--faction",
        help=(
            "Faction. Reads from DEFAULT_AGENT_FACTION "
            "env var if not provided."
        ),
    ),
    clear_cache_flag: bool = typer.Option(
        False,
        "--clear-cache",
        help="Clear all cached data after registration.",
    ),
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Register a new agent using an account token.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    load_dotenv()

    account_token_to_use = account_token or os.getenv(
        "SPACETRADERS_ACCOUNT_TOKEN"
    )
    if not account_token_to_use:
        raise typer.BadParameter(
            "Missing account token. Set --account-token or "
            "SPACETRADERS_ACCOUNT_TOKEN env var."
        )

    symbol_to_use = symbol or os.getenv("DEFAULT_AGENT_SYMBOL")
    faction_to_use = faction or os.getenv("DEFAULT_AGENT_FACTION")

    try:
        data = agent.register_new_agent(
            account_token=account_token_to_use,
            symbol=symbol_to_use,
            faction=faction_to_use,
        )

        if clear_cache_flag:
            cache.clear_cache()
            print("Cache cleared.")

        agent_data = data.get("agent", {})
        agent_symbol = agent_data.get("symbol", "UNKNOWN")
        print(
            f"Successfully registered agent {agent_symbol}. "
            "Token saved to .env."
        )

    except APIError as e:
        print(f"API Error: {e}")
        raise typer.Exit(code=1) from e
    except (ValueError, KeyError) as e:
        print(f"Registration failed: {e}")
        raise typer.Exit(code=1) from e
