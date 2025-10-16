## Makefile for py-st project

.PHONY: all lint type test ci fetch-spec regen-spec clean-spec build-model-aliases help
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
	pytest -q

ci: fmt check type test ## Run all checks for continuous integration

# ==============================================================================
# API Spec & Model Generation
# ==============================================================================

fetch-spec: ## Fetch the latest SpaceTraders API spec
	rm -rf tmp/api-docs
	git clone https://github.com/SpaceTradersAPI/api-docs.git tmp/api-docs
	mkdir -p src/py_st/_generated/reference
	cp tmp/api-docs/reference/SpaceTraders.json src/py_st/_generated/reference/SpaceTraders.json

regen-spec: fetch-spec ## Regenerate Pydantic models from the spec
	rm -rf src/py_st/_generated/models
	mkdir -p src/py_st/_generated/models
	datamodel-codegen \
	 --input tmp/api-docs/models \
	 --input-file-type jsonschema \
	 --target-python-version 3.12 \
	 --output-model-type pydantic_v2.BaseModel \
	 --output src/py_st/_generated/models
	$(MAKE) build-model-aliases

clean-spec: ## Clean up the fetched spec files
	rm -rf tmp/api-docs

build-model-aliases: tools/gen_model_aliases.py ## Generate model aliases
	./tools/gen_model_aliases.py

# ==============================================================================
# Help
# ==============================================================================

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
