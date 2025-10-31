# Project Architecture

This is a Python 3.11+ application.

  * Code is in `src/py_st`
  * Data structures (Pydantic models) are auto-generated in `src/py_st/_generated/models`
  * Tests are in `tests` and use pytest.
  * Use `.venv/bin/python` to run python in your context

## Key Modules

  * **`src/py_st/client/`**: Handles raw API communication with the SpaceTraders API, including transport logic (`transport.py`) and endpoint definitions (`endpoints/`).
  * **`src/py_st/services/`**: Contains higher-level functions that orchestrate client calls to perform specific game actions (e.g., `list_ships`, `Maps_ship`). This is where most business logic and caching logic resides.
  * **`src/py_st/cli/`**: Implements the command-line interface using Typer. These modules parse arguments and call functions in the `services` layer to execute commands.
  * **`src/py_st/cache.py`**: Manages the file-based JSON cache for API responses to reduce redundant calls.

## Coding Standards

### General Standards

  * **Line Length:** All code must be 79 characters or less per line.
  * **Style:** Follow PEP 8 and use type hints.
  * **Verification:** All changes must pass `make ci` (ruff, black, mypy, pytest) before committing.
  * **Clean Code:** Write "clean code": prefer small, descriptively-named functions.

### Commenting & Docstrings

  * **Avoid Self-Documenting Comments:** Do not add comments that merely restate what the code is doing. For example, `full_cache = cache.load_cache()` is self-explanatory and does not need a `# Load cache` comment.
  * **Focus on "Why," not "What":** Use comments primarily to explain *why* a piece of logic exists, especially if it's complex, non-obvious, or has business-logic implications.
  * **Keep Docstrings General:** Docstrings should explain *what* a function does and its parameters. Avoid hard-coding specific, changeable values (like "cache expires in 1 hour"). Instead, refer to the *concept* or *variable* (e.g., "Returns cached data if it's considered fresh, based on `CACHE_STALENESS_THRESHOLD`.").

### Unit Testing Standards

  * **Structure with Arrange-Act-Assert:** All unit tests must be clearly structured with comments separating these three logical blocks:

    ```python
    # Arrange
    mock_data = ...
    mock_client.return_value = ...

    # Act
    result = function_to_test(...)

    # Assert
    assert result == expected, "A helpful message explaining the failure"
    ```

  * **Use Descriptive Assertion Messages:** All `assert` statements should include a string message that explains what condition failed and what it implies (e.g., `assert result == "SHIP-NEW", "Should return new ship data on stale cache, not old data."`) unless the failure cause is apparent.

### CLI & UX Design

  * **Use 0-Based Indexing:** All user-facing list indexes (e.g., for selecting a ship) must be **0-based**.

-----

# Guidance for Claude Code

## 1. Setup & Environment

Before running any tests or CI checks, ensure all dependencies are installed, including testing tools.

1.  `python3 -m pip install -e .` (This installs from `pyproject.toml`)
2.  `python3 -m pip install pytest mypy` (These are specified for CI but not in `pyproject.toml`)

* **Python:** Use `/usr/local/bin/python3`
* **Testing:** Use `PYTHONPATH=src python3 -m pytest` (see `.github/workflows/ci.yml` for CI setup)
* **Workflow:** See `Makefile` for all commands. `make ci` must pass before any commit.

## 2. Important: Verification Process

Before making ANY changes:

1.  Run `make ci` to establish a baseline. Note any pre-existing errors.
2.  You will many pre-existing `mypy` errors due to the nature of your configuration.
3.  Focus on ensuring your changes do not introduce NEW errors beyond the baseline.
4.  Formatting (`make check`) and tests (`make test`) are the critical checks.
