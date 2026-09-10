"""Loopback-only UI over shared intelligence. Never holds an API token."""

from __future__ import annotations

import json
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

from py_st.services.contract_planning import plan_contract_procurement
from py_st.services.contract_sources import contract_sources
from py_st.services.doctor import diagnose
from py_st.services.intelligence import Intelligence
from py_st.services.market_history import market_history
from py_st.services.stop_control import request_stop, stop_requested


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
                        json.dumps(result),
                    )
                    return
                if url.path == "/api/sources":
                    result = contract_sources(
                        database, scope, query.get("contract", [""])[0]
                    )
                    self.reply(200, json.dumps(result))
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
            if self.path not in ("/api/control", "/api/contract-model"):
                self.reply(404, "{}")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                model_request = self.path == "/api/contract-model"
                if not 0 < length <= (65536 if model_request else 4096):
                    raise ValueError("Invalid length or payload too large")
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("Transfer-Encoding is not supported")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or not secrets.compare_digest(
                    str(body.get("csrf", "")), csrf
                ):
                    self.reply(403, "{}")
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
                elif body.get("action") == "resume":
                    (root / "STOP").unlink(missing_ok=True)
                else:
                    raise ValueError("action")
                paused = stop_requested(root)
            except OSError:
                self.reply(
                    503, json.dumps({"error": "STOP control unavailable"})
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
