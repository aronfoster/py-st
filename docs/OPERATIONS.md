# Flight Ledger Operations

Use the isolated worktree, not master. Activate the owner's existing virtual
environment or install `pip install -e '.[dev]'` into a project environment.
Run all examples from the worktree with `PYTHONPATH=src`. The CLI discovers
the ignored `.env` up the current directory's parent chain. Never pass tokens
as command arguments. No automatic registration is performed.

## Read and Observe

```sh
python -m py_st auto observe
python -m py_st auto scan X1-CY22
python -m py_st auto report
python -m py_st auto dashboard --port 8765
```

Open http://127.0.0.1:8765 (use the IP, not localhost). The dashboard reads
SQLite, not the game API. Refresh ledger reloads stored data; `auto observe`
refreshes live fleet/agent/contracts. `auto scan` records a system's markets
and waypoints. Detailed prices generally require one of your ships present.
The dashboard distinguishes observation age from live telemetry. Route figures
are estimates after round-trip fuel, not guaranteed profit or executable orders.

For offline fixed-route evaluation over historical observations, use
`auto backtest --help` and [Historical Route Replay](HISTORICAL_ROUTES.md).
It requires explicit time/fuel assumptions, never uses future quotes at entry,
reports unresolved exposure, and leaves STOP and the database unchanged.

## Guarded Procurement

See [Mining and Contract Assessment](MINING_CONTRACTS.md) for the fresh mining
capability diagnosis, exact prerequisites, negotiation-versus-acceptance workflow
and proposed next experiments. `auto negotiate SHIP` is a GET-only dry run by
default; `--execute` requests one journaled offer, never accepts it. Existing
FOS-63 authority covers this guarded workflow. It blocks uncertain actions and
existing unfulfilled contracts; a timeout requires reconciliation, not replay.
Extraction remains outside the automation allowlist. Legacy manual negotiation
and extraction commands bypass the automation STOP/journal safeguards.

```sh
python -m py_st auto contract SOURCE_CODE-1 CONTRACT_ID
python -m py_st auto contract SOURCE_CODE-1 CONTRACT_ID --execute --seconds 600 --actions 30
python -m py_st auto move SOURCE_CODE-2 WAYPOINT --execute --seconds 300 --actions 2
```

Single-good procurement supports the delivery market or a remote source via
`--source WAYPOINT`. Remote procurement requires the hauler already at source,
the entire remaining load fitting its hold, carried delivery-leg round-trip
fuel, and an independent stationary fuel-free probe at the delivery market.
Reposition with guarded `auto move` dry runs/executions before acceptance.
Fresh destination fuel must fund a full tank at a persisted 20% price ceiling,
in addition to the 50,000 floor, 1,000 allowance and all remaining goods.
Remote execution aggregates purchase batches before one delivery flight, then
delivers and fulfills. Run guarded `auto refuel` afterward; its reserved refill
is not automatically spent, and no return trip is promised. Multi-good and
simultaneous accepted obligations fail closed. Dry-run
prices must be available at the source, so scout with the probe first if needed.
Purchases retain a 50,000 floor, 1,000 fuel allowance and budget for remaining
contract goods. Unit prices may rise at most 20% from the original plan.
Navigation requires CRUISE and the same system. It normally carries twice leg
distance plus 10 fuel. A fresh, funded destination fuel source can permit a
one-way leg when there are no uncosted obligations; see
[Refueling-Aware Navigation](FUEL_NAVIGATION.md) for exact guards and recovery.
Capacity-zero probes are fuel-free; no DRIFT is used. Arrival is confirmed by GET.

Restart the same command after a normal stop. Each iteration observes current
contract progress and cargo; fulfilled contracts do nothing. Acquisition cargo
is delivered before buying more for same-market sourcing; remote sourcing
finishes acquisition of the full load before departing. Remote position records
retain the original ship/source/goods and fuel ceilings across acceptance,
partial/full acquisition, delivery and fulfillment. Omitting `--source` on a
restart uses that original source. Unknown outcomes still require reconciliation.
No jettison, scrap, jump, warp or ship purchase
is available through this automation.

Recovery delivers owned goods and fulfills satisfied contracts before requesting
an acquisition quote or reserving purchase credits. Only goods still needing
purchase enter the reserve calculation. Completion does not need the one-hour
acquisition lead time, but expired contracts remain blocked and navigation fuel
guards still apply. Dry runs can report `ready to deliver` or `ready to fulfill`.

## Trade and Refuel

```sh
python -m py_st auto refuel SOURCE_CODE-1
python -m py_st auto refuel SOURCE_CODE-1 --execute
python -m py_st auto trade SOURCE_CODE-1 SOURCE DESTINATION GOOD
python -m py_st auto trade SOURCE_CODE-1 SOURCE DESTINATION GOOD --execute --cycles 2 --seconds 600 --actions 30
```

Keep a scout at the buyer so fresh destination prices are visible. Trading
refuses active contract obligations and untracked cargo. It protects 50,000
credits plus a 1,000 fuel allowance, caps buy slippage at 5% and sell slippage
at 5%, and checks trade volume and three legs of fuel plus 10 before buying.
Open positions are persisted before purchase; resuming sells held cargo before
buying again. A completed invocation with `--execute` starts new cycles if
invoked again. Refuel deliberately between cycles when reserve checks stop.
Adverse buyer prices leave cargo aboard for review, never jettison it. New
cycles automatically use guarded refueling when route reserves are low.

Trading validates CRUISE before refueling or buying, including at the source.
Every purchase rechecks both counterparties, including resumed unbought positions;
missing/adverse buyer quotes or reduced buyer volume stop before acquisition.
These are preflight observations, not server-enforced limit orders. Prices may
still change between observation and execution or during travel.

`auto fleet` ranks currently visible routes by conservative margin and rough
CRUISE time, pairing a hauler at the source with a price scout at the buyer.
`auto fleet --execute --cycles 3` executes the best fuel-ready candidate through
the same trade service. It buys no ships and does not auto-explore unpriced routes.

Open positions take priority over new fleet assignments. A recovery invocation
finishes each original ship/route/good once and returns, without opening extra
cycles even when `--cycles` is greater than one. Rerun to schedule new trades after
recovery. A fleet dry run shows the open positions instead of new candidates.

## Local Market Scouting

`auto scout` fills the discovery gap before `auto fleet`: it discovers local
MARKETPLACE waypoints and uses existing fuel-free probes to collect detailed
prices, including markets with no previously known profitable route. It does not
trade, buy ships, refuel, change flight mode, jump or warp. Existing fleet/trade
commands do not automatically invoke it; `auto earn` connects the services.

The handoff STOP is restored. Live verification visited seven markets in two
bounded sessions, adding six navigation actions without spending fuel or credits.
Detailed-price coverage increased from 5 to 11 markets. Preview stored state
without clearing STOP or loading a token:

```sh
export PATH="$PWD/../../.venv/bin:$PATH"
export PYTHONPATH=src
python -m py_st auto scout X1-CY22 --offline --scope 2026-09-06:SOURCE_CODE
python -m py_st auto scout X1-CY22 --offline --scope 2026-09-06:SOURCE_CODE --database .state/handoff.sqlite3 --max-age 1800
python -m py_st auto scout --help
```

Offline mode opens an existing schema-v1 SQLite database read-only, requires an
explicit reset/agent scope, and rejects `--execute`. It neither creates a missing
database nor writes observations. The plan uses stored ships/waypoints and price
timestamps; missing/stale fleet or waypoint data limits the preview. It is not a
claim about current ship eligibility, market coverage or executable routes.

For a live session under the ticket's authorization, deliberately clear STOP
after reviewing recovery state. Review a fresh dry run before navigation; these
four-attempt examples are templates, not a promise that old prices remain valid:

```sh
# Live GET-only dry run: refresh account/fleet/contracts and local waypoints.
python -m py_st auto scout X1-CY22 --attempts 4 --max-age 900 --seconds 600 --actions 8
# Review the JSON plan before explicitly authorizing navigation.
python -m py_st auto scout X1-CY22 --execute --attempts 4 --max-age 900 --seconds 600 --actions 8
# After a normal interruption, rerun the same bounded command deliberately.
python -m py_st auto report --scope 2026-09-06:SOURCE_CODE
```

Eligibility requires `FRAME_PROBE`, zero fuel capacity, empty cargo, CRUISE and
same-system navigation state. Multiple eligible probes are considered, but visits
execute sequentially under one shared Session/lock, not concurrently. Active
trade positions block scouting so a buyer's price observer is not moved during
trade recovery. Pending mutations also block execution and require the existing
explicit reconciliation procedure; scouting never clears or replays them.

Plans show eligible/excluded ships, blockers, the next ship/target, detailed-price
age, reason, distance and required orbit/navigation actions. Candidate lists are
rankings from current state, **not itineraries**. Eligible in-transit destinations
and current markets needing prices take priority; otherwise never-priced markets
precede stale ones, oldest prices first, then nearest probe/distance with stable
symbol tie breaks. Fresh detailed quotes are skipped. Sparse advertisements do
not reset the timestamp of older detailed prices. A confirmed visit still lacking
prices is recorded as `unpriced` and cooled down for `--max-age` seconds, separately
from quote freshness. It is not treated as successful price discovery.

Each invocation allows 1..100 visit attempts (default 4), 1..200 journaled actions
(default 8), and 1..7200 monotonic seconds (default 600). `--max-age` is 1..86400
seconds (default 900). A market is attempted at most once per invocation, including
unpriced results; HTTP failures stop rather than cycling through retries of the
itinerary. Transport retry limits still apply independently. A planned leg that
cannot fit the remaining action budget does not start. Session guards enforce
STOP, action limits and interruptible travel/pacing waits. Requests already in
flight cannot be cancelled and may exceed the deadline by their request timeout.
No detached loop or scheduler is started.

Resume uses freshly observed navigation and SQLite price/visit state, not the
saved plan: an already orbiting probe does not orbit again; a probe travelling to
a stale/unpriced market finishes that flight without another navigate; an arrived
probe observes its current market; a newly priced market is skipped on restart.
Moving a probe manually between sessions causes replanning, not blind replay.
Interrupted GETs may be repeated safely. Sparse-visit cooldowns survive restart.
Successful quotes feed the existing route reports/dashboard; `auto report` also
includes `scout_visits`, and saved `scout:SYSTEM` plans explain the latest decision.

Limits: no cross-system exploration, route/value optimizer, calibrated travel-time
estimate, parallel dispatch, automatic trading handoff or profit guarantee. A
transiting probe whose destination is already fresh or is not a marketplace is
not redirected; rerun after arrival to consider it for new targets. Without a
probe or stored waypoints an offline preview may have no candidates. Live scout
refresh discovers waypoints, but does not chart or explore hidden systems.

## Bounded Earning Controller

`auto earn SYSTEM` connects discovery to trading without requiring a route/good
argument. It is foreground, dry-run-first, and has **offline regression proof
only**, not live execution proof. Keep the handoff STOP until parent review.

```sh
export PATH="$PWD/../../.venv/bin:$PATH"
export PYTHONPATH=src
# Offline, no Session/token/API calls; existing SQLite opened read-only:
python -m py_st auto scout X1-CY22 --offline --scope 2026-09-06:SOURCE_CODE --database .state/handoff-scout.sqlite3
python -m py_st auto earn --help
# Future reviewed live GET-only dry run, requires STOP deliberately cleared:
python -m py_st auto earn X1-CY22 --cycles 3 --seconds 600 --actions 30
# Future explicit execution, only after reviewing fresh dry-run output:
python -m py_st auto earn X1-CY22 --execute --cycles 3 --seconds 600 --actions 30
```

The earn dry run is **not offline**: it loads credentials, makes GET requests,
acquires the shared lock, and writes observations/plans to SQLite. It does not
POST or simulate future visits/trades. It reports only the next decision (or
recovery), even with multiple cycles requested. There is no `earn --offline`;
the read-only scout preview above is stored discovery context, not an earn plan.

Each of 1..5 decision cycles (default 3) refreshes account/fleet/contracts and:

1. Refuses pending actions and accepted, unfulfilled contracts. A single open
   trade is recovered using its original ship/route/good, then the invocation
   returns without discovery or new cycles. Recovery is account-wide, even if
   the supplied system differs. Multiple or unknown positions require manual
   recovery review, preventing one recovering hauler from moving another trade's
   buyer observer.
2. Ranks ready routes in the requested system using shared fleet planning.
   Local waypoint discovery also enables fresh quotes at occupied markets not
   previously recorded. Both goods must be present with positive prices in the
   current GET responses; a sparse response cannot fall back to historical prices.
   The hauler must already be at the seller, empty, CRUISE and fuel-ready, with
   another stationary ship at the buyer. Executes one existing guarded trade.
3. If no route is ready, invokes one fuel-free probe scout visit. The next cycle
   reranks with fresh quotes and can trade the discovered route immediately.
   Visited targets are excluded across all cycles, even if their freshness expires.
   If neither a route nor a scout target exists, returns without looping further.

One discovery or one trade consumes a cycle, not each individual mutation. A
discovery in the last cycle needs a subsequent invocation to trade. All stages
share one Session, deadline, STOP checks, lock, journal and action budget:
1..200 actions (default 30), 1..7200 seconds (default 600). These bounds may stop
mid-trade; normal restart recovers persisted exposure first. Unknown outcomes
never trigger automatic fallback scouting or another route. Saved `earn:SYSTEM`,
`fleet` and `scout:SYSTEM` plans explain decisions; the journal records outcomes.

Trading retains the 50,000-credit floor plus 1,000 fuel allowance, three-leg fuel
margin, 5% price bounds and fresh pre-purchase buyer/seller rechecks. Active
contract obligations are refused rather than guessed. Quotes are not limit orders
and can change after observation. `--max-age` (1..86400, default 900) controls
scout freshness/cooldowns, not permission to buy from historical prices.

Deliberate limits: no historical-route hauler/probe reposition planner, automatic
return to a prior seller, speculative approach-fuel spending, or stand-alone
refuel-to-enable selection. After selling, the hauler remains at the buyer; later
cycles only trade routes ready at its new location or discover markets. Discovery
is coverage-ranked, not profit-targeted, and may find no executable route. The
controller does not promise unattended compounding or a profit per cycle. No new
mutation types, daemon, account registration or fleet purchases are enabled.

## Stop and Recovery

- `touch STOP` in the worktree or dashboard Pause requests a clean stop. Waits
  poll every 250ms. An in-flight network request may finish before stopping.
- Ctrl-C terminates the foreground command. Remove STOP deliberately before
  running another reviewed command. Dashboard Clear stop never starts a process.
- Limits are 1..200 mutations and 1..7200 seconds per session. HTTP requests use
  a 30-second timeout, so a request already dispatched can exceed the deadline.
- A single-writer lock prevents competing local automation sessions. Do not run
  manual gameplay or other agents against the same account while a loop runs.
- An uncertain request outcome stays `pending` and blocks further mutations.
  Inspect `auto report` and fresh live state. Do not erase the database or blindly
  replay. `auto reconcile ACTION_ID` displays the pending action and fresh
  account/fleet/contracts. After verifying actual effects, use
  `auto reconcile ACTION_ID --confirm-reviewed --evidence 'Specific observed outcome'`
  to record the review. This never replays the API action. Do not put secrets in
  the evidence. Unclear effects should remain pending.
- A STOP/deadline/Ctrl-C interruption in transport pacing before dispatch is
  `not_sent`; an interruption while waiting after a definitive cooldown/429
  rejection is `rejected`. These known outcomes need no uncertain-action review.
  Network ambiguity, in-flight interruptions, 5xx and invalid JSON replies remain
  pending, even after earlier rejected retries. Existing pending rows are never
  automatically cleared based on the new handling.
- On HTTP 401/API 4113, stop live work. Owner checks reset/account state and
  updates ignored ST_TOKEN to the correct agent token. Never auto-register.

## Storage and Verification

`.cache/data.json` is disposable and atomically replaced. `.state/intelligence.sqlite3`
is durable: schema version 1, WAL, FULL synchronous writes, reset/agent scope,
timestamp and source on observations, pending/succeeded/rejected/not_sent action
journal, and explicit reviewed outcomes.
Never clear `.state` as a cache-recovery step. Keep WAL sidecars with a running
database; use SQLite backup tooling rather than copying an active database alone.
No tokens are stored in the database. The JSON report is a machine-readable
export; select `--scope RESET:AGENT` if multiple resets/agents exist.

`auto report` also reconciles journal purchases, sales, refueling and contract
receipts against observed credit changes. Any unexplained difference is shown,
not silently counted as strategy profit. `auto backup .state/BACKUP_NAME.sqlite3`
creates an online, WAL-consistent backup and refuses to overwrite a file.
Keep backups ignored. Installed wheels include the dashboard and a `py-st`
entry point. `python tools/audit_spec.py` compares upstream/vendored API paths
and versions without credentials (not a complete schema comparison).

```sh
make ci
pip install -e '.[browser]'
python tools/check_dashboard.py
```

Browser verification uses installed Chrome headless and real local data. It
temporarily toggles STOP, so only run when automation is idle and STOP is absent.
It acquires the automation lock and never runs alongside a live session.
It does not mutate the game. Normal pytest uses mocks and a local test HTTP
server. The read-only live integration test requires both `ST_LIVE_TESTS=1`
and `ST_TOKEN`; no test performs live mutations.
