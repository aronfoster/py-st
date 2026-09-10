"""Thin CLI adapters for guarded automation and shared intelligence."""

from __future__ import annotations

import json
import os
import shlex
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import typer
from dotenv import find_dotenv, load_dotenv

from py_st.client import APIError, SpaceTradersClient
from py_st.services.automation import SafetyStop, Session
from py_st.services.contract_planning import plan_contract_procurement
from py_st.services.contract_sources import contract_sources
from py_st.services.dashboard import dashboard_server
from py_st.services.doctor import diagnose
from py_st.services.earning import earn_run
from py_st.services.infrastructure import (
    infrastructure_run,
    validate_infrastructure,
)
from py_st.services.intelligence import Intelligence
from py_st.services.mining import diagnose_mining
from py_st.services.negotiation import negotiate_run
from py_st.services.pilot import pilot_run
from py_st.services.procurement_recovery import abandon_procurement
from py_st.services.route_history import RouteScenario, evaluate_route
from py_st.services.scouting import scout_plan, scout_run
from py_st.services.strategies import (
    contract_run,
    fleet_run,
    refuel_run,
    trade_run,
)

auto_app = typer.Typer(help="Bounded automation; dry-run unless --execute.")


@contextmanager
def session(
    execute: bool, seconds: int, actions: int, *, initialize: bool = False
) -> Iterator[Session]:
    guidance = (
        "Return to the authoritative workspace first. Use auto observe only "
        "for genuinely new history; do not copy or create an empty ledger "
        "as a workaround."
    )
    try:
        store = Intelligence(
            existing_only=not initialize, existing_or_create=initialize
        )
    except (OSError, sqlite3.Error, ValueError):
        raise typer.BadParameter(
            f"Cannot open a supported durable intelligence ledger. {guidance}"
        ) from None
    run: Session | None = None
    try:
        recorded: set[str] = set()
        if not initialize:
            try:
                for scope in store.scopes():
                    reset, separator, symbol = scope.partition(":")
                    if (
                        not separator
                        or not reset
                        or not symbol
                        or reset != reset.strip()
                        or symbol != symbol.strip()
                        or ":" in symbol
                    ):
                        continue
                    for row in store.latest(scope, "agent"):
                        data = row["data"]
                        if (
                            row["key"] == symbol
                            and isinstance(data, dict)
                            and data.get("symbol") == symbol
                        ):
                            recorded.add(scope)
            except (sqlite3.Error, ValueError, TypeError):
                raise SafetyStop("Invalid recorded agent history") from None
            if not recorded:
                raise SafetyStop(
                    f"No valid recorded agent history. {guidance}"
                )
        load_dotenv(find_dotenv(usecwd=True))
        token = os.environ.get("ST_TOKEN")
        if not token:
            raise typer.BadParameter(
                "Set ST_TOKEN in ignored .env; never in argv"
            )
        with SpaceTradersClient(token) as client:
            try:
                run = Session(
                    client,
                    store,
                    execute=execute,
                    seconds=seconds,
                    actions=actions,
                )
            except (OSError, ValueError):
                raise SafetyStop("Cannot initialize bounded session") from None
            try:
                run.check()
                status = client.status()
                agent = run.get("/my/agent")
                live_reset = (
                    status.get("resetDate")
                    if isinstance(status, dict)
                    else None
                )
                live_symbol = (
                    agent.get("symbol") if isinstance(agent, dict) else None
                )
                if any(
                    not isinstance(value, str)
                    or not value.strip()
                    or value != value.strip()
                    or ":" in value
                    for value in (live_reset, live_symbol)
                ):
                    raise SafetyStop("Invalid live reset/agent identity")
                scope = f"{live_reset}:{live_symbol}"
                if not initialize and scope not in recorded:
                    raise SafetyStop(
                        "Live reset/agent has no matching recorded agent in "
                        "this ledger. Return to the authoritative workspace; "
                        "review reset/account state without replacing history."
                    )
                run.check()
                run.scope = scope
                yield run
            finally:
                run.close()
    except (SafetyStop, APIError, httpx.HTTPError) as exc:
        # Do not dump response payloads, headers or credential-bearing URLs.
        message = (
            str(exc) if isinstance(exc, SafetyStop) else type(exc).__name__
        )
        if isinstance(exc, APIError):
            details = []
            if type(exc.status) is int:
                details.append(f"HTTP {exc.status}")
            if type(exc.code) is int:
                details.append(f"code {exc.code}")
            if details:
                message += f" ({', '.join(details)})"
        typer.echo(f"Stopped: {message}", err=True)
        if isinstance(exc, APIError) and exc.authentication_failed:
            typer.echo(
                "Owner must update ST_TOKEN; do not auto-register.", err=True
            )
        if run is not None and run.scope:
            try:
                typer.echo(
                    json.dumps(
                        {
                            "economics": store.economics(run.scope),
                            "pending_action": store.pending(run.scope),
                        },
                        indent=2,
                    )
                )
            except (sqlite3.Error, ValueError, TypeError, KeyError):
                typer.echo(
                    "Recorded summary unavailable; inspect ledger.", err=True
                )
        raise typer.Exit(1) from None
    finally:
        store.close()


@auto_app.command()
def observe() -> None:
    """Fresh agent, fleet and contracts into SQLite (no mutations)."""
    with session(False, 120, 1, initialize=True) as run:
        run.refresh()
        typer.echo(json.dumps(run.store.report(run.scope), indent=2))


@auto_app.command()
def scan(system: str) -> None:
    """Record all waypoints and advertised markets in a system."""
    with session(False, 300, 1) as run:
        typer.echo(json.dumps(run.scan(system), indent=2))


@auto_app.command()
def infrastructure(
    system: str,
    max_sites: int = typer.Option(10, min=1, max=100),
    seconds: int = typer.Option(300, min=1, max=7200),
) -> None:
    """GET-only gate, shipyard and construction observations; no execution."""
    try:
        validate_infrastructure(system, max_sites, seconds)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None
    with session(False, seconds, 1) as run:
        typer.echo(
            json.dumps(infrastructure_run(run, system, max_sites), indent=2)
        )


@auto_app.command()
def move(
    ship: str,
    destination: str,
    execute: bool = False,
    seconds: int = 600,
    actions: int = 4,
) -> None:
    """Guarded CRUISE travel, arrival confirmation and market observation."""
    with session(execute, seconds, actions) as run:
        run.refresh()
        if not execute:
            plan = run.navigation_plan(run.arrive(ship), destination)
            typer.echo(json.dumps(plan, indent=2))
            return
        result = run.navigate(ship, destination)
        typer.echo(json.dumps({"ship": ship, "nav": result["nav"]}, indent=2))
        typer.echo(json.dumps(run.market(destination), indent=2))


@auto_app.command()
def mining(
    ship: str,
    seconds: int = typer.Option(120, min=1, max=7200),
) -> None:
    """GET-only unsurveyed ore diagnostics; never extract, orbit or wait."""
    with session(False, seconds, 1) as run:
        run.check()
        run.refresh()
        fresh_ship = run.ship(ship)
        nav = fresh_ship["nav"]
        waypoint = run.get(
            f"/systems/{nav['systemSymbol']}/waypoints/{nav['waypointSymbol']}"
        )
        typer.echo(
            json.dumps(
                diagnose_mining(fresh_ship, waypoint, now=datetime.now(UTC)),
                indent=2,
            )
        )


@auto_app.command()
def negotiate(
    ship: str,
    execute: bool = False,
    seconds: int = typer.Option(120, min=1, max=7200),
) -> None:
    """Inspect eligibility or request ONE journaled offer; never accept it."""
    with session(execute, seconds, 1) as run:
        typer.echo(json.dumps(negotiate_run(run, ship), indent=2))


@auto_app.command()
def contract(
    ship: str,
    contract_id: str,
    source: str = "",
    execute: bool = False,
    seconds: int = 600,
    actions: int = 30,
) -> None:
    """Plan/resume single-good or same-market multi-good procurement."""
    with session(execute, seconds, actions) as run:
        typer.echo(
            json.dumps(contract_run(run, ship, contract_id, source), indent=2)
        )


@auto_app.command("abandon-procurement")
def abandon_procurement_command(
    contract_id: str,
    execute: bool = False,
    reason: str = typer.Option(
        "", help="Local audit reason; omit sensitive data."
    ),
    seconds: int = typer.Option(120, min=1, max=7200),
) -> None:
    """LIVE GET preview; --execute closes local intent, never game actions.

    Requires an unaccepted contract and empty ship at its original source.
    Execution requires --reason of at least 20 characters. STOP is preserved.
    """
    if execute and len(reason.strip()) < 20:
        raise typer.BadParameter(
            "--execute requires --reason of at least 20 characters"
        )
    with session(False, seconds, 1) as run:
        typer.echo(
            json.dumps(
                abandon_procurement(
                    run, contract_id, execute=execute, reason=reason
                ),
                indent=2,
            )
        )


@auto_app.command("contract-model")
def contract_model(input_file: Path) -> None:
    """Model a complete procurement contract from an offline JSON fixture."""
    try:
        payload = json.loads(input_file.read_text(encoding="utf-8"))
        plan = plan_contract_procurement(
            payload["contract"],
            payload["quotes"],
            ship_capacity=payload["ship_capacity"],
            credits=payload["credits"],
            credit_floor=payload.get("credit_floor", 50_000),
            fuel_allowance=payload.get("fuel_allowance", 1_000),
            price_margin=payload.get("price_margin", 0.20),
            deadline_margin_seconds=payload.get(
                "deadline_margin_seconds", 3_600
            ),
        )
    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise typer.BadParameter(str(exc)) from None
    typer.echo(json.dumps(plan, indent=2))


@auto_app.command()
def sources(
    contract_id: str,
    scope: str = typer.Option(..., help="Explicit RESET:AGENT scope."),
    database: Path = Path(".state/intelligence.sqlite3"),
    max_age: int = typer.Option(900, min=1, max=86400),
) -> None:
    """OFFLINE ONLY: contract sources without ledger record writes.

    Requires an existing ledger. SQLite may create WAL/shared-memory
    sidecars or update shared memory; this is not zero filesystem writes.
    """
    try:
        result = contract_sources(
            database, scope, contract_id, max_age=max_age
        )
    except (ValueError, sqlite3.Error) as exc:
        raise typer.BadParameter(str(exc)) from None
    typer.echo(json.dumps(result, indent=2))


@auto_app.command()
def doctor(
    scope: str = typer.Option(..., help="Explicit RESET:AGENT scope."),
    database: Path = Path(".state/intelligence.sqlite3"),
    root: Path = Path("."),
    max_age: int = typer.Option(900, min=1, max=86400),
) -> None:
    """OFFLINE ONLY: recorded concerns, not execution or process readiness.

    Exit 0: no recorded concerns; 1: attention; 2: invalid/unavailable.
    Existing database only. No credentials, API, lock or STOP changes.
    --root selects the STOP directory only and defaults to cwd.
    SQLite read-only may create/use WAL/shared-memory sidecars; not zero
    filesystem writes. Missing contract rows do not verify an empty list.
    """
    result = diagnose(database, scope, root=root, max_age=max_age)
    typer.echo(json.dumps(result, separators=(",", ":")))
    raise typer.Exit(result["exit_code"])


@auto_app.command()
def refuel(ship: str, execute: bool = False) -> None:
    """Fill fuel with a live quote and protected credit reserve."""
    with session(execute, 120, 2) as run:
        typer.echo(json.dumps(refuel_run(run, ship), indent=2))


@auto_app.command()
def trade(
    ship: str,
    source: str,
    destination: str,
    good: str,
    execute: bool = False,
    cycles: int = 1,
    seconds: int = 600,
    actions: int = 30,
) -> None:
    """Plan/resume a trade with bounded cycles and persisted open positions."""
    with session(execute, seconds, actions) as run:
        typer.echo(
            json.dumps(
                trade_run(run, ship, source, destination, good, cycles),
                indent=2,
            )
        )


@auto_app.command()
def fleet(
    execute: bool = False,
    cycles: int = 1,
    seconds: int = 600,
    actions: int = 30,
) -> None:
    """Rank visible routes and assign existing haulers and scouts."""
    with session(execute, seconds, actions) as run:
        typer.echo(json.dumps(fleet_run(run, cycles), indent=2))


@auto_app.command()
def earn(
    system: str,
    execute: bool = False,
    reposition: bool = typer.Option(
        False,
        help="Allow one costed return to a completed trade's original source.",
    ),
    cycles: int = typer.Option(3, min=1, max=5),
    max_age: int = typer.Option(900, min=1, max=86400),
    seconds: int = typer.Option(600, min=1, max=7200),
    actions: int = typer.Option(30, min=1, max=200),
) -> None:
    """Trade ready routes or scout one market per cycle; dry run uses GETs."""
    with session(execute, seconds, actions) as run:
        typer.echo(
            json.dumps(
                earn_run(run, system, cycles, max_age, reposition=reposition),
                indent=2,
            )
        )


@auto_app.command()
def pilot(
    system: str,
    execute: bool = False,
    steps: int = typer.Option(10, min=1, max=100),
    seconds: int = typer.Option(3600, min=1, max=7200),
    actions: int = typer.Option(100, min=1, max=200),
    max_age: int = typer.Option(900, min=1, max=86400),
    reposition: bool = False,
    recover_contracts: bool = typer.Option(
        False,
        help="Recover one existing procurement intent using its original "
        "ship/source/contract. With --execute this may accept that original "
        "unaccepted intent; never selects new offers or negotiates. "
        "Without --execute, preview only.",
    ),
) -> None:
    """Continue bounded earning decisions; dry run inspects only the next."""
    with session(execute, seconds, actions) as run:
        try:
            result = pilot_run(
                run,
                system,
                steps,
                max_age,
                reposition=reposition,
                recover_contracts=recover_contracts,
            )
        except BaseException:
            if run.scope:
                typer.echo(
                    "Inspect automation_runs in `python -m py_st auto report "
                    f"--scope {shlex.quote(run.scope)}` or the dashboard "
                    "for this scope. The terminal record may be missing if "
                    "storage failed.",
                    err=True,
                )
            else:
                typer.echo(
                    "Pilot scope unavailable; "
                    "no scoped run ID can be reported.",
                    err=True,
                )
            typer.echo(
                "After reviewing blockers, STOP and pending actions, restart "
                "with auto pilot SYSTEM and explicit bounds. Restart creates "
                "a NEW run with NEW budgets and fresh decisions; it never "
                "replays recorded decisions or uncertain actions.",
                err=True,
            )
            raise
        typer.echo(json.dumps(result, indent=2))


@auto_app.command()
def scout(
    system: str,
    execute: bool = False,
    attempts: int = typer.Option(4, min=1, max=100),
    max_age: int = typer.Option(900, min=1, max=86400),
    seconds: int = typer.Option(600, min=1, max=7200),
    actions: int = typer.Option(8, min=1, max=200),
    offline: bool = False,
    scope: str = "",
    database: Path = Path(".state/intelligence.sqlite3"),
) -> None:
    """Plan/resume local fuel-free probe visits; --offline uses SQLite only."""
    if offline:
        if execute or not scope:
            raise typer.BadParameter(
                "Offline requires --scope and no --execute"
            )
        try:
            store = Intelligence(database, read_only=True)
            try:
                if scope not in store.scopes():
                    raise ValueError("Unknown reset/agent scope")
                plan = scout_plan(
                    store,
                    scope,
                    system,
                    [row["data"] for row in store.latest(scope, "ship")],
                    [row["data"] for row in store.latest(scope, "waypoint")],
                    attempts=attempts,
                    max_age=max_age,
                )
                typer.echo(
                    json.dumps(
                        {"status": "offline snapshot", "plan": plan}, indent=2
                    )
                )
            finally:
                store.close()
        except (ValueError, sqlite3.Error) as exc:
            raise typer.BadParameter(str(exc)) from None
        return
    if scope or database != Path(".state/intelligence.sqlite3"):
        raise typer.BadParameter("--scope/--database require --offline")
    with session(execute, seconds, actions) as run:
        typer.echo(
            json.dumps(scout_run(run, system, attempts, max_age), indent=2)
        )


@auto_app.command()
def reconcile(
    action_id: int, evidence: str = "", confirm_reviewed: bool = False
) -> None:
    """Inspect an uncertain action; explicitly record review without replay."""
    if evidence and not confirm_reviewed:
        raise typer.BadParameter(
            "Use --confirm-reviewed after inspecting fresh state"
        )
    with session(False, 120, 1) as run:
        typer.echo(json.dumps(run.reconcile(action_id, evidence), indent=2))


@auto_app.command()
def dashboard(port: int = 8765) -> None:
    """Serve local shared-data UI; no API credentials or gameplay commands."""
    server = dashboard_server(Path.cwd(), port)
    typer.echo(f"Flight Ledger: http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


@auto_app.command()
def backup(destination: Path) -> None:
    """Create a consistent SQLite backup without overwriting existing data."""
    store = Intelligence()
    try:
        store.backup(destination)
        typer.echo("Consistent intelligence backup created")
    finally:
        store.close()


@auto_app.command()
def backtest(
    source: str,
    destination: str,
    good: str,
    scope: str = typer.Option(..., help="Explicit RESET:AGENT scope."),
    start: str = typer.Option(..., help="Inclusive ISO time with timezone."),
    end: str = typer.Option(..., help="Inclusive ISO time with timezone."),
    leg_seconds: int = typer.Option(..., help="Assumed one-way travel time."),
    fuel_allowance: int = typer.Option(
        ..., help="Assumed credits per round trip, charged at entry."
    ),
    capacity: int = 40,
    initial_credits: int = 175_000,
    credit_floor: int = 50_000,
    max_age: int = 900,
    slippage_bps: int = 500,
    database: Path = Path(".state/intelligence.sqlite3"),
) -> None:
    """Offline fixed-route quote replay, not realized or guaranteed profit."""
    try:
        result = evaluate_route(
            database,
            RouteScenario(
                scope=scope,
                source=source,
                destination=destination,
                good=good,
                start=start,
                end=end,
                leg_seconds=leg_seconds,
                fuel_allowance=fuel_allowance,
                capacity=capacity,
                initial_credits=initial_credits,
                credit_floor=credit_floor,
                max_age=max_age,
                slippage_bps=slippage_bps,
            ),
        )
    except (ValueError, sqlite3.Error) as exc:
        raise typer.BadParameter(str(exc)) from None
    typer.echo(json.dumps(result, indent=2))


@auto_app.command()
def report(scope: str = "") -> None:
    """Offline JSON export of scoped history, fleet, markets and actions."""
    store = Intelligence()
    try:
        scopes = store.scopes()
        if not scope:
            if len(scopes) != 1:
                typer.echo(json.dumps({"select_scope": scopes}))
                return
            scope = scopes[0]
        typer.echo(json.dumps(store.report(scope), indent=2))
    finally:
        store.close()
