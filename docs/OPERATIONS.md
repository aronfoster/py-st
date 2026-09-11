# Flight Ledger Operations

Run commands from the normal repository root; no extra worktree is needed.
The local checkout and its `.state` ledger were consolidated here. Activate a
Python 3.12 virtual environment
and install `python -m pip install -e '.[dev]'` (see the README for setup).
For source-tree execution, use `export PYTHONPATH=src`. The CLI discovers
the ignored `.env` up the current directory's parent chain. Never pass tokens
as command arguments. No automatic registration is performed.

Live commands, including GET-only previews, require an existing version-1 WAL
ledger with a valid recorded agent identity in the current directory. They never
silently create replacement history. Before a workflow starts, its locked Session
checks the live reset/agent against that recorded identity without first writing
it. A mismatch or authentication failure does not initialize a new scope.

If a command reports missing history, return to the authoritative repository
directory first. **Do not create an empty ledger in another directory to bypass
the error.** `auto observe` explicitly permits initialization for genuinely new
history or an owner-reviewed reset/account transition. Existing initialized
ledgers require no migration or marker. Offline report/backup tools can create
empty local stores, but an empty or market-only store does not authorize live
workflows. Read-only SQLite and existing-file opens may still use WAL sidecars.

## Choose the Right Workflow

All command fragments below follow `python -m py_st`. Uppercase identifiers are
placeholders. Existing `X1-CY22` / `SOURCE_CODE` examples illustrate syntax, not
current account state; substitute your observed system, ship, contract and scope.
An offline command means **no game API or token**, not necessarily no disk writes.

| Task | Command | Mode and Local Effects |
| --- | --- | --- |
| Inspect history and recovery | `auto report --scope RESET:AGENT` | OFFLINE; can initialize the default ledger |
| Browse fleet, Contract Desk and pilot records | `auto dashboard --port 8765` | OFFLINE local server; reads existing ledger; explicit STOP controls |
| Shortlist contract suppliers | `auto sources CONTRACT_ID --scope RESET:AGENT` | OFFLINE read-only existing ledger; possible SQLite sidecars |
| Model procurement | `auto contract-model INPUT.json` | OFFLINE pure model, no saved plan or execution |
| Preview historical discovery/routes | `auto scout SYSTEM --offline --scope RESET:AGENT` / `auto backtest --help` | OFFLINE stored evidence, not live eligibility |
| Refresh observations | `auto observe` / `auto scan SYSTEM` | LIVE GET; local ledger writes |
| Diagnose ore extraction | `auto mining SHIP` | LIVE GET only; no execution option |
| Preview earning | `auto earn SYSTEM` / `auto pilot SYSTEM` | LIVE GET dry run; Session, lock, observations/plans |
| Act under bounded guards | `auto pilot SYSTEM --execute` | LIVE mutations; shared action/time budget and journal |

`auto contract`, `trade`, `fleet`, `scout`, `move`, `refuel` and `negotiate`
also default to live GET-only planning; their `--execute` flag permits the
specific guarded mutations described below. There is no `earn --offline` or
`pilot --offline`, and no standalone `auto reposition` command: repositioning
is an optional flag on earn/pilot. Legacy manual gameplay commands are not a
substitute for these STOP/journal safeguards. `--help` requires no game access.

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

### Synthetic System Explorer demo

A fresh checkout can create a clearly synthetic, separate ledger without a game
token. The command refuses to overwrite an existing destination:

```sh
.venv/bin/python tools/populate_dashboard_demo.py
cd .cache/nightly/system-explorer-demo
../../../.venv/bin/python -m py_st auto dashboard --port 8765
```

Open `http://127.0.0.1:8765`. The demo contains overlapping waypoints, market,
shipyard and jump-gate observations, one stationary ship, one ship in transit,
and deliberately missing waypoint traits/market/shipyard details. Remove the
demo directory or provide a new root argument before regenerating it; the tool
never opens or changes the normal `.state/intelligence.sqlite3`.
The dashboard distinguishes observation age from live telemetry. Route figures
are estimates after round-trip fuel, not guaranteed profit or executable orders.

For offline fixed-route evaluation over historical observations, use
`auto backtest --help` and [Historical Route Replay](HISTORICAL_ROUTES.md).
It requires explicit time/fuel assumptions, never uses future quotes at entry,
reports unresolved exposure, and leaves STOP and the database unchanged.

## Market Desk (Offline)

In Flight Ledger, select a universe/agent, then a cached market and good in
Market Desk. The market table shows actual cached buy/sell prices, batch volume,
supply and activity from the report's last nonempty detailed observation.
"Current stored detail" is not a live quote. If a newer sparse advertisement
exists, the table says "Retained history" and keeps the original detailed
timestamp and provenance. Detail over 15 minutes old is marked STALE; invalid
and future timestamps are explicitly labeled, never treated as fresh.

Good history reads matching detailed observations, retaining the newest 50 by
actual timestamp and displaying them oldest first. Buy and sell trends use
elapsed time on the horizontal axis, not equal spacing between observations.
Missing, zero, malformed or duplicate-good quotes stay unknown; gaps are not
interpolated. Invalid/future history timestamps are skipped with visible counts.
One observation still has a useful table but cannot establish a trend. Volume
is a transaction batch limit, not available stock; supply/activity are recorded
market labels, not execution guarantees.

`GET /api/market-history?scope=RESET:AGENT&waypoint=X1-CY22-C45&good=FUEL&limit=50`
requires explicit scope and valid waypoint/good symbols. Limit is an integer
from 1 through 100 (default 50). Unknown markets/scopes, repeated or unexpected
query parameters are rejected. A known market with no matching good history
returns an empty series. The endpoint uses only the server's fixed-root existing
SQLite ledger in `mode=ro`, including committed WAL data; it never initializes
a database, reads credentials, creates a Session, or calls the game. SQLite
may use WAL/shared-memory sidecars; `immutable=1` is deliberately not used.
The loopback Host guard applies. No authentication token or execution control
is added. Refresh ledger preserves valid same-scope selections and only reloads
cached evidence; scope/selection changes invalidate outstanding history results.

## Recorded Safety Doctor (Offline)

STOP is a filesystem sentinel: any directory entry named `STOP`, including a
dangling symbolic link, requests a stop. Runner, report and doctor use the same
detection. Dashboard pause exclusively creates the sentinel if absent and preserves
an existing entry/target; clear-stop unlinks the sentinel, never a symlink target.
A directory or inaccessible control path may require owner filesystem review;
the dashboard reports the control unavailable rather than claiming STOP cleared.

```sh
python -m py_st auto doctor --scope RESET:AGENT
python -m py_st auto doctor --scope RESET:AGENT --database .state/backup.sqlite3 --root . --max-age 900
```

Doctor requires an explicit scope and an existing ledger. It loads no credentials
or dotenv, creates no Session or process lock, and makes no game API calls.
`--root` selects only the STOP directory (default current directory); `--database`
selects the existing ledger. `--max-age` is 1..86400 seconds, default 900.
Exit **0** means no recorded concerns, **1** means recorded concerns need attention,
and **2** means invalid or unavailable input, including missing database or unknown
scope. Neither 0 nor fresh per-key records proves complete lists or live readiness.

For one open procurement intent, the recovery finding includes a `procurement`
summary joined to the latest contract and original ship in that scope. It shows
required/delivered/remaining goods, matching held cargo, quantities still to acquire,
excess and unrelated cargo, and a suggested recovery step to review. Missing or
inconsistent evidence stays unknown. The position, contract and ship keep their
separate observation timestamps: this is not a simultaneous live snapshot.
Acceptance/delivery deadlines are classified against the report clock as open,
expired or unknown; accepted contracts no longer need acceptance-time headroom.
Expired completed contracts can still require local intent closure. These summaries
never supply execution authority or automatically reconcile/abandon a position.

In Flight Ledger, select a universe/agent and click **Check recorded safety** near
Automation Runs. `GET /api/doctor?scope=RESET:AGENT` calls the same shared doctor
with the server's fixed root and `.state/intelligence.sqlite3`. Exact loopback
Host validation applies. Only one `scope` parameter is accepted; arbitrary root,
database, execution and other parameters are rejected. Structured exit 0/1 results
return HTTP 200; invalid/unavailable results return HTTP 400. An empty checkout
does not create a ledger. The check runs only on click, not on background refresh.
New checks and scope changes discard late diagnostic responses and old findings.
The same per-good progress, observation times and deadline states appear beneath
the procurement finding in the dashboard.

Findings are offline recorded evidence: live scope and readiness remain unverified,
process liveness unknown, and execution unauthorized. Pending action IDs and any
paths are plain text, not executable links. The check does not clear STOP,
reconcile actions, autoplay, restart a controller, or recommend a saved execution
command. Review recovery separately with fresh state and explicit authorization.
No live authority is granted by the CLI, dashboard or this documentation.

SQLite is opened read-only without ledger writes, initialization or migrations.
It may create/use WAL/shared-memory sidecars or update shared memory, so this is
not a zero-filesystem-write promise. STOP is a separate point-in-time check,
not atomic with the database snapshot. Missing records remain unknown.

## Contract Desk (Offline)

For the CLI equivalent, use an existing ledger and explicit reset/agent scope:

```sh
python -m py_st auto sources CONTRACT_ID --scope RESET:AGENT
python -m py_st auto sources CONTRACT_ID --scope RESET:AGENT --database .state/backup.sqlite3 --max-age 900
python -m py_st auto contract-model INPUT.json
```

`sources` does not scan or fetch missing prices. `--max-age` accepts 1..86400
seconds (default 900). Its shortlist is evidence, not a ready-to-execute model;
use Contract Desk to prepare inputs or follow the JSON format in
[Offline Contract Planning](CONTRACT_PLANNING.md).

The Flight Ledger page includes a Contract Desk over the same shared ledger as
`auto sources`. Select a universe/agent, then any stored unfulfilled contract
(offered or accepted). Fulfilled contracts remain in the contract summary but
cannot be selected for modeling. An empty checkout or scope shows an empty
state; opening the page does not create a database or fetch game data.

`GET /api/sources?scope=RESET:AGENT&contract=ID` calls the shared
`contract_sources` service against the server root's fixed
`.state/intelligence.sqlite3`. Unknown scopes/contracts, repeated parameters,
and extra parameters (including filesystem paths) are rejected. Reads use
SQLite read-only mode; no observations, plans or actions are written. SQLite
may still create or update WAL/shared-memory sidecars when reading a WAL ledger.

Every source shows its waypoint, advertisement timestamp, detailed-quote
timestamp and age, purchase price/batch volume when usable, and quote status.
"CURRENT stored detail at evaluation" means stored detailed evidence within
900 seconds at the displayed evaluation time, not a live quote. Displayed ages
are also measured at evaluation; reload sources to reevaluate them.
A newer sparse advertisement never refreshes an older detailed
timestamp. Historical detail is explicitly not current visibility; stale,
missing and invalid detail is marked stale or unknown. Adverts are not inventory,
and geometric distance is not a fuel or travel estimate.

Use **Choose routes and enter costs** to prepare a model without editing JSON:

1. Review the selected observed ship and edit **Credits** and **Free cargo units**
   as needed. Defaults come from the cached agent and ship snapshot; missing
   observations leave blank inputs. A zero free hold requires a different ship
   or an explicit positive capacity assumption, not an invented default.
2. Check the source routes to include. None are selected automatically. Selection
   is only a modeling choice, never execution authority. Unselected routes are
   omitted from the built draft and their hidden, disabled inputs need no values.
3. Review each selected route's purchase price and trade volume. Defaults use
   the shortlist's usable cached quotes; stale/unknown values are blank and must
   be supplied explicitly. Price and batch volume must be positive integers.
4. Enter **Fuel credits per trip** and **Travel seconds per trip** for each
   selected route. Both start blank, including same-market routes. Explicit zero
   is permitted; neither is inferred from coordinates or ship fuel. Include any
   complete-trip approach/return assumptions you intend to model.
5. Optionally enter **Available units**. Blank means unbounded modeled supply;
   explicit zero means none. This is a shared source/good ceiling, not trade
   volume. When one source/good serves multiple destinations, supply ceilings
   must agree; the shared planner validates these cross-route constraints.
6. Click **Build draft from form**, then **Calculate offline model**. Build is
   local only and focuses missing/invalid fields without replacing the draft or
   sending a request. Successful build replaces the entire JSON draft with the
   selected contract, selected routes and form values, using the planner's
   50,000 credit floor, 1,000 fuel allowance, 20% price margin and one-hour
   deadline margin. Review or edit that draft before calculating if needed.

The **Advanced JSON editor** remains directly editable and can be calculated
without using the builder. It initially includes all shortlisted quotes with
`fuel_cost: null` and `travel_seconds: null`. Use it for custom routes, empty
quote sets, contract edits or different reserve/margin assumptions. A later
**Build draft from form** explicitly replaces those advanced edits; the form
does not synchronize from JSON. Form edits alone do not alter the existing
JSON draft or its result. All builder numbers must be whole, safe JavaScript
integers, with non-negative costs, credits and optional availability, and
positive free capacity, prices and batch volumes.

Expand the evidence section for timestamped contract/agent/ship records. Selecting
another observed ship or **Reset draft from cached evidence** resets both the
builder and JSON draft, clearing route selections and fuel/travel inputs.
**Reload sources and reset draft** reloads source evidence and retries after
errors. Background ledger refreshes overwrite neither form nor JSON edits.
Switching scope or contract clears both and ignores late responses. Scope changes
also clear the other scoped panels and disable export until a successful report,
including when the first report fails. Review capacity, reserves and other
obligations yourself; no stock or execution readiness is inferred.

**Calculate offline model** posts `{csrf, model}` to `/api/contract-model`.
The endpoint accepts at most 65,536 bytes of JSON and uses the same exact
loopback Host, Origin and per-server CSRF protections as STOP control. It calls
only the pure `plan_contract_procurement` function: no token, Session, game API,
database access, saved plan, or STOP change. Malformed inputs return HTTP 400;
valid but infeasible models return HTTP 200 with reasons. Results show
feasibility, costs, reserves, revenue/net, cargo trips, purchase batches and full
JSON, always with `execution_authorized: false`.

This is a counterfactual planning tool, not a live launcher. It does not establish
ship eligibility, physical fuel feasibility, current market visibility, all
other obligations or global allocation optimality. Edited inputs may depart
from stored evidence. See [Offline Contract Planning](CONTRACT_PLANNING.md)
for model limitations. STOP controls retain their existing semantics: Pause
creates STOP; Clear stop removes it and never starts a process.

Synthetic-only verification (optional browser dependency, installed Chrome):

```sh
ST_LIVE_TESTS=0 PYTHONPATH=src pytest -q tests/test_dashboard.py
ST_LIVE_TESTS=0 DASHBOARD_BROWSER_TESTS=1 PYTHONPATH=src pytest -q tests/test_dashboard.py
```

Normal CI skips the browser test. The opt-in check also skips if Playwright is
not installed; when installed it requires Chrome and fails on browser errors.
It uses only a temporary synthetic ledger, never copies the real ledger or
touches runtime STOP, and checks 1440px desktop and 390px mobile, structured form
selection/validation/build/calculation without JSON editing, and direct JSON
editing/calculation. It also covers preserved form/draft edits on refresh,
failed-scope retries, late source/report/model responses, automation-run display,
safe text rendering, and horizontal overflow. Screenshots are written inside
pytest's temporary synthetic fixture directory. Do not use
`tools/check_dashboard.py` for this test; that older tool toggles runtime STOP.

Contract Desk verification: full offline `make ci` passed Black, Ruff
`--no-fix`, mypy (162 source files), and **857 passed, 2 skipped**. The opt-in
dashboard suite passed **30 tests**, including synthetic Chrome at both viewport
sizes with no JavaScript errors or horizontal overflow. These results establish
offline behavior only, not live account state or execution readiness.

## Guarded Procurement

`auto mining SHIP --seconds 120` refreshes agent/fleet/contracts, the selected
ship and its current waypoint using GETs. The time bound accepts 1..7200 seconds.
It reports orbit, mining-laser, cargo and cooldown blockers plus unknowns and
depletion warnings. It never extracts, surveys, orbits, waits for readiness or
installs equipment, and has no `--execute` option. The assessment remains
`blocked` or `unknown`, with `execution_authorized: false`: equipment operability,
server acceptance, ore yield and profitability are not established by snapshots.

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
including the refill command's own 20% headroom at that ceiling, in addition
to the 50,000 floor, 1,000 allowance and all remaining goods. For a 400-unit tank
and a 72-credit fuel quote, the ceiling is 87 and the full refill reserve is
`4 * ceil(87 * 1.2) = 420`, not 348. Older saved price ceilings stay unchanged;
acquisition rechecks the corrected funding requirement before further spending.
Remote execution aggregates purchase batches before one delivery flight, then
delivers and fulfills. Run guarded `auto refuel` afterward; its reserved refill
is not automatically spent, and no return trip is promised. Remote multi-good
and simultaneous accepted obligations fail closed. Dry-run
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

### Same-Market Multi-Good Execution

`auto contract SHIP CONTRACT_ID` now handles one contract with multiple distinct
goods when every delivery and acquisition uses the same marketplace and the ship
is already there. It does not move or refuel the ship. It checks all goods and
funds the complete remaining obligation before acceptance, then delivers after
each capacity/volume-bounded purchase. This supports quantities larger than the
hold without any travel legs. Repeated terms for the same good are rejected
because the API's delivery request does not identify an individual term.

A `procurement:CONTRACT_ID` execution intent preserves original ship, market,
terms and per-good ceilings. Other nonclosed exposure blocks procurement, and
an unaccepted procurement intent also blocks unrelated trading, fleet selection
and refueling. Completed purchases/deliveries are observed, never blindly replayed;
unknown outcomes remain pending. Owned-cargo delivery and final fulfillment do
not require acquisition quotes or purchase liquidity. Read
[Stationary Multi-Good Procurement](LOCAL_PROCUREMENT.md) before execution.

For offline multi-good/multi-load analysis, use `auto contract-model INPUT.json`;
see [Offline Contract Planning](CONTRACT_PLANNING.md). Shared source/good
availability is consumed across terms/destinations with consistent ceilings and
no duplicate route quotes. Batches are counted per load. The model rejects
fulfilled contracts, marks expired unaccepted offers infeasible using
`deadlineToAccept` (legacy `expiration` if absent), and validates non-negative
reserves and finite margins. Its input-order greedy allocation can falsely
report infeasibility when scarce supply could be assigned differently; it is
not globally optimal and never authorizes live execution.

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

At-source trade dry runs include a funded refill plan when carried fuel is low.
An explicit manual `auto trade` dry run while away from the source instead notes
`Approach/refill before reaching source not modeled`. It does not cost or prove
that approach; manual trade execution can navigate to the source. This is not
permission for `auto earn` to spend speculative approach fuel.

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
only**, not end-to-end live execution proof. The new funded local refuel
selection has no live proof yet. Review fresh state and coordinate with the
active operator before deliberately clearing STOP; do not overlap sessions.

```sh
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
3. If no fuel-ready route exists, tries ranked candidates with a funded local
   refill at the seller. The hauler must already be there, stationary, empty,
   CRUISE and large enough for the planned load. A full tank must cover the
   three-leg fuel guard before fuel spending. A successful refill preflight
   selects one guarded trade, not a stand-alone speculative refuel decision.
4. If no ready or locally refuelable route qualifies, invokes one fuel-free
   probe scout visit. The next cycle reranks with fresh quotes and can trade
   the discovered route immediately.
   Visited targets are excluded across all cycles, even if their freshness expires.
   If neither a qualifying route nor a scout target exists, returns without
   looping further.

One discovery or one trade consumes a cycle, not each individual mutation. A
discovery in the last cycle needs a subsequent invocation to trade. All stages
share one Session, deadline, STOP checks, lock, journal and action budget:
1..200 actions (default 30), 1..7200 seconds (default 600). These bounds may stop
mid-trade; normal restart recovers persisted exposure first. Unknown outcomes
never trigger automatic fallback scouting or another route. Saved `earn:SYSTEM`,
`fleet` and `scout:SYSTEM` plans explain decisions; the journal records outcomes.

Refill planning refreshes ship/contract state, seller and buyer prices/volumes,
positive local fuel price/volume and credits. Execution repeats the preflight
after docking and before purchasing fuel, then verifies carried fuel before
goods acquisition. Both goods counterparties and credits are checked again
before buying goods. The required funding is **50,000 floor + 1,000 allowance +
route fuel allowance + units at max buy price + maximum estimated refill cost**.
The refill estimate rounds missing fuel up to 100-unit packs and applies a 20%
fuel price margin. A positive trade spread does not replace this funding check;
the refill outlay is not a separate all-in profit guarantee.

Fuel mutations use the existing write-ahead journal. The trade position is
persisted after refueling and before goods purchase; an interrupted confirmed
refill before that position exists is handled by fresh fuel/credit observation
and replanning, not replay of a saved refill. Unknown dispatched outcomes remain
pending for explicit reconciliation. Selection may skip a candidate whose refill
economics fail, but STOP, budget/deadline, pending-action and active-contract
guards must not become permission for fallback scouting. Once a trade is
selected, execution failure stops rather than trying another route or scouting.

Trading retains the 50,000-credit floor plus 1,000 fuel allowance, three-leg fuel
margin, 5% price bounds and fresh pre-purchase buyer/seller rechecks. Active
contract obligations are refused rather than guessed. Quotes are not limit orders
and can change after observation. `--max-age` (1..86400, default 900) controls
scout freshness/cooldowns, not permission to buy from historical prices.

Deliberate limits: no arbitrary historical-route hauler/probe reposition planner.
Returning to a prior seller requires the explicit bounded opt-in below. Funded local
refuel-to-enable selection is supported only after fuel-ready candidates; it
does not reposition ships. After selling, the hauler remains at the buyer; later
cycles can trade ready or locally refuelable routes there, or discover markets.
Discovery is coverage-ranked, not profit-targeted, and may find no executable route. The
controller does not promise unattended compounding or a profit per cycle. No new
mutation types, daemon, account registration or fleet purchases are enabled.

## Foreground Pilot

`auto pilot SYSTEM` is the foreground controller for repeating earning decisions
without manually restarting `earn` after each returned cycle or recovery. It
does not choose new contracts or extraction. With `--recover-contracts`, it can
recover one saved procurement intent before earning. It is not a daemon,
scheduler, background service or dashboard-launchable process.

1. Activate the environment at the repository root. Inspect `auto report` first;
   select `--scope RESET:AGENT` if it lists multiple scopes. Review open positions,
   pending actions and previous `automation_runs`. Do not overlap controllers or
   manual gameplay against the same account.
2. Configure the correct agent's `ST_TOKEN` in ignored `.env`. Review why STOP
   exists, reconcile uncertain actions, then deliberately clear STOP only when
   safe and authorized. Dashboard Clear stop only removes STOP; it starts nothing.
3. Run `auto observe` for fresh fleet, credits and contracts. Keep at least 50,000
   credits plus fuel and known obligations. Accepted unfulfilled contracts block
   earning; use the procurement/recovery workflow instead of bypassing the guard.
4. Preview the next decision using the first command below. It uses live GETs,
   the Session lock and local observation/plan/run-record writes. Even with
   `--steps 10`, dry run evaluates only one decision, not a simulated itinerary.
5. Review the decision, blockers and bounds before explicitly authorizing the
   second command. Keep the terminal attached; inspect report/dashboard history
   after completion or interruption before deciding whether to start again.

```sh
# LIVE GET-only dry run; substitute your observed system:
python -m py_st auto pilot SYSTEM --steps 10 --seconds 3600 --actions 100
# LIVE execution only after review and authorization:
python -m py_st auto pilot SYSTEM --execute --steps 10 --seconds 3600 --actions 100
# OFFLINE review after the run, including failures:
python -m py_st auto report --scope RESET:AGENT
```

| Option | Default | Bounds / Meaning |
| --- | ---: | --- |
| `--steps` | 10 | 1..100 returned earning decisions, not trades or mutations |
| `--seconds` | 3600 | 1..7200 monotonic seconds for the entire Session |
| `--actions` | 100 | 1..200 journaled mutations for the entire Session |
| `--max-age` | 900 | 1..86400 seconds; scouting freshness and reposition evidence |
| `--reposition` | false | Opt in to the costed return-to-original-source policy below |
| `--recover-contracts` | false | Recover a single original procurement execution intent; never choose a new offer |
| `--execute` | false | Explicitly permit guarded gameplay mutations |

Execution calls `earn_run(..., cycles=1)` or opted-in contract recovery with
**one shared Session**:
one lock, deadline, action budget, STOP boundary and write-ahead journal. Budgets
do not reset between steps. Each returned decision increments `completed_steps`;
a decision that raises midway may have used actions without incrementing it.
Steps are neither guaranteed profitable trades nor a promised duration.

Unlike standalone `earn`, pilot continues after `cycle limit` **and** `recovery
only` if steps and budgets remain. Thus a recovered trade or confirmed reposition
arrival can be followed by another freshly planned earn call in the same pilot
invocation. No saved itinerary is replayed; later purchases still require fresh
quotes, usable source fuel and the unchanged trade guards. Scout freshness and
persisted visit cooldowns carry across calls, but earn's per-call visited set is
not a pilot-wide itinerary exclusion.

`--recover-contracts` only considers one open `procurement:CONTRACT_ID` position,
not an offline Contract Desk model or saved preview. It validates the original
ship/source/contract and invokes the same contract service. Recovery may include
accepting an original unaccepted execution intent when `--execute` is supplied;
it never negotiates or chooses a new offer. Missing/ambiguous identities, pending
actions, other positions or other accepted obligations stop the run. One complete
contract recovery counts as one returned decision, possibly many mutations. With
more steps, ordinary earning can follow fulfillment. Use `--steps 1` to request
only recovery; this still shares the overall time/action bounds.

```sh
# Live GET-only preview of an existing execution intent, not offline:
python -m py_st auto pilot SYSTEM --recover-contracts --steps 1 --seconds 600 --actions 30
# Explicit recovery only after reviewing the original intent and preview:
python -m py_st auto pilot SYSTEM --recover-contracts --execute --steps 1 --seconds 600 --actions 30
```

Pilot stops on `no ready routes or scout targets` or `reposition blocked` instead
of spinning. STOP, exhausted time/actions, pending outcomes and other safety
exceptions terminate the run; HTTP, storage and unexpected failures do not retry
another step. Ctrl-C interrupts the foreground process. In-flight requests can
outlast a deadline or STOP request. Completion at the step limit does not itself
prove all positions closed: inspect the ledger before a restart.

### Recorded Runs and Restart

Each pilot invocation generates a UUID and persists `automation_run` observations
in its reset/agent scope. `auto report` exposes the latest record for each UUID
as `automation_runs`; the dashboard's Automation Runs section shows up to 20
latest records for the selected scope, including mode, saved status, returned
steps, actions, outcome, last decision and reviewed restart command. Full records
also include timestamps and remaining budgets. Ordinary earn invocations do not
create pilot run records. No new schema migration is needed: these use the
existing schema-v1 observations table.

Statuses are recorded `running`, `completed`, `stopped`, `interrupted` or
`failed`. **This is persisted history, not a process monitor or heartbeat.** A
crash, forced termination or storage failure can leave `running` stale; the
dashboard does not detect that a process is alive. Displayed remaining time is
the last saved value, not a ticking live budget. Check the foreground process
and operator coordination separately, without starting a competing controller.

On any failure, inspect `auto report --scope RESET:AGENT` and the dashboard
before rerunning. Review journal outcomes, open positions and fresh live state
when safe; use the explicit reconciliation procedure below for pending actions.
A storage exception may prevent the terminal update or the entire record from
being saved. Failure before scope discovery may provide no scoped run record at
all. Missing history is not proof that no mutation occurred. Preserve the ledger
and sidecars, resolve storage availability/integrity before resuming, and never
delete state or blindly replay an uncertain action to get past an error.

The saved `resume_command` is a **suggestion for a NEW run with NEW budgets**,
not continuation of the old UUID, remaining-time allowance or recorded decisions.
It may include `--execute`, `--reposition` and `--recover-contracts`; review
those flags and set explicit
bounds yourself. A deliberate restart observes current state and recovers durable
positions before selecting new work. STOP is never automatically cleared and
the UI cannot execute the suggested command. This documentation does not claim
end-to-end live pilot proof or unattended profitability.

## Bounded Return to Source

`auto earn SYSTEM --reposition` (also available on `auto pilot`) opts in to one
costed return per earning call to the **original
source of the most recent completed trade**, after exhausting ready and funded
local-refill routes but before coverage scouting. It defaults to false. This is
an automation capability with synthetic Session regression tests, not live proof
or an arbitrary historical-route optimizer. It does not buy or sell anything
during repositioning, and never moves the independent buyer observer.

```sh
# Future reviewed GET-only preview, not offline; normal STOP controls apply:
python -m py_st auto earn X1-CY22 --reposition --cycles 3
# Explicit bounded execution after reviewing fresh output:
python -m py_st auto earn X1-CY22 --reposition --execute --seconds 600 --actions 6
```

The completed position must preserve its original ship/source/buyer/good and
show a completed purchase, not a cancelled never-dispatched intent. Both the
completion and original detailed seller observation must be within `--max-age`.
Sparse visits do not refresh that detailed observation's timestamp. The original
ship must be empty, stationary CRUISE at the buyer, with a separate stationary
observer remaining there. Active contracts, pending actions, and other open or
unknown positions block the operation. Missing evidence is reported with a
reason: no completed trade, or an expired original trade/source quote with no
open exposure, declines to normal discovery. Old suggestions do not permanently
suppress coverage scouting. Other unsafe candidates remain terminal blockers.
An already-open reposition never falls through to discovery when evidence expires.
It remains protected for recovery/review unless verified undispatched abandonment
is safe; even abandonment terminates that earn call without discovery.

The JSON decision exposes route, ship, observer, source evidence timestamp/age,
fresh buyer timestamp, units and price ceilings, fuel costs, protected credits,
expected net, and recovery policy. Historical seller prices authorize **only
reposition evidence**, never purchase. Goods use 5% adverse price bounds. With
`d = ceil(distance)` (minimum 1), fueled ships must carry **3d + 10**: `d` for
approach and `2d + 10` at source so a physical return can pass the unchanged
Session round-trip guard. Full-tank capacity must also support the later trade's
`3d + 10` guard. If current fuel is insufficient but a full tank passes, a new
candidate may fund one full refill at the current buyer before creating its
intent. No en-route refueling, one-way exception, or DRIFT is enabled.

Fuel costing rounds to 100-unit packs and uses the higher usable source/buyer
fuel price plus 20%. It costs an approach-and-return pair and a future trade
round trip separately. A source **full-tank** refill allowance additionally uses
20% price growth followed by the refuel guard's 20% headroom. This deliberately
over-reserves fuel rather than assuming exact depletion or counting future sales.
Current credits must cover **50,000 + 1,000 + the entire candidate goods load at
max buy + all costed fuel + source full refill + any upfront buyer refill**.
The buyer refill rounds current missing fuel to 100-unit packs at the fresh
buyer price plus 20%. Expected goods spread must remain strictly positive after
subtracting all these fuel costs, including the upfront refill.
This is a conservative estimate, not a price guarantee or escrow.

Buyer refueling happens under the same exclusive Session, before any new
reposition intent. Docking is followed by fresh full-candidate and refill checks;
the shared refuel planner's nonnegative `additional_reserve` preserves goods,
approach/trade fuel and the source full-refill budget on top of the unchanged
50,000 floor and 1,000 allowance. Changed economics or ship state stops spending.
Original trade/source evidence and the fresh buyer quote bound transport waits.
After a confirmed refill, replan from actual fuel and credits before persisting
or navigating. STOP at that boundary leaves no navigation intent; the next call
reobserves rather than replaying the refill. An unknown refill remains pending
and blocks the next invocation even if the tank appears full. Dry run reports
`buyer_upfront_refill_allowance` without docking, refueling or position writes.

An existing open intent cannot dock or refuel. If it needs fuel after a safe
orbit, only verified undispatched navigation at the original buyer can be retired
through the existing abandonment checks. That call ends recovery-only; a new
bounded earn invocation may then evaluate a refill. Unknown or possibly dispatched
navigation is never retired this way. Session's orbit/navigation-only authority
for open reposition intents is unchanged.

A distinct `reposition:SHIP` open intent is saved before orbit/navigation.
Both supplied and persisted plans must match the actual original completed trade
observation in the current reset/agent scope: ship, source, buyer, and good, not
just its observation ID. This validation precedes intent writes and the
already-arrived shortcut. Malformed numeric bounds, nonpositive IDs/units/prices,
out-of-range max-age, negative fuel/cost fields, and changed identities stop
without silently replacing the plan or closing exposure.

Recovery precedes fleet planning and scouting even without `--reposition`, and
even when a different system is supplied. It uses the original ship/current nav
and journal dispatch boundary, not a replayed itinerary. Confirmed or unknown
navigation is never reissued. Unknown actions require explicit reconciliation;
STOP, deadline and action limits remain in force after orbit, dispatch and during
arrival observation. Ambiguous positions fail closed; old trade purchase exposure
is never retired by this feature. Dry runs write observations/plans, not positions.

Standalone fleet, direct trade, refuel and local/remote contract automation also
refuse open reposition exposure, including dry runs. The Session mutation boundary
blocks other automation POSTs, including manual `auto move` of the hauler or buyer
observer and negotiation, while that intent is open. Only explicitly identified
reposition orbit/navigation of the original hauler to the saved source is allowed.
This is a scoped interoperation guard, not a relaxation of the mutation allowlist.

Departure prepares orbit explicitly, revalidates the plan, and calls the unchanged
Session navigation planner once. After preparation GETs it reobserves ship,
contracts, credits and buyer observer, then checks original completion age, original
detailed seller age and the buyer's 60-second quote bound immediately before the
journaled navigation mutation. There is no second navigation-plan/orbit pass after
that check. Changed ship/route/fuel state or expired evidence stops before dispatch;
STOP, deadlines, action budgets and unknown-outcome journaling remain unchanged.

Fresh confirmed source arrival closes only the reposition position and returns
**recovery only**, terminating standalone `earn` regardless of remaining cycles.
Output reports actual arrival fuel and whether it still supports physical return.
It does not automatically return, refill or purchase. Missing source goods/fuel
quotes do not authorize a purchase or DRIFT. A later earn call must
obtain new source/buyer quotes, usable source fuel, and satisfy the existing
fresh-purchase and actual-fuel/refill guards before trading. An interrupted open
reposition likewise finishes recovery only, never trading in that earn call.
Pilot may make the next fresh earn call within its existing shared budget;
standalone earn requires a deliberate new invocation.

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
- A pilot failure or storage exception requires report/journal review before
  rerun, even if `automation_runs` still says `running` or has no terminal row.
  Restart means a new UUID and new budgets, never replay of recorded decisions.

## Storage and Verification

This documentation pass checked CLI help with CliRunner while mocking Session,
ledger construction, dotenv loading and HTTP requests to reject access. No live
commands, dashboard server, runtime database, `.env` or STOP were used or changed.
No code/test changes or new migrations are part of this documentation update.

Previously reported full offline verification for the planner and funded local
refuel increment: **560 passed, 1 skipped**. Checks were not rerun in this
documentation-only pass. No new live refuel-feature proof, browser check or
current account-state observation is claimed here; concurrent live evidence
belongs in the operator's separate record.

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
temporarily toggles STOP by default, so only run that mode when automation is idle
and STOP is absent. For display-only verification with an existing STOP, use
`PYTHONPATH=src python tools/check_dashboard.py --read-only`. Both modes acquire
the shared automation lock and refuse an active controller. `--root PATH` selects
the ledger/STOP root (default cwd); read-only mode requires an existing ledger
and never initializes one. It checks stored credits/fleet and available Market
Desk data at 1440px desktop and 390px mobile, JavaScript errors and overflow,
without clicking control/model POST actions. Browser non-GET and external requests
are aborted and fail the check. STOP existence must remain unchanged, including
on failure; an operator change is reported, never restored or unlinked. Unique
`.state/dashboard-product-readonly-<run-id>-desktop.png` and `-mobile.png` captures
preserve the original screenshots. The lock file, screenshots and possible SQLite
WAL/shared-memory sidecars mean this is not a zero-filesystem-write promise.
Neither mode accesses game APIs or credentials; `--help` needs no browser or
runtime state. Normal pytest uses mocks and a local test HTTP
server. The read-only live integration test requires both `ST_LIVE_TESTS=1`
and `ST_TOKEN`; no test performs live mutations.
