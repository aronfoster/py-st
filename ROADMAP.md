# Roadmap

The immediate goal is to improve the "playability" of the CLI by implementing a comprehensive cache. This will reduce the need to copy-paste IDs, remember waypoint symbols, and manually look up market data.

---

## Sprint 2: Waypoint Playability

The goal of this sprint is to replicate the "playability" features from Sprint 1 for **waypoints**. This will allow users to use `wp 0` in commands like `ships navigate`.

* **Improve CLI Argument Ergonomics:**
    * Update CLI commands to use `Enum` types for arguments where possible (e.g., `ShipNavFlightMode` for the `ships flight-mode` command) so `typer` can provide automatic validation and help.

---

## Sprint 3: Contracts & Market Queries

This sprint focuses on adding caching to the `contracts` domain and making market data queryable from the CLI.

* **Write Unit Tests for `contracts.py`:**
    * Add a new test file (`tests/test_services_contracts.py`).
    * Write tests for all public functions in `services/contracts.py`, mocking the `SpaceTradersClient`.

* **Implement `contracts` Caching:**
    * Implement time-based caching for `services/contracts.list_contracts`.
    * Implement "pretty-print" for the `contracts list` command, showing an index.
    * Implement index lookup for contract commands (e.g., `contracts accept 0`).

* **Add CLI Commands to Query Cache:**
    * Create new CLI commands to query cached system data. Examples:
        * `py-st systems markets --buys IRON_ORE`
        * `py-st systems markets --sells FUEL`
        * `py-st systems waypoints --trait SHIPYARD` (This should be fast, as `list_waypoints` is already cached).

---

## 🧹 Refactoring & Tech Debt

These items improve code quality and performance but are not tied to a specific feature sprint.

* **Refactor "Smart Merge" Caching Logic:**
    * The `get_market` and `get_shipyard` functions in `services/systems.py` share nearly identical "smart merge" caching logic.
    * Refactor this duplicated code into a single, generic helper function to keep the services module clean.

* **Update `list_system_goods`:**
    * Modify `list_system_goods` to use the cached `get_market` function. This will make it much faster as it will no longer make N-1 API calls.

---

## 🔭 Long-Term Goals

(These items are carried over from the previous roadmap)

* Develop a script to run a basic ship automation loop.
* Investigate `openapi-python-client` or rolling my own method to turn `SpaceTraders.json` spec automatically into client prototypes.
* Currently using agent tokens, which expire every week. Explore Register by API with an account token, then automatically create a new agent if none exist.
* Improve web requests (rate limiting, async, etc.).
* GUI
    * Research and select a GUI framework (e.g., PySide6, Tkinter).
    * Design a basic UI to display universe/fleet data and trigger actions.
    * Implement the GUI, ensuring it runs in a separate thread from the automation logic.
 
---

## ✅ Done

* **Sprint 2: Waypoint Playability**
    * ✅ **Improve `systems waypoints` command:** `waypoints` now defaults to an indexed "pretty-print" list and uses `--json` for raw output.
    * ✅ **Implement Waypoint Index Lookup:** Added `resolve_waypoint_id` to `cli/_helpers.py` and updated `systems market/shipyard` commands to accept 0-based indexes.

* **Sprint 1: Ships Playability**
    * ✅ **Testing:** Added `tests/test_services_ships.py` with full unit test coverage for `services/ships.py`.
    * ✅ **Caching:** Added time-based caching to `services/ships.list_ships`.
    * ✅ **CLI Indexing:** Implemented `cli/_helpers.py` with `resolve_ship_id` and updated all `ships_cmd.py` commands to accept a 0-based index.
    * ✅ **CLI Listing:** `py-st ships list` now defaults to a "pretty-print" format and retains JSON output via `--json`.

* **Infrastructure:**
    * ✅ Added `make clear-cache` to the `Makefile` to delete `.cache/data.json`.
