# Roadmap

The goal remains: make the CLI feel *alive*—fast, readable, forgiving—and keep the backend clean and unified.

---

## Bugs

### High Priority

* **Cache freshness logic**

  * Add `need_clean: bool` to all cache-using functions.
  * All cache entries use a `dirty` flag. Functions that need dynamic fields (e.g., money, fuel, prices) should call with `need_clean=True`.
* **Market cache returns incomplete data** ✅ **FIXED**

  * CLI market/shipyard detail commands now call services with `force_refresh=True` to ensure prices/ships are always shown.
* **Ship cache in-transit logic** ✅ **FIXED**

  * `list_ships()` now auto-refreshes when any cached ship with `IN_TRANSIT` status has `arrival <= now(UTC)` and `need_clean=True`.

### Low Priority

* Implement pagination in `get_ships` and `get_contracts`.
* Drop unused `traits` filter in `SystemsEndpoint.list_waypoints_all`.
* Align pretty-print contract headers and rows dynamically.
* Fix misaligned indexes and parentheses in `systems waypoints`.
* Correct help text for contract-id arguments to mention all relevant commands and shortcut syntax.

---

## Sprint 5: Ergonomics & Cache Refactor

### Core Work

* **Need-clean caching**

  * Introduce `need_clean` parameter across `ships`, `systems`, and `contracts` services.
  * Add central `services/cache/policy.py` with per-type helpers:

    * `ships_requires_fetch`
    * `market_requires_fetch`
    * `shipyard_requires_fetch`
  * `resolve_ship_id` and other resolvers use stale cache (`need_clean=False`) to avoid unnecessary API calls.
  * CLI listing commands use `need_clean=True` to ensure freshness.
* **Smart Merge Refactor**

  * Consolidate duplicate “smart merge” logic from `get_market` and `get_shipyard` into one helper.
* **Document Cache Schema**

  * Add `cache/SCHEMA.md` describing all cache entry types (`ships`, `waypoints`, `contracts`, `agent`, `markets`, `shipyards`).
  * Normalize cache key naming and add helpers (`key_for_ship_list`, `key_for_market`, etc.).
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

---

## ✅ Completed

* CLI Enum conversion across all modules.
* Market cache and `systems markets` improvements.
* Compact `contracts list` display with relative due, payments, faction, and waypoint index.
* Ships and contracts cache refactor to “dirty” pattern.
* Waypoint indexing and pretty-print display.
* Initial cache implementation and testing harness.
* Infrastructure: added `make clear-cache` target.
