# Project Architecture

This is a Python 3.11+ application.

- Code is in `src/py_st`
- Data structures (Pydantic models) are auto-generated in `src/py_st/_generated/models`
- Tests are in `tests` and use pytest.
- Use `.venv/bin/python` to run python in your context

## Key Modules

- **`src/py_st/client/`**: Handles raw API communication with the SpaceTraders API, including transport logic (`transport.py`) and endpoint definitions (`endpoints/`).
- **`src/py_st/services.py`**: Contains higher-level functions that orchestrate client calls to perform specific game actions (e.g., `list_ships`, `Maps_ship`). This is where most business logic resides.
- **`src/py_st/cli/`**: Implements the command-line interface using Typer. These modules parse arguments and call functions in `services.py` to execute commands.
- **`src/py_st/cache.py`**: Manages the file-based JSON cache for API responses to reduce redundant calls.

## Coding Standards

- You must limit all changes to 79 characters or less per line
- Use industry standards for python (e.g., follow PEP 8, use type hints).
- Ensure code passes checks defined in `.pre-commit-config.yaml` (ruff, black) and `mypy`.
- Build "clean code", using small descriptively named functions
