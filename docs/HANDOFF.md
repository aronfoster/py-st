# FOS-63 Handoff

## Current Checkout and New Nightly Attempt

The owner consolidated the repository after the previous run. The normal root
checkout is now on `aron/fos-63-review`, continued from `c6be829`;
`tmp/astra` no longer exists.
The existing `.env`, `.venv`, STOP, authoritative `.state/intelligence.sqlite3`,
backups and screenshots are all rooted here. Use `.venv/bin/python` directly;
no alternate checkout or PYTHONPATH workaround is needed. Do not recreate the
old worktree. Keep temporary work inside ignored `.cache/nightly` and do not
request access to parent directories or global configuration.

The new nightly attempt started with a clean checkout and independently verified
**1,021 passed, 10 skipped**, Black/Ruff/mypy passing. Current offline verification
is **1,543 passed, 10 skipped**, plus **73 passed** with explicit synthetic Chrome
dashboard tests. Test artifacts are under `.cache/nightly` and use the existing
`.venv`. No new worktree, parent-directory access request, live gameplay or runtime
ledger migration was needed.

### September 10 Owner-Requested Delivery

The owner requested a commit/push of the accumulated changes and an updated
FOS-63 ticket. This delivery includes the earlier September 10 work and the
unsupervised continuation below. The exact published revision and push result are
recorded in Linear; identify this delivery locally with `git log -1 --format=%H`.

Pre-delivery Python 3.12 `ST_LIVE_TESTS=0 make ci` was independently repeated:
**1,543 passed, 10 skipped**, Black/Ruff/mypy clean. The latest full explicit
synthetic dashboard suite passed **73 tests**. Only source, tests and repository
documentation belong in this delivery; credentials and runtime data stay local.

Also included: bounded GET-only `auto infrastructure SYSTEM` for jump gates,
shipyards and construction observations, with partial-progress reporting and
shared scoped exports. It enables no construction supplies, ship purchases or
inter-system travel. See OPERATIONS for bounds and visibility limitations.

The owner-requested delivery is the current task boundary. The preceding turn
ended at a verified checkpoint; no token exhaustion or external blocker was
established, so the full-budget unattended requirement remains unmet.

### September 10 Unsupervised Continuation

The owner explicitly requested continued unsupervised engineering. This continuation
started from the existing uncommitted tree on `aron/fos-63-review` (HEAD `c6be829`),
independently verified **1,449 passed, 10 skipped**, and added **94 regression and
diagnostic cases**. Prior work was preserved rather than reconstructed.

- Procurement now shares strict contract identity/status admission. Duplicate
  IDs, including conflicting same-ID observations, cannot select a first result
  and authorize acquisition. Multi-good malformed evidence yields recovery stops.
- Multi-good abandonment inspects both original and latest per-good progress;
  empty current cargo cannot erase saved acquisition/delivery evidence.
- Remote acquisition rechecks contracts, ship cargo/fuel/navigation, destination
  observer, pending actions, positions and credits after quote reads. Goods/fuel
  quotes must be unique with positive integer prices and volume. Transport waits
  honor quote expiry, acceptance expiry and the delivery-planning margin.
- Remote recovery rejects contradictory fulfillment/quantities, discards contract
  evidence from before arrival polling, and refreshes obligations after navigation
  and docking. Delivery/fulfillment waits honor the actual contract deadline.
  Closed, unrecognized or mismatched remote intents cannot regain acquisition
  authority from a later unfulfilled contract observation.
- `auto doctor` and its shared dashboard endpoint join scoped procurement progress
  to recorded ship/contract observations. They show per-good outstanding/held/
  to-acquire/excess quantities, provenance, deadline state and the next step to
  review. Missing evidence stays unknown; these results never authorize dispatch.
- Runner, doctor and dashboard agree that any STOP directory entry requests a
  stop, including a dangling symlink. Dashboard pause uses exclusive creation and
  cannot follow an existing link or change its target. Filesystem control failures
  return an explicit unavailable response while preserving the sentinel.

Full offline checks pass: **1,543 passed, 10 skipped**, Black/Ruff/mypy clean
(180 checked source files). Full explicit synthetic dashboard suite: **73 passed**,
including desktop/mobile recovery display, deadline rendering, scoped-response
races, STOP controls and text-only handling of markup in stored data. Regression
tests reproduced unsafe behavior before fixes; tests never used the game API.

Before the owner's delivery request, no live requests, live-ledger writes, STOP
changes, schema migration, commit or push were performed in this continuation.
The historical live snapshot below remains
the latest recorded game evidence. The open-ended overnight mandate remains in
progress; these results are engineering verification, not a claim of a completed
overnight run or live proof of the new recovery paths.

Next live validation should test one supported original remote intent with a fresh
GET-only preview, then a small action budget and explicit restart after navigation.
Use the authoritative ledger, back it up first, inspect pending/exposure and STOP,
and retain the 50,000-credit floor plus all obligations. Example command shape:

```sh
.venv/bin/python -m py_st auto doctor --scope RESET:AGENT
# GET-only preview, with actual identifiers from fresh state:
.venv/bin/python -m py_st auto contract SHIP CONTRACT_ID --source SOURCE --seconds 300 --actions 2
# After reviewing the preview, execute one bounded increment:
.venv/bin/python -m py_st auto contract SHIP CONTRACT_ID --source SOURCE --execute --seconds 300 --actions 2
```

Choose an experiment that validates recovery rather than repeating earnings. Remote
multi-load/multi-good execution and broader fleet scheduling remain next product
opportunities. No automated retry of uncertain outcomes is permitted.

### September 10 Application Increments

- `auto contract` now executes multiple distinct goods at one marketplace when
  the ship is already there. Whole-obligation funding, per-good immutable price
  ceilings, owned-cargo completion, status validation and transport-enforced
  evidence deadlines have synthetic regression proof. See LOCAL_PROCUREMENT.md.
- Local single-good procurement now refuses unrelated nonclosed exposure. Trade,
  fleet and refuel also respect an unaccepted procurement execution intent's
  reserved funds. Remote refill funding includes the recovery command's own
  headroom at the original ceiling; old price ceilings remain unchanged.
- `auto pilot --recover-contracts` explicitly recovers one saved procurement
  intent, sharing the original runner bounds. It does not choose or negotiate
  offers. With `--execute`, it can accept the original unaccepted execution intent.
- `auto abandon-procurement` previews safe local retirement; `--execute` and a
  reviewed reason append an abandoned position without game POST permission.
  Acceptance receipts in the active scope, pending actions, cargo, changed
  identity or competing obligations block closure. Abandoned intents cannot
  silently resume through a different dispatcher path.
- The dashboard shows multi-good recovery quantities and unrecognized positions,
  and displays the correct return destination. Doctor recognizes procurement
  recovery. These are stored observations, never live execution authority.
- Ordinary live CLI commands require an existing compatible WAL ledger and
  recorded agent identity before loading credentials or contacting the API.
  A locked non-recording identity preflight rejects a different reset/agent;
  only explicit `auto observe` permits new live-history initialization. Return
  to the authoritative workspace instead of creating an empty replacement.

STOP remains in place during offline development; old live balances below are
historical. New contract execution/recovery/admission paths have not been tested
live. Before deployment, review their fresh previews and existing pending/exposure
state. Do not downgrade while a new `local-multi` intent is open. The existing
database schema is unchanged; normal version-1 WAL ledgers require no migration.

## September 9 Morning Handoff

**Application development is primary.** The owner clarified this explicitly
during this run, and FOS-63 and AGENTS.md now preserve that direction. Gameplay
is secondary validation, not the goal.

**Unattended execution failed again.** The owner reported that an unnecessary
permission request for `~/git` paused the entire OpenCode workflow overnight.
This was a permission-prompt stall, not demonstrated token exhaustion and not
successful completion of the overnight mandate. The owner requested this status,
a commit and push, then a stop before work. Do not request access to a broad
parent directory when the repository worktree and approved temporary directory
are sufficient. No global permissions or security settings were changed to hide
or bypass the failure.

The clean review worktree was fast-forwarded from `d312606` to `28342c4` on
`aron/fos-63-review`, integrating the daytime contract model. Exact integrated
base: `28342c47d630f854ee989c453198039ed36997a2`. Application changes are delivered
with this handoff on the review branch; identify the delivery revision with
`git log -1 --format=%H`. `master` and the retained original implementation
history remain unchanged. Only the review branch is authorized for this push.
No detached supervisor or automatic post-exhaustion restart is claimed.

### Product Capabilities Added

- Contract model corrections: source/good capacity shared across obligations,
  per-load purchase batching, acceptance expiry, fulfilled-contract rejection,
  and validated finite margins/reserves. Duplicate/conflicting quotes fail closed.
- `auto sources`: offline, scoped source discovery with original detailed-price
  timestamps, stale/historical visibility labels, and no execution authorization.
- `auto mining`: GET-only, spec-limited diagnostics. Unknown or incomplete
  evidence stays unknown; it does not reproduce the owner's original failure.
- Funded local refueling in earning selection, after ready routes. Execution
  protects the goods budget and costed fuel in addition to the floor/allowance,
  rechecks after docking, and rejects impossible full-tank routes before spending.
- Definitively rejected, freshly created, unpurchased trade intents are retired
  so the next invocation can replan. Resumed/unknown/STOP-interrupted intents
  remain protected; no uncertain action is cleared automatically.
- Opt-in `auto earn --reposition`: costed return to a completed trade's original
  source, persisted recovery and observer protection. Fresh purchase checks are
  still mandatory after arrival. New position guards cover other automation
  entry points. Evidence expiry also bounds transport pacing/retry waits.
  Funded buyer refueling can enable a return without relaxing physical reserves.
  The final review fix rechecks contracts and the observer after preparation,
  before spending. Expired, provably undispatched intents can be safely retired;
  uncertain navigation remains protected.
- `auto pilot`: foreground repeated earning decisions sharing one Session,
  lock, deadline and action budget. UUID-scoped run history records outcomes and
  restart instructions. A restart creates new budgets, not replayed decisions.
- Flight Ledger Contract Desk: real scoped source discovery, structured route
  and cost inputs, advanced JSON editing, and the shared pure procurement model.
  Explicit fuel/time assumptions are required. Recorded pilot runs are visible;
  a stored RUNNING record is not proof of a live process. No GUI execution
  launcher was added. Failed scope switches clear old agent data immediately.
- Market Desk shows cached price details and bounded historical trends with
  original provenance and normalized plotting times. Contract Desk drafts bind
  to the exact contract observation used by the source shortlist.
- `auto doctor` and dashboard recorded-safety checks explain STOP, all pending
  actions, recovery exposure, accepted contracts and stale observations offline.
  No recorded concerns is not live readiness. Reconciliation now uses an exact
  scoped lookup, including pending actions outside the recent 200-row report.

### Verification and Data Compatibility

Final fresh Python 3.12 installation from `.[dev,browser]`: **1,021 passed,
10 skipped**; Black, Ruff and mypy pass. The skipped tests are opt-in live
integration and synthetic browser verification.
Explicit synthetic Chrome dashboard suite: **70 passed**, including desktop
1440px/mobile 390px, structured model entry, stale responses and scope-switch
failure/retry, with no JavaScript errors or horizontal overflow.

Read-only browser verification against the preserved real ledger also passed:
stored credits/fleet/Market Desk at both widths, no browser writes, STOP unchanged.
Captures use the ignored prefix
`.state/dashboard-product-readonly-bd0dc74331af4f7bbfb0411c0d404eda-`.
These show stored state, not new live observations. A wheel install/CLI/asset
smoke passed during development; the complete final source checks above are
the final-code verification. Original screenshots were not overwritten.

No SQL schema migration is required. New `automation_run` observations and
`reposition:SHIP` positions use the existing scoped store. **Do not downgrade
to older automation while a reposition intent is open**: older code does not
understand that exposure. Recover with current code first. Read-only SQLite
opens do not write ledger records but may create/use WAL/shared-memory sidecars;
do not use `immutable=1` against an active ledger to suppress them.

Preserved backups: `.state/overnight-start-20260909-0015.sqlite3` before live
validation and `.state/product-validation-20260909-0119.sqlite3` afterward.
The latter backup passed integrity checking with 160 succeeded actions.
Earlier backups remain. Original `.state/intelligence.sqlite3` remains authoritative.
STOP is present for application development. No gameplay process remains running.

### Bounded Live Evidence (Not the Product Goal)

The existing agent was verified without registration. Last live observation:
**2026-09-09 01:18:37 UTC**, scope `2026-09-06:SOURCE_CODE`, **690,264 credits**,
no pending actions or open positions, and 160 journal actions. Both ships are
at C45; hauler docked with **253/400 fuel and empty cargo**, probe in orbit and
fuel-free. All four contracts are fulfilled. No API requests have been needed
for the subsequent offline product work.

New cash since the 496,772-credit starting snapshot: **+193,492**, reconciled
with zero unexplained change. Supporting receipts, counting fuel only once:

| Validation | Cash Before Shared Fuel Costs |
| --- | ---: |
| 23 ELECTRONICS contract: 118,864 rewards minus 36,770 goods | +82,094 |
| One funded-refuel earn trade: 133,640 sales minus 77,480 goods | +56,160 |
| 5 SHIP_PARTS contract: 71,385 rewards minus 15,715 goods | +55,670 |
| All new fuel purchases | -432 |
| Total | **+193,492** |

The one-cycle `auto earn` trial selected a low-fuel route, refueled, purchased,
arrived and sold successfully under a 600-second/15-action bound. That is live
proof of funded earning, **not** live proof of the later `--reposition` or
`auto pilot` additions. Those have synthetic recovery/real-transport regression
proof only. The fourth contract repeated an existing workflow and is not a new
capability; the owner redirected the run back to application development.

### Resume Deliberately

From the review worktree with its Python environment selected:

```sh
PYTHONPATH=src ST_LIVE_TESTS=0 make ci
PYTHONPATH=src ST_LIVE_TESTS=0 DASHBOARD_BROWSER_TESTS=1 python -m pytest tests/test_dashboard.py -q
PYTHONPATH=src python -m py_st auto pilot --help
PYTHONPATH=src python -m py_st auto sources --help
PYTHONPATH=src python -m py_st auto doctor --scope 2026-09-06:SOURCE_CODE
PYTHONPATH=src python -m py_st auto dashboard
```

Read OPERATIONS for offline planning versus GET-only live previews. Before any
deferred live test, preserve the ledger, deliberately clear STOP, reobserve the
existing agent and resolve pending/open exposure. A bounded future runner preview
is `auto pilot X1-CY22 --steps 2 --seconds 300 --actions 8 --reposition`; it calls
the game even without `--execute`. Only execute after a useful product-validation
question and a freshly reviewed plan exist. Do not resume manual profit loops
as a substitute for completing the application.

Remaining priorities: bounded live validation of pilot/repositioning (not yet
proved live), fuller multi-good/multi-load execution, broader fleet scheduling,
and guarded user execution controls. Preserve the current recovery-aware code
and ledger; do not launch a runner just because STOP was cleared. Before another
unattended run, verify permission handling in the actual workspace so a needless
access prompt cannot silently suspend the workflow again.

## Earlier September 8 Snapshot

This file describes the last recorded state, not a fresh morning observation.
See [ASTRA_LOG.md](ASTRA_LOG.md) for dated implementation and live evidence.
Start with [REVIEW.md](REVIEW.md) for remote review and fresh-clone setup.

The assistant stopped at a checkpoint despite the instruction to continue
overnight. No token exhaustion or external blocker was established. This is a
partial engineering result, not fulfillment of that unattended-run requirement.

### 2026-09-08 Daytime Offline Increment

The cloud/daytime continuation started from review tip `d312606` and made no
SpaceTraders gameplay requests, token reads, registrations, or live-ledger
copies. Implementation commit `c0fab42` adds a pure multi-obligation procurement
model and `auto contract-model INPUT.json`. It accepts explicit synthetic or
operator-exported contract/route snapshots, costs every good across source
capacity, purchase batches and cargo trips, applies price/fuel/reserve/deadline
guards, and always emits `execution_authorized: false`. It does **not** expand
the existing live single-good executor or mutation allowlist.

Fresh Python 3.12 offline CI after this increment: **494 passed, 1 skipped**;
Black, Ruff `--no-fix`, and mypy pass across 154 source files. No schema change
or migration is included. Read [Offline Contract Planning](CONTRACT_PLANNING.md)
for the input format, limitations, official API findings, and a bounded sequence
for converting the model into a journaled nighttime workflow. The eventual
daytime branch tip is the latest descendant of `c0fab42`; inspect it rather than
resetting or overwriting the original worktree.

- Review branch: `aron/fos-63-review`, prepared for the owner's authorized push.
- Original local history: `aron/fos-63-run-gpt-6-astra-overnight-on-py-st`.
  Historical SHAs in the logs refer to that retained local branch, not the
  squashed review branch. Its earlier machine-specific path is not published.
- Worktree: `tmp/astra` relative to the original repository. Master remains at
  `e5d6c2f`. Cleanup does not run gameplay or publish runtime data.
- Last fresh fleet/account observation: **2026-09-08 03:34:08 UTC**.
- Credits: **496,772**, up **321,772** from 175,000, with **zero unexplained
  cash changes**. These are in-game credits, not real money.
- Both contracts fulfilled; no pending journal actions or open positions.
- **124 succeeded mutations**. No registration, ship purchase, scrap, jettison,
  DRIFT, jump or warp was performed. No paid services or system security changes.
- Both ships are at **X1-CY22-C45**. SOURCE_CODE-1 is DOCKED, CRUISE, fuel
  **400/400**, cargo **0/40**. SOURCE_CODE-2 is IN_ORBIT, CRUISE, fuel-free,
  empty cargo.
- **STOP is present in the original local worktree**, not in fresh checkouts.
  No background gameplay controller or dashboard server was left running.
  Read this snapshot before deliberately clearing STOP.

## Exact Contract Accounting

The first contract's ore was **delivered, not sold**. Journal actions 8 and 10
delivered 40 and 17 ALUMINUM_ORE; action 11 fulfilled the 57/57 obligation.
There are zero ALUMINUM_ORE sell actions. Later ALUMINUM trades concern a
different commodity. Both acceptance and fulfillment awards are included below.

| Cash Flow | Credits |
| --- | ---: |
| Original ore contract acceptance, action 5 | +1,678 |
| Original ore contract fulfillment, action 11 | +11,236 |
| 40 ore at 154 and 17 at 156 | -8,812 |
| Original contract before fuel | **+4,102** |
| Restoring refill, action 12 | -72 |
| Original contract with restored fuel | **+4,030** |

After fulfillment we negotiated another offer, action 109. The delivery market
C45 charged 6,664 per EQUIPMENT, making local procurement unprofitable. A probe
found the exporter E52 selling for 2,076. Remote procurement was implemented,
tested and committed before acceptance; subsequent batch prices were rechecked.

| Second Contract: `cmts1w1oni5liuo6x08fsx690` | Credits |
| --- | ---: |
| Acceptance award | +39,972 |
| Fulfillment award | +113,766 |
| 20 EQUIPMENT at 2,076 | -41,520 |
| 6 EQUIPMENT at 2,195 | -13,170 |
| Full restoring refill | -216 |
| Net gain, including approach/delivery fuel restoration | **+98,832** |

All 26 EQUIPMENT were delivered to C45 and the contract fulfilled. Fuel consumed
was 63 for approach plus 150 for delivery, 213 total; the tank is restored.
No return to the original location was attempted or counted as completed.

Full run reconciliation, counting fuel exactly once:

```text
First contract: both awards minus ore                +4,102
ALUMINUM trading                                     +8,360
SHIP_PLATING trading                               +108,234
ADVANCED_CIRCUITRY trading                          +103,180
Second contract: both awards minus EQUIPMENT         +99,048
All refueling (936 earlier + 216 second contract)     -1,152
Total cash gain                                    +321,772
175,000 starting credits + 321,772 =                  496,772
```

Ship wear and opportunity cost are not valued as cash profit. Historical replay
results and unaccepted offer estimates are never added to realized earnings.

## Implemented Capabilities

- Shared closing clients, proactive pacing, semantic retries and Retry-After,
  latched authentication failures, pagination, atomic disposable cache writes.
- Shared bounded Session: monotonic deadline, action limit, STOP-aware waits,
  arrival confirmation, Linux single-writer lock and narrow mutation allowlist.
- SQLite reset/agent-scoped observations, price history, write-ahead actions,
  positions, plans, reconciliation, reports, exports and consistent backups.
- Negotiation after fulfillment: dry-run eligibility and one journaled offer
  request, no automatic retries, duplicate-offer or unknown-outcome replay.
- Same-market and remote single-good procurement. Remote support aggregates
  batches into one cargo load, protects original ceilings and destination refill,
  and recovers observed acceptance/acquisition/delivery/fulfillment progress.
- Offline multi-good/multi-load contract portfolio modeling with explicit
  quotes, batches, trips, reserves and deadlines. This is analysis only and is
  not wired to live execution.
- Resumable trading, guarded refueling, existing-fleet hauler/scout selection.
  Every purchase rechecks the buyer as well as the source.
- Bounded local scouting using fuel-free probes, original price freshness,
  sparse-visit cooldowns and observed-state rather than itinerary replay.
- `auto earn`: bounded recovery-first controller choosing ready trading routes
  or one-market discovery. Tested offline, not yet demonstrated live as a whole.
- Refueling-aware one-way navigation to a freshly verified fuel market with
  protected refill credits and fuel margin; conservative fallback otherwise.
- Offline historical route replay with explicit time/fuel assumptions,
  no-lookahead joins, losses and unresolved exposure, not guaranteed execution.
- Flight Ledger: local browser dashboard for real fleet/map, credits, contracts,
  routes, history, positions, journal, exports and guarded STOP controls.

## Verification

- Current full offline CI after the daytime planner increment: **494 passed,
  1 skipped**; Black, Ruff `--no-fix`, mypy and commit hooks pass.
- Review fixes include fresh buyer checks, completion-first recovery, prohibited
  flight-mode rejection before spending, dispatch-aware interruption records,
  original-position fleet recovery, funded refill headroom and accepted-contract
  restart without incorrectly dropping the already-paid acceptance award.
- Remote procurement was committed as `1bb3a78` before its successful live trial.
  Full CI before/after that trial: 470 passed, 1 skipped. Latest fixes `6615e95`
  are offline-regression proof, not a new live contract trial.
- Live scouting completed two bounded sessions with seven visits and six
  navigations, increasing detailed-price coverage from 5 to 11 markets. Later
  contract scouting observed C45/E52 and repositioning completed successfully.
- Headless Chrome desktop 1440px/mobile 390px verification passed after the
  seven-visit scout trial, including real ledger data, STOP controls, no horizontal
  overflow or JavaScript errors. Screenshots predate the second contract balance.
- Earlier evidence: explicit read-only live pytest passed; wheel import/assets
  and CLI packaging passed; upstream/vendored OpenAPI 2.3.0 both had 55 paths.
  Those checks were not rerun against every later commit. Path equality does not
  establish full model/schema equality.
- Latest backup `.state/remote-contract-124-1bb3a78.sqlite3`: integrity `ok`,
  124 succeeded actions and matching cash reconciliation.

## Usage and Data

From the isolated worktree:

```sh
export PATH="$PWD/../../.venv/bin:$PATH"
export PYTHONPATH=src
ST_LIVE_TESTS=0 make ci
python -m py_st auto report --scope 2026-09-06:SOURCE_CODE
python -m py_st auto dashboard --port 8765
```

Open **http://127.0.0.1:8765**. Refresh ledger reloads SQLite, not the live game.
Pause creates STOP; clear stop removes it without launching a process. Browser
tests run headless with explicit viewport dimensions and do not need the monitor.

The original Python 3.12 `.venv` is shared; Playwright was installed locally.
Its editable installation was not repointed away from master, so use the working
directory and `PYTHONPATH` shown above. Credentials stay in the owner's ignored
ancestor `.env`; do not print, pass in arguments, or commit them.

`.state/intelligence.sqlite3` is the durable ledger, not a disposable cache.
Backups and screenshots are ignored by Git; preserve them before deleting the
worktree. All earlier uniquely named backups remain. `.cache/data.json` is
disposable. Use `auto backup NEW_PATH` instead of copying active WAL files.

Owner guides:

- [Operations](OPERATIONS.md): commands, safety and recovery.
- [Architecture](ARCHITECTURE.md): components and design decisions.
- [Mining and Contracts](MINING_CONTRACTS.md): actual ship capabilities, prices,
  contract receipts and supported procurement workflow.
- [Fuel and Navigation](FUEL_NAVIGATION.md): verified refueling, flight modes,
  explicit formula assumptions and limitations.
- [Historical Routes](HISTORICAL_ROUTES.md): offline replay interpretation.
- [Offline Contract Planning](CONTRACT_PLANNING.md): multi-obligation fixture
  model, official API constraints, and nighttime implementation checklist.
- [Exploration](EXPLORATION.md): combat status, gate construction and future travel.

## Remaining Work and Resume

No external dependency currently blocks further engineering. Useful next work:

1. Reobserve at C45, negotiate the next offer if eligible, and compare supported
   procurement with trading. Do not replay old routes or price estimates.
2. Improve earn-controller repositioning and test it live after review; it currently
   trades ready routes or scouts, not arbitrary historical-route repositioning.
3. Use `auto contract-model` to inspect a complete fresh obligation portfolio,
   then expand live procurement only after adding persisted portfolio recovery
   and interruption tests. The offline model does not silently relax limits.
4. Investigate mining economically. The command ship has Mining Laser II and
   Surveyor II; its earlier station/docked state was not extractable. XC5Z is
   STRIPPED, but no extraction experiment has established the earlier error.
5. Home-system trading first, then costed gate construction and controlled wider
   exploration. Combat is planned in official docs with no current attack endpoint.
   Other players already affect markets; player awareness is not combat.

On 401/4113, stop live work and have the owner verify reset/token configuration.
Never register automatically. Unknown dispatched mutations stay pending and must
be reconciled with fresh evidence, not replayed. Pre-dispatch interruptions and
definitive rejection waits have separate known-outcome statuses. One-way funding
is not escrow: missing fuel or adverse prices beyond the plan can still block
recovery. No cross-system/destructive actions are enabled in current automation.

Continuation prompt:

> Continue FOS-63 on the review branch, using tmp/astra on the original machine
> or a fresh checkout elsewhere. Read AGENTS.md,
> this handoff, ASTRA_LOG and owner guides. Inspect git status, run offline CI,
> preserve the durable ledger/backups and clear STOP deliberately only when ready
> for reviewed live work under the ticket's existing authorization. Observe before
> mutations, keep 50,000 credits plus all known fuel/contract obligations, bound
> every session, and stop on 401/4113 or uncertain outcomes. Continue beyond each
> milestone for the available budget. Negotiate/evaluate further contracts and
> improve home-system trading/mining based on actual economics. Keep local coherent
> commits and owner docs. Push only with owner authorization. No package
> publication, paid charges, system security
> changes or automatic registration. Existing jump/warp/destructive guards remain
> until the ticket's requirements for a tested needed experiment are satisfied.
