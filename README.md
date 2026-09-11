# py-st

Explore your SpaceTraders fleet and fly ships from the local Flight Ledger
browser application. Authenticated flight commands run through a durable worker;
the same dashboard shows fleet state, economics, contract models and history.

## Play the Offline Flight Demo

See [Browser Flight Operations](docs/FLIGHT_OPERATIONS.md) for setup and a
complete synthetic select → preview → navigate → arrival → dock → refuel trip.
It uses the real UI, queue, worker and services without game credentials/network.

Live CLI mutations are retired in this revision in favor of worker ownership.
Historical trading/pilot execution commands below are retained as documentation
of existing strategy code, not supported live dispatch instructions. Browser
trading, contracts and persistent pilot controls are subsequent assignments.

## Review Without Game Credentials

From a fresh checkout on Linux, with Python 3.12 and Make available:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
ST_LIVE_TESTS=0 make ci
python -m py_st --help
python -m py_st auto dashboard
```

Open http://127.0.0.1:8765. A fresh checkout has no local game history, so the
dashboard starts empty; it does not download the recorded run or call the game.
The private local ledger, backups, screenshots and `.env` are not committed.
The server stays in the foreground; Ctrl-C stops it. It never launches gameplay.

## Choose a Task

Commands below follow `python -m py_st`. Replace `SYSTEM`, `SHIP`, `CONTRACT_ID`
and `RESET:AGENT` with your own identifiers, not historical example values.

| I Want To | Command | Game Access |
| --- | --- | --- |
| Inspect stored fleet, cash and pilot runs | `auto report` or `auto dashboard` | **OFFLINE**, no token/API |
| Find stored contract suppliers | `auto sources CONTRACT_ID --scope RESET:AGENT` | **OFFLINE**, existing ledger required |
| Cost a contract with explicit assumptions | `auto contract-model INPUT.json` or dashboard Contract Desk | **OFFLINE**, never authorizes execution |
| Refresh fleet/contracts or map markets | `auto observe` / `auto scan SYSTEM` | **LIVE GET**, writes local observations |
| Diagnose mining blockers | `auto mining SHIP` | **LIVE GET**, no extraction or `--execute` |
| Preview the next earning decision | `auto earn SYSTEM` / `auto pilot SYSTEM` | **LIVE GET dry run**, not offline |
| Fly ships in the browser | `flight serve` plus `flight worker` | Configured offline demo or guarded live flight |
| Preview an original contract execution intent | `auto pilot SYSTEM --recover-contracts --steps 1` | **LIVE GET preview** outside managed mode; mutation disabled |

`auto scout SYSTEM --offline --scope RESET:AGENT` previews stored discovery;
without `--offline`, scouting uses live GETs; direct execution is now disabled.
Direct `auto contract`, `trade`, `fleet`, `move`, `refuel` and `negotiate` remain
available for previews outside managed mode; see [operations](docs/OPERATIONS.md)
for historical guards and recovery. Their real-client writes are refused.

`auto contract` also supports multiple distinct goods at one marketplace when
the ship is already there, with whole-obligation funding and journaled recovery.
See [stationary multi-good procurement](docs/LOCAL_PROCUREMENT.md) for limits.

## Optional Live Observation

Run live commands from the authoritative repository directory. Previews and
execution now require its existing initialized ledger and matching recorded
agent identity; they will not silently create new history in another folder.
Only `auto observe` permits deliberate live-session initialization. If you see
a missing-history error, return to the correct directory rather than creating
an empty replacement ledger.

Configure `ST_TOKEN` in ignored `.env`, then run `python -m py_st auto observe`
to fetch current agent/fleet/contracts into the local ledger. This makes live
GET requests but does not perform gameplay mutations. Never register another
agent just to review the code, and do not run a second automation controller
against an account already in use.

Keep `ST_TOKEN` out of command arguments. Review stored recovery state and STOP
before live work. Dry runs can fetch data and write local observations/plans;
they are not offline previews or approval of future trades.

## Historical Foreground Pilot (Live Dispatch Retired)

The legacy strategy remains tested offline. These earlier command shapes explain
its API; `--execute` cannot dispatch through the real client in this revision:

```sh
# Live GET-only preview of ONE decision, not ten simulated steps:
python -m py_st auto pilot SYSTEM --steps 10 --seconds 3600 --actions 100
# Only after review and explicit authorization:
python -m py_st auto pilot SYSTEM --execute --steps 10 --seconds 3600 --actions 100
```

Defaults are **10 steps, 3,600 seconds and 100 actions** shared across the whole
run. Optional `--reposition` permits a guarded, costed return to a completed
trade's original source; it is off by default. A step is a returned earning
decision, not a guaranteed trade or profit. No daemon or UI execution launcher
is provided. Pause requests STOP; Clear stop never starts a process.

Pilot UUID records appear in report `automation_runs` and the dashboard. They
are saved history, not a process monitor: `running` can be stale after a crash.
On failure, inspect the report, positions and pending actions **before rerunning**;
a storage error may leave no terminal record. Restart creates a **new run with
new budgets and fresh decisions**, not continuation of the old budget or replay.

## Deeper Guides

- [Operations and recovery](docs/OPERATIONS.md): command workflows, budgets,
  STOP, journal reconciliation and durable storage.
- [Offline contract planning](docs/CONTRACT_PLANNING.md): Contract Desk inputs,
  assumptions and model limitations.
- [Mining and contracts](docs/MINING_CONTRACTS.md),
  [fuel-aware navigation](docs/FUEL_NAVIGATION.md), and
  [historical route replay](docs/HISTORICAL_ROUTES.md): specialized workflows.
- [Review guide](docs/REVIEW.md) and [contributor rules](AGENTS.md): code entry
  points, verification and safety. `make ci` runs non-mutating checks.

[Run evidence](docs/ASTRA_LOG.md) and [handoff](docs/HANDOFF.md) are historical
operator records, not prerequisites for understanding the product or fresh
account-state evidence. New pilot/reposition capabilities are not a claim of
end-to-end live proof or unattended profitability.
