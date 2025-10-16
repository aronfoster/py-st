from __future__ import annotations

import re
from datetime import datetime

import typer
from typer.testing import CliRunner

from py_st.cli._errors import handle_errors
from py_st.client.transport import APIError


def build_app() -> typer.Typer:
    app = typer.Typer()

    @app.command("ok")
    @handle_errors
    def ok_cmd() -> None:
        typer.echo("OK")

    @app.command("apierror")
    @handle_errors
    def api_error_cmd() -> None:
        raise APIError(
            "Boom from API",
            status=400,
            payload={"error": {"message": "Boom from API"}, "code": 123},
        )

    @app.command("apierror-nonjson")
    @handle_errors
    def api_error_nonjson_cmd() -> None:
        # datetime is not JSON-serializable by default
        raise APIError(
            "Non-JSON payload",
            status=500,
            payload={"when": datetime(2030, 1, 2, 3, 4, 5)},
        )

    return app


runner = CliRunner()


def test_ok_command_succeeds() -> None:
    app = build_app()
    result = runner.invoke(app, ["ok"])
    assert result.exit_code == 0
    assert "OK" in result.stdout
    assert "Traceback" not in result.stdout


def test_api_error_prints_message_and_payload_and_exits_1() -> None:
    app = build_app()
    result = runner.invoke(app, ["apierror"])
    assert result.exit_code == 1
    assert "API error: Boom from API" in result.stdout
    # pretty JSON dumped
    assert '"code": 123' in result.stdout
    assert '"message": "Boom from API"' in result.stdout
    assert "Traceback" not in result.stdout


def test_api_error_with_nonjson_payload_falls_back_to_str() -> None:
    app = build_app()
    result = runner.invoke(app, ["apierror-nonjson"])
    assert result.exit_code == 1
    assert "API error: Non-JSON payload" in result.stdout
    # stringified dict; allow either repr with datetime(...) or at least key
    has_dt = re.search(r"datetime\.datetime\(", result.stdout) is not None
    assert has_dt or "when" in result.stdout
    assert "Traceback" not in result.stdout
