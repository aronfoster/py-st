"""Local flight application setup and independent worker entry points."""

from __future__ import annotations

import getpass
import os
import sqlite3
import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

import httpx
import typer
from dotenv import load_dotenv

from py_st.client import APIError, SpaceTradersClient
from py_st.services.automation import SafetyStop
from py_st.services.dashboard import dashboard_server
from py_st.services.flight_auth import save_password
from py_st.services.flight_demo import (
    SCOPE,
    create_demo,
    demo_client,
    scenario,
)
from py_st.services.flight_queue import FlightQueue, canonical_root
from py_st.services.flight_worker import FlightWorker
from py_st.services.intelligence import Intelligence
from py_st.services.stop_control import request_stop

flight_app = typer.Typer(help="Authenticated local flight operations")
P = ParamSpec("P")
R = TypeVar("R")


def safe_errors(function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return function(*args, **kwargs)
        except (APIError, httpx.HTTPError) as exc:
            typer.echo(
                f"Flight stopped: {type(exc).__name__}; inspect worker state",
                err=True,
            )
            raise typer.Exit(1) from None
        except (SafetyStop, ValueError, OSError, sqlite3.Error) as exc:
            typer.echo(f"Flight stopped: {exc}", err=True)
            raise typer.Exit(1) from None

    return wrapped


def live_client() -> SpaceTradersClient:
    root = canonical_root()
    load_dotenv(root / ".env")
    token = os.environ.get("ST_TOKEN")
    if not token:
        raise ValueError("Set ST_TOKEN in canonical-root .env, never argv")
    return SpaceTradersClient(token)


@flight_app.command()
@safe_errors
def setup(demo: bool = False) -> None:
    """Initialize flight commands over existing history or a new demo."""
    root = canonical_root()
    if (root / ".state/flight.sqlite3").exists():
        raise typer.BadParameter(
            "Flight state already exists; do not reinitialize"
        )
    password = getpass.getpass("New local owner password (blank allowed): ")
    if password != getpass.getpass("Confirm local owner password: "):
        raise typer.BadParameter("Passwords differ")
    if demo:
        create_demo(root)
        scope = SCOPE
    else:
        store = Intelligence(
            root / ".state/intelligence.sqlite3", existing_only=True
        )
        try:
            with live_client() as client:
                status = client.status()
                agent = client.request("GET", "/my/agent")
                if not isinstance(agent, dict):
                    raise ValueError("Invalid agent identity")
                scope = f"{status['resetDate']}:{agent['symbol']}"
                if scope not in store.scopes():
                    request_stop(root)
                    raise ValueError(
                        "Account/reset absent from existing ledger"
                    )
        except APIError as exc:
            if exc.authentication_failed:
                request_stop(root)
            raise
        finally:
            store.close()
    save_password(root, password)
    queue = FlightQueue(
        root, create=True, scope=scope, mode="demo" if demo else "live"
    )
    queue.close()
    request_stop(root)
    typer.echo(
        "Flight setup complete, paused. Start worker and serve; "
        "log in to resume."
    )


@flight_app.command()
@safe_errors
def serve(port: int = 8765) -> None:
    """Serve the authenticated loopback application; holds no game token."""
    root = canonical_root()
    queue = FlightQueue(root)
    queue.close()
    server = dashboard_server(root, port)
    typer.echo(f"Flight Ledger: http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


@flight_app.command()
@safe_errors
def worker(once: bool = False) -> None:
    """Execute persisted commands independently of the browser."""
    root = canonical_root()
    queue = FlightQueue(root)
    mode = queue.settings["mode"]
    queue.close()
    with demo_client(root) if mode == "demo" else live_client() as client:
        runner = FlightWorker(root, client)
        try:
            while True:
                runner.tick()
                if once:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            runner.close()


@flight_app.command("demo-scenario")
@safe_errors
def demo_scenario(name: str) -> None:
    """Inject low-fuel, low-funds or lost-response into the offline world."""
    root = canonical_root()
    queue = FlightQueue(root)
    try:
        if queue.settings["mode"] != "demo":
            raise typer.BadParameter(
                "Scenarios only apply to isolated demo mode"
            )
        scenario(root, name)
    finally:
        queue.close()
