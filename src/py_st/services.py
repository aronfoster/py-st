from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from .api_client import APIError, SpaceTraders
from .models import (
    Agent,
    Contract,
    Extraction,
    Market,
    MarketTransaction,
    Ship,
    ShipCargo,
    ShipFuel,
    ShipNav,
    ShipNavFlightMode,
    Shipyard,
    Survey,
    TradeGood,
    Waypoint,
)


@dataclass
class MarketGoods:
    sells: list[TradeGood] = []
    buys: list[TradeGood] = []


@dataclass
class SystemGoods:
    by_waypoint: dict[str, MarketGoods] = {}
    # by_good maps TRADE_SYMBOL -> {"sells": [waypoints], "buys": [waypoints]}
    by_good: dict[str, dict[str, list[str]]] = {}


def _sym(obj: Any) -> str:
    """
    Return a plain string trade symbol from either:
    - a TradeGood (g.symbol may be Enum or str)
    - an Enum value (use .value)
    - a raw str
    """
    if hasattr(obj, "symbol"):
        s = obj.symbol
    elif hasattr(obj, "tradeSymbol"):
        s = obj.tradeSymbol
    else:
        s = obj
    return s.value if hasattr(s, "value") else str(s)


def _has_marketplace(wp: dict[str, Any]) -> bool:
    return any(t.get("symbol") == "MARKETPLACE" for t in wp.get("traits", []))


def _uniq_by_symbol(goods: list[TradeGood] | None) -> list[TradeGood]:
    if not goods:
        return []
    seen: set[str] = set()
    out: list[TradeGood] = []
    for g in goods:
        k = _sym(g)
        if k not in seen:
            seen.add(k)
            out.append(g)
    return out


def get_agent_info(token: str) -> Agent:
    """
    Fetches agent data from the API.
    """
    client = SpaceTraders(token=token)
    agent = client.get_agent()
    return agent


def list_contracts(token: str) -> list[Contract]:
    """
    Fetches all contracts from the API.
    """
    client = SpaceTraders(token=token)
    contracts = client.get_contracts()
    return contracts


def negotiate_contract(token: str, ship_symbol: str) -> Contract:
    """
    Negotiates a new contract using the specified ship.
    """
    client = SpaceTraders(token=token)
    new_contract = client.negotiate_contract(ship_symbol)
    return new_contract


def deliver_contract(
    token: str,
    contract_id: str,
    ship_symbol: str,
    trade_symbol: str,
    units: int,
) -> tuple[Contract, ShipCargo]:
    """
    Delivers cargo to fulfill part of a contract.
    """
    client = SpaceTraders(token=token)
    contract, cargo = client.deliver_contract(
        contract_id, ship_symbol, trade_symbol, units
    )
    return contract, cargo


def fulfill_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Fulfills a contract.
    """
    client = SpaceTraders(token=token)
    agent, contract = client.fulfill_contract(contract_id)
    return agent, contract


def accept_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Accepts a contract.
    """
    client = SpaceTraders(token=token)
    result = client.accept_contract(contract_id)
    agent: Agent = cast(Agent, result["agent"])
    contract: Contract = cast(Contract, result["contract"])
    return agent, contract


def list_ships(token: str) -> list[Ship]:
    """
    Fetches all ships from the API.
    """
    client = SpaceTraders(token=token)
    ships = client.get_ships()
    return ships


def navigate_ship(
    token: str, ship_symbol: str, waypoint_symbol: str
) -> ShipNav:
    """
    Navigates a ship to a waypoint.
    """
    client = SpaceTraders(token=token)
    result = client.navigate_ship(ship_symbol, waypoint_symbol)
    return result


def orbit_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Moves a ship into orbit.
    """
    client = SpaceTraders(token=token)
    result = client.orbit_ship(ship_symbol)
    return result


def dock_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Docks a ship.
    """
    client = SpaceTraders(token=token)
    result = client.dock_ship(ship_symbol)
    return result


def extract_resources(
    token: str, ship_symbol: str, survey_json: str | None = None
) -> Extraction | None:
    """
    Extracts resources from a waypoint, optionally using a survey.
    """
    try:
        client = SpaceTraders(token=token)
        survey_to_use = None
        if survey_json:
            try:
                survey_data = json.loads(survey_json)
                survey_to_use = Survey.model_validate(survey_data)
            except (json.JSONDecodeError, TypeError):
                print("Error: Invalid survey JSON provided. Aborting.")
                return None

        extraction = client.extract_resources(
            ship_symbol, survey=survey_to_use
        )
        return extraction
    except APIError as e:
        print(f"Extraction failed: {e}")
        return None


def create_survey(token: str, ship_symbol: str) -> list[Survey]:
    """
    Creates a survey of the current waypoint.
    """
    client = SpaceTraders(token=token)
    surveys = client.create_survey(ship_symbol)
    return surveys


def refuel_ship(
    token: str, ship_symbol: str, units: int | None
) -> tuple[Agent, ShipFuel, MarketTransaction]:
    """
    Refuels a ship.
    """
    client = SpaceTraders(token=token)
    agent, fuel, transaction = client.refuel_ship(ship_symbol, units)
    return agent, fuel, transaction


def jettison_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> ShipCargo:
    """
    Jettisons cargo from a ship.
    """
    client = SpaceTraders(token=token)
    cargo = client.jettison_cargo(ship_symbol, trade_symbol, units)
    return cargo


def set_flight_mode(
    token: str, ship_symbol: str, flight_mode: ShipNavFlightMode
) -> ShipNav:
    """
    Sets the flight mode for a ship.
    """
    client = SpaceTraders(token=token)
    nav = client.set_flight_mode(ship_symbol, flight_mode)
    return nav


def list_waypoints(
    token: str, system_symbol: str, traits: list[str] | None
) -> list[Waypoint]:
    """
    Lists waypoints in a system, optionally filtered by traits.
    """
    client = SpaceTraders(token=token)
    waypoints = client.get_waypoints_in_system(system_symbol, traits=traits)
    return waypoints


def get_shipyard(
    token: str, system_symbol: str, waypoint_symbol: str
) -> Shipyard:
    """
    Gets the shipyard for a waypoint.
    """
    client = SpaceTraders(token=token)
    shipyard = client.get_shipyard(system_symbol, waypoint_symbol)
    return shipyard


def refine_materials(token: str, ship_symbol: str, produce: str) -> None:
    """
    Refines materials on a ship and prints the result.
    """
    try:
        client = SpaceTraders(token=token)
        result = client.refine_materials(ship_symbol, produce)
        print("🔬 Refining complete!")
        # The response contains multiple nested models.
        # For simplicity, we'll print the raw dictionary.
        print(json.dumps(result, indent=2))
    except APIError as e:
        print(f"Refining failed: {e}")


def get_market(token: str, system_symbol: str, waypoint_symbol: str) -> Market:
    """
    Gets the market for a waypoint.
    """
    client = SpaceTraders(token=token)
    return client.get_market(system_symbol, waypoint_symbol)


def sell_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> tuple[Agent, ShipCargo, MarketTransaction]:
    """
    Sells cargo from a ship at the current marketplace.
    """
    client = SpaceTraders(token=token)
    return client.sell_cargo(ship_symbol, trade_symbol, units)


def list_system_goods(token: str, system_symbol: str) -> SystemGoods:
    """
    Aggregate goods across all markets in a system (no prices).
    - sells := exports ∪ exchange
    - buys  := imports ∪ exchange
    Returns real TradeGood objects grouped by waypoint, plus a reverse index.
    """
    client = SpaceTraders(token=token)
    waypoints = [
        wp
        for wp in client.list_waypoints_all(system_symbol)
        if _has_marketplace(wp)
    ]

    by_waypoint: dict[str, MarketGoods] = {}
    by_good_sells: dict[str, list[str]] = {}
    by_good_buys: dict[str, list[str]] = {}

    for wp in waypoints:
        wp_sym = wp["symbol"]
        mkt: Market = client.get_market(system_symbol, wp_sym)

        imports = list(mkt.imports or [])
        exports = list(mkt.exports or [])
        exchange = list(mkt.exchange or [])

        sells = _uniq_by_symbol(exports + exchange)
        buys = _uniq_by_symbol(imports + exchange)

        by_waypoint[wp_sym] = MarketGoods(
            sells=sorted(sells, key=_sym),
            buys=sorted(buys, key=_sym),
        )

        for g in by_waypoint[wp_sym].sells:
            by_good_sells.setdefault(_sym(g), []).append(wp_sym)
        for g in by_waypoint[wp_sym].buys:
            by_good_buys.setdefault(_sym(g), []).append(wp_sym)

    # determinism
    by_good: dict[str, dict[str, list[str]]] = {}
    for sym in sorted(set(by_good_sells) | set(by_good_buys)):
        by_good[sym] = {
            "sells": sorted(by_good_sells.get(sym, [])),
            "buys": sorted(by_good_buys.get(sym, [])),
        }

    return SystemGoods(by_waypoint=by_waypoint, by_good=by_good)
