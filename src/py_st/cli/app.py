from __future__ import annotations

import typer

from . import agent_cmd, contracts_cmd, ships_cmd, systems_cmd

app = typer.Typer(help="SpaceTraders CLI for py-st")
app.add_typer(contracts_cmd.contracts_app, name="contracts")
app.add_typer(ships_cmd.ships_app, name="ships")
app.add_typer(systems_cmd.systems_app, name="systems")
app.add_typer(agent_cmd.agent_app, name="agent")


@app.callback()
def callback() -> None:
    """
    SpaceTraders CLI for py-st
    """


def main() -> None:
    app()


if __name__ == "__main__":
    main()
