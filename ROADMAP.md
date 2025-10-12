# Roadmap

Here is the planned development path for `py-st`.

## Phase 1: Complete the Tutorial and Refactor
- [ ] Expand the CLI with more commands for tutorial actions (`contracts list`, `ships list`, etc.).
- [ ] Add corresponding methods to the `client.py` for each new CLI command.

## Phase 2: Universe Cache and State Management
- [ ] Create a `Universe` class (`src/py_st/universe.py`) to cache game data.
- [ ] Create a `Fleet` class (`src/py_st/fleet.py`) to manage your ships.
- [ ] Refactor the client to be used by the `Universe` and `Fleet` classes.

## Phase 3: Automation Engine
- [ ] Create a `ShipAutomator` class (`src/py_st/automator.py`) with a state machine for ship actions.
- [ ] Develop a script (e.g., `mine_and_sell.py`) to run a ship automation loop.

## Phase 4: GUI
- [ ] Research and select a GUI framework (e.g., PySide6, Tkinter).
- [ ] Design a basic UI to display universe/fleet data and trigger actions.
- [ ] Implement the GUI, ensuring it runs in a separate thread from the automation logic.


## Random thoughts
- Update retry logic to fail if it's a 400 error
  - Maybe make it intelligently understand all return codes
  - Also reduce retry time dramatically to align with rate limits
