# FOS-63 Review Guide

## Scope and Delivery

Review branch: `aron/fos-63-review`, based on `e5d6c2f`. It contains the final
implementation as a squashed change plus review cleanup. The 28 original local
commits remain on `aron/fos-63-run-gpt-6-astra-overnight-on-py-st`; they are not
being pushed because an earlier log version included a machine-specific path.
Commit SHAs in historical evidence refer to that local history.

The assistant stopped at checkpoints rather than continuing through the requested
overnight budget. That requirement was not met. There is no background agent or
automatic restart supervisor, and no claim of token exhaustion. The morning
request is to make the existing work reviewable, not resume gameplay.

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
| Offline contract portfolio model | `services/contract_planning.py`, `cli/auto_cmd.py` | `test_contract_planning.py` |
| New contract offers | `services/negotiation.py` | `test_negotiation.py` |
| Discovery and earning decisions | `services/scouting.py`, `services/earning.py` | `test_scouting.py`, `test_earning.py` |
| Historical intelligence | `services/intelligence.py`, `services/route_history.py` | `test_route_history.py`, `test_automation.py` |
| Local web interface | `services/dashboard.py`, `services/dashboard.html` | `test_dashboard.py`, `tools/check_dashboard.py` |

Implementation paths are relative to `src/py_st`; tests are under `tests`.
CLI adapters live in `src/py_st/cli/auto_cmd.py`. Full architecture and operational
guides are linked from [HANDOFF.md](HANDOFF.md#usage-and-data).

## Evidence Versus Limitations

- Daytime checks in a fresh Python 3.12 environment installed from `.[dev]`:
  **494 passed, 1 skipped**, Black/Ruff/mypy clean. Formatter versions now match
  the existing pre-commit hooks. The live test is opt-in and read-only; CI explicitly
  disables it. Normal tests use fake APIs, not gameplay mutations.
- Recorded live result at **2026-09-08 03:34:08 UTC**: **496,772 credits**, up
  **321,772** from 175,000. Two contracts fulfilled, all cargo empty, hauler full
  fuel, 124 successful journal actions and zero unexplained cash changes.
- Those balances are historical receipts, not a fresh morning API check. Both
  acceptance and fulfillment awards are included; [HANDOFF.md](HANDOFF.md)
  gives exact arithmetic and separates the two contracts from trading.
- Trading, negotiation, remote procurement and local scouting have bounded live
  evidence. `auto earn` has offline integration tests, not end-to-end live proof.
- Mining is exposed by the client, but no live extraction experiment proved the
  earlier owner-reported failure. Combat is not a currently documented callable
  operation. Gate construction and inter-system travel are roadmap work.
- Remote execution remains single-good/single-load. A new offline model covers
  multi-good/multi-load portfolios but does not authorize or orchestrate live
  actions. No global route optimizer, automatic ship purchasing, cross-system
  controller or fleet-wide concurrent execution is claimed.
- Quote freshness and credit margins do not guarantee future liquidity. One-way
  refueling is not escrow; extreme price changes or unavailable fuel can require
  intervention. Exact fuel formulas remain explicit assumptions where undocumented.
- Unknown dispatched mutations block execution until evidence-based review;
  this is not exactly-once delivery. Linux file locking is local to this machine
  and does not coordinate other computers or manual gameplay.
- The dashboard reads SQLite and controls STOP only. Clearing STOP never starts
  automation. An in-flight HTTP request may finish after STOP is requested.

## Preserved Local Data

The original worktree retains its STOP sentinel, ignored `.env` discovery,
`.state/intelligence.sqlite3`, consistent backups and browser screenshots.
None are included in this branch. Keep the worktree until those artifacts are
retained separately; the latest backup is listed in HANDOFF.md. No live API call
or gameplay action is needed for code review.
