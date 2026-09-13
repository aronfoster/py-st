from __future__ import annotations

import json
import logging

import typer

from ..services import agent
from .options import (
    ACCOUNT_TOKEN_OPTION,
    AGENT_FACTION_OPTION,
    AGENT_SYMBOL_OPTION,
    SHOW_OPTION,
    TOKEN_OPTION,
    VERBOSE_OPTION,
    _get_token,
)

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
    account_token: str | None = ACCOUNT_TOKEN_OPTION,
    symbol: str | None = AGENT_SYMBOL_OPTION,
    faction: str | None = AGENT_FACTION_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """
    Register a new agent using an account token.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        data = agent.register_new_agent(
            account_token=account_token,
            symbol=symbol,
            faction=faction,
        )

        print(
            f"Registered agent {data.agent.symbol}. "
            "Token saved to the working directory's .env; cache cleared."
        )
        print(
            "Verification pending. Run: py-st agent verify-registration "
            f"--symbol {data.agent.symbol} "
            f"--faction {data.agent.startingFaction}"
        )

    except (agent.RegistrationError, ValueError) as e:
        print(f"Registration failed: {e}")
        raise typer.Exit(code=1) from e


@agent_app.command("verify-registration")
def verify_registration(
    symbol: str = typer.Option(..., "--symbol", help="Expected agent symbol."),
    faction: str = typer.Option(..., "--faction", help="Expected faction."),
) -> None:
    """Verify the local saved token using fresh read-only GETs."""
    try:
        current, ships, contracts = agent.verify_registration(symbol, faction)
    except agent.RegistrationError as exc:
        print(str(exc))
        raise typer.Exit(code=1) from exc
    print(
        f"Verified agent {current.symbol}; faction {current.startingFaction}; "
        f"HQ {current.headquarters}; credits {current.credits}."
    )
    for ship in ships:
        print(
            f"Ship {ship.symbol}: {ship.registration.role.value}, "
            f"{ship.nav.waypointSymbol}, {ship.nav.status.value}."
        )
    for contract in contracts:
        print(
            f"Contract {contract.id}: {contract.factionSymbol}, "
            f"accepted={contract.accepted}, fulfilled={contract.fulfilled}."
        )
