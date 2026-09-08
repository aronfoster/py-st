# py-st

Personal project to interact with SpaceTraders.io through Python in order to learn Python for a corporate environment

## CLI, Automation and Flight Ledger

Typed SpaceTraders client and CLI with guarded procurement automation,
reset-scoped SQLite intelligence, and a local fleet/economics dashboard.

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
See the [review guide](docs/REVIEW.md) for code entry points, verified results
and known limitations.

## Optional Live Observation

Configure `ST_TOKEN` in ignored `.env`, then run `python -m py_st auto observe`
to fetch current agent/fleet/contracts into the local ledger. This makes live
GET requests but does not perform gameplay mutations. Never register another
agent just to review the code, and do not run a second automation controller
against an account already in use.

Keep `ST_TOKEN` in ignored `.env`, never in command arguments. Automation is
dry-run by default and enforces credit/fuel reserves and bounded sessions.
The dashboard shows stored fleet state, credit history, market routes and pause
controls. It does not call the game API or load tokens. Live command dry runs
can still fetch data and write local observations; they are not offline previews.

Read [operations and recovery](docs/OPERATIONS.md) before live execution.
See [run evidence](docs/ASTRA_LOG.md), [handoff](docs/HANDOFF.md), and
[contributor safety rules](AGENTS.md). `make ci` runs non-mutating checks.
