.PHONY: lint type test ci fetch-spec regen-spec clean-spec build-model-aliases
lint:  ; ruff check . && black --check .
type:  ; mypy .
test:  ; pytest -q
ci:    ; PYTHONPATH=src ruff check . && black --check . && mypy . && pytest -q
# Clone full repo (shallow) into tmp/, then copy the spec JSON into your tree
fetch-spec:
	rm -rf tmp/api-docs
	git clone https://github.com/SpaceTradersAPI/api-docs.git tmp/api-docs
	mkdir -p src/py_st/_generated/reference
	cp tmp/api-docs/reference/SpaceTraders.json src/py_st/_generated/reference/SpaceTraders.json

# Re-generate Pydantic models from the canonical JSON Schemas
regen-spec: fetch-spec
	rm -rf src/py_st/_generated/models
	mkdir -p src/py_st/_generated/models
	datamodel-codegen \
	 --input tmp/api-docs/models \
	 --input-file-type jsonschema \
	 --target-python-version 3.12 \
	 --output-model-type pydantic_v2.BaseModel \
	 --output src/py_st/_generated/models
	$(MAKE) build-model-aliases


# Remove the temp checkout
clean-spec:
	rm -rf tmp/api-docs

build-model-aliases:
	./tools/gen_model_aliases.py
