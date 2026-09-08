"""Loopback-only UI over shared intelligence. Never holds an API token."""

from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

from py_st.services.intelligence import Intelligence


def dashboard_server(root: Path, port: int = 8765) -> ThreadingHTTPServer:
    root = root.resolve()
    csrf = secrets.token_hex(32)
    html = Path(__file__).with_name("dashboard.html").read_text()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def reply(
            self, status: int, body: str, kind: str = "application/json"
        ) -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; frame-ancestors 'none'; "
                f"script-src 'nonce-{csrf}'; style-src 'unsafe-inline'",
            )
            self.end_headers()
            self.wfile.write(data)

        def local(self) -> bool:
            port = cast(ThreadingHTTPServer, self.server).server_port
            return self.headers.get("Host") == f"127.0.0.1:{port}"

        def do_GET(self) -> None:
            if not self.local():
                self.reply(403, "{}")
                return
            url = urlsplit(self.path)
            if url.path == "/":
                self.reply(200, html.replace("__NONCE__", csrf), "text/html")
                return
            if url.path != "/api/report":
                self.reply(404, "{}")
                return
            store = Intelligence(root / ".state/intelligence.sqlite3")
            try:
                scopes = store.scopes()
                scope = parse_qs(url.query).get("scope", [""])[0]
                if not scope and len(scopes) == 1:
                    scope = scopes[0]
                report = store.report(scope) if scope in scopes else {}
                report.update(
                    {"scopes": scopes, "paused": (root / "STOP").exists()}
                )
                self.reply(200, json.dumps(report))
            finally:
                store.close()

        def do_POST(self) -> None:
            port = cast(ThreadingHTTPServer, self.server).server_port
            origin = f"http://127.0.0.1:{port}"
            if not self.local() or self.headers.get("Origin") != origin:
                self.reply(403, "{}")
                return
            if self.path != "/api/control":
                self.reply(404, "{}")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("length")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or not secrets.compare_digest(
                    str(body.get("csrf", "")), csrf
                ):
                    self.reply(403, "{}")
                    return
                if body.get("action") == "pause":
                    (root / "STOP").touch()
                elif body.get("action") == "resume":
                    (root / "STOP").unlink(missing_ok=True)
                else:
                    raise ValueError("action")
            except (ValueError, TypeError):
                self.reply(400, "{}")
                return
            self.reply(200, json.dumps({"paused": (root / "STOP").exists()}))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
