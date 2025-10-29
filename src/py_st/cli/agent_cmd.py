from __future__ import annotations

import json
import logging

import typer

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
