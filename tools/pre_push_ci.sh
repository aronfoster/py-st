#!/bin/sh
set -eu

# Keep local pushes aligned with .github/workflows/ci.yml. The hook is
# intentionally non-mutating: formatting or generated-asset drift must be fixed
# and reviewed before a push can proceed.
black --check .
ruff check --no-fix .
mypy .
pytest -q
npm --prefix frontend run check
npm --prefix frontend run build
git diff --exit-code -- src/py_st/services/ui
test -z "$(git status --porcelain --untracked-files=all -- \
  src/py_st/services/ui)"
