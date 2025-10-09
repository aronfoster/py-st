.PHONY: lint type test ci
lint:  ; ruff check . && black --check .
type:  ; mypy .
test:  ; pytest -q
ci:    ; PYTHONPATH=src ruff check . && black --check . && mypy . && pytest -q
