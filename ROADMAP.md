# Roadmap

The goal remains: make the CLI feel *alive*—fast, readable, forgiving—and keep the backend clean and unified.

---

## Bugs

### High Priority

### Low Priority

* Drop unused `traits` filter in `SystemsEndpoint.list_waypoints_all`.
* Correct help text for contract-id arguments to mention all relevant commands and shortcut syntax.
* Add `--force-update` or some similar flag to `systems waypoints` to force a cache refresh. Do other command line commands need this?

---

## Owner-Managed Authentication Recovery

The older automatic-registration proposal is superseded by FOS-63 safety rules.
On HTTP 401 or reset mismatch 4113, stop live automation and report the recovery
step. The owner verifies the reset and updates ignored token configuration;
registration, if required, is an explicit owner action. Never put tokens in
command arguments, silently register, or replay a mutation after re-registration.

---

## Planned: Home System to Wider Exploration

Owner direction: flesh out home-system trading, understand combat if implemented,
then repair/complete the jumpgate and visit other systems, possibly meeting other
players. See [Exploration Plan](docs/EXPLORATION.md) for prerequisites, evidence
URLs checked 2026-09-08 UTC, validation gaps and phase exit criteria.

1. Establish repeatable local trading, fresh scouting and costed procurement.
2. Assess combat availability, gate connections/material deficits and ship
   capabilities read-only. Official combat remains future work; multiplayer
   economic competition and player visibility are distinct existing capabilities.
3. Complete gate construction only if needed and economically justified, using
   fresh per-material requirements and tested, bounded, authorized supply actions.
4. Test a single costed cross-system route with a return/refuel plan before wider
   discovery. Preserve the FOS-63 live jump/warp guard until behavior is tested,
   travel is needed, and ticket authorization resolves the explicit run ban.
5. Expand discovery and player awareness after travel proof; do not implement
   speculative combat or treat a ship scan as a read-only GET.

This plan enables no live actions and changes no safety guard or allowlist.

---

## Sprint 5: Ergonomics & Cache Refactor

### Core Work
* **Formatting & UX polish**

  * Standardize column widths in CLI tables (programmatic alignment).
  * Keep relative time, short money, and id6 conventions consistent across modules.
* **Systems/Markets improvements**

  * Continue reusing cached waypoints and markets.
  * Optimize system-wide market queries for faster filters.

### Cleanup & Refactors

* Split `services/ships.py` into `services/ships/navigation.py`, `services/ships/cargo.py`, etc., to reduce file size.
* Centralize resolver logic (`resolve_ship_id`, `resolve_waypoint_id`, `resolve_contract_id`) in one helper file.
* Improve CLI error messages for missing cache data or invalid indexes.

---

## 🔭 Long-Term Goals

* **Additional Functions**
  * Install Module, Install Mount, Siphon Resources, Register New Agent, Get Agent Events

* **Automation Loop**

  * Extend the implemented bounded workflows with tested repositioning and
    multi-load/multi-good obligations; prove unattended continuation separately.
* **Client generation**

  * Investigate `openapi-python-client` or a custom generator for `SpaceTraders.json`.
* **Persistent registration**

  * Improve owner-managed credential recovery without automatic agent creation.
* **Async & rate limiting**

  * Rework request layer for concurrency and adaptive throttling.
* **GUI**

  * Extend the existing local Flight Ledger dashboard over shared services.
  * Add tested controls beyond STOP without exposing tokens or bypassing guards.
* **Trait name abbreviation**

  * Consider abbreviating long trait names in `systems waypoints` output for more compact display.

---

## ✅ Completed

* FOS-63 local branch: semantic retries, shared sessions, pagination, atomic
  cache, bounded journaled procurement/trading, SQLite history and cash audit,
  fleet assignment, bounded same-system fuel-free probe market scouting, and a
  working local dashboard. Scouting has seven live verified visits. A bounded
  `auto earn SYSTEM` controller connects ready-route trading and discovery with
  offline regression proof only; historical-route repositioning remains deferred.
  See `docs/HANDOFF.md` for verification, measured economics, safety limits
  and remaining work. Remote single-good/single-load procurement now has live
  proof; multi-load/multi-good procurement, extraction optimization and
  cross-system discovery remain opportunities, not completed features.

* **Agent Register Command**: Added `py-st agent register` CLI command to create a new agent using an account token. Supports CLI flags `--account-token`, `--symbol`, `--faction`, and `--clear-cache`. Sends POST to `/v2/register`, saves the returned agent token to `.env` (ST_TOKEN), and prints a success summary. Non-interactive implementation with clean error handling.
* **CLI Table Alignment**: Fixed column alignment in `contracts list` and `systems waypoints` to handle mixed-digit indexes correctly. Contract columns (IDX, ID6, T, A/F, DUE(REL), DELIVER) now align properly when indexes expand from single to double digits. Waypoint indexes are right-aligned within brackets with fixed-width type fields ensuring "Traits:" column aligns vertically across all rows. Added comprehensive alignment tests.
* **Document and Normalize Cache Schema**: Created `cache/SCHEMA.md` documenting all cache entry types (agent, ships, contracts, waypoints, markets, shipyards) with JSON structures, refresh policies, and invalidation triggers. Added `src/py_st/services/cache_keys.py` with helper functions for consistent cache key generation. Refactored all services to use centralized key helpers. Added comprehensive tests including drift check to prevent documentation-code divergence.
* **Transfer Cargo Command**: Added `ships transfer-cargo` CLI command supporting ship index shortcuts (`s-0`, `s-1`) or full symbols. Includes client endpoint, service wrapper with cache invalidation, validation for same-ship and positive units, and comprehensive tests.
* **Smart Merge Refactor**: Extracted and unified duplicate cache merge logic from `get_market` and `get_shipyard` into reusable `smart_merge_cache()` helper in `src/py_st/services/cache_merge.py`. Added comprehensive tests in `tests/test_cache_merge.py`.
* CLI Enum conversion across all modules.
* Market cache and `systems markets` improvements.
* Compact `contracts list` display with relative due, payments, faction, and waypoint index.
* Ships and contracts cache refactor to "dirty" pattern.
* Waypoint indexing and pretty-print display.
* Initial cache implementation and testing harness.
* Infrastructure: added `make clear-cache` target.
* Market cache returns incomplete data
* Ship cache in-transit logic
