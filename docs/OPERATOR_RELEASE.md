# Operator-run GCP release (FOS-101)

This procedure builds a pinned release in Cloud Shell and activates it from
the VM SSH terminal. The first live rollout is supervised under FOS-74.
Neither command resumes gameplay. Preserve the old release, checkpoint and
STOP after any error. The bundle checksum detects damage, not a signature.

## Cloud Shell: first use and subsequent releases

Cloud Shell must have Linux x86_64, `git`, `gcloud`, and Python 3.12 with
`pip` and `venv`. Run `python3.12 --version`. If the command is absent and
Cloud Shell has a working stock `python3 -m venv`, this user-local setup can
install Python 3.12 without system changes:

```sh
python3 -m venv "$HOME/.local/share/py-st-bootstrap"
"$HOME/.local/share/py-st-bootstrap/bin/python" -m pip install uv
"$HOME/.local/share/py-st-bootstrap/bin/uv" python install 3.12
mkdir -p "$HOME/.local/bin"
ln -s "$("$HOME/.local/share/py-st-bootstrap/bin/uv" python find 3.12)" "$HOME/.local/bin/python3.12"
export PATH="$HOME/.local/bin:$PATH"
python3.12 -m venv "$HOME/.local/share/py-st-python-check"
```

If stock `venv` or downloads fail, repair the Cloud Shell prerequisite before
building. The development environment verified Python 3.12 and venv; Cloud
Shell itself is not available for this offline implementation.

In **Cloud Shell**, first clone the public repository into a dedicated build
checkout (no GitHub token or private state):

```sh
git clone https://github.com/aronfoster/py-st.git "$HOME/py-st-build"
cd "$HOME/py-st-build"
python3.12 deploy/release.py prepare --project py-st-508516 --zone us-central1-a --instance py-st-1
```

For a later release, refresh that checkout without resetting an arbitrary work
tree. The prepare command independently fetches and pins the remote default
HEAD, even if the branch changes from `master` to another name:

```sh
cd "$HOME/py-st-build"
git status --short
git pull --ff-only
python3.12 deploy/release.py prepare --project py-st-508516 --zone us-central1-a --instance py-st-1
```

Keep the dedicated checkout clean; if `git pull` refuses local changes, use a
fresh dedicated clone. The script rejects a locally stale entrypoint. It uses a
clean archive of the pinned commit, never working-tree edits. It prints branch,
full SHA, SHA256 and **one ready-to-copy VM activation command** with absolute
paths. Run that command only after pausing in the browser. A failed transfer
prints an exact `transfer` retry command for the same completed bundle.
`prepare --prepare-only` builds and checks locally without GCP access and
prints the same retry command for later transfer. Generated frontend resources
are checked in and validated in the wheel; their freshness remains a CI gate.

## VM SSH terminal: pause and activate

Open the hosted browser's **Operations** page and pause gameplay. Confirm STOP
and desired pause. In the **VM SSH terminal**, paste the exact activation
command printed by Cloud Shell. It begins `sudo python3.12` and includes
absolute paths plus `--sha256`. No editing is needed.

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
against a successful same-SHA release reports already installed. A partial
activation is deliberately refused on retry: inspect the receipt, actual
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

Code-only switch-back requires an explicit compatibility check against the
current state. State restoration is a separate owner decision: preserve the
latest state and uncertain outcomes, use the *exact matching old code* and
the existing quiesced `flight restore` procedure in
[HOSTED_OPERATIONS.md](HOSTED_OPERATIONS.md). Checkpoints omit root `.env` and
cannot recover the game token. No receipt or transfer artifact is a secret
backup; protect checkpoints as private state.

## Sanitized example outcomes

```text
Prepared master 0123456789abcdef0123456789abcdef01234567 SHA256 <digest>: ...
VM activation command: sudo python3.12 /home/operator/.../release.py deploy ...
Deployed 0123456789abcdef0123456789abcdef01234567 from <old-sha>; checkpoint /srv/py-st/checkpoints/<old-sha>-<run-id>
Current: <new-sha>; services: {'py-st-dashboard.service': 'active', 'py-st-worker.service': 'active'}; state: {'stop': True, 'paused': True, 'worker_state': 'paused', ...}
Log in again; verify Explorer destination → detail → preview; resume deliberately when ready.
```

```text
Incomplete phase=checkpoint: runuser exited 1
Current: <old-sha>; services: {'py-st-dashboard.service': 'inactive', 'py-st-worker.service': 'inactive'}; state: {'stop': True, 'paused': True, ...}
If both services are safely stopped and STOP/desired pause remain, explicitly restart the old release...
```
