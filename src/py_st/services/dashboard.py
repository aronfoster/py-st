"""Loopback-only UI over shared intelligence. Never holds an API token."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

from py_st.services.contract_planning import plan_contract_procurement
from py_st.services.contract_sources import contract_sources
from py_st.services.doctor import diagnose
from py_st.services.flight_auth import verify_password
from py_st.services.flight_queue import FlightQueue
from py_st.services.flight_worker import preview
from py_st.services.intelligence import Intelligence
from py_st.services.market_history import market_history
from py_st.services.stop_control import request_stop, stop_requested
from py_st.services.system_explorer import system_explorer


def dashboard_server(root: Path, port: int = 8765) -> ThreadingHTTPServer:
    root = root.resolve()
    csrf = secrets.token_hex(32)
    html = (
        Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    )
    assets = Path(__file__).with_name("ui")
    script = re.sub(
        r"</(?=script)",
        r"<\/",
        (assets / "shell.js").read_text(encoding="utf-8"),
        flags=re.IGNORECASE,
    ).replace("<!--", r"\x3c!--")
    style = re.sub(
        r"</(?=style)",
        r"<\/",
        (assets / "shell.css").read_text(encoding="utf-8"),
        flags=re.IGNORECASE,
    )
    html = html.replace("__UI_SCRIPT__", script).replace("__UI_STYLE__", style)
    managed = (root / ".state/flight.sqlite3").exists()
    sessions: dict[str, float] = {}
    auth_lock = threading.Lock()
    attempts: list[float] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def reply(
            self,
            status: int,
            body: str,
            kind: str = "application/json",
            cookie: str = "",
        ) -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if cookie:
                self.send_header("Set-Cookie", cookie)
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

        def authenticated(self) -> bool:
            if not managed:
                return True
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
                token = cookies["flight_session"].value
            except (KeyError, ValueError):
                return False
            with auth_lock:
                return sessions.get(token, 0) > time.monotonic()

        def do_GET(self) -> None:
            if not self.local():
                self.reply(403, "{}")
                return
            url = urlsplit(self.path)
            if url.path == "/":
                self.reply(200, html.replace("__NONCE__", csrf), "text/html")
                return
            if url.path == "/api/auth":
                self.reply(
                    200,
                    json.dumps(
                        {
                            "managed": managed,
                            "authenticated": self.authenticated(),
                        }
                    ),
                )
                return
            if not self.authenticated():
                self.reply(401, json.dumps({"error": "Owner login required"}))
                return
            if url.path == "/api/flight" and managed:
                queue = None
                try:
                    queue = FlightQueue(root)
                    self.reply(200, json.dumps(queue.report()))
                except (OSError, ValueError, sqlite3.Error):
                    self.reply(
                        503, json.dumps({"error": "Flight state unavailable"})
                    )
                finally:
                    if queue is not None:
                        queue.close()
                return
            if url.path not in (
                "/api/report",
                "/api/sources",
                "/api/doctor",
                "/api/market-history",
            ):
                self.reply(404, "{}")
                return
            database = root / ".state/intelligence.sqlite3"
            store = None
            try:
                query = parse_qs(url.query, keep_blank_values=True)
                allowed = (
                    {"scope", "waypoint", "good", "limit"}
                    if url.path == "/api/market-history"
                    else (
                        {"scope", "contract"}
                        if url.path == "/api/sources"
                        else {"scope"}
                    )
                )
                if set(query) - allowed or any(
                    len(values) != 1 for values in query.values()
                ):
                    raise ValueError("Unexpected or repeated query parameter")
                scope = query.get("scope", [""])[0]
                if url.path == "/api/market-history":
                    raw_limit = query.get("limit", ["50"])[0]
                    if (
                        not raw_limit.isascii()
                        or not raw_limit.isdecimal()
                        or len(raw_limit) > 3
                    ):
                        raise ValueError(
                            "limit must be an integer from 1 to 100"
                        )
                    result = market_history(
                        database,
                        scope,
                        query.get("waypoint", [""])[0],
                        query.get("good", [""])[0],
                        int(raw_limit),
                    )
                    self.reply(200, json.dumps(result, allow_nan=False))
                    return
                if url.path == "/api/doctor":
                    result = diagnose(database, scope, root=root)
                    self.reply(
                        400 if result["exit_code"] == 2 else 200,
                        json.dumps(result, allow_nan=False),
                    )
                    return
                if url.path == "/api/sources":
                    result = contract_sources(
                        database, scope, query.get("contract", [""])[0]
                    )
                    self.reply(200, json.dumps(result, allow_nan=False))
                    return
                if not database.is_file():
                    if scope:
                        raise ValueError("Unknown reset/agent scope")
                    self.reply(
                        200,
                        json.dumps(
                            {"scopes": [], "paused": stop_requested(root)}
                        ),
                    )
                    return
                store = Intelligence(database, read_only=True)
                store.db.execute("BEGIN")
                scopes = store.scopes()
                if scope and scope not in scopes:
                    raise ValueError("Unknown reset/agent scope")
                if not scope and len(scopes) == 1:
                    scope = scopes[0]
                report = store.report(scope) if scope in scopes else {}
                report["explorer"] = (
                    system_explorer(store, scope) if scope in scopes else {}
                )
                report["agents"] = store.latest(scope, "agent")
                report.update(
                    {"scopes": scopes, "paused": stop_requested(root)}
                )
                self.reply(200, json.dumps(report))
            except ValueError as exc:
                self.reply(400, json.dumps({"error": str(exc)}))
            except sqlite3.Error:
                self.reply(503, json.dumps({"error": "Ledger unavailable"}))
            except OSError:
                self.reply(
                    503, json.dumps({"error": "Local state unavailable"})
                )
            finally:
                if store is not None:
                    store.close()

        def do_POST(self) -> None:
            port = cast(ThreadingHTTPServer, self.server).server_port
            origin = f"http://127.0.0.1:{port}"
            if not self.local() or self.headers.get("Origin") != origin:
                self.reply(403, "{}")
                return
            if self.path not in (
                "/api/control",
                "/api/contract-model",
                "/api/login",
                "/api/logout",
                "/api/flight",
                "/api/flight-preview",
            ):
                self.reply(404, "{}")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                model_request = self.path == "/api/contract-model"
                if not 0 < length <= (65536 if model_request else 4096):
                    raise ValueError("Invalid length or payload too large")
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Transfer-Encoding is not supported")
                if (
                    managed
                    and self.headers.get_content_type() != "application/json"
                ):
                    raise ValueError("Expected application/json")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or not secrets.compare_digest(
                    str(body.get("csrf", "")), csrf
                ):
                    self.reply(403, "{}")
                    return
                if managed and self.path == "/api/login":
                    if set(body) != {"csrf", "password"} or not isinstance(
                        body["password"], str
                    ):
                        raise ValueError("Expected owner password")
                    with auth_lock:
                        current = time.monotonic()
                        attempts[:] = [t for t in attempts if t > current - 60]
                        if len(attempts) >= 5:
                            self.reply(
                                429,
                                json.dumps(
                                    {"error": "Wait one minute before login"}
                                ),
                            )
                            return
                        valid_password = verify_password(
                            root, body["password"]
                        )
                        if not valid_password:
                            attempts.append(current)
                    if not valid_password:
                        self.reply(
                            401, json.dumps({"error": "Invalid owner login"})
                        )
                        return
                    token = secrets.token_hex(32)
                    with auth_lock:
                        expired = [
                            k for k, v in sessions.items() if v <= current
                        ]
                        for key in expired:
                            del sessions[key]
                        sessions[token] = current + 8 * 3600
                    self.reply(
                        200,
                        "{}",
                        cookie=f"flight_session={token}; Path=/; HttpOnly; "
                        "SameSite=Strict; Max-Age=28800",
                    )
                    return
                if not self.authenticated():
                    self.reply(
                        401, json.dumps({"error": "Owner login required"})
                    )
                    return
                if managed and self.path == "/api/logout":
                    cookies = SimpleCookie(self.headers.get("Cookie", ""))
                    with auth_lock:
                        if "flight_session" in cookies:
                            sessions.pop(cookies["flight_session"].value, None)
                    self.reply(
                        200,
                        "{}",
                        cookie="flight_session=; Path=/; HttpOnly; "
                        "SameSite=Strict; Max-Age=0",
                    )
                    return
                if self.path in ("/api/flight", "/api/flight-preview"):
                    if not managed:
                        raise ValueError(
                            "Initialize managed flight mode first"
                        )
                    queue = FlightQueue(root)
                    try:
                        if self.path == "/api/flight":
                            if set(body) != {
                                "csrf",
                                "scope",
                                "request_id",
                                "payload",
                            }:
                                raise ValueError("Invalid command envelope")
                            result = queue.enqueue(
                                body["scope"],
                                body["request_id"],
                                body["payload"],
                            )
                        else:
                            if (
                                set(body)
                                != {"csrf", "scope", "ship", "destination"}
                                or body["scope"] != queue.scope
                            ):
                                raise ValueError(
                                    "Invalid preview scope/fields"
                                )
                            store = Intelligence(
                                root / ".state/intelligence.sqlite3",
                                read_only=True,
                            )
                            try:
                                result = preview(
                                    store,
                                    queue.scope,
                                    body["ship"],
                                    body["destination"],
                                )
                            finally:
                                store.close()
                        self.reply(200, json.dumps(result, allow_nan=False))
                    finally:
                        queue.close()
                    return
                if model_request:
                    if self.headers.get_content_type() != "application/json":
                        raise ValueError("Expected application/json")
                    model = body.get("model")
                    allowed = {
                        "contract",
                        "quotes",
                        "ship_capacity",
                        "credits",
                        "credit_floor",
                        "fuel_allowance",
                        "price_margin",
                        "deadline_margin_seconds",
                    }
                    if (
                        set(body) != {"csrf", "model"}
                        or not isinstance(model, dict)
                        or set(model) - allowed
                        or not isinstance(model.get("contract"), dict)
                        or not isinstance(model.get("quotes"), list)
                    ):
                        raise ValueError("Expected a contract model object")
                    for quote in model["quotes"]:
                        if not isinstance(quote, dict) or any(
                            type(quote.get(key)) is not int or quote[key] < 0
                            for key in ("fuel_cost", "travel_seconds")
                        ):
                            raise ValueError(
                                "Every quote requires explicit non-negative "
                                "integer fuel_cost and travel_seconds"
                            )
                    result = plan_contract_procurement(**model)
                    self.reply(200, json.dumps(result, allow_nan=False))
                    return
                if body.get("action") == "pause":
                    request_stop(root)
                    if managed:
                        queue = FlightQueue(root)
                        try:
                            queue.control(True)
                        finally:
                            queue.close()
                elif body.get("action") == "resume":
                    if managed:
                        queue = FlightQueue(root)
                        try:
                            queue.control(False)
                        finally:
                            queue.close()
                    (root / "STOP").unlink(missing_ok=True)
                else:
                    raise ValueError("action")
                paused = stop_requested(root)
            except OSError:
                self.reply(
                    503, json.dumps({"error": "STOP control unavailable"})
                )
                return
            except sqlite3.Error:
                self.reply(
                    503, json.dumps({"error": "Flight ledger unavailable"})
                )
                return
            except (
                ValueError,
                TypeError,
                AttributeError,
                KeyError,
                OverflowError,
                RecursionError,
            ) as exc:
                self.reply(400, json.dumps({"error": str(exc)}))
                return
            self.reply(200, json.dumps({"paused": paused}))

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
