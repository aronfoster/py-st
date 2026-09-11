"""Persistent synthetic remote API; MockTransport cannot contact the game."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from py_st.client import SpaceTradersClient
from py_st.services.intelligence import Intelligence

SCOPE = "DEMO-RESET:SYNTHETIC"


def create_demo(root: Path) -> None:
    state = root / ".state"
    state.mkdir(parents=True, exist_ok=True)
    if (state / "intelligence.sqlite3").exists() or (
        state / "remote.sqlite3"
    ).exists():
        raise FileExistsError(
            "Use a new isolated demo root; never overwrite state"
        )
    points: list[dict[str, Any]] = [
        {
            "symbol": f"X-DEMO-{name}",
            "systemSymbol": "X-DEMO",
            "type": "PLANET",
            "x": x,
            "y": y,
            "traits": [{"symbol": "MARKETPLACE"}],
        }
        for name, x, y in (("A1", 0, 0), ("B2", 12, 0), ("C3", 100, 100))
    ]
    ship = {
        "symbol": "SYNTHETIC-1",
        "engine": {"speed": 10},
        "nav": {
            "systemSymbol": "X-DEMO",
            "waypointSymbol": "X-DEMO-A1",
            "status": "DOCKED",
            "flightMode": "CRUISE",
            "route": {
                "origin": points[0],
                "destination": points[0],
                "departureTime": datetime.now(UTC).isoformat(),
                "arrival": datetime.now(UTC).isoformat(),
            },
        },
        "fuel": {"current": 100, "capacity": 100},
        "cargo": {"units": 0, "capacity": 40, "inventory": []},
        "cooldown": {"remainingSeconds": 0},
    }
    world: dict[str, Any] = {
        "agent": {"symbol": "SYNTHETIC", "credits": 123456},
        "ships": [ship],
        "contracts": [],
        "waypoints": points,
        "loss_next": False,
        "mutations": [],
        "transit_seconds": 3,
    }
    db = sqlite3.connect(state / "remote.sqlite3")
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        with db:
            db.execute(
                "CREATE TABLE world (id INTEGER PRIMARY KEY, data TEXT)"
            )
            db.execute("INSERT INTO world VALUES(1,?)", (json.dumps(world),))
    finally:
        db.close()
    store = Intelligence(state / "intelligence.sqlite3")
    try:
        for kind, items, key in (
            ("agent", [world["agent"]], "symbol"),
            ("ship", world["ships"], "symbol"),
            ("waypoint", points, "symbol"),
        ):
            for item in items:
                store.observe(SCOPE, kind, item[key], item, "synthetic-demo")
    finally:
        store.close()


def scenario(root: Path, name: str) -> None:
    db = sqlite3.connect(
        (root / ".state/remote.sqlite3").as_uri() + "?mode=rw", uri=True
    )
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            world = json.loads(
                db.execute("SELECT data FROM world").fetchone()[0]
            )
            if name == "lost-response":
                world["loss_next"] = True
            elif name == "low-funds":
                world["agent"]["credits"] = 50010
                world["ships"][0]["fuel"]["current"] = 50
            elif name == "low-fuel":
                world["ships"][0]["fuel"]["current"] = 1
            else:
                raise ValueError("Unknown demo scenario")
            db.execute("UPDATE world SET data=?", (json.dumps(world),))
    finally:
        db.close()


def demo_client(root: Path) -> SpaceTradersClient:
    path = (root / ".state/remote.sqlite3").resolve(strict=True)

    def handle(request: httpx.Request) -> httpx.Response:
        db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
        lost = False
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                world = json.loads(
                    db.execute("SELECT data FROM world").fetchone()[0]
                )
                for ship in world["ships"]:
                    nav = ship["nav"]
                    if nav["status"] == "IN_TRANSIT" and datetime.now(
                        UTC
                    ) >= datetime.fromisoformat(nav["route"]["arrival"]):
                        nav["status"] = "IN_ORBIT"
                response = dispatch(world, request)
                if request.method == "POST" and response.status_code < 400:
                    world["mutations"].append(request.url.path)
                    lost = world["loss_next"]
                    world["loss_next"] = False
                db.execute("UPDATE world SET data=?", (json.dumps(world),))
        finally:
            db.close()
        if lost:
            raise httpx.ReadError(
                "Synthetic response lost after remote commit"
            )
        return response

    return SpaceTradersClient(
        "synthetic-not-a-game-token",
        httpx.Client(
            base_url="https://offline.invalid",
            transport=httpx.MockTransport(handle),
        ),
    )


def dispatch(world: dict[str, Any], request: httpx.Request) -> httpx.Response:
    path = request.url.path
    parts = path.split("/")
    missing = httpx.Response(
        404, json={"error": {"message": "Unknown synthetic resource"}}
    )
    if path.startswith("/my/ships/") and parts[3] not in {
        ship["symbol"] for ship in world["ships"]
    }:
        return missing
    if path.startswith("/systems/") and (
        parts[2] != "X-DEMO"
        or (
            "/waypoints/" in path
            and parts[4]
            not in {point["symbol"] for point in world["waypoints"]}
        )
    ):
        return missing

    def ok(data: Any) -> httpx.Response:
        return httpx.Response(200, json={"data": data})

    if request.method == "GET":
        if path == "/":
            return httpx.Response(200, json={"resetDate": "DEMO-RESET"})
        if path == "/my/agent":
            return ok(world["agent"])
        if path in ("/my/ships", "/my/contracts"):
            return ok(world[path.rsplit("/", 1)[-1]])
        if path.startswith("/my/ships/"):
            return ok(
                next(
                    s
                    for s in world["ships"]
                    if s["symbol"] == path.rsplit("/", 1)[-1]
                )
            )
        if path == "/systems/X-DEMO/waypoints":
            return ok(world["waypoints"])
        if path.endswith("/market"):
            return ok(
                {
                    "symbol": path.split("/")[-2],
                    "exports": [{"symbol": "FUEL"}],
                    "imports": [],
                    "exchange": [],
                    "tradeGoods": [
                        {
                            "symbol": "FUEL",
                            "purchasePrice": 72,
                            "sellPrice": 69,
                            "tradeVolume": 100,
                        }
                    ],
                }
            )
        if "/waypoints/" in path:
            return ok(
                next(
                    p
                    for p in world["waypoints"]
                    if p["symbol"] == path.rsplit("/", 1)[-1]
                )
            )
    if request.method == "POST" and path.startswith("/my/ships/"):
        symbol, kind = path.split("/")[-2:]
        ship = next(s for s in world["ships"] if s["symbol"] == symbol)
        nav = ship["nav"]
        if nav["status"] == "IN_TRANSIT":
            return httpx.Response(
                400, json={"error": {"message": "In transit"}}
            )
        if kind in ("dock", "orbit"):
            nav["status"] = "DOCKED" if kind == "dock" else "IN_ORBIT"
            return ok({"nav": nav})
        if kind == "navigate":
            body = json.loads(request.content)
            if body.get("waypointSymbol") not in {
                point["symbol"] for point in world["waypoints"]
            }:
                return missing
            target = next(
                p
                for p in world["waypoints"]
                if p["symbol"] == body["waypointSymbol"]
            )
            origin = nav["route"]["destination"]
            fuel = max(
                1,
                math.ceil(
                    math.hypot(
                        target["x"] - origin["x"], target["y"] - origin["y"]
                    )
                ),
            )
            if nav["status"] != "IN_ORBIT" or ship["fuel"]["current"] < fuel:
                return httpx.Response(
                    400, json={"error": {"message": "Fuel/orbit"}}
                )
            ship["fuel"]["current"] -= fuel
            nav.update(
                status="IN_TRANSIT",
                waypointSymbol=target["symbol"],
                route={
                    "origin": origin,
                    "destination": target,
                    "departureTime": datetime.now(UTC).isoformat(),
                    "arrival": (
                        datetime.now(UTC)
                        + timedelta(seconds=world["transit_seconds"])
                    ).isoformat(),
                },
            )
            return ok({"nav": nav, "fuel": ship["fuel"]})
        if kind == "refuel" and nav["status"] == "DOCKED":
            units = math.ceil(
                (ship["fuel"]["capacity"] - ship["fuel"]["current"]) / 100
            )
            cost = units * 72
            if world["agent"]["credits"] < cost:
                return httpx.Response(
                    400, json={"error": {"message": "Funds"}}
                )
            world["agent"]["credits"] -= cost
            ship["fuel"]["current"] = ship["fuel"]["capacity"]
            return ok(
                {
                    "fuel": ship["fuel"],
                    "agent": world["agent"],
                    "transaction": {
                        "totalPrice": cost,
                        "units": units,
                        "pricePerUnit": 72,
                        "tradeSymbol": "FUEL",
                        "type": "PURCHASE",
                        "shipSymbol": symbol,
                        "waypointSymbol": nav["waypointSymbol"],
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                }
            )
    return httpx.Response(
        404, json={"error": {"message": "Offline endpoint unavailable"}}
    )
