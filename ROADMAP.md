# Roadmap

The immediate goal is to improve the "playability" of the CLI by implementing a comprehensive cache. This will reduce the need to copy-paste IDs, remember waypoint symbols, and manually look up market data.

---

## ✅ Done

* **Write Unit Tests for `ships.py`:**
    * ✅ Added test file `tests/test_services_ships.py` with comprehensive unit tests.
    * ✅ Added factories for `Extraction`, `Survey`, `MarketTransaction`, `ShipyardTransaction`, and `RefineResult` to `tests/factories.py`.
    * ✅ All 15 test cases pass, covering all public functions in `services/ships.py`.

* **Implement `ships` Caching:**
    * ✅ Added time-based caching to `services/ships.py` for `list_ships`.
    * ✅ Added unit tests to `tests/test_services_ships.py` for cache-hit, cache-miss (stale), and cache-miss (not found) scenarios.

* **Connect Cache to CLI Arguments:**
    * ✅ Modify `ships` commands to accept a 0-based index (e.g., `0`) in addition to the full ship symbol.
        * ✅ Implemented `cli/_helpers.py` with `resolve_ship_id` and updated all commands in `ships_cmd.py`.

---

## 🚀 Playability & CLI Enhancements

The top priority is making the CLI "smart" by leveraging cached data.

* **Waypoint Index Lookup:**
    * Implement a similar system for waypoints (`--wp 1`, `--wp 2`) once a good way to "list" and index waypoints is established.

* **Add CLI Commands to Query Cache:**
    * Create new CLI commands to quickly query the cached data, addressing the "which market bought iron?" problem. Examples:
        * `py-st systems markets --buys IRON_ORE`
        * `py-st systems markets --sells FUEL`
        * `py-st ships list` (should now be fast, reading from cache)

* **Improve CLI Argument Ergonomics:**
    * Update CLI commands to use `Enum` types for arguments where possible (e.g., `ShipNavFlightMode` for the `ships flight-mode` command) so `typer` can provide automatic validation and help.

---

## 🗃️ Caching & Service Layer

This is the core implementation work required for the playability features.

* **Refactor "Smart Merge" Caching Logic:**
    * The `get_market` and `get_shipyard` functions in `services/systems.py` share nearly identical "smart merge" caching logic.
    * Refactor this duplicated code into a single, generic helper function to keep the services module clean.

* **Update `list_system_goods`:**
    * Modify `list_system_goods` to use the cached `get_market` function. This will make it much faster as it will no longer make N-1 API calls.

* **Implement `contracts` Caching:**
    * Implement caching for `services/contracts.py` (e.g., for `list_contracts`).

* **Add Cache Clearing Mechanism:**
    * Add a command to the `Makefile` (e.g., `make clear-cache`) to delete the `.cache/data.json` file. This is needed to manually invalidate the cache after a weekly server reset.

---

## 🧪 Testing & Correctness

This is a high-priority background task to ensure the project remains stable and "un-sloppy."

* **Write Unit Tests for `contracts.py`:**
    * Add a new test file (`tests/test_services_contracts.py`).
    * Write tests for all public functions in `services/contracts.py`, mocking the `SpaceTradersClient`.
    * This should be done *before or during* the implementation of caching for this module.

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
