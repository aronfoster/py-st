# Hosted application package — Task 05A

This package prepares the existing manual browser game for a single HTTPS
reverse proxy. It does not provision GCP, authorize live operation, transfer
authority between hosts, or prove publicly trusted TLS. Local loopback HTTP
and local blank passwords remain supported.

## Boundary and deployment contract

Set one `ST_PUBLIC_ORIGIN`, for example `https://game.example` or
`https://[2001:db8::1]:8443`. DNS names, canonical IPv4 and compressed bracketed
IPv6 are supported. There is no trailing slash, path, userinfo, query or
fragment. Port 443 is normalized away; other explicit ports remain part of
Host and Origin. Ambiguous numeric hosts and authorities are rejected.

Hosted mode uses pinned Waitress 3.0.2 on IPv4 loopback. A small WSGI adapter
reuses application methods from the existing handler, without invoking its
stdlib HTTP parser or socket server. This avoids rewriting gameplay or having
two implementations of authorization/CSRF. Local mode retains its original
server. Waitress and the edge bound headers, bodies, connections and timeouts.
The [Waitress proxy guide](https://docs.pylonsproject.org/projects/waitress/en/v3.0.2/reverse-proxy.html)
describes preserving Host; this app deliberately trusts no forwarded headers.
The proxy must preserve the original Host, including its nondefault port.
Never rewrite arbitrary inbound Host to the configured trusted authority.

Only the application shell and auth bootstrap are public. Data and mutation
routes require owner authentication; mutations retain CSRF and exact Origin
checks. Hosted cookies are Secure, HttpOnly and SameSite=Strict, including
logout expiration. Login sessions expire on application restart. Missing or
incompatible managed ledgers, malformed/private-permission failures or a blank
hosted owner verifier fail closed. Removing state during service does not
activate the local unmanaged fallback. Password input stays in private prompts.
Every authenticated request checks the existing owner and both ledgers again.
This deliberately favors prompt refusal after state loss over caching these
checks. Measure before optimizing this single-owner workload.

## Build and synthetic launch

Use Python 3.12 and a virtual environment in the release checkout. Build and
test outside the small future VM. Python packages already include the generated
frontend; no Node process runs in production. If frontend source changes,
follow `frontend/README.md` and rebuild before packaging.

`deploy/requirements-py312.lock` records the resolved runtime dependency
versions for this delivery. On a Python 3.12 Linux build host matching the VM
architecture, prepare an offline wheel directory and retain it with the release:

```sh
.venv/bin/python -m pip download --only-binary=:all: \
  -r deploy/requirements-py312.lock -d .cache/nightly/wheels
.venv/bin/python -m pip wheel --no-deps . -w .cache/nightly/wheels
```

Verify the bundle in a NEW isolated venv before moving it to the VM:

```sh
python3.12 -m venv .cache/nightly/offline-install
.cache/nightly/offline-install/bin/python -m pip install --no-index \
  --find-links .cache/nightly/wheels -r deploy/requirements-py312.lock py-st
.cache/nightly/offline-install/bin/python -m pip check
.cache/nightly/offline-install/bin/python -m py_st flight serve --help
```

Do not generate this lock from stale editable-install metadata. After any
`pyproject.toml` dependency change, reinstall the project before resolving its
installed dependency tree. The regression suite checks that the lock includes
every declared runtime requirement, including the exact Waitress pin; the
clean `--no-index` install validates the transitive wheel set.

Install that directory in the final release venv using `pip install --no-index
--find-links WHEEL_DIRECTORY -r deploy/requirements-py312.lock py-st`. Review
dependency updates explicitly and rebuild the bundle; don't resolve new versions
during unattended production startup. No runtime database or credential belongs
in the release bundle.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,browser]'
mkdir -p .cache/nightly/hosted-demo
export ST_STATE_ROOT="$PWD/.cache/nightly/hosted-demo"
export ST_PUBLIC_ORIGIN=https://127.0.0.1:8443
.venv/bin/python -m py_st flight setup --demo --public-origin "$ST_PUBLIC_ORIGIN"
.venv/bin/python -m py_st flight serve
```

Use a NEW root. Setup refuses an existing queue and prompts for the owner
password; hosted setup rejects blank before creating state. In a separate
terminal with the same absolute root, run `flight worker`. Configure Caddy with
a local test certificate and the same origin, as demonstrated in the test
fixture below. Log in, resume, and follow `FLIGHT_OPERATIONS.md` for the trip or
`BROWSER_CONTRACTS.md` for the existing manual contract path. Demo remote state
persists in `.state/remote.sqlite3` across both process restarts.

## Repeatable offline verification

No tests install host services, modify firewall settings, register a real
pilot, or contact the game API. Use a downloaded user-local Caddy binary.

```sh
export CADDY_TEST_BINARY="$PWD/.cache/nightly/caddy"
export ST_LIVE_TESTS=0
export ST_CACHE_DIR=.cache/nightly/hosted-test-cache
export TMPDIR="$PWD/.cache/nightly"
.venv/bin/python -m pytest tests/test_hosted_boundary.py -q \
  --basetemp=.cache/nightly/hosted-proof
.venv/bin/python -m playwright install chromium
DASHBOARD_BROWSER_TESTS=1 .venv/bin/python -m pytest \
  tests/test_hosted_boundary.py -q --basetemp=.cache/nightly/hosted-browser
.venv/bin/python -m black --check .
.venv/bin/python -m ruff check --no-fix .
.venv/bin/python -m mypy .
.venv/bin/python -m pytest -q --basetemp=.cache/nightly/hosted-full
```

The HTTPS fixture generates a one-day synthetic certificate with OpenSSL,
launches Caddy and Waitress on isolated loopback ports and shuts both down.
HTTPX verifies that certificate explicitly. The browser fixture accepts only
its isolated test environment's certificate errors; it installs no system CA.
Neither proves public ACME support. Desktop and 390px tests perform real login,
resume, preview, queued flight, browser closure/reopen and resulting fuel/credit
checks through the production UI and worker. Screenshots stay in the test root.
The worker requires Linux abstract Unix sockets for existing single-authority
exclusion. Do not stub or disable that guard to claim a passing workflow.

## Quiesced checkpoint and restore

1. Pause in the browser and verify STOP. Stop dashboard AND worker and all
   legacy tools that use this root. Keep services stopped for the operation.
2. Run `flight checkpoint NEW_DIRECTORY` with the canonical `ST_STATE_ROOT`.
   Destination must be outside that root and must not exist.
3. Protect the checkpoint as private authentication/game data: it includes
   `.state` (including the owner password verifier), STOP and, when present,
   HANDOFF_REQUIRED. Canonical-root `.env` is deliberately excluded, so its
   live `ST_TOKEN` is not copied or restored. Recover tokens and other external
   credentials through a separate private procedure during Task 05B, before
   deliberately arming a restored worker.
4. Run `flight restore CHECKPOINT EMPTY_TARGET` using exactly matching Python,
   HTML, JavaScript and CSS package files. The target may be nonexistent or an
   existing empty directory, but not a mount point. Do not overwrite a populated
   target. Retain old state separately.
5. Inspect restored queue, journal and STOP before deciding the next action.

The shared process lease excludes running dashboard/queue/worker instances.
SQLite write locks also reject active database writers during capture. These
are cooperative SAME-HOST locks; stop older/uncooperative tools explicitly.
The snapshot contains consistent SQLite backup images rather than a mixture of
live database/WAL files. It validates ledgers, scope and owner shape, and refuses
missing ledgers, incompatible schema, missing STOP, symlinks/special files and
nonempty destinations. A final file-hash manifest plus code identity detects
incomplete/altered snapshots. Hashes detect corruption, not hostile tampering:
checkpoint directories must remain private and trusted.

The conservative release fingerprint includes shipped UI assets, not just
Python. Even a comment-only Python hotfix or CSS-only change makes an old
checkpoint require its original release. Retain both release and checkpoint:
a state rollback after upgrading/hotfixing means restoring matching code first,
then restoring its state; there is no inferred forward migration. The initial
unmerged PR #54 fingerprint format is superseded by this corrected fingerprint.

Restore validates and stages privately, rewrites only the canonical root and
paused setting, preserves command/journal uncertainty, creates STOP and
atomically publishes the target. Live imports also get HANDOFF_REQUIRED:
worker startup and browser resume refuse until the separate Task 05B authority
review. This package has no automatic arming or cross-host transfer command.
Even same-path disaster recovery of live state needs this review. A local lock
does not prevent a worker on another machine. Never clear STOP to test restore.

## Future one-VM installation and release lifecycle

Templates in `deploy/` are reviewable examples; this task installs none of them.
Their conventional paths are parameters to adjust together before installation:
versioned code under `/opt/py-st/releases/<revision>`, a `current` symlink,
data mount `/srv/py-st`, canonical root `/srv/py-st/state`, protected
configuration `/etc/py-st`, and
an unprivileged service user. Code belongs to the deployment owner; runtime
state belongs to the service user. Both service units require the state mount.
The canonical root is a CHILD of the mount, so restore can stage on the same
filesystem and atomically publish it without trying to remove a mount point.
Runtime writes are restricted to that child; the service user should not be
able to replace the mount directory or release code. With services stopped, a
supervised restore operator stages in the mount and assigns the restored child
to the runtime user before starting services. Do not move an initialized root
by hand: its recorded path must match. This layout is for the inactive/new
deployment; existing live roots require checkpoint/restore and handoff review.

1. Build the reviewed revision and wheel/dependency artifacts off-VM. Record
   the exact Python/dependency versions and retain that release for rollback.
   Install its venv in its final versioned location (venvs are not relocatable).
2. Review the state mount and ownership, private owner verifier, ingress and
   secret delivery in Task 05B. No template runs setup or initializes state.
3. Use `deploy/hosted.env.example` as the non-secret `/etc/py-st/hosted.env`:
   set `ST_PUBLIC_ORIGIN` and `PY_ST_BACKEND_PORT` once. The dashboard unit and
   the supplied Caddy service drop-in both read this file, so the backend port
   and public origin cannot drift between two configuration files. The
   dashboard does not need a game token. Keep tokens private/server-side;
   never put them in this shared file. Ensure both Caddy and py-st users can read
   the shared file and traverse its parent directory. Keep it owned and
   writable only by the deployment administrator. Install the drop-in under
   `caddy.service.d` and adapt `deploy/Caddyfile` with the installed Caddy
   version before activation. Restart both services after changing the file.
4. With both processes stopped, take a checkpoint. Serialize activation and
   atomically switch `current` to the reviewed release. Run offline compatibility
   checks against the canonical root; start dashboard first and verify login.
5. The worker unit additionally requires an operator-created `worker-armed`
   gate and absence of HANDOFF_REQUIRED. Create that gate only during the
   separately reviewed authority transfer. Never enable overlapping workers.
6. For ordinary restart, stop/start the two processes without setup, state
   deletion or STOP removal. An interrupted mutation remains uncertain and
   must use the existing reconciliation workflow; login again after restart.
7. For upgrade, pause, quiesce, checkpoint, retain the old release, switch code,
   check compatibility and inspect before deliberate resume. No automatic
   migrations or CI/CD activation are added here.
8. For rollback, stop both processes and restore the matching prior release.
   If state compatibility is uncertain, preserve current evidence and restore
   the matching checkpoint with matching code. With all services stopped,
   retain the old `state` child under a distinct recovery name on the data
   mount, then restore to the canonical `/srv/py-st/state` (absent or empty).
   Never rename/unmount `/srv/py-st` itself. Check ownership and privately
   restore credentials; retain STOP/HANDOFF_REQUIRED pending review. Never mix
   databases from different checkpoints or replay an uncertain command.

Remaining Task 05B gates: public certificate issuance and renewal (especially
literal-IP certificates), actual inbound/outbound IPv6, GCP memory/disk load,
mount/service/VM restart tests, private secrets/bootstrap, structural cross-host
authority handoff and supervised live acceptance. Persistent pilot automation
remains after that hosted proof. Caddy's local certificate success is not public
TLS or proof of free-tier suitability.
