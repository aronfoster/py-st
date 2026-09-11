"""Publishable read-only capability report."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from py_st.client.client import SpaceTradersClient
from py_st.client.transport import APIError
from py_st.services.capabilities import SnapshotTimeBudget, capability_snapshot


def snapshot(
    output: Annotated[
        Path | None, typer.Option(help="Save sanitized JSON to file.")
    ] = None,
) -> None:
    """Print fresh, sanitized JSON using ST_TOKEN; never mutate game state."""
    load_dotenv()
    token = os.getenv("ST_TOKEN", "")
    if not token:
        typer.echo(
            "Snapshot unavailable: ST_TOKEN is not configured.", err=True
        )
        raise typer.Exit(1)
    # Third-party debug logging and exception reprs are not publishable output.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    deadline = time.monotonic() + 180

    def wait(seconds: float) -> None:
        if time.monotonic() + seconds >= deadline:
            raise SnapshotTimeBudget("Snapshot time budget exhausted")
        time.sleep(seconds)

    try:
        with SpaceTradersClient(token) as client:
            client.set_wait(wait)
            report = capability_snapshot(client)
        rendered = json.dumps(report, indent=2, allow_nan=False)
        # Defense in depth even if credential material appears in allowed data.
        rendered = rendered.replace(token, "[REDACTED]")
    except Exception as exc:
        message = "Snapshot failed; no response or exception details emitted."
        if isinstance(exc, APIError) and exc.authentication_failed:
            message = (
                "Snapshot stopped: authentication/reset mismatch. Owner must "
                "check account/reset and refresh ST_TOKEN."
            )
        typer.echo(message, err=True)
        raise typer.Exit(1) from None
    finally:
        logging.disable(previous)

    if output is None:
        typer.echo(rendered)
        return
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    except OSError:
        typer.echo(
            "Snapshot collected, but file save failed; "
            "sanitized JSON follows on stdout.",
            err=True,
        )
        typer.echo(rendered)
        raise typer.Exit(1) from None
    typer.echo("Sanitized snapshot saved.")
