# Agent Instructions

The primary goal is the best application for a human or automated process to
play SpaceTraders. Gameplay is secondary: use bounded live experiments to
validate capabilities, then return to building the tools. Profitable manual
play is not a substitute for application development. Continue engineering
through the available overnight token/runtime budget, not just green tests.

## Workspace

Work in this normal repository checkout on `aron/fos-63-review`. The former
`tmp/astra` worktree was removed and its runtime state moved to root `.state`.
Do not create another worktree or request parent-directory access. Keep new
temporary work under ignored `.cache/nightly`; use `.venv/bin/python` here.
Subagents must use the same boundaries and explicit in-project test temp paths.
Historical worktree instructions in the logs are not current setup instructions.

Read this file, ROADMAP.md, docs/ASTRA_LOG.md and docs/HANDOFF.md first.
This is Python 3.11+; use the owner's Python 3.12 virtual environment.
Preserve CLI -> services/automation -> client/transport layering. Generated
models are not hand-edited. Use typed code, 79-column Black/Ruff formatting,
pytest with Arrange/Act/Assert, and zero-based UI indexes.

Run non-mutating Black, Ruff --no-fix, mypy and pytest before commits.
Manual edits use apply_patch. Stage intended files only, inspect status/diff
and recent log before each coherent local commit. Push only when explicitly
authorized by the owner; never publish packages or runtime data implicitly.

## Live Safety (FOS-63)

- Observe fresh agent/fleet/contracts before any mutation. Never register.
- Stop live on HTTP 401 or API code 4113. Owner must refresh ST_TOKEN after
  checking reset/account state; never print credentials or pass them in argv.
- Keep at least 50,000 credits plus known contract/fuel obligations.
- No live jump, warp, scrap, jettison, ship purchases or DRIFT in this run.
- Protect all cargo required by accepted, unfulfilled contracts.
- Bound cycles by actions and monotonic wall time. Check project STOP between
  mutations and during waits. Unknown mutation outcomes require reconciliation,
  never blind replay. Normal pytest never calls the live API.
- Store runtime data under ignored .state; disposable cache under .cache.
  Scope durable data by API reset and agent, never by secret token.
- No paid services, security-setting changes or system-level harness.

## Run Checklist

- [x] Reliability floor and regression tests
- [x] Bounded, journaled profit workflow with live economics
- [x] SQLite observations, history, reports
- [x] Local dashboard over shared data, browser verification
- [x] Further tested improvements and review handoff
- [ ] Unattended continuation through the requested overnight budget (not achieved)
