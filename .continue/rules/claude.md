# Guidance for Claude Code

## 1. Setup & Environment

Before running any tests or CI checks, ensure all dependencies are installed, including testing tools.

1.  `python3 -m pip install -e .` (This installs from `pyproject.toml`)
2.  `python3 -m pip install pytest mypy` (These are specified for CI but not in `pyproject.toml`)

* **Python:** Use `/usr/local/bin/python3`
* **Testing:** Use `PYTHONPATH=src python3 -m pytest` (see `.github/workflows/ci.yml` for CI setup)
* **Workflow:** See `Makefile` for all commands. `make ci` must pass before any commit.

## 2. Project Standards & Architecture

For all coding standards, project structure, and architectural rules, refer to the main guidance file:
**See `.continue/rules/overview.md`**

## 3. Important: Verification Process

Before making ANY changes:

1.  Run `make ci` to establish a baseline. Note any pre-existing errors.
2.  You will many pre-existing `mypy` errors due to the nature of your configuration.
3.  Focus on ensuring your changes do not introduce NEW errors beyond the baseline.
4.  Formatting (`make check`) and tests (`make test`) are the critical checks.
