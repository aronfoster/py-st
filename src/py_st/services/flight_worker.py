"""One host/account authority executing durable, bounded flight steps."""

from __future__ import annotations

import hashlib
import json
import math
import socket
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from py_st.client import APIError, SpaceTradersClient
from py_st.services.automation import SafetyStop, Session
from py_st.services.flight_queue import FlightQueue, now
from py_st.services.intelligence import Intelligence
from py_st.services.stop_control import request_stop, stop_requested
from py_st.services.strategies import CREDIT_FLOOR, FUEL_ALLOWANCE, refuel_run


def trade_preview(
    store: Intelligence,
    scope: str,
    symbol: str,
    good: str,
    units: int,
    kind: str,
) -> dict[str, Any]:
    """Build a dated, non-authoritative trade estimate from stored evidence."""
    if kind not in ("purchase", "sell") or units <= 0:
        raise ValueError("Invalid trade preview")
    ships = [
        row for row in store.latest(scope, "ship") if row["key"] == symbol
    ]
    agents = store.latest(scope, "agent")
    if len(ships) != 1 or not agents:
        raise ValueError("Owned ship or credit observation is unavailable")
    ship_row, agent_row = ships[0], agents[-1]
    ship = ship_row["data"]
    waypoint = ship["nav"]["waypointSymbol"]
    markets = [
        r for r in store.latest(scope, "market") if r["key"] == waypoint
    ]
    quote = None
    market_row = markets[0] if markets else None
    if market_row:
        matches = [
            item
            for item in market_row["data"].get("tradeGoods", [])
            if item.get("symbol") == good
        ]
        if len(matches) == 1:
            quote = matches[0]
    price_key = "purchasePrice" if kind == "purchase" else "sellPrice"
    price = quote.get(price_key) if quote else None
    volume = quote.get("tradeVolume") if quote else None
    inventory = {
        item["symbol"]: item["units"]
        for item in ship["cargo"].get("inventory", [])
    }
    protected: dict[str, int] = {}
    procurement_remaining = 0
    open_contracts = False
    unknown_contracts = False
    for row in store.latest(scope, "contract"):
        contract = row["data"]
        if (
            contract.get("fulfilled") is not True
            and contract.get("accepted") is not False
        ):
            open_contracts = True
            if contract.get("accepted") is not True:
                unknown_contracts = True
        if (
            contract.get("accepted") is True
            and contract.get("fulfilled") is not True
        ):
            for item in contract.get("terms", {}).get("deliver", []):
                remaining = max(
                    0, item["unitsRequired"] - item["unitsFulfilled"]
                )
                protected[item["tradeSymbol"]] = max(
                    protected.get(item["tradeSymbol"], 0), remaining
                )
                if item["tradeSymbol"] == good:
                    procurement_remaining += remaining
    procurement_remaining = max(
        0, procurement_remaining - inventory.get(good, 0)
    )
    credits = agent_row["data"]["credits"]
    total = price * units if type(price) is int and price > 0 else None
    free = ship["cargo"]["capacity"] - ship["cargo"]["units"]
    sellable = max(0, inventory.get(good, 0) - protected.get(good, 0))
    age = None
    if market_row:
        age = (
            datetime.now(UTC)
            - datetime.fromisoformat(market_row["observed_at"])
        ).total_seconds()
    feasible = bool(
        total is not None
        and type(volume) is int
        and volume > 0
        and units <= volume
        and age is not None
        and age <= 900
        and ship["nav"]["status"] == "DOCKED"
        and (
            (
                kind == "purchase"
                and (not open_contracts or units <= procurement_remaining)
                and units <= free
                and credits - total >= CREDIT_FLOOR + FUEL_ALLOWANCE
            )
            or (kind == "sell" and not unknown_contracts and units <= sellable)
        )
    )
    return {
        "kind": kind,
        "ship": symbol,
        "good": good,
        "units": units,
        "waypoint": waypoint,
        "unit_price": price,
        "total_price": total,
        "trade_volume": volume,
        "credits_before": credits,
        "credits_after": (
            credits + (total if kind == "sell" else -total)
            if total is not None
            else None
        ),
        "cargo_before": ship["cargo"]["units"],
        "cargo_after": ship["cargo"]["units"]
        + (units if kind == "purchase" else -units),
        "cargo_capacity": ship["cargo"]["capacity"],
        "fixed_floor": CREDIT_FLOOR,
        "fuel_reserve": FUEL_ALLOWANCE,
        "fixed_floor_headroom": credits - CREDIT_FLOOR,
        "protected_contract_cargo": protected,
        "open_contract_obligations": open_contracts,
        "contract_state_unknown": unknown_contracts,
        "sellable_units": sellable,
        "observed_at": market_row["observed_at"] if market_row else None,
        "stale": age is None or age > 900,
        "estimated": True,
        "feasible": feasible,
        "reason": (
            "Purchase is limited to a known active deliverable; worker still "
            "protects the fixed floor and fuel reserve"
            if kind == "purchase" and open_contracts and procurement_remaining
            else (
                "Contract acceptance is unknown; trade is blocked"
                if unknown_contracts
                else (
                    "Stored estimate; worker requires an unchanged live "
                    "quote, "
                    "ship, credits, cargo and obligations before dispatch"
                    if price is not None
                    else "No observed current price detail; unknown is not "
                    "zero"
                )
            )
        ),
    }


def contract_preview(
    store: Intelligence, scope: str, contract_id: str
) -> dict[str, Any]:
    """Describe an offer and its obligations from dated stored evidence."""
    rows = [
        row
        for row in store.latest(scope, "contract")
        if row["key"] == contract_id
    ]
    if len(rows) != 1:
        raise ValueError("Contract observation is unavailable")
    row = rows[0]
    contract = row["data"]
    markets = store.latest(scope, "market")
    inventory: dict[str, list[dict[str, Any]]] = {}
    for ship_row in store.latest(scope, "ship"):
        for item in ship_row["data"].get("cargo", {}).get("inventory", []):
            inventory.setdefault(item["symbol"], []).append(
                {"ship": ship_row["key"], "units": item["units"]}
            )
    sources: dict[str, list[dict[str, Any]]] = {}
    for delivery in contract.get("terms", {}).get("deliver", []):
        good = delivery.get("tradeSymbol")
        if not isinstance(good, str):
            raise ValueError("Contract deliverable good is unavailable")
        options = []
        for market in markets:
            quote = next(
                (
                    q
                    for q in market["data"].get("tradeGoods", [])
                    if q.get("symbol") == good
                    and type(q.get("purchasePrice")) is int
                    and q["purchasePrice"] > 0
                ),
                None,
            )
            if quote:
                age = (
                    datetime.now(UTC)
                    - datetime.fromisoformat(market["observed_at"])
                ).total_seconds()
                options.append(
                    {
                        "waypoint": market["key"],
                        "unit_price": quote["purchasePrice"],
                        "trade_volume": quote.get("tradeVolume"),
                        "observed_at": market["observed_at"],
                        "freshness": "fresh" if age <= 900 else "stale",
                        "estimated": True,
                    }
                )
        sources[str(good)] = sorted(options, key=lambda x: x["unit_price"])
    agents = store.latest(scope, "agent")
    credits = agents[-1]["data"].get("credits") if agents else None
    procurement_cost = 0
    blockers: list[str] = []
    if any(
        other["data"].get("accepted") is not False
        and other["data"].get("fulfilled") is not True
        and other["key"] != contract_id
        for other in store.latest(scope, "contract")
    ):
        blockers.append("Resolve existing uncosted contract obligations first")
    remaining: dict[str, int] = {}
    for delivery in contract.get("terms", {}).get("deliver", []):
        good = delivery["tradeSymbol"]
        remaining[good] = remaining.get(good, 0) + max(
            0, delivery["unitsRequired"] - delivery["unitsFulfilled"]
        )
    for good, required in remaining.items():
        held = sum(item["units"] for item in inventory.get(good, []))
        needed = max(0, required - held)
        fresh = [
            source
            for source in sources[good]
            if source["freshness"] == "fresh"
            and type(source["trade_volume"]) is int
            and source["trade_volume"] >= needed
        ]
        if needed and not fresh:
            blockers.append(f"No fresh funded source for {good}")
        elif needed:
            procurement_cost += needed * fresh[0]["unit_price"]
    if type(credits) is not int:
        blockers.append("Credit observation is unavailable")
    elif credits - procurement_cost < CREDIT_FLOOR + FUEL_ALLOWANCE:
        blockers.append("Procurement estimate violates protected reserves")
    evidence_body = {
        "contract": contract,
        "cargo": inventory,
        "sources": sources,
        "credits": credits,
    }
    evidence = hashlib.sha256(
        json.dumps(evidence_body, sort_keys=True).encode()
    ).hexdigest()
    return {
        "contract": contract,
        "observed_at": row["observed_at"],
        "cargo": inventory,
        "sources": sources,
        "credits": credits,
        "fixed_floor": CREDIT_FLOOR,
        "fuel_reserve": FUEL_ALLOWANCE,
        "estimated": True,
        "procurement_cost": procurement_cost,
        "feasible": not blockers,
        "blockers": blockers,
        "evidence": evidence,
        "warning": "Stored preview only; worker revalidates before dispatch.",
    }


def preview(
    store: Intelligence, scope: str, symbol: str, destination: str
) -> dict[str, Any]:
    ships = [r for r in store.latest(scope, "ship") if r["key"] == symbol]
    points = {r["key"]: r for r in store.latest(scope, "waypoint")}
    result: dict[str, Any] = {
        "estimated": True,
        "feasible": False,
        "fuel": None,
        "required_fuel": None,
        "seconds": None,
        "observed_at": None,
        "assumptions": "CRUISE, conservative round-trip fuel + 10; "
        "approximate time 15 + 25 × distance / engine speed. "
        "Worker revalidates authoritative state before every dispatch.",
    }
    try:
        record = ships[0]
        ship = record["data"]
        origin = points[ship["nav"]["waypointSymbol"]]
        target = points[destination]
        stamps = [
            record["observed_at"],
            origin["observed_at"],
            target["observed_at"],
        ]
        result["observed_at"] = min(stamps)
        age = datetime.now(UTC) - datetime.fromisoformat(min(stamps))
        result["stale"] = age.total_seconds() > 60
        if destination.rsplit("-", 1)[0] != ship["nav"]["systemSymbol"]:
            raise ValueError("Only same-system travel")
        distance = max(
            1,
            math.ceil(
                math.hypot(
                    target["data"]["x"] - origin["data"]["x"],
                    target["data"]["y"] - origin["data"]["y"],
                )
            ),
        )
        capacity = ship["fuel"]["capacity"]
        if any(
            type(ship["fuel"].get(key)) is not int or ship["fuel"][key] < 0
            for key in ("current", "capacity")
        ):
            raise ValueError("Unknown or invalid fuel evidence")
        required = 2 * distance + 10 if capacity else 0
        speed = ship.get("engine", {}).get("speed")
        if type(speed) is not int or speed <= 0:
            speed = None
        result.update(
            fuel=distance if capacity else 0,
            required_fuel=required,
            seconds=round(15 + 25 * distance / speed) if speed else None,
            feasible=(
                ship["fuel"]["current"] >= required
                and ship["nav"]["status"] != "IN_TRANSIT"
                and ship["nav"]["flightMode"] == "CRUISE"
            ),
            reason="Conservative stored-data preview; refresh stale evidence",
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        result["reason"] = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Missing ship, waypoint, coordinates or fuel evidence"
        )
    return result


def validate_receipt(path: str, result: dict[str, Any]) -> None:
    kind = path.rsplit("/", 1)[-1]
    if not isinstance(result, dict):
        raise SafetyStop("Unparseable receipt; reconciliation required")
    if kind in ("orbit", "dock", "navigate"):
        nav = result.get("nav")
        expected = {
            "orbit": "IN_ORBIT",
            "dock": "DOCKED",
            "navigate": "IN_TRANSIT",
        }[kind]
        if (
            not isinstance(nav, dict)
            or nav.get("status") != expected
            or not isinstance(nav.get("waypointSymbol"), str)
            or not isinstance(nav.get("systemSymbol"), str)
            or not isinstance(nav.get("route"), dict)
        ):
            raise SafetyStop("Invalid navigation receipt; reconcile outcome")
    if kind in ("refuel", "navigate"):
        fuel = result.get("fuel", {})
        if not isinstance(fuel, dict) or any(
            type(fuel.get(k)) is not int or fuel[k] < 0
            for k in ("current", "capacity")
        ):
            raise SafetyStop("Invalid fuel receipt; reconcile outcome")
        if fuel["current"] > fuel["capacity"]:
            raise SafetyStop("Invalid fuel capacity; reconcile outcome")
    if kind == "navigate":
        try:
            route = result["nav"]["route"]
            arrival = datetime.fromisoformat(route["arrival"])
            departure = datetime.fromisoformat(route["departureTime"])
            if (
                arrival.tzinfo is None
                or departure.tzinfo is None
                or arrival < departure
            ):
                raise ValueError("Invalid route timestamps")
        except (KeyError, TypeError, ValueError) as exc:
            raise SafetyStop(
                "Invalid travel receipt; reconcile outcome"
            ) from exc
    if kind == "refuel":
        transaction = result.get("transaction", {})
        if (
            not isinstance(transaction, dict)
            or type(transaction.get("totalPrice")) is not int
            or transaction["totalPrice"] < 0
        ):
            raise SafetyStop("Invalid refuel receipt; reconcile outcome")
    if kind in ("purchase", "sell"):
        agent = result.get("agent")
        cargo = result.get("cargo")
        transaction = result.get("transaction")
        if (
            not isinstance(agent, dict)
            or type(agent.get("credits")) is not int
            or agent["credits"] < 0
            or not isinstance(cargo, dict)
            or any(
                type(cargo.get(key)) is not int
                for key in ("units", "capacity")
            )
            or not 0 <= cargo["units"] <= cargo["capacity"]
            or not isinstance(transaction, dict)
            or type(transaction.get("totalPrice")) is not int
            or transaction["totalPrice"] < 0
            or type(transaction.get("units")) is not int
            or transaction["units"] <= 0
        ):
            raise SafetyStop("Invalid trade receipt; reconcile outcome")
    if kind in ("accept", "deliver", "fulfill", "contract"):
        contract = result.get("contract", result)
        if not isinstance(contract, dict) or not isinstance(
            contract.get("id"), str
        ):
            raise SafetyStop("Invalid contract receipt; reconcile outcome")


class FlightWorker:
    def __init__(self, root: Path, client: SpaceTradersClient) -> None:
        if (root / "HANDOFF_REQUIRED").exists() or (
            root / "HANDOFF_REQUIRED"
        ).is_symlink():
            raise SafetyStop(
                "Restored state requires authority-transfer review"
            )
        self.queue = FlightQueue(root)
        self.root = self.queue.root
        self.client = client
        self.lock = socket.socket(socket.AF_UNIX)
        digest = hashlib.sha256(self.queue.scope.encode()).hexdigest()
        try:
            # Abstract namespace is independent of checkout or filesystem path.
            self.lock.bind(f"\0py-st-flight-{digest}")
        except OSError:
            self.lock.close()
            self.queue.close()
            raise SafetyStop("Another worker owns this reset/agent") from None
        self.store: Intelligence
        self.run: Session
        try:
            self.store = Intelligence(
                self.root / ".state/intelligence.sqlite3", existing_only=True
            )
            try:
                agent_symbol = self.queue.scope.partition(":")[2]
                if not any(
                    row["key"] == agent_symbol
                    and row["data"].get("symbol") == agent_symbol
                    for row in self.store.latest(self.queue.scope, "agent")
                ):
                    raise SafetyStop(
                        "Managed ledger lacks matching agent history"
                    )
                self.run = Session(
                    client,
                    self.store,
                    root=self.root,
                    execute=True,
                    seconds=120,
                    actions=10,
                    validate_result=validate_receipt,
                )
            except BaseException:
                self.store.close()
                raise
        except BaseException:
            self.lock.close()
            self.queue.close()
            raise
        self.run.scope = self.queue.scope
        self.dispatch_until = 0.0
        self.evidence_until = time.monotonic() + 30
        self.allowed_path = ""
        self.previous_guard = client._transport.dispatch_guard
        client._transport.dispatch_guard = self.guard

    def close(self) -> None:
        self.client._transport.dispatch_guard = self.previous_guard
        self.run.close()
        self.store.close()
        self.queue.close()
        self.lock.close()

    def guard(self, method: str, path: str) -> None:
        self.run.check()
        if method != "GET" and (
            path != self.allowed_path or time.monotonic() > self.dispatch_until
        ):
            raise SafetyStop("Flight dispatch evidence expired; replan")

    def fresh(self, symbol: str = "") -> dict[str, Any]:
        state = self.run.refresh()
        if (
            symbol
            and len([s for s in state["ships"] if s["symbol"] == symbol]) != 1
        ):
            raise SafetyStop("Ship is not uniquely owned by this agent")
        if type(state["agent"].get("credits")) is not int:
            raise SafetyStop("Invalid authoritative credit balance")
        if symbol:
            ship = next(s for s in state["ships"] if s["symbol"] == symbol)
            if (
                ship["nav"].get("status")
                not in ("IN_TRANSIT", "DOCKED", "IN_ORBIT")
                or any(
                    type(ship["fuel"].get(k)) is not int or ship["fuel"][k] < 0
                    for k in ("current", "capacity")
                )
                or ship["fuel"]["current"] > ship["fuel"]["capacity"]
            ):
                raise SafetyStop("Invalid authoritative navigation/fuel state")
        return state

    def mutate(
        self,
        command: dict[str, Any],
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        before = self.store.db.execute(
            "SELECT COALESCE(MAX(id),0) FROM actions"
        ).fetchone()[0]
        self.queue.update(
            command["id"],
            "dispatching",
            "Persisted before dispatch",
            before_action=before,
        )
        self.allowed_path = path
        self.dispatch_until = min(time.monotonic() + 30, self.evidence_until)
        try:
            return self.run.mutate(path, body)
        finally:
            self.allowed_path = ""

    def recover(self, command: dict[str, Any]) -> bool:
        """Never infer refuel success from a full tank or replay ambiguity."""
        if command["status"] not in ("dispatching", "reconciliation_required"):
            return False
        actions = self.store.db.execute(
            "SELECT * FROM actions WHERE scope=? AND id>? ORDER BY id",
            (self.queue.scope, command["before_action"]),
        ).fetchall()
        if not actions:
            self.queue.update(
                command["id"],
                "queued",
                "No journal dispatch; safe to revalidate",
            )
            return True
        if len(actions) != 1:
            self.queue.update(
                command["id"],
                "reconciliation_required",
                "Ambiguous journal association; inspect evidence",
            )
            return True
        action = dict(actions[0])
        if action["status"] == "succeeded":
            self.advance(command, {"receipt": json.loads(action["result"])})
        elif action["status"] in ("not_sent", "rejected"):
            if stop_requested(self.root):
                self.queue.update(
                    command["id"],
                    "queued",
                    "STOP before dispatch; resume revalidates",
                    before_action=None,
                )
                return True
            self.queue.update(
                command["id"],
                "blocked",
                (
                    "Dispatch not sent; revalidate before resubmitting"
                    if action["status"] == "not_sent"
                    else "Dispatch definitively rejected; inspect journal"
                ),
                evidence=action,
            )
        else:
            self.queue.update(
                command["id"],
                "reconciliation_required",
                "Unknown dispatched outcome. Observe and inspect journal; "
                "no automatic retry or dependent steps.",
                evidence=action,
            )
        return True

    def advance(self, command: dict[str, Any], evidence: Any) -> None:
        index = command["step"] + 1
        status = "completed" if index == len(command["steps"]) else "queued"
        previous = command.get("evidence") or {}
        if not isinstance(previous, dict):
            previous = {}
        previous.pop("arrival_poll_after", None)
        previous[command["steps"][command["step"]]] = evidence
        self.queue.update(
            command["id"],
            status,
            "Step confirmed from API evidence",
            step=index,
            evidence=previous,
            before_action=None,
        )

    def tick(self) -> bool:
        self.queue.check_compatibility()
        settings = self.queue.report()["settings"]
        if settings["paused"] or stop_requested(self.root):
            self.queue.heartbeat("paused")
            return False
        self.queue.heartbeat("running")
        self.run.deadline = time.monotonic() + 120
        self.run.remaining = 10
        row = self.queue.db.execute(
            "SELECT id FROM commands WHERE status IN "
            "('queued','running','dispatching','in_transit') "
            "ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            self.queue.heartbeat("idle")
            return False
        command = self.queue.get(row[0])
        try:
            if command["status"] == "in_transit":
                after = (command.get("evidence") or {}).get(
                    "arrival_poll_after"
                )
                if after and datetime.fromisoformat(after) > datetime.now(UTC):
                    self.queue.heartbeat("waiting for arrival")
                    return False
            if command["status"] == "dispatching":
                self.fresh()
                self.recover(command)
                return True
            self.queue.update(command["id"], "running", "Revalidating step")
            self.execute_step(command)
        except (
            SafetyStop,
            APIError,
            httpx.HTTPError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            IndexError,
        ) as exc:
            if isinstance(exc, APIError) and exc.authentication_failed:
                request_stop(self.root)
                self.queue.control(True)
            if isinstance(exc, SafetyStop) and "Reset/agent" in str(exc):
                request_stop(self.root)
                self.queue.control(True)
            current = self.queue.get(command["id"])
            if current["status"] == "dispatching":
                self.recover(current)
                if (
                    isinstance(exc, SafetyStop)
                    and self.queue.get(command["id"])["status"] == "blocked"
                ):
                    self.queue.update(command["id"], "blocked", str(exc))
            elif stop_requested(self.root):
                reason = "STOP interrupted; explicit owner resume required"
                if isinstance(exc, APIError) and exc.authentication_failed:
                    reason = (
                        "Authentication/reset failure: refresh token and "
                        "restart worker; no registration"
                    )
                elif isinstance(exc, SafetyStop):
                    reason = str(exc)
                self.queue.update(command["id"], "queued", reason)
            else:
                detail = (
                    str(exc)
                    if isinstance(exc, SafetyStop)
                    else (
                        f"{type(exc).__name__}; refresh evidence "
                        "and inspect journal"
                    )
                )
                self.queue.update(command["id"], "blocked", detail)
        self.queue.heartbeat("idle")
        return True

    def execute_step(self, command: dict[str, Any]) -> None:
        self.evidence_until = time.monotonic() + 30
        payload = command["payload"]
        step = command["steps"][command["step"]]
        if step == "reconcile":
            self.fresh()
            original = self.queue.get(payload["command"])
            if original["status"] != "reconciliation_required":
                raise SafetyStop(
                    "Original command does not need reconciliation"
                )
            evidence = original["evidence"]
            if not isinstance(evidence, dict) or "id" not in evidence:
                raise SafetyStop("No uniquely associated journal action")
            action_id = evidence["id"]
            pending = self.store.pending_action(self.queue.scope, action_id)
            if pending:
                self.run.reconcile(action_id, payload["explanation"])
            else:
                reviewed = self.store.db.execute(
                    "SELECT status FROM actions WHERE id=? AND scope=?",
                    (action_id, self.queue.scope),
                ).fetchone()
                if reviewed is None or reviewed[0] != "reviewed":
                    raise SafetyStop(
                        "Journal evidence changed; manual inspection needed"
                    )
            self.queue.update(
                original["id"],
                "cancelled",
                "Owner reviewed outcome; remaining steps cancelled",
            )
            self.advance(command, {"reviewed_action": action_id})
            return
        if step == "refresh":
            state = self.fresh()
            system = payload["system"]
            if system not in {
                s["nav"]["systemSymbol"] for s in state["ships"]
            }:
                raise SafetyStop("Refresh only an occupied system")
            points = self.run.get_all(f"/systems/{system}/waypoints")
            for point in points:
                self.store.observe(
                    self.queue.scope, "waypoint", point["symbol"], point
                )
            # Earlier observations survive partial refresh failures.
            locations = {
                s["nav"]["waypointSymbol"]
                for s in state["ships"]
                if s["nav"]["status"] != "IN_TRANSIT"
            }
            for point in points:
                if point["symbol"] in locations and any(
                    t["symbol"] == "MARKETPLACE" for t in point["traits"]
                ):
                    self.run.market(point["symbol"])
            self.advance(
                command, {"waypoints": len(points), "observed": now()}
            )
            return
        contract_kind = payload["kind"] in (
            "negotiate_contract",
            "accept_contract",
            "deliver_contract",
            "fulfill_contract",
        )
        symbol = payload.get("ship", "")
        state = self.fresh(symbol)
        ship = (
            next(s for s in state["ships"] if s["symbol"] == symbol)
            if symbol
            else None
        )
        if self.store.pending(self.queue.scope):
            raise SafetyStop("Pending journal outcome requires reconciliation")
        if any(
            p["data"].get("status") != "closed"
            for p in self.store.latest(self.queue.scope, "position")
        ):
            raise SafetyStop("Recover existing automation exposure first")
        # Contract travel without paid refueling is necessary for delivery.
        # Refueling remains blocked until obligations are fully costed; trades
        # separately protect reserves and accepted delivery cargo.
        if (
            not contract_kind
            and (
                step == "refuel"
                or (step == "orbit" and payload.get("refuel") is True)
            )
            and any(
                c.get("accepted") is not False
                and c.get("fulfilled") is not True
                for c in state["contracts"]
            )
        ):
            raise SafetyStop(
                "Active contracts need a costed obligation reserve"
            )
        if contract_kind:
            current = {c["id"]: c for c in state["contracts"]}
            now_at = datetime.now(UTC)
            if step == "negotiate_contract":
                assert ship is not None
                if ship["nav"]["status"] == "IN_TRANSIT":
                    raise SafetyStop("Negotiating ship cannot be in transit")
                if any(
                    c["accepted"] and not c["fulfilled"]
                    for c in state["contracts"]
                ):
                    raise SafetyStop("Resolve the active contract first")
                result = self.mutate(
                    command, f"/my/ships/{symbol}/negotiate/contract"
                )
            else:
                contract = current.get(payload["contract"])
                if contract is None:
                    raise SafetyStop("Contract no longer exists")
                terms = contract.get("terms", {})
                deadline_key = (
                    "deadlineToAccept"
                    if step == "accept_contract"
                    else "deadline"
                )
                deadline = contract.get(deadline_key) or terms.get(
                    deadline_key
                )
                if step == "accept_contract" and not deadline:
                    deadline = contract.get("expiration")
                if (
                    not isinstance(deadline, str)
                    or datetime.fromisoformat(deadline) <= now_at
                ):
                    raise SafetyStop("Contract deadline has expired")
                if step == "accept_contract":
                    if contract["accepted"] or contract["fulfilled"]:
                        raise SafetyStop("Contract is no longer an open offer")
                    acceptance = contract_preview(
                        self.store, self.queue.scope, payload["contract"]
                    )
                    if (
                        not acceptance["feasible"]
                        or acceptance["evidence"] != payload["evidence"]
                    ):
                        raise SafetyStop(
                            "Acceptance evidence changed or is not funded"
                        )
                    result = self.mutate(
                        command, f"/my/contracts/{payload['contract']}/accept"
                    )
                elif step == "deliver_contract":
                    assert ship is not None
                    if not contract["accepted"] or contract["fulfilled"]:
                        raise SafetyStop("Contract is not active")
                    matches = [
                        d
                        for d in terms.get("deliver", [])
                        if d.get("tradeSymbol") == payload["good"]
                        and d.get("destinationSymbol")
                        == payload["destination"]
                    ]
                    if len(matches) != 1:
                        raise SafetyStop("Good is not a unique deliverable")
                    term = matches[0]
                    remaining = term["unitsRequired"] - term["unitsFulfilled"]
                    inventory = {
                        i["symbol"]: i["units"]
                        for i in ship["cargo"].get("inventory", [])
                    }
                    if (
                        ship["nav"]["status"] != "DOCKED"
                        or ship["nav"]["waypointSymbol"]
                        != term["destinationSymbol"]
                    ):
                        raise SafetyStop(
                            "Ship must be docked at the destination"
                        )
                    if payload["units"] > min(
                        remaining, inventory.get(payload["good"], 0)
                    ):
                        raise SafetyStop(
                            "Delivery exceeds cargo or remaining units"
                        )
                    result = self.mutate(
                        command,
                        f"/my/contracts/{payload['contract']}/deliver",
                        {
                            "shipSymbol": symbol,
                            "tradeSymbol": payload["good"],
                            "units": payload["units"],
                        },
                    )
                    self.run.ship(symbol)
                else:
                    if not contract["accepted"] or contract["fulfilled"]:
                        raise SafetyStop("Contract is not ready to fulfill")
                    if any(
                        d["unitsFulfilled"] != d["unitsRequired"]
                        for d in terms.get("deliver", [])
                    ):
                        raise SafetyStop("Delivery obligations remain")
                    result = self.mutate(
                        command, f"/my/contracts/{payload['contract']}/fulfill"
                    )
            self.fresh(symbol)
            self.advance(command, {"receipt": result})
            return
        assert ship is not None
        nav = ship["nav"]
        if step in ("purchase", "sell"):
            if (
                nav["status"] != "DOCKED"
                or nav["waypointSymbol"] != payload["waypoint"]
            ):
                raise SafetyStop(
                    "Trade ship must remain docked at the quoted market"
                )
            estimate = trade_preview(
                self.store,
                self.queue.scope,
                symbol,
                payload["good"],
                payload["units"],
                step,
            )
            if estimate["observed_at"] != payload["observed_at"]:
                raise SafetyStop(
                    "Trade preview evidence changed; preview again"
                )
            market = self.run.market(nav["waypointSymbol"])
            quotes = [
                g
                for g in market.get("tradeGoods", [])
                if g.get("symbol") == payload["good"]
            ]
            key = "purchasePrice" if step == "purchase" else "sellPrice"
            if (
                len(quotes) != 1
                or quotes[0].get(key) != payload["quote"]
                or type(quotes[0].get("tradeVolume")) is not int
                or quotes[0]["tradeVolume"] < payload["units"]
            ):
                raise SafetyStop(
                    "Market price or volume changed; refresh and preview again"
                )
            latest = self.fresh(symbol)
            latest_ship = next(
                s for s in latest["ships"] if s["symbol"] == symbol
            )
            if (
                latest_ship != ship
                or latest["agent"]["credits"] != state["agent"]["credits"]
                or not estimate["feasible"]
            ):
                raise SafetyStop(
                    "Trade preconditions changed or reserves/cargo are "
                    "insufficient"
                )
            result = self.mutate(
                command,
                f"/my/ships/{symbol}/{step}",
                {"symbol": payload["good"], "units": payload["units"]},
            )
            self.run.ship(symbol)
            self.fresh(symbol)
            self.advance(command, {"receipt": result, "preview": estimate})
            return
        if step == "arrival":
            if nav["waypointSymbol"] != payload["destination"]:
                raise SafetyStop("Ship destination changed during trip")
            if nav["status"] == "IN_TRANSIT":
                current_time = datetime.now(UTC)
                arrival = datetime.fromisoformat(nav["route"]["arrival"])
                remaining = (arrival - current_time).total_seconds()
                delay = min(30, remaining) if remaining > 0 else 5
                after = (current_time + timedelta(seconds=delay)).isoformat()
                evidence = dict(command.get("evidence") or {})
                evidence["arrival_poll_after"] = after
                self.queue.update(
                    command["id"],
                    "in_transit",
                    f"Awaiting API-confirmed arrival; next check {after}",
                    evidence=evidence,
                )
                return
            self.advance(command, {"ship": ship, "observed": now()})
            return
        if nav["status"] == "IN_TRANSIT":
            raise SafetyStop("Ship is in transit; wait for confirmed arrival")
        if payload["kind"] == "trip" and step == "orbit":
            if nav["waypointSymbol"] == payload["destination"]:
                self.advance(command, {"already": "destination"})
                return
            plan = self.run.navigation_plan(ship, payload["destination"])
            if not plan["feasible"]:
                raise SafetyStop(plan["reason"])
            latest = self.fresh(symbol)
            if (
                next(s for s in latest["ships"] if s["symbol"] == symbol)
                != ship
                or latest["contracts"] != state["contracts"]
                or latest["agent"]["credits"]
                < plan.get("protected_credits", CREDIT_FLOOR)
            ):
                raise SafetyStop("Flight preconditions changed before orbit")
        if (
            payload["kind"] == "trip"
            and step in ("dock", "refuel")
            and nav["waypointSymbol"] != payload["destination"]
        ):
            raise SafetyStop("Ship moved before dependent arrival step")
        if step in ("orbit", "dock"):
            desired = "IN_ORBIT" if step == "orbit" else "DOCKED"
            if nav["status"] == desired:
                self.advance(command, {"ship": ship, "already": desired})
                return
            result = self.mutate(command, f"/my/ships/{symbol}/{step}")
        elif step == "navigate":
            if nav["waypointSymbol"] == payload["destination"]:
                self.advance(command, {"ship": ship, "already": "destination"})
                return
            plan = self.run.navigation_plan(ship, payload["destination"])
            if not plan["feasible"]:
                raise SafetyStop(plan["reason"])
            if nav["status"] != "IN_ORBIT":
                raise SafetyStop("Ship must be in orbit before navigation")
            # Recheck account and ship after quote/waypoint reads.
            latest = self.fresh(symbol)
            latest_ship = next(
                s for s in latest["ships"] if s["symbol"] == symbol
            )
            if (
                latest_ship != ship
                or latest["contracts"] != state["contracts"]
            ):
                raise SafetyStop(
                    "Flight preconditions changed; refresh/replan"
                )
            if latest["agent"]["credits"] < plan.get(
                "protected_credits", CREDIT_FLOOR
            ):
                raise SafetyStop(
                    "Flight would violate protected credit reserve"
                )
            result = self.mutate(
                command,
                f"/my/ships/{symbol}/navigate",
                {"waypointSymbol": payload["destination"]},
            )
            route = result["nav"]["route"]
            duration = datetime.fromisoformat(
                route["arrival"]
            ) - datetime.fromisoformat(route["departureTime"])
            estimate = preview(
                self.store, self.queue.scope, symbol, payload["destination"]
            )
            result = {
                "receipt": result,
                "estimate": plan,
                "comparison": {
                    "estimated_fuel": plan["estimated_leg_fuel"],
                    "observed_fuel_used": ship["fuel"]["current"]
                    - result["fuel"]["current"],
                    "estimated_seconds": estimate["seconds"],
                    "observed_route_seconds": duration.total_seconds(),
                },
            }
        elif step == "refuel":
            if nav["status"] != "DOCKED":
                raise SafetyStop("Dock before refueling")
            plan = refuel_run(self.run, symbol, plan_only=True)
            if plan.get("status"):
                self.advance(command, plan)
                return
            # Refuse ambiguous duplicate quotes before permitting paid refuel.
            market = self.run.market(nav["waypointSymbol"])
            fuel_quotes = [
                g
                for g in market.get("tradeGoods", [])
                if g.get("symbol") == "FUEL"
            ]
            if (
                market.get("symbol") != nav["waypointSymbol"]
                or len(fuel_quotes) != 1
                or any(
                    type(fuel_quotes[0].get(k)) is not int
                    or fuel_quotes[0][k] <= 0
                    for k in ("purchasePrice", "tradeVolume")
                )
            ):
                raise SafetyStop("No unique valid current FUEL quote")
            latest_cost = math.ceil(plan["missing_fuel"] / 100) * math.ceil(
                fuel_quotes[0]["purchasePrice"] * 1.2
            )
            if latest_cost > plan["maximum_estimated_cost"]:
                raise SafetyStop("Fuel quote changed; refresh/replan")
            latest = self.fresh(symbol)
            latest_ship = next(
                s for s in latest["ships"] if s["symbol"] == symbol
            )
            if (
                latest_ship != ship
                or latest["contracts"] != state["contracts"]
                or latest["agent"]["credits"]
                < CREDIT_FLOOR
                + FUEL_ALLOWANCE
                + plan["maximum_estimated_cost"]
            ):
                raise SafetyStop(
                    "Refuel preconditions changed; refresh/replan"
                )
            result = self.mutate(command, f"/my/ships/{symbol}/refuel")
        else:
            raise SafetyStop("Unsupported flight step")
        self.run.ship(symbol)
        self.advance(command, result)
