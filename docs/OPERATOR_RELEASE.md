# Operator-run GCP release

Use this runbook to update the hosted py-st application on the existing GCP VM.
The normal release path is deliberately short: prepare and transfer from Cloud
Shell, pause gameplay in the browser, paste the generated activation command
into the VM terminal, verify, then resume deliberately.

The deployment tooling never resumes gameplay for you. Preserve the old
release, checkpoint and STOP after any error. The bundle checksum detects
transfer damage; it is not a signature.

## Routine release

### 1. Cloud Shell: refresh, build, verify and transfer

In **GCP Cloud Shell**:

```sh
cd "$HOME/py-st-build"
git pull --ff-only
python3.12 deploy/release.py prepare \
  --project py-st-508516 \
  --zone us-central1-a \
  --instance py-st-1
```

The prepare command independently resolves the repository's remote default
branch and pins its full SHA. It builds from a clean archive of that commit,
verifies a fresh offline install including packaged UI assets, creates the
release bundle, transfers the bundle and deployment entrypoint through IAP, and
verifies their remote digests.

A successful prepare prints:

- the pinned branch, full SHA and bundle SHA256;
- one **VM activation command** with absolute paths and digest; and
- one independent **VM status command**.

Do not manually edit the generated SHA, checksum or staging paths.

If `git pull --ff-only` refuses because the dedicated checkout has local
changes, do not reset an unrelated work tree. Inspect the checkout or replace
it with a fresh dedicated clone.

### 2. Browser: pause gameplay

Before VM activation, open the hosted application's **Operations** page and
pause gameplay. Leave STOP and desired pause in place.

Do not pause before the Cloud Shell prepare/transfer phase; the running release
can stay online while the next release is built and transferred.

### 3. VM SSH terminal: activate

Open an SSH terminal to `py-st-1` and paste the **exact VM activation command**
printed by the prepare step. It begins with `sudo systemd-run`.

Do not reconstruct the command by hand. The generated command points at the
transferred entrypoint and bundle for the pinned SHA and includes the expected
digest.

The activation command performs preflight checks, stages the new release,
stops both application services, captures a checkpoint with the old release's
code, runs new-code compatibility checks, atomically switches `current`,
starts both services, waits for a fresh paused worker heartbeat, probes local
and public HTTP readiness, and writes the deployment receipt.

Success should end with all of these true:

- `Current` is the intended new full SHA;
- `py-st-dashboard.service` is active;
- `py-st-worker.service` is active;
- STOP is true;
- desired pause is true and worker state is `paused`;
- a fresh heartbeat is reported;
- queued and uncertain command counts are understood; and
- `Last receipt: success` is reported.

### 4. Browser: accept and resume

After a successful activation:

1. Log in again if the restarted application expired the prior session.
2. Verify the expected browser workflow, including Explorer destination →
   detail → preview for map/UI releases.
3. Return to **Operations** and resume gameplay deliberately.

An HTTP 200 only proves transport readiness. Browser acceptance verifies the
actual hosted application behavior.

## First-time Cloud Shell bootstrap

Cloud Shell needs Linux x86_64, `git`, `gcloud`, and Python 3.12 with
`pip` and `venv`. Verify:

```sh
python3.12 --version
uname -m
git --version
gcloud --version
```

If `python3.12` is absent but the stock Python can create a venv, install a
user-local Python 3.12 without changing the system Python:

```sh
python3 -m venv "$HOME/.local/share/py-st-bootstrap"
"$HOME/.local/share/py-st-bootstrap/bin/python" -m pip install uv
"$HOME/.local/share/py-st-bootstrap/bin/uv" python install 3.12
mkdir -p "$HOME/.local/bin"
ln -s "$("$HOME/.local/share/py-st-bootstrap/bin/uv" python find 3.12)" \
  "$HOME/.local/bin/python3.12"
export PATH="$HOME/.local/bin:$PATH"
python3.12 -m venv "$HOME/.local/share/py-st-python-check"
```

Run this interactive IAP SSH check once so `gcloud` can create keys or show any
passphrase prompt before the deployment script later uses non-interactive
captured output:

```sh
gcloud compute ssh py-st-1 \
  --project py-st-508516 \
  --zone us-central1-a \
  --tunnel-through-iap \
  --command true
```

Then create the dedicated build checkout:

```sh
git clone https://github.com/aronfoster/py-st.git "$HOME/py-st-build"
cd "$HOME/py-st-build"
python3.12 deploy/release.py prepare \
  --project py-st-508516 \
  --zone us-central1-a \
  --instance py-st-1
```

This checkout exists only to obtain and run the checked-in release tooling. The
build itself uses a clean archive of the pinned remote commit rather than dirty
working-tree contents.

For build-only rehearsal or a transfer retry, `prepare --prepare-only` keeps
the completed artifact and prints an exact `transfer` command for that same
SHA and digest.

## VM SSH terminal: pause and activate

Open the hosted browser's **Operations** page and pause gameplay. Confirm STOP
and desired pause. In the **VM SSH terminal**, paste the exact activation
command printed by Cloud Shell. It begins `sudo systemd-run`, runs the pinned
Python command as a transient root service, and includes absolute paths plus
`--sha256`. No editing is needed. `--wait --pipe` shows its output while your
SSH connection is up. If SSH disconnects, the transient service continues;
the terminal client may exit, so use the independent status command afterward.
The unit name starts `py-st-deploy-` followed by the first twelve SHA characters.
Its journal is available with `sudo journalctl -u UNIT_NAME -n 80 --no-pager`.

The command checks the mount, installed services, existing authority gates,
credentials' presence/ownership, paused ledger and STOP before downtime. It
installs an offline venv in `/opt/py-st/releases/<sha>`, stops both services,
captures a private old-code checkpoint under `/srv/py-st/checkpoints`, checks
new-code compatibility, switches `current` atomically, starts both services,
waits for a new paused worker heartbeat and probes loopback and public HTTPS.
It records a protected receipt in `/var/lib/py-st-deploy/receipt.json`.

The final result includes the new and previous SHA, checkpoint, current link,
both services, pause/STOP, queue counts and receipt. Log in again; verify
Explorer destination → detail → preview, then resume deliberately. HTTP 200
only proves the shell is reachable, not authenticated gameplay acceptance.

## VM SSH terminal: status and recovery

The transferred script lives in the operator's private incoming directory,
outside `/opt/py-st/current`. Use the exact status command printed by Cloud
Shell, optionally appending `--json`. It is safe after a dropped SSH session.
The private incoming path includes the pinned full SHA and stays reachable if
`/opt/py-st/current` changes.

This command changes no service or state and calls no game API. A second deploy
against a successful same-SHA release reports already installed only when both
services are active and the heartbeat is fresh. A partial activation is
deliberately refused on retry: inspect the receipt, actual
`systemctl status py-st-dashboard.service py-st-worker.service`, and private
checkpoint. Do not delete STOP or automatically restore a checkpoint.

If a failure occurred **before the symlink switch** and both processes are
confirmed stopped, the old release still points at `current`. After confirming
the state is still paused/STOP and checking the worker gate, explicitly run:

```sh
sudo systemctl start py-st-dashboard.service py-st-worker.service
```

Check both services and a newly paused worker heartbeat. If stopping timed
out or a writer may still be running, resolve that first; never checkpoint
or switch around it. A failure **after switch** needs inspection of both
service journals and the recorded checkpoint. A public TLS/DNS failure with
healthy local services does not require stopping them.

After a failed **staging** attempt, the script removes its newly created
incomplete release directory so the same bundle can be retried. If it cannot
remove that directory, first verify `current` points to a different full SHA,
inspect the exact incomplete path reported by status, and remove only that
unreferenced directory before retrying. Never remove `current` or a release
with a valid `.release.json` marker.

After an **activation** failure, first recover manually and verify both units
are active, STOP and desired pause remain, the worker has a fresh paused
heartbeat, and `current` points to the known old or new release. Then run the
exact `acknowledge --run-id` command printed by status. Acknowledgement checks
those conditions again and inspects state with the new release when it is
current. When the old release is current, its active units and fresh paused
heartbeat are the recovery proof: the old code may lack `inspect-state`, and
the staged code may be what rejected this state. It records the failure and
recovery in
`/var/lib/py-st-deploy/runs/<run-id>.json`. It does not restart, switch,
restore or resume anything. Resolve the cause of a failed new-code
compatibility check before attempting that release again. A subsequent
deployment is explicit and creates a new run receipt, even if `current` already
points at the target SHA; it repeats the checks and checkpoint. If status says
`receipt.json` is unreadable, it still prints the service/state observation.
Inspect it and the per-run receipts manually; do not delete them.

Code-only switch-back requires an explicit compatibility check against the
current state. State restoration is a separate owner decision: preserve the
latest state and uncertain outcomes, use the *exact matching old code* and
the existing quiesced `flight restore` procedure in
[HOSTED_OPERATIONS.md](HOSTED_OPERATIONS.md). Checkpoints omit root `.env` and
cannot recover the game token. No receipt or transfer artifact is a secret
backup; protect checkpoints as private state.
Checkpoints accumulate under `/srv/py-st/checkpoints`; review retained
checkpoint/release pairs and free space before a later cleanup. This workflow
does not prune evidence automatically.

## Sanitized example outcomes

```text
Prepared master 0123456789abcdef0123456789abcdef01234567 SHA256 <digest>: ...
VM activation command: sudo systemd-run --wait --collect --pipe ... python3.12 /home/operator/.../release.py deploy ...
Deployed 0123456789abcdef0123456789abcdef01234567 from <old-sha>; checkpoint /srv/py-st/checkpoints/<old-sha>-<run-id>
Current: <new-sha>; services: {'py-st-dashboard.service': 'active', 'py-st-worker.service': 'active'}; state: {'stop': True, 'paused': True, 'worker_state': 'paused', ...}
Log in again; verify Explorer destination → detail → preview; resume deliberately when ready.
```

```text
Incomplete phase=checkpoint: runuser exited 1
Current: <old-sha>; services: {'py-st-dashboard.service': 'inactive', 'py-st-worker.service': 'inactive'}; state: {'stop': True, 'paused': True, ...}
If both services are safely stopped and STOP/desired pause remain, explicitly restart the old release...
```
