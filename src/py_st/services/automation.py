"""Bounded, single-writer live sessions with a durable mutation journal."""

from __future__ import annotations

import fcntl
import math
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from py_st import cache
from py_st._generated.models import Contract
from py_st.client import APIError, SpaceTradersClient
from py_st.client.transport import JSONDict, JSONList, RequestAborted
from py_st.services.intelligence import Intelligence


class SafetyStop(Exception):
    """A resumable stop, not permission to replay an uncertain action."""


class Session:
    def __init__(
        self,
        client: SpaceTradersClient,
        store: Intelligence,
        *,
        execute: bool = False,
        seconds: int = 600,
        actions: int = 30,
        root: Path = Path("."),
    ) -> None:
        if not 1 <= seconds <= 7200 or not 1 <= actions <= 200:
            raise ValueError("Bounds: 1..7200 seconds, 1..200 actions")
        self.client = client
        self.store = store
        self.execute = execute
        self.deadline = time.monotonic() + seconds
        self.remaining = actions
        self.root = root
        self.scope = ""
        state = root / ".state"
        state.mkdir(parents=True, exist_ok=True)
        self.lock = (state / "automation.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise SafetyStop("Another automation session is active") from None
        client.set_wait(self.wait)

    def close(self) -> None:
        self.client.set_wait(time.sleep)
        self.lock.close()

    def check(self) -> None:
        if (self.root / "STOP").exists():
            raise SafetyStop("STOP sentinel present; remove deliberately")
        if time.monotonic() >= self.deadline:
            raise SafetyStop(
                "Wall-clock budget exhausted; resume from live state"
            )

    def wait(self, seconds: float) -> None:
        until = time.monotonic() + seconds
        while True:
            self.check()
            left = until - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(left, 0.25))

    def get(self, path: str) -> JSONDict:
        self.check()
        return cast(JSONDict, self.client.request("GET", path))

    def refresh(self) -> dict[str, Any]:
        status = self.client.status()
        agent = self.get("/my/agent")
        scope = f"{status['resetDate']}:{agent['symbol']}"
        if self.scope and self.scope != scope:
            raise SafetyStop(
                "Reset/agent changed; start a new reviewed session"
            )
        self.scope = scope
        agent.pop("accountId", None)
        self.store.observe(scope, "agent", agent["symbol"], agent)
        result: dict[str, Any] = {"agent": agent}
        for plural, kind, key in (
            ("ships", "ship", "symbol"),
            ("contracts", "contract", "id"),
        ):
            self.check()
            items = cast(
                JSONList,
                self.client.request("GET", f"/my/{plural}", paginate=True),
            )
            result[plural] = items
            for item in items:
                self.store.observe(scope, kind, item[key], item)
        return result

    def check_reposition(self) -> None:
        if any(
            p["key"].startswith("reposition:")
            and p["data"].get("status") != "closed"
            for p in self.store.latest(self.scope, "position")
        ):
            raise SafetyStop("Recover open reposition before other automation")

    def mutate(
        self, path: str, body: JSONDict | None = None, *, reposition: str = ""
    ) -> JSONDict:
        self.check()
        if not re.fullmatch(
            r"/my/(ships/[A-Za-z0-9_-]+/"
            r"(orbit|dock|navigate|purchase|sell|refuel|negotiate/contract)"
            r"|contracts/[A-Za-z0-9_-]+/(accept|deliver|fulfill))",
            path,
        ):
            raise SafetyStop(
                "Mutation is outside the reviewed automation allowlist"
            )
        if not self.scope:
            raise SafetyStop("Observe live state before mutations")
        if reposition:
            positions = [
                p
                for p in self.store.latest(self.scope, "position")
                if p["data"].get("status") != "closed"
            ]
            if (
                len(positions) != 1
                or positions[0]["key"] != reposition
                or not reposition.startswith("reposition:")
                or positions[0]["data"].get("status") != "open"
            ):
                raise SafetyStop("Ambiguous reposition mutation authority")
            ship = reposition.removeprefix("reposition:")
            source = positions[0]["data"].get("plan", {}).get("source")
            if not (
                (path == f"/my/ships/{ship}/orbit" and body is None)
                or (
                    path == f"/my/ships/{ship}/navigate"
                    and source
                    and body == {"waypointSymbol": source}
                )
            ):
                raise SafetyStop("Reposition permits only original approach")
        else:
            self.check_reposition()
        if not self.execute:
            raise SafetyStop(f"Dry run: would POST {path} {body or {}}")
        if self.remaining <= 0:
            raise SafetyStop("Action budget exhausted; resume from live state")
        if self.store.pending(self.scope):
            raise SafetyStop(
                "Pending action: inspect journal and reconcile first"
            )
        self.remaining -= 1
        action = self.store.begin_action(self.scope, path, body)
        cache.clear_cache()
        try:
            result = cast(
                JSONDict, self.client.request("POST", path, body=body)
            )
        except RequestAborted as exc:
            self.store.finish_action(
                action,
                "not_sent" if exc.status is None else "rejected",
                {
                    "status": exc.status,
                    "reason": "Interrupted before dispatch",
                },
            )
            if exc.__cause__ is not None:
                raise exc.__cause__ from None
            raise
        except APIError as exc:
            # Rejections are definitive; transport/5xx remains uncertain.
            if exc.status is not None and 400 <= exc.status < 500:
                self.store.finish_action(
                    action,
                    "rejected",
                    {
                        "status": exc.status,
                        "code": exc.code,
                    },
                )
            raise
        if path.endswith("/negotiate/contract"):
            try:
                Contract.model_validate(result.get("contract"))
            except ValidationError:
                raise SafetyStop(
                    "Invalid negotiation response; reconcile pending action"
                ) from None
        if "agent" in result:
            result["agent"].pop("accountId", None)
        self.store.finish_action(action, "succeeded", result)
        if "contract" in result:
            contract = result["contract"]
            self.store.observe(
                self.scope, "contract", contract["id"], contract
            )
        if "agent" in result:
            agent = dict(result["agent"])
            agent.pop("accountId", None)
            self.store.observe(self.scope, "agent", agent["symbol"], agent)
        if "transaction" in result:
            self.store.observe(
                self.scope, "transaction", str(action), result["transaction"]
            )
        return result

    def ship(self, symbol: str) -> JSONDict:
        ship = self.get(f"/my/ships/{symbol}")
        self.store.observe(self.scope, "ship", symbol, ship)
        return ship

    def market(self, waypoint: str) -> JSONDict:
        system = waypoint.rsplit("-", 1)[0]
        market = self.get(f"/systems/{system}/waypoints/{waypoint}/market")
        self.store.observe(self.scope, "market", waypoint, market)
        return market

    def arrive(self, symbol: str) -> JSONDict:
        for _ in range(100):
            ship = self.ship(symbol)
            if ship["nav"]["status"] != "IN_TRANSIT":
                return ship
            arrival = datetime.fromisoformat(ship["nav"]["route"]["arrival"])
            self.wait(max(1, (arrival - datetime.now(UTC)).total_seconds()))
        raise SafetyStop("Arrival not confirmed after bounded polling")

    def dock(self, symbol: str) -> JSONDict:
        ship = self.arrive(symbol)
        if ship["nav"]["status"] != "DOCKED":
            self.mutate(f"/my/ships/{symbol}/dock")
            ship = self.ship(symbol)
        return ship

    def navigate(self, symbol: str, destination: str) -> JSONDict:
        ship = self.arrive(symbol)
        plan = self.navigation_plan(ship, destination)
        self.store.observe(self.scope, "plan", f"move:{symbol}", plan)
        if ship["nav"]["waypointSymbol"] == destination:
            return ship
        if not plan["feasible"]:
            raise SafetyStop(plan["reason"])
        if ship["nav"]["status"] != "IN_ORBIT":
            self.mutate(f"/my/ships/{symbol}/orbit")
        if (
            plan["policy"] == "destination-refuel"
            and (
                datetime.now(UTC)
                - datetime.fromisoformat(plan["fuel_quote_observed_at"])
            ).total_seconds()
            > 60
        ):
            raise SafetyStop("Destination fuel quote expired; replan")
        self.mutate(
            f"/my/ships/{symbol}/navigate", {"waypointSymbol": destination}
        )
        return self.arrive(symbol)

    def navigation_plan(
        self, ship: JSONDict, destination: str
    ) -> dict[str, Any]:
        """Cost one CRUISE leg; historical prices never authorize departure."""
        nav = ship["nav"]
        if nav["waypointSymbol"] == destination:
            return {"feasible": True, "policy": "already there"}
        if destination.rsplit("-", 1)[0] != nav["systemSymbol"]:
            raise SafetyStop("Only same-system navigation is enabled")
        if nav["flightMode"] != "CRUISE":
            raise SafetyStop("Only CRUISE is enabled")
        target = self.get(
            f"/systems/{nav['systemSymbol']}/waypoints/{destination}"
        )
        origin = nav["route"]["destination"]
        distance = max(
            1,
            math.ceil(
                math.hypot(
                    target["x"] - origin["x"], target["y"] - origin["y"]
                )
            ),
        )
        capacity = ship["fuel"]["capacity"]
        current = ship["fuel"]["current"]
        plan: dict[str, Any] = {
            "source": nav["waypointSymbol"],
            "destination": destination,
            "flight_mode": "CRUISE",
            "estimated_leg_fuel": distance if capacity else 0,
            "required_fuel": 2 * distance + 10 if capacity else 0,
            "policy": "round-trip",
            "feasible": not capacity or current >= 2 * distance + 10,
            "reason": "Insufficient round-trip fuel plus 10-unit margin",
        }
        if plan["feasible"]:
            plan["reason"] = "Carried round-trip reserve or fuel-free ship"
            return plan
        margin = max(10, math.ceil(distance * 0.1))
        plan["one_way_required_fuel"] = distance + margin
        if current < distance + margin:
            plan["reason"] = "Insufficient one-way fuel plus route margin"
            return plan
        if not any(
            t["symbol"] == "MARKETPLACE" for t in target.get("traits", [])
        ):
            return plan
        # A fresh sparse response must not resurrect an old detailed quote.
        market = self.market(destination)
        observed_at = datetime.now(UTC)
        fuel = next(
            (g for g in market.get("tradeGoods", []) if g["symbol"] == "FUEL"),
            None,
        )
        if (
            market.get("symbol") != destination
            or not fuel
            or fuel.get("purchasePrice", 0) <= 0
            or fuel.get("tradeVolume", 0) <= 0
        ):
            plan["reason"] += "; no fresh usable destination FUEL quote"
            return plan
        state = self.refresh()
        if any(
            c["accepted"] and not c["fulfilled"] for c in state["contracts"]
        ):
            plan["reason"] = "One-way travel needs costed contract obligations"
            return plan
        if any(
            p["data"].get("status") == "open"
            for p in self.store.latest(self.scope, "position")
        ) or self.store.pending(self.scope):
            plan["reason"] = "Resolve open positions/pending actions first"
            return plan
        # Fund a full tank after 20% price growth, including refuel_run's own
        # 20% headroom. No cargo sales or future payouts finance recovery.
        refill = math.ceil(capacity / 100) * math.ceil(
            math.ceil(fuel["purchasePrice"] * 1.2) * 1.2
        )
        plan.update(
            {
                "policy": "destination-refuel",
                "required_fuel": distance + margin,
                "safety_margin": margin,
                "fuel_purchase_price": fuel["purchasePrice"],
                "fuel_quote_observed_at": observed_at.isoformat(),
                "full_refill_credit_reserve": refill,
                "protected_credits": 50_000 + 1_000 + refill,
                "recovery": "Dock and run auto refuel here before onward "
                "travel; recheck quote and credits. No DRIFT fallback.",
                "feasible": state["agent"]["credits"] >= 51_000 + refill,
                "reason": "Destination refill would violate credit reserve",
            }
        )
        if (datetime.now(UTC) - observed_at).total_seconds() > 60:
            plan.update(
                feasible=False, reason="Destination fuel quote expired"
            )
        elif plan["feasible"]:
            plan["reason"] = "Fresh destination fuel and full refill funded"
        return plan

    def scan(self, system: str) -> dict[str, Any]:
        self.refresh()
        waypoints = cast(
            JSONList,
            self.client.request(
                "GET", f"/systems/{system}/waypoints", paginate=True
            ),
        )
        markets = []
        for waypoint in waypoints:
            self.check()
            self.store.observe(
                self.scope, "waypoint", waypoint["symbol"], waypoint
            )
            if any(t["symbol"] == "MARKETPLACE" for t in waypoint["traits"]):
                market = self.market(waypoint["symbol"])
                markets.append(
                    {
                        "symbol": market["symbol"],
                        "exports": [g["symbol"] for g in market["exports"]],
                        "priced": bool(market.get("tradeGoods")),
                    }
                )
        return {"scope": self.scope, "markets": markets}

    def reconcile(self, action_id: int, evidence: str = "") -> dict[str, Any]:
        """Record review after fresh observations, never replay API calls."""
        state = self.refresh()
        action = self.store.pending_action(self.scope, action_id)
        if action is None:
            raise SafetyStop(
                "No pending action with that ID in the live scope"
            )
        result = {
            "action": action,
            "fresh_state": state,
            "warning": "Confirm actual effect before recording review",
        }
        if evidence:
            if len(evidence.strip()) < 20:
                raise SafetyStop(
                    "Provide a concrete outcome explanation (20+ characters)"
                )
            self.store.finish_action(
                action_id,
                "reviewed",
                {
                    "evidence": evidence,
                    "fresh_state": state,
                },
            )
        return result
