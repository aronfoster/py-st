from __future__ import annotations

import json
import logging
import os

import typer
from dotenv import load_dotenv

from .client import SpaceTraders

app = typer.Typer(help="SpaceTraders CLI for py-st")


@app.callback()
def callback() -> None:
    """
    SpaceTraders CLI for py-st
    """


def _get_token(token: str | None) -> str:
    load_dotenv()
    t = token or os.getenv("ST_TOKEN")
    if not t:
        raise typer.BadParameter(
            "Missing token. Set --token or ST_TOKEN env var."
        )
    return t


@app.command("agent")
def agent(
    show: bool = typer.Option(True, help="Show current agent info."),
    token: str | None = typer.Option(None, help="API token (overrides env)."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbose logging."
    ),
) -> None:
    """
    Query and print agent info.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    t = _get_token(token)
    client = SpaceTraders(token=t)
    if show:
        agent = client.get_agent()
        # print as JSON for easy piping / inspection
        print(json.dumps(agent.model_dump(), indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
