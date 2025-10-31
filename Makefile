## Makefile for py-st project

.PHONY: all lint type test ci fetch-spec regen-spec clean-spec build-model-aliases help prepare-tools clear-cache
.DEFAULT_GOAL := help

# ==============================================================================
# Development Tasks
# ==============================================================================

# Apply fixes locally so you can review diffs before committing
fmt:
	@ruff check --fix .
	@black .

# Run both checks and fail if either fails (no writes)
check:
	@{ \
	  black --check .; rc1=$$?; \
	  ruff check .;   rc2=$$?; \
	  exit $$((rc1||rc2)); \
	}

type: ## Run static type checking
	mypy .

test: ## Run tests
	PYTHONPATH=src python3 -m pytest -q

ci: fmt check type test ## Run all checks for continuous integration

# ==============================================================================
# API Spec & Model Generation
# ==============================================================================

# Ensure our helper scripts are executable (fresh clone safety)
prepare-tools:
	@for f in tools/inject_titles.py tools/gen_model_init.py; do \
		if [ -f "$$f" ] && [ ! -x "$$f" ]; then chmod +x "$$f"; fi; \
	done

fetch-spec: ## Fetch and store the latest SpaceTraders API spec
	rm -rf tmp/api-docs
	git clone https://github.com/SpaceTradersAPI/api-docs.git tmp/api-docs
	mkdir -p src/py_st/_generated/reference/models
	cp tmp/api-docs/reference/SpaceTraders.json src/py_st/_generated/reference/
	cp tmp/api-docs/models/*.json src/py_st/_generated/reference/models/

regen-spec: prepare-tools fetch-spec
	rm -rf src/py_st/_generated/models
	mkdir -p src/py_st/_generated/models
	./tools/inject_titles.py src/py_st/_generated/reference/models
	datamodel-codegen \
	  --input src/py_st/_generated/reference/models \
	  --input-file-type jsonschema \
	  --target-python-version 3.12 \
	  --output-model-type pydantic_v2.BaseModel \
	  --use-title-as-name \
	  --reuse-model \
		--use-exact-imports \
	  --output src/py_st/_generated/models
	./tools/gen_model_init.py

clean-spec: ## Clean up the temporary spec files
	rm -rf tmp/api-docs

build-model-aliases: tools/gen_model_aliases.py ## Generate model aliases
	./tools/gen_model_aliases.py

clear-cache: ## Remove the local JSON cache
	@rm -f src/.cache/data.json
	@echo "Cache cleared."

# ==============================================================================
# Help
# ==============================================================================

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
