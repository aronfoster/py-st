# Roadmap

The goal remains: make the CLI feel *alive*—fast, readable, forgiving—and keep the backend clean and unified.

---

## Bugs

### High Priority

### Low Priority

* Implement pagination in `get_ships` and `get_contracts`.
* Drop unused `traits` filter in `SystemsEndpoint.list_waypoints_all`.
* Correct help text for contract-id arguments to mention all relevant commands and shortcut syntax.
* Add `--force-update` or some similar flag to `systems waypoints` to force a cache refresh. Do other command line commands need this?

---

## Planned: Agent Bootstrap & Auto-Register Flow

### Automatic Register on 401 (interactive)
Enhance the HTTP transport to handle 401 Unauthorized from endpoints.

If running in an interactive TTY and SPACETRADERS_ACCOUNT_TOKEN exists:

Prompt user to register a new agent immediately.

Ask for confirmation once.

Reuse registration logic, retry the failed request once on success.

Non-interactive or missing account token → show guidance:
"Authentication failed. Run: py-st agent register --account-token <TOKEN>"

Prevent infinite retries.

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

  * Build the first playable ship automation script:
    contract → navigate → refuel → buy → deliver → complete.
* **Client generation**

  * Investigate `openapi-python-client` or a custom generator for `SpaceTraders.json`.
* **Persistent registration**

  * Migrate from agent tokens to account-based registration with auto-create on missing agent.
* **Async & rate limiting**

  * Rework request layer for concurrency and adaptive throttling.
* **GUI**

  * Research frameworks (PySide6, Tkinter, etc.).
  * Prototype a live UI for universe/fleet visualization and simple command triggers.
  * Run GUI in its own thread, independent of automation logic.
* **Trait name abbreviation**

  * Consider abbreviating long trait names in `systems waypoints` output for more compact display.

---

## ✅ Completed

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
