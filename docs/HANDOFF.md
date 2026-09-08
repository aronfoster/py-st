# FOS-63 Handoff

## Current Snapshot

This file describes the last recorded state, not a fresh morning observation.
See [ASTRA_LOG.md](ASTRA_LOG.md) for dated implementation and live evidence.
Start with [REVIEW.md](REVIEW.md) for remote review and fresh-clone setup.

The assistant stopped at a checkpoint despite the instruction to continue
overnight. No token exhaustion or external blocker was established. This is a
partial engineering result, not fulfillment of that unattended-run requirement.

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

- Current full offline CI after independent safety review fixes: **487 passed,
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
- [Exploration](EXPLORATION.md): combat status, gate construction and future travel.

## Remaining Work and Resume

No external dependency currently blocks further engineering. Useful next work:

1. Reobserve at C45, negotiate the next offer if eligible, and compare supported
   procurement with trading. Do not replay old routes or price estimates.
2. Improve earn-controller repositioning and test it live after review; it currently
   trades ready routes or scouts, not arbitrary historical-route repositioning.
3. Expand remote procurement beyond single-good/single-load only after modeling
   all obligations and tested fuel/recovery; do not silently relax those limits.
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
