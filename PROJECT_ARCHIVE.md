# Project Archive — 2026-09-24

## Status

**py-st is archived / paused indefinitely.**

The project reached the point where the SpaceTraders browser application and its hosted deployment were usable enough to answer the owner's original curiosity: how far an LLM-heavy development workflow could take the project. The owner does not currently enjoy the game enough to justify additional development time or ongoing GCP expense.

This is a deliberate stopping point, not a failed deployment and not a request to finish the remaining roadmap.

## What exists

At archive time the repository contains, among other things:

- a Python SpaceTraders client and automation/service layers;
- durable SQLite observations/history and reporting;
- a browser UI with fleet/economics/contracts/exploration surfaces;
- browser flight operations backed by a durable worker;
- dense-system destination browsing with search/filter/detail/trip-preview and map navigation;
- offline/synthetic validation paths that do not require SpaceTraders credentials;
- GCP-oriented hosted-operation and operator-release/deployment documentation;
- extensive design, safety, architecture, handoff, and historical run notes under `docs/`.

See `docs/ARCHIVED_LINEAR_STATE.md` for the distilled product decisions, GCP rollout history, unfinished work, and issue-state context that had not yet been transferred from Linear. Also see `README.md`, `docs/ARCHITECTURE.md`, `docs/CAPABILITY_SNAPSHOT.md`, `docs/HOSTED_OPERATIONS.md`, `docs/OPERATOR_RELEASE.md`, and `docs/HANDOFF.md` for implementation detail.

## Hosted deployment

A GCP deployment was running during the final development pass. It is **not intended to remain running after archival**. The operator should stop/delete chargeable GCP resources rather than preserve a live deployment merely for this project.

Do not assume a historical hostname, VM, disk, IP address, secret, token, or DNS entry still exists when resuming. Treat the repository as the durable artifact and provision infrastructure afresh if needed.

Runtime state and secrets were intentionally excluded from Git. A future restart should use a current SpaceTraders token/account state rather than attempting to reconstruct a stale live session.

## Why work stopped

The owner resumed the project partly to see whether Astra could drive a large increment of the work effectively. That experiment was satisfying, but continuing to build and host the application is not currently worth the time or cloud cost given the owner's limited interest in playing SpaceTraders.

Accordingly:

- do not interpret unchecked roadmap items as active commitments;
- do not continue work merely because old Linear tickets or handoff notes say something is "next";
- do not redeploy or incur paid cloud costs without a new explicit owner decision;
- historical FOS/Linear references remain provenance only. **The repository, not Linear, is the archive record.**

## If the project is resumed

Start from the then-current default branch and reassess the game/API, dependencies, credentials, infrastructure, and product goals before following old task plans.

A sensible restart sequence is:

1. Read this file, `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`,
   `docs/CAPABILITY_SNAPSHOT.md`, and `docs/HOSTED_OPERATIONS.md`.
2. Run the offline CI/review path before touching live SpaceTraders.
3. Reassess whether the existing architecture and roadmap still match the desired use.
4. Provision fresh infrastructure only if persistent hosting is again desired.
5. Treat old Linear tickets as historical context, not the canonical backlog.

No restart is currently planned.
