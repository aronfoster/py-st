from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import cast

from .client import APIError, SpaceTradersClient
from .client.endpoints.ships import RefineResult
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
    ShipyardTransaction,
    Survey,
    TradeGood,
    TradeSymbol,
    Waypoint,
)


@dataclass
class MarketGoods:
    sells: list[TradeGood] = field(default_factory=list)
    buys: list[TradeGood] = field(default_factory=list)


@dataclass
class SystemGoods:
    by_waypoint: dict[str, MarketGoods] = field(default_factory=dict)
    by_good: dict[str, dict[str, list[str]]] = field(default_factory=dict)


def _sym(obj: TradeGood | TradeSymbol | str) -> str:
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


def _has_marketplace(wp: Waypoint) -> bool:
    """Checks if a Waypoint model has the MARKETPLACE trait."""
    return any(trait.symbol.value == "MARKETPLACE" for trait in wp.traits)


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
    client = SpaceTradersClient(token=token)
    agent = client.agent.get_agent()
    return agent


def list_contracts(token: str) -> list[Contract]:
    """
    Fetches all contracts from the API.
    """
    client = SpaceTradersClient(token=token)
    contracts = client.contracts.get_contracts()
    return contracts


def negotiate_contract(token: str, ship_symbol: str) -> Contract:
    """
    Negotiates a new contract using the specified ship.
    """
    client = SpaceTradersClient(token=token)
    new_contract = client.contracts.negotiate_contract(ship_symbol)
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
    client = SpaceTradersClient(token=token)
    contract, cargo = client.contracts.deliver_contract(
        contract_id, ship_symbol, trade_symbol, units
    )
    return contract, cargo


def fulfill_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Fulfills a contract.
    """
    client = SpaceTradersClient(token=token)
    agent, contract = client.contracts.fulfill_contract(contract_id)
    return agent, contract


def accept_contract(token: str, contract_id: str) -> tuple[Agent, Contract]:
    """
    Accepts a contract.
    """
    client = SpaceTradersClient(token=token)
    result = client.contracts.accept_contract(contract_id)
    agent: Agent = cast(Agent, result["agent"])
    contract: Contract = cast(Contract, result["contract"])
    return agent, contract


def list_ships(token: str) -> list[Ship]:
    """
    Fetches all ships from the API.
    """
    client = SpaceTradersClient(token=token)
    ships = client.ships.get_ships()
    return ships


def navigate_ship(
    token: str, ship_symbol: str, waypoint_symbol: str
) -> ShipNav:
    """
    Navigates a ship to a waypoint.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.navigate_ship(ship_symbol, waypoint_symbol)
    return result


def orbit_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Moves a ship into orbit.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.orbit_ship(ship_symbol)
    return result


def dock_ship(token: str, ship_symbol: str) -> ShipNav:
    """
    Docks a ship.
    """
    client = SpaceTradersClient(token=token)
    result = client.ships.dock_ship(ship_symbol)
    return result


def extract_resources(
    token: str, ship_symbol: str, survey_json: str | None = None
) -> Extraction | None:
    """
    Extracts resources from a waypoint, optionally using a survey.
    """
    try:
        client = SpaceTradersClient(token=token)
        survey_to_use = None
        if survey_json:
            try:
                survey_data = json.loads(survey_json)
                survey_to_use = Survey.model_validate(survey_data)
            except (json.JSONDecodeError, TypeError):
                print("Error: Invalid survey JSON provided. Aborting.")
                return None

        extraction = client.ships.extract_resources(
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
    client = SpaceTradersClient(token=token)
    surveys = client.ships.create_survey(ship_symbol)
    return surveys


def refuel_ship(
    token: str, ship_symbol: str, units: int | None
) -> tuple[Agent, ShipFuel, MarketTransaction]:
    """
    Refuels a ship.
    """
    client = SpaceTradersClient(token=token)
    agent, fuel, transaction = client.ships.refuel_ship(ship_symbol, units)
    return agent, fuel, transaction


def jettison_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> ShipCargo:
    """
    Jettisons cargo from a ship.
    """
    client = SpaceTradersClient(token=token)
    cargo = client.ships.jettison_cargo(ship_symbol, trade_symbol, units)
    return cargo


def set_flight_mode(
    token: str, ship_symbol: str, flight_mode: ShipNavFlightMode
) -> ShipNav:
    """
    Sets the flight mode for a ship.
    """
    client = SpaceTradersClient(token=token)
    nav = client.ships.set_flight_mode(ship_symbol, flight_mode)
    return nav


def list_waypoints(
    token: str, system_symbol: str, traits: list[str] | None
) -> list[Waypoint]:
    """
    Lists waypoints in a system, optionally filtered by traits.
    """
    client = SpaceTradersClient(token=token)
    waypoints = client.systems.get_waypoints_in_system(
        system_symbol, traits=traits
    )
    return waypoints


def list_waypoints_all(
    token: str, system_symbol: str, traits: list[str] | None = None
) -> list[Waypoint]:
    """
    Lists waypoints in a system, optionally filtered by traits.
    """
    client = SpaceTradersClient(token=token)
    waypoints = client.systems.list_waypoints_all(system_symbol, traits=traits)
    return waypoints


def get_shipyard(
    token: str, system_symbol: str, waypoint_symbol: str
) -> Shipyard:
    """
    Gets the shipyard for a waypoint.
    """
    client = SpaceTradersClient(token=token)
    shipyard = client.systems.get_shipyard(system_symbol, waypoint_symbol)
    return shipyard


def refine_materials(
    token: str, ship_symbol: str, produce: str
) -> RefineResult:
    """
    Refines materials on a ship and prints the result.
    """
    client = SpaceTradersClient(token=token)
    return client.ships.refine_materials(ship_symbol, produce)


def get_market(token: str, system_symbol: str, waypoint_symbol: str) -> Market:
    """
    Gets the market for a waypoint.
    """
    client = SpaceTradersClient(token=token)
    return client.systems.get_market(system_symbol, waypoint_symbol)


def sell_cargo(
    token: str, ship_symbol: str, trade_symbol: str, units: int
) -> tuple[Agent, ShipCargo, MarketTransaction]:
    """
    Sells cargo from a ship at the current marketplace.
    """
    client = SpaceTradersClient(token=token)
    return client.ships.sell_cargo(ship_symbol, trade_symbol, units)


def purchase_ship(
    token: str, ship_type: str, waypoint_symbol: str
) -> tuple[Agent, Ship, ShipyardTransaction]:
    """
    Purchases a ship of the specified type at a waypoint.
    """
    client = SpaceTradersClient(token=token)
    agent, ship, transaction = client.ships.purchase_ship(
        ship_type, waypoint_symbol
    )
    return agent, ship, transaction


def list_system_goods(token: str, system_symbol: str) -> SystemGoods:
    """
    Aggregate goods across all markets in a system (no prices).
    - sells := exports ∪ exchange
    - buys  := imports ∪ exchange
    Returns real TradeGood objects grouped by waypoint, plus a reverse index.
    """
    client = SpaceTradersClient(token=token)
    waypoints: list[Waypoint] = client.systems.list_waypoints_all(
        system_symbol
    )
    waypoints = [wp for wp in waypoints if _has_marketplace(wp)]

    by_waypoint: dict[str, MarketGoods] = {}
    by_good_sells: dict[str, list[str]] = {}
    by_good_buys: dict[str, list[str]] = {}

    for wp in waypoints:
        wp_sym = wp.symbol.root
        mkt: Market = client.systems.get_market(system_symbol, wp_sym)

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
