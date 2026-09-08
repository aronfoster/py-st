"""Offline, fixed-route counterfactual replay of recorded market quotes."""

from __future__ import annotations

import json
import math
import sqlite3
from bisect import bisect_right
from collections import Counter
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def utc_time(value: str) -> datetime:
    """Require an explicit timezone; local-time guesses spoil as-of joins."""
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Timestamps must include a timezone (Z or +00:00)")
    return result.astimezone(UTC)


@dataclass(frozen=True)
class RouteScenario:
    scope: str
    source: str
    destination: str
    good: str
    start: str
    end: str
    leg_seconds: int
    fuel_allowance: int
    capacity: int = 40
    initial_credits: int = 175_000
    credit_floor: int = 50_000
    max_age: int = 900
    slippage_bps: int = 500


@dataclass(frozen=True)
class Quote:
    observation_id: int
    observed_at: datetime
    purchase: int
    sell: int
    volume: int

    def evidence(self, at: datetime) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "observed_at": self.observed_at.isoformat(),
            "age_seconds": (at - self.observed_at).total_seconds(),
            "purchase_price": self.purchase,
            "sell_price": self.sell,
            "trade_volume": self.volume,
            "source": "live-api",
        }


def evaluate_route(path: Path, scenario: RouteScenario) -> dict[str, Any]:
    """Replay one chosen route, never select routes using subsequent outcomes.

    Quotes are evidence of prices, not fills. No game client or writable
    Intelligence instance is constructed. An unresolved exit blocks re-entry.
    """
    s = scenario
    start, end = utc_time(s.start), utc_time(s.end)
    if start >= end:
        raise ValueError("start must precede end")
    if (
        not all((s.scope, s.source, s.destination, s.good))
        or s.source == s.destination
        or s.source.rsplit("-", 1)[0] != s.destination.rsplit("-", 1)[0]
    ):
        raise ValueError(
            "Choose a scope, good and distinct same-system markets"
        )
    if (
        s.leg_seconds <= 0
        or s.fuel_allowance < 0
        or s.capacity <= 0
        or s.credit_floor < 50_000
        or s.initial_credits < s.credit_floor
        or s.max_age <= 0
        or not 0 <= s.slippage_bps < 10_000
    ):
        raise ValueError(
            "Invalid scenario limits; credit floor is at least 50000"
        )

    quotes: dict[str, list[Quote]] = {s.source: [], s.destination: []}
    # mode=ro refuses nonexistent databases and cannot migrate or journal runs.
    with closing(
        sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Expected intelligence schema version 1")
        if not db.execute(
            "SELECT 1 FROM observations WHERE scope=? LIMIT 1", (s.scope,)
        ).fetchone():
            raise ValueError("Unknown scope; choose an existing RESET:AGENT")
        rows = db.execute(
            "SELECT id,key,observed_at,data FROM observations "
            "WHERE scope=? AND kind='market' AND source='live-api' "
            "AND key IN (?,?) ORDER BY id",
            (s.scope, s.source, s.destination),
        )
        for identifier, key, timestamp, payload in rows:
            at = utc_time(timestamp)
            if at > end:
                continue
            goods = json.loads(payload).get("tradeGoods") or []
            matches = [g for g in goods if g.get("symbol") == s.good]
            if not matches:
                continue
            if len(matches) != 1:
                raise ValueError(f"Duplicate good in observation {identifier}")
            good = matches[0]
            values = [
                good.get(field)
                for field in ("purchasePrice", "sellPrice", "tradeVolume")
            ]
            if any(type(v) is not int or v <= 0 for v in values):
                raise ValueError(f"Invalid quote in observation {identifier}")
            quotes[key].append(Quote(identifier, at, *values))

    for history in quotes.values():
        history.sort(key=lambda q: (q.observed_at, q.observation_id))
    buyers = quotes[s.destination]
    buyer_keys = [(q.observed_at, q.observation_id) for q in buyers]
    credits = s.initial_credits
    available_at = start
    attempts: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    results: list[int] = []
    open_position = False
    candidates = 0
    for buy in quotes[s.source]:
        at = buy.observed_at
        if not start <= at <= end:
            continue
        candidates += 1
        if open_position:
            skipped["unresolved_position"] += 1
            continue
        if at < available_at:
            skipped["in_transit"] += 1
            continue
        if (end - at).total_seconds() < 2 * s.leg_seconds:
            skipped["insufficient_horizon"] += 1
            continue
        arrival = at + timedelta(seconds=s.leg_seconds)
        available_at_next = arrival + timedelta(seconds=s.leg_seconds)
        # ID breaks timestamp ties: a later recorded quote is not known yet.
        index = bisect_right(buyer_keys, (at, buy.observation_id)) - 1
        if (
            index < 0
            or (at - buyers[index].observed_at).total_seconds() > s.max_age
        ):
            skipped["missing_or_stale_entry_buyer"] += 1
            continue
        buyer = buyers[index]
        buy_price = (buy.purchase * (10_000 + s.slippage_bps) + 9999) // 10_000
        planned_sell = buyer.sell * (10_000 - s.slippage_bps) // 10_000
        affordable = max(
            0, (credits - s.credit_floor - s.fuel_allowance) // buy_price
        )
        units = min(s.capacity, buy.volume, buyer.volume, affordable)
        planned_net = units * (planned_sell - buy_price) - s.fuel_allowance
        if units == 0:
            skipped["credit_reserve"] += 1
            continue
        if planned_net <= 0:
            skipped["nonpositive_entry_margin"] += 1
            continue
        cost = units * buy_price + s.fuel_allowance
        credits -= cost
        attempt: dict[str, Any] = {
            "entry_at": at.isoformat(),
            "arrival_at": arrival.isoformat(),
            "available_at": available_at_next.isoformat(),
            "units": units,
            "buy_unit_assumption": buy_price,
            "entry_net_estimate": planned_net,
            "cash_committed": cost,
            "source_quote": buy.evidence(at),
            "entry_buyer_quote": buyer.evidence(at),
        }
        attempts.append(attempt)
        # At arrival, only quotes already observed are eligible, never the
        # nearest future quote. Require new evidence since the entry decision.
        index = bisect_right(buyer_keys, (arrival, math.inf)) - 1
        exit_quote = buyers[index] if index >= 0 else None
        reason = "missing_post_entry_exit_quote"
        if exit_quote is not None and exit_quote.observed_at > at:
            attempt["exit_quote"] = exit_quote.evidence(arrival)
            reason = "stale_exit_quote"
            if (arrival - exit_quote.observed_at).total_seconds() <= s.max_age:
                reason = "insufficient_exit_volume"
                if exit_quote.volume >= units:
                    sell_price = (
                        exit_quote.sell * (10_000 - s.slippage_bps) // 10_000
                    )
                    proceeds = units * sell_price
                    net = proceeds - cost
                    credits += proceeds
                    results.append(net)
                    attempt.update(
                        status="settled_scenario",
                        sell_unit_assumption=sell_price,
                        scenario_net=net,
                        cash_after=credits,
                    )
                    available_at = available_at_next
                    continue
        attempt.update(status="unresolved", reason=reason, cash_after=credits)
        open_position = True

    return {
        "scenario": asdict(s),
        "note": "Counterfactual quote replay, not realized or guaranteed "
        "profit. "
        "No live requests or mutations. See docs/HISTORICAL_ROUTES.md.",
        "summary": {
            "source_candidates": candidates,
            "entries": len(attempts),
            "settled": len(results),
            "unresolved": int(open_position),
            "skipped": dict(sorted(skipped.items())),
            "settled_scenario_net": sum(results),
            "worst_settled_net": min(results) if results else None,
            "losses": sum(net < 0 for net in results),
            "ending_cash": credits,
            "cash_change": credits - s.initial_credits,
            "unvalued_inventory_units": (
                attempts[-1]["units"] if open_position else 0
            ),
        },
        "attempts": attempts,
    }
