"""Waitress adapter for existing handlers, without stdlib HTTP parsing."""

from __future__ import annotations

import io
from http import HTTPStatus
from http.client import HTTPMessage
from pathlib import Path
from typing import Any

from waitress.server import create_server

from py_st.services.dashboard import dashboard_handler
from py_st.services.hosted_config import PublicOrigin
from py_st.services.state_lease import StateLease


def hosted_server(root: Path, origin: str, port: int = 8765) -> Any:
    """Bind only loopback. Waitress owns HTTP framing and resource limits."""
    lease = StateLease(root)
    try:
        handler = dashboard_handler(root, PublicOrigin.parse(origin))

        class Request(handler):  # type: ignore[misc,valid-type]
            def __init__(self, environ: dict[str, Any]) -> None:
                # Application methods only; never handle()/parse_request().
                self.headers = HTTPMessage()
                for key, value in environ.items():
                    if key.startswith("HTTP_"):
                        self.headers[key[5:].replace("_", "-")] = value
                for key in ("CONTENT_TYPE", "CONTENT_LENGTH"):
                    if environ.get(key):
                        self.headers[key.replace("_", "-")] = environ[key]
                self.path = environ["PATH_INFO"]
                if environ.get("QUERY_STRING"):
                    self.path += "?" + environ["QUERY_STRING"]
                self.rfile = environ["wsgi.input"]
                self.wfile = io.BytesIO()
                self.status = 500
                self.response_headers: list[tuple[str, str]] = []

            def send_response(self, code: int, message: str = "") -> None:
                self.status = code

            def send_header(self, keyword: str, value: str) -> None:
                self.response_headers.append((keyword, value))

            def end_headers(self) -> None:
                pass

        def application(
            environ: dict[str, Any], start_response: Any
        ) -> list[bytes]:
            request = Request(environ)
            method = environ["REQUEST_METHOD"]
            if method == "GET":
                request.do_GET()
            elif method == "POST":
                request.do_POST()
            else:
                request.reply(405, "{}")
            status = request.status
            start_response(
                f"{status} {HTTPStatus(status).phrase}",
                request.response_headers,
            )
            return [request.wfile.getvalue()]

        server = create_server(
            application,
            host="127.0.0.1",
            port=port,
            threads=4,
            connection_limit=64,
            channel_timeout=30,
            cleanup_interval=5,
            max_request_body_size=65536,
            max_request_header_size=16384,
            clear_untrusted_proxy_headers=True,
            expose_tracebacks=False,
            ident="py-st",
        )
        close = server.close

        def close_with_lease() -> None:
            try:
                close()
                server.task_dispatcher.shutdown()
            finally:
                lease.close()

        server.close = close_with_lease  # type: ignore[method-assign]
        return server
    except BaseException:
        lease.close()
        raise
