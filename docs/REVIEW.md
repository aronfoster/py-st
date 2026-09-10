# FOS-63 Review Guide

## Scope and Delivery

Review branch: `aron/fos-63-review`, based on `e5d6c2f`. It contains the final
implementation as a squashed change plus review cleanup. The 28 original local
commits remain on `aron/fos-63-run-gpt-6-astra-overnight-on-py-st`; they are not
being pushed because an earlier log version included a machine-specific path.
Commit SHAs in historical evidence refer to that local history.

The September 9 continuation integrated `28342c4` and added the product tools
below. The unattended requirement was not met: the owner reported that an
unnecessary parent-directory permission request froze OpenCode overnight.
The owner requested status, commit and push, then a stop. This is not a claim
of token exhaustion or a working automatic restart supervisor. Read the current
morning section in HANDOFF; later sections preserve historical evidence.

## Start Here

The [README](../README.md#review-without-game-credentials) describes a fresh Linux
checkout, Python 3.12 environment, development installation and offline checks.
No game token is needed to run the tests or open the dashboard. A fresh dashboard
is empty because the local runtime ledger is intentionally excluded from Git.
Do not copy live credentials or journal databases into a PR or repository.

| Review Area | Implementation | Focused Tests |
| --- | --- | --- |
| Transport and cache reliability | `client/transport.py`, `client/client.py`, `cache.py` | `test_reliability.py` |
| Mutation bounds and recovery | `services/automation.py` | `test_automation.py`, `test_fuel_navigation.py` |
| Trading and procurement | `services/strategies.py`, `services/remote_procurement.py` | `test_strategies.py`, `test_remote_procurement.py` |
| Multi-good execution and intent retirement | `services/local_procurement.py`, `services/procurement_recovery.py`, `services/contract_state.py` | `test_local_procurement.py`, `test_procurement_recovery.py` |
| Offline recovery progress and deadlines | `services/procurement_status.py`, `services/doctor.py` | `test_procurement_status.py`, `test_doctor.py` |
| Shared STOP semantics | `services/stop_control.py`, `services/automation.py`, `services/dashboard.py` | `test_automation.py`, `test_dashboard.py` |
| Offline contract portfolio model | `services/contract_planning.py`, `cli/auto_cmd.py` | `test_contract_planning.py` |
| Source discovery and restart diagnosis | `services/contract_sources.py`, `services/doctor.py` | `test_contract_sources.py`, `test_doctor.py` |
| Recorded market history and mining diagnostics | `services/market_history.py`, `services/mining.py` | `test_market_history.py`, `test_mining.py` |
| New contract offers | `services/negotiation.py` | `test_negotiation.py` |
| Discovery and earning decisions | `services/scouting.py`, `services/earning.py` | `test_scouting.py`, `test_earning.py` |
| Foreground runner and return recovery | `services/pilot.py`, `services/repositioning.py` | `test_pilot.py`, `test_repositioning.py` |
| Historical intelligence | `services/intelligence.py`, `services/route_history.py` | `test_route_history.py`, `test_automation.py` |
| Local web interface | `services/dashboard.py`, `services/dashboard.html` | `test_dashboard.py`, `tools/check_dashboard.py` |

Implementation paths are relative to `src/py_st`; tests are under `tests`.
CLI adapters live in `src/py_st/cli/auto_cmd.py`. Full architecture and operational
guides are linked from [HANDOFF.md](HANDOFF.md#usage-and-data).

## Evidence Versus Limitations

September 10 continuation in the consolidated checkout: current full offline CI
is **1,543 passed, 10 skipped**, Black/Ruff/mypy clean. The full explicit synthetic
dashboard suite passed **73 tests**. This includes further procurement identity,
quote/eligibility/expiry, completion recovery and STOP regressions. The changes
are included in the owner-requested delivery on `aron/fos-63-review`, based on
`c6be829`; see HANDOFF and FOS-63 for the published revision and continuation
details. No new gameplay evidence or schema migration is
claimed. The September 9 delivery evidence below remains historical.

- Final clean Python 3.12 installation: **1,021 passed, 10 skipped**, with Black,
  Ruff and mypy passing. Explicit synthetic Chrome dashboard suite: **70 passed**.
  The skipped tests are opt-in browser/live checks. Read-only real-ledger browser
  smoke also passed with STOP unchanged; it is not fresh gameplay evidence.
- Recorded live result at **2026-09-08 03:34:08 UTC**: **496,772 credits**, up
  **321,772** from 175,000. Two contracts fulfilled, all cargo empty, hauler full
  fuel, 124 successful journal actions and zero unexplained cash changes.
- Those balances are historical receipts, not a fresh morning API check. Both
  acceptance and fulfillment awards are included; [HANDOFF.md](HANDOFF.md)
  gives exact arithmetic and separates the two contracts from trading.
- Trading, negotiation, remote procurement and local scouting have bounded live
  evidence. One bounded funded-refuel `auto earn` cycle was proved live on
  September 9. Later pilot and opt-in original-source return support have offline
  regression proof only. Fuel-ready routes take priority, then funded local
  refueling, optional costed return, and fuel-free discovery.
  Fresh trade terms, fuel and credits are checked before refueling, again after
  docking, and before goods acquisition as applicable. Full-tank range is checked
  before fuel spending; funding protects the 50,000 floor, 1,000 allowance,
  route fuel, maximum goods cost and maximum estimated refill cost together.
- Mining is exposed by the client, but no live extraction experiment proved the
  earlier owner-reported failure. Combat is not a currently documented callable
  operation. Gate construction and inter-system travel are roadmap work.
- Remote execution remains single-good/single-load. A new offline model covers
  multi-good/multi-load portfolios but does not authorize or orchestrate live
  actions. It shares source/good availability across terms and destinations,
  rejects inconsistent ceilings and duplicate route quotes, and counts purchase
  batches per cargo load. It rejects fulfilled contracts, marks expired unaccepted
  offers infeasible (`deadlineToAccept`, legacy `expiration` when absent), and validates
  reserves and finite margins. Input-order greedy allocation can exhaust scarce
  supply and falsely report infeasibility; it is not globally optimal. No global
  route optimizer, automatic ship purchasing, cross-system controller or
  fleet-wide concurrent execution is claimed.
- Quote freshness and credit margins do not guarantee future liquidity. One-way
  refueling is not escrow; extreme price changes or unavailable fuel can require
  intervention. Exact fuel formulas remain explicit assumptions where undocumented.
  Manual away-source trade dry runs explicitly leave approach/refill before
  reaching the source unmodeled; they do not prove a funded approach. Local refill
  funding is also not a guarantee of all-in realized trade profit.
- Unknown dispatched mutations block execution until evidence-based review;
  this is not exactly-once delivery. Linux file locking is local to this machine
  and does not coordinate other computers or manual gameplay.
  Refills are journaled before the trade position is persisted. A confirmed
  refill interrupted before position creation is recovered by fresh observation
  and replanning; an unknown refill stays pending, never blindly replayed or
  treated as permission to scout. Trade intent persists before buying goods.
- The dashboard provides shared Contract Desk modeling, Market Desk history,
  recorded run status and offline safety diagnosis. Its only gameplay-related
  control is STOP; it never loads tokens or launches a live process. Clearing
  STOP never starts automation. An in-flight HTTP request may finish after STOP.
- The latest preserved live state is the September 9 01:18:37 UTC snapshot:
  690,264 credits, four fulfilled contracts, empty cargo and no pending/open
  exposure. The hauler has 253/400 fuel, not a restored tank. Both ships are at
  C45. This is historical state; fresh observations are required before mutation.
- New observation/position kinds use schema v1 without migration. Do not run
  older automation while a reposition intent is open. Freshly abandoned intents
  require proof of no possible navigation dispatch; unknown outcomes are never
  automatically cleared. Pilot restarts create new budgets and fresh decisions.

## Preserved Local Data

The original worktree retains its STOP sentinel, ignored `.env` discovery,
`.state/intelligence.sqlite3`, consistent backups and browser screenshots.
None are included in this branch. Keep the worktree until those artifacts are
retained separately; the latest backup is listed in HANDOFF.md. No live API call
or gameplay action is needed for code review.
