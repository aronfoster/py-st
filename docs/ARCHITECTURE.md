# Architecture and Owner Decisions

## What This System Is

Flight Ledger is a local SpaceTraders operations tool, not a hosted service.
Python commands operate the fleet; a browser presents the same durable data.
The dashboard does not hold credentials, call the game, or start an agent.
Its pause button requests a stop; clearing that request does not start work.

Start with [Operations](OPERATIONS.md) for commands and [Handoff](HANDOFF.md)
for the last verified fleet state, results and remaining work. The append-only
[run log](ASTRA_LOG.md) explains the implementation sequence and experiments.

## Code Map

| Component | Responsibility |
| --- | --- |
| `src/py_st/cli/auto_cmd.py` | Thin command adapters and sanitized failure output |
| `src/py_st/services/automation.py` | Shared session, journal, reserves, bounded actions and arrival waits |
| `src/py_st/services/strategies.py` | Procurement, trading, refueling and fleet assignment |
| `src/py_st/services/scouting.py` | Local market discovery with existing fuel-free probes |
| `src/py_st/services/earning.py` | Bounded recovery-first ready-trade/discovery decisions over shared services |
| `src/py_st/services/intelligence.py` | SQLite observations, journal, reports and cash reconciliation |
| `src/py_st/services/route_history.py` | Offline historical quote replay, not live execution |
| `src/py_st/services/dashboard.py` | Loopback HTTP adapter over the shared ledger |
| `src/py_st/client/transport.py` | Connections, pacing, semantic retry and authentication failure handling |

The original CLI/services/client layering remains. New automation bypasses
the legacy response cache and observes the API into the scoped datastore.
Generated API models remain separate from orchestration and strategy decisions.

## Why These Choices

**SQLite instead of more JSON files:** observations and actions need atomic,
queryable history. WAL and FULL synchronous writes make committed checkpoints
durable; reset/agent scopes prevent different game universes being mixed. The
database is not a cache. Retain it when removing a worktree or clearing responses.

**Headless web UI instead of desktop automation:** the interface is usable in a
normal browser, while Playwright verifies explicit desktop/mobile viewports using
installed Chrome. Monitor power, desktop resolution and screen locking are not
browser-test dependencies. Computer suspension still interrupts execution.

**Sequential guarded execution instead of maximum concurrency:** one process
holds the local automation lock, shares rate limiting and persists each mutation.
This makes attribution and recovery tractable. Multiple computers or manual game
clients are not covered by that lock; do not operate the same account concurrently.

**Fresh-state recovery instead of replay:** a pending journal action may have
succeeded remotely even if its response was lost. Unknown outcomes block further
mutations until evidence-based review. Known pre-dispatch stops and definitive
rejections are distinguished from ambiguity. This is not an exactly-once protocol.

**Cash reconciliation instead of a single profit counter:** observed balances
are compared against journaled receipts, purchases, sales and fuel. Unexplained
changes stay visible. Ship wear, opportunity cost and inventory valuation are not
silently called cash profit. Historical simulations remain labeled counterfactual.

## Operational Boundaries

- Keep `ST_TOKEN` in ignored configuration, never command arguments or documents.
- Live commands default to planning unless `--execute` is supplied; plans still
  make GET requests and record observations unless an offline mode is selected.
- The 50,000-credit floor is a minimum, not an amount the planner may spend down
  to without considering fuel and contract obligations.
- Quote checks do not reserve liquidity or enforce server-side limit prices.
- STOP is checked between mutations and during waits, not inside an HTTP request
  already in flight. A normal stop can leave a ship travelling; resume by observing.
- No automatic registration, ship purchase, scrap, jettison, jump, warp or DRIFT
  is enabled by the new automation in this run.
- Run from the isolated worktree with `PYTHONPATH=src`; the shared environment's
  original editable installation was deliberately not repointed away from master.
- No daemon or restart supervisor is installed. An ended OpenCode process does
  not resume itself. Bounded gameplay commands and documented checkpoints survive
  that interruption without promising indefinite unattended model execution.

## Growing the System

`auto earn SYSTEM` now connects scouting to fleet assignment: one shared Session
runs at most five decisions, each selecting a ready trade or scouting one market
before reranking. Fleet planning can be requested without enabling execution or
changing Session authority. Current GET responses, not retained historical quotes,
qualify both counterparties. Persisted trades take priority and recovery returns
without discovery; multiple/unknown positions fail closed for manual review.

The first version deliberately omits historical-route repositioning. Costing a
hauler approach, safe return/refuel options and quote visibility throughout would
need more than the existing ready-route economics. Discovery can enable immediate
trade when a hauler is already at the seller, but cannot guarantee such a route.
This is tested offline, not new live earnings. See the exact commands and dry-run
versus offline distinction in [Operations](OPERATIONS.md#bounded-earning-controller).

The next useful capabilities are multi-leg procurement with complete obligations,
measured extraction economics, and fully costed route repositioning. Broader endpoint coverage is useful
only when a tested strategy needs it. Ship expansion should follow demonstrated
returns after travel, fuel, market impact and reserves, not gross-price spreads.

For any new strategy, add failure/restart tests before live trials, show its dry
run, enforce Session guards, record measured results, and distinguish an API quote
from a transaction that actually occurred. Prefer improving shared services over
putting separate gameplay logic in the dashboard.
