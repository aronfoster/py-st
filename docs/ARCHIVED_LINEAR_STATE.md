# Archived Linear state — 2026-09-24

This document preserves durable project state and product decisions that were
still primarily recorded in Linear when active py-st development stopped. It is
a **distillation**, not a dump of every Linear comment. The repository is the
archive of record from this point forward.

Linear references are retained as provenance. Their workflow status should not
be interpreted as active work after 2026-09-24.

## Delivered product sequence

The browser product was built as a series of bounded end-to-end slices:

| Slice | Delivery |
| --- | --- |
| Stored-data System Explorer | PR #45, merge `39a9b7c6130829afa51618976859fd43c280cb66` |
| Durable browser flight operations | PR #46, merge `6d4f2ff6c9f0ebeabba6d07836355765120f0c44` |
| Read-only capability snapshot | PR #47, merge `a28f76d3dc4f7d27cb93e4702b3388e7643ba047` |
| React/browser UI foundation | PR #48, merge `f42271419838d5bd57ea22a00f6e3b2e9c501eff` |
| Guarded browser trading | PR #49, merge `7e1a65000d59efc6b6a1c994fd600cf6194d47a1` |
| Hardened supervised registration | PR #50, merged 2026-09-13 |
| Browser contract lifecycle | PR #51, merge `5aac3f5773d3503efdfe714c7f122d51a35af174` |
| Offline hosted package / checkpoint recovery | PR #54, merge `b51f9d3760ea758d9732dc06132f93f9703cf4af` |
| Dense-system Explorer usability | PR #56, merge `133fc5c65dbaf6bf53e7f48f88b7cd5e6e44ea2d` |
| Operator-run Cloud Shell/VM releases | PR #57, merge `83f0860cc47d9f5dac3fe2f93dc5457ff36f5c6a` |
| Routine deployment documentation | PR #58, merge `7b4c57d54464ddbe4639c01575caa1f000a005b3` |

The original FOS-71 dispatch sequence considered Tasks 01–05A complete. Task
05B became the real GCP rollout/authority-handoff work in FOS-74. Persistent
pilot controls and the larger gameplay roadmap were never completed.

## What the browser application could do

By the stopping point the repository included:

- stored-data system exploration and a React shell;
- durable queued flight operations with a separate authoritative worker;
- browser trading with preview, reserve/contract protection and reconciliation;
- browser contract negotiation, acceptance, procurement, delivery and
  fulfillment flows;
- owner authentication, Host/Origin/CSRF protections and production packaging;
- STOP/pause state, command journaling and unknown-outcome preservation;
- quiesced checkpoints with strict code/state compatibility;
- a read-only account/system capability snapshot;
- a dense-system destination workflow with search/filtering, detail and
  trip-preview handoff, d3 zoom/pan, label-density controls, clustering and
  exact-coordinate disambiguation;
- operator-run build/transfer/activate/status tooling with durable deployment
  receipts and explicit interrupted-deployment recovery.

The implementation deliberately distinguished offline/synthetic proof from
live SpaceTraders proof. Many capabilities had strong offline/browser tests but
were never exercised end-to-end in unattended live operation.

## Final GCP architecture and operational facts

The deployment work converged on one small Compute Engine host, not a managed
multi-service platform.

Known final architecture:

- GCP project: `py-st-508516`.
- Network: custom `py-st-network`.
- Subnet: `py-st-us-central1`.
- VM: `py-st-1`, `e2-micro`, zone `us-central1-a`, Ubuntu 24.04.
- Runtime service account:
  `py-st-runtime@py-st-508516.iam.gserviceaccount.com`.
- IAP SSH firewall path: TCP 22 from `35.235.240.0/20`.
- Boot disk: 20 GiB.
- Separate data disk: 10 GiB, mounted at `/srv/py-st`.
- Canonical application state: `/srv/py-st/state`.
- Versioned releases: `/opt/py-st/releases/<full-sha>`.
- Active-release symlink: `/opt/py-st/current`.
- Non-secret hosted configuration: `/etc/py-st/hosted.env`.
- Private SpaceTraders credential file: `/srv/py-st/state/.env`.
- Worker authority gate: `/etc/py-st/worker-armed`.
- Public hostname: `spacetraders.foster.cool`, using Cloudflare DNS and Caddy.
- The deployment ultimately used both static IPv4 and IPv6. The IPv4 was kept
  because SpaceTraders API DNS did not provide a usable AAAA-only path during
  the deployment investigation.

The cost objective was free tier where practical, with roughly $5/month treated
as an acceptable ceiling for this hobby project. The external IPv4 was the main
known recurring charge; a Google external HTTPS load balancer was explicitly
rejected as disproportionate for a one-user service.

A 2026-09-18 idle snapshot on the e2-micro showed approximately 953 MiB RAM
total, 538 MiB available, 15 GiB free on the root filesystem and 9.3 GiB free
on the data disk. That established idle fit, not load capacity.

## Hosted rollout history worth preserving

The first hosted baseline was release
`b51f9d3760ea758d9732dc06132f93f9703cf4af`. During supervised rollout:

- the owner registered pilot `SOURCE_CODE` in faction `DOMINION`;
- read-only verification observed headquarters `X1-QS7-A1`, 175,000 starting
  credits, a COMMAND ship and a SATELLITE ship;
- dashboard and worker were run under systemd behind Caddy;
- STOP survived service restart;
- a same-release checkpoint was created at
  `/srv/py-st/backups/initial-20260918T170908Z`;
- an isolated restore rehearsal succeeded and retained STOP and
  HANDOFF_REQUIRED while deliberately excluding `.env`;
- the worker authority gate was explicitly created and a paused hosted worker
  heartbeat was observed.

A later deployment installed release
`83f0860cc47d9f5dac3fe2f93dc5457ff36f5c6a`, which included the dense Explorer
work and the operator release tooling. Its immediately previous release was
`bd38c737c0b65847174b1e4d3c5e1858971a22ed`; the deployment created checkpoint
`/srv/py-st/checkpoints/bd38c737c0b65847174b1e4d3c5e1858971a22ed-48dd264cde0c4d5ea9fb6887a8e0fa67`.

The deployment tooling from PR #57 was subsequently documented as the normal
two-terminal release path in PR #58. See `docs/OPERATOR_RELEASE.md`.

## Last hosted incident

FOS-102 records that immediately after deployment of
`83f0860cc47d9f5dac3fe2f93dc5457ff36f5c6a`, queued commands stopped processing
with:

```
Authentication/reset failure: refresh token and restart worker; no registration
```

The safety decision was explicit: do not register a new pilot merely because of
401/reset evidence, do not replay uncertain mutations, preserve STOP/pause and
reconcile the queue before retrying.

A later operator session showed `py-st-worker.service` active again after
credential/restart work, but Linear never received a canonical FOS-102
resolution or queue-reconciliation record before archival. A future restart
should therefore treat the final live queue/account state as **unknown**, not
as proven clean.

## Important product decisions that were not fully represented in the repo

### Opt-in automatic reset rollover was desired, but never implemented

FOS-77 deliberately delivered a conservative owner-invoked registration path.
Afterward, FOS-78 recorded a later product decision: support a separately
enabled automatic-reset controller that, after **confirmed** season rollover,
could register the configured symbol/faction, handle bounded symbol collisions,
verify the new identity, create a fresh reset/agent scope and start configured
operations without a second routine owner action.

That work remained Todo. Important design constraints from FOS-78:

- a 401, bad token, network failure or forecast reset time is not proof of a
  completed reset;
- use the hardened FOS-77 registration path rather than a second POST path;
- persist the exact candidate before registration and distinguish preferred
  symbol from effective symbol;
- only a verified no-side-effect collision permits another candidate;
- timeout/5xx/malformed post-dispatch outcomes are uncertain and must not be
  blindly retried;
- keep old-season queues/history scoped and never replay old ship IDs/contracts;
- explicit owner STOP/disable wins over automatic rollover;
- deduplicate startup with a durable transition/profile key;
- account/agent credentials never belong in public transition state or logs.

The current code remains the manual/supervised baseline. `ROADMAP.md` contained
older language saying automatic registration was superseded; that sentence
should be read as the **implemented baseline**, not the final product intent.

### Immediate remaining Fleet usability gap

FOS-96 remained Todo. Fleet readiness did not expose installed modules and
equipment well enough to explain what a ship could do. The intended workflow
was to show modules, mounts, frame/reactor/engine, capacities and evidence-based
capability summaries while clearly separating installed capability from current
action eligibility. Missing, empty, repeated and stale equipment observations
were to be represented honestly.

### Persistent automation remained the next major product slice

After hosted execution, the desired user-facing controls were not merely
"background automation." Owner priorities recorded in FOS-63 included simple
high-value controls such as:

- complete the most profitable trade loop;
- activate an automatic trade loop;
- automatically refresh/update market observations.

These were explicitly higher priority than additional mobile polish at the
time. Persistent pilot controls were intended to include start/pause/resume,
goals, budgets/reserves, scheduling, manual takeover, reporting and restart-safe
operation against the single authoritative hosted worker.

None of that persistent pilot slice was completed.

### Other later gameplay directions

The longer-term product scope included:

- fleet purchases and outfitting;
- module/mount installation and configuration planning;
- repair/maintenance/replacement economics;
- mining, surveying, siphoning, hauling and refinery coordination;
- market/supply-chain planning;
- reconnaissance/probe placement and observation freshness;
- season/reset handling;
- jumpgate completion and multi-system progression.

A specific owner idea was to make jumpgate repair progress visible, list all
required goods, and eventually automate economical sourcing/mining/refining of
those materials. These are archived ideas, not implemented commitments.

## Linear issue map at archival

The main surviving Linear state was:

| Issue | State at archive | Durable meaning |
| --- | --- | --- |
| FOS-63 | In Progress | Parent product roadmap; intentionally stopped by owner |
| FOS-71 | In Progress | Dispatch/decomposition tracker; Tasks 01–05A delivered, later work unfinished |
| FOS-72 | Done | UI/UX foundation delivered |
| FOS-73 | Done | Repeatable read-only capability snapshot delivered |
| FOS-74 | In Progress | GCP deployment/authority handoff; substantial hosted proof completed, but not every original acceptance gate closed |
| FOS-77 | Done | Hardened supervised registration delivered |
| FOS-78 | Todo | Opt-in automatic reset registration/startup design only |
| FOS-95 | Todo | Full single-command deployment/recovery automation beyond the operator-run milestone |
| FOS-96 | Todo | Fleet equipment/capability presentation |
| FOS-97 | Done | Dense Explorer implementation delivered |
| FOS-101 | In Review in Linear | Code was actually merged as PR #57; Linear state was stale |
| FOS-102 | In Progress | Authentication/reset incident lacked a canonical closure record |

This table is evidence of why Linear workflow status must not be treated as
authoritative after archival: FOS-101, for example, still said In Review even
though PR #57 was merged and deployed.

## Safety and architectural invariants worth keeping

If py-st is ever revived, preserve these unless deliberately redesigned:

- exactly one authoritative live mutation dispatcher;
- STOP/pause survives restart and is never silently cleared;
- local process locks do not provide cross-host authority;
- unknown mutation outcomes require reconciliation, not blind replay;
- durable data is scoped by SpaceTraders reset and agent identity;
- old-season work is never replayed into a new season;
- authentication/reset failures are not automatic registration evidence;
- credentials stay out of argv, logs, receipts, Git and checkpoints;
- checkpoint restore requires matching code/state compatibility evidence;
- browser transport readiness is not equivalent to gameplay acceptance;
- free/low recurring cost remains a design constraint for hobby hosting.

## If work resumes

Do not reopen the old Linear queue and start at the first Todo. Start from the
repository and make a new product decision about what is worth building.

At minimum:

1. Reassess the current SpaceTraders API/reset model and dependencies.
2. Inspect current GCP resources rather than assuming any archived resource
   still exists.
3. Treat the final live account/queue state as stale/unknown.
4. Run the full offline test suite and browser suite.
5. Decide whether the next goal is actual gameplay enjoyment, automation
   experimentation, or infrastructure/agent experimentation.
6. Only then recreate a backlog from the unfinished items above.
