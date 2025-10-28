# src/py_st/cli/_errors.py
from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import ParamSpec, TypeVar, cast

import typer

from py_st.client.transport import APIError

P = ParamSpec("P")
R = TypeVar("R")


def handle_errors(  # noqa: UP047
    original_function: Callable[P, R],
) -> Callable[P, R]:
    """
    Decorator for Typer commands:
    - Catches APIError and prints a friendly message.
    - Prints payload JSON if present; falls back to str(payload).
    - Exits cleanly with code 1 (no traceback).
    """

    @functools.wraps(original_function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
        try:
            return original_function(*args, **kwargs)
        except APIError as api_error:
            typer.secho(f"API error: {api_error}", fg=typer.colors.RED)
            payload = getattr(api_error, "payload", None)
            if payload:
                try:
                    typer.echo(json.dumps(payload, indent=2))
                except Exception:
                    typer.echo(str(payload))
            raise typer.Exit(code=1) from None

    return cast(Callable[P, R], wrapper)
