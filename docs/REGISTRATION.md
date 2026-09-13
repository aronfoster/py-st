# Supervised reset-night registration (FOS-77)

Registration creates a real pilot. Only Aron should invoke it, after checking
the reset and deliberately choosing a symbol/faction. Never register to test
this code, recover automatically from 401/4113, or replay an uncertain request.
The rehearsal below is offline; live registration remains unperformed.

## Reset-night procedure

1. In the account dashboard, confirm the reset and whether the desired pilot
   already exists. If it exists, recover its agent token instead of registering.
2. Pause gameplay and stop all workers, dashboard servers and CLI controllers,
   including other checkouts sharing the credentials/cache. Preserve STOP and
   take a consistent private backup of `.state` and token configuration using
   [the flight backup procedure](FLIGHT_OPERATIONS.md#compatibility-and-backups).
   Registration does not migrate/delete old ledgers, queues, journals or STOP.
3. Work from the authoritative checkout root. In a private editor, set
   `SPACETRADERS_ACCOUNT_TOKEN` in its ignored `.env` to the account credential.
   Set `DEFAULT_AGENT_SYMBOL` (3–14 characters) and `DEFAULT_AGENT_FACTION`
   (e.g. `COSMIC`) to the deliberate choices. Preserve unrelated configuration.
   Keep the file private (`chmod 600 .env`). Never paste credentials into shell
   arguments, screenshots, tickets or logs; do not use shell tracing. The legacy
   `--account-token` flag exists, but the private file is the recommended path.
4. Clear stale exported overrides in this shell, then register **once**:

   ```sh
   unset ST_TOKEN SPACETRADERS_ACCOUNT_TOKEN
   unset DEFAULT_AGENT_SYMBOL DEFAULT_AGENT_FACTION
   .venv/bin/python -m py_st agent register
   ```

   Non-secret `--symbol` and `--faction` flags can override the saved defaults.
   The command POSTs `/v2/register`, invalidates the entire legacy JSON cache
   (`ST_CACHE_DIR/data.json`, default `.cache/data.json`), then atomically saves
   the agent token as `ST_TOKEN` in **this working directory's `.env`**, mode
   0600. It does not search parent directories. Cache removal must succeed before
   the saved identity changes. `--clear-cache` was removed: clearing is mandatory.
   Keep the same exported `ST_CACHE_DIR` as other clients if using a custom cache.
5. A successful registration exits 0 with **Verification pending** and prints a
   credential-free command with the returned symbol/faction. Run that command
   immediately (or replace the placeholders below with your chosen values):

   ```sh
   .venv/bin/python -m py_st agent verify-registration \
     --symbol YOUR_SYMBOL --faction YOUR_FACTION
   ```

   This reads `ST_TOKEN` directly from the working directory's `.env`, ignoring
   exported `ST_TOKEN`. It bypasses all caches and uses only GET `/my/agent`,
   GET `/my/ships` and GET `/my/contracts` (including pagination). It checks the
   expected identity/faction, fleet ownership/count, a command ship and a
   starting-faction contract. It reports HQ, credits, ship roles/locations and
   contract acceptance/fulfillment without printing credentials. Review the
   starter state: current docs describe 175,000 credits, a command ship, a probe
   and an unaccepted contract. Counts/credits are reported rather than hard-coded
   as eternal game rules. No contract is accepted and no ship is moved.
6. Proceed only after verification exits 0 and the state matches expectations.
   Unset old `ST_TOKEN` overrides in every application shell and restart clients
   deliberately so they load the saved token. New reset/agent state still needs
   the separately reviewed [live setup](FLIGHT_OPERATIONS.md#live-setup-separate-verification).
   Do not remove STOP, reuse old queued work or treat registration as permission
   to resume automation. Old scoped history stays available as evidence.

## Failure and recovery

- **Argument/configuration failure:** no registration request is sent. Fix the
  named setting; CLI usage errors exit 2, operational failures exit 1.
- **API rejection, timeout, 5xx or malformed response:** the saved token, legacy
  cache and durable runtime state are unchanged. A timeout or unusable response
  can mean the pilot was created remotely. Check the account dashboard before
  retrying. On 401/4113 check the **account** credential and reset status; do not
  repeat registration automatically. Raw server/error payloads are not printed.
- **Pilot registered remotely, local activation failed:** no new token was
  published to `.env`. Cache may already be empty. Do not register again. Fix
  filesystem permissions/disk space, recover or regenerate the existing pilot's
  agent token in the account dashboard, and save it privately. With all clients
  still stopped, this prompted command clears cache strictly before saving the
  recovered token atomically (input is hidden and absent from argv/history):

  ```sh
  .venv/bin/python -c 'from getpass import getpass; from py_st import cache; from py_st.env import save_agent_token; token = getpass("Recovered agent token: "); cache.clear_cache(strict=True); save_agent_token(token)'
  ```

  Then run `agent verify-registration` for the expected identity/faction.
- **Verification failure:** keep gameplay stopped. Check `.env`, expected pilot,
  account/reset status and connectivity; recover that pilot's token if needed.
  Rerun verification, not registration. Verification changes no local game state.
- **Process interruption:** inspect the saved credential through verification
  and inspect the account dashboard before retrying registration. The remote
  POST and local file replacement cannot form one transaction. A crash can leave
  private temporary files, but cannot publish a partially written `.env`.
- **Rollback:** a real registration cannot be undone locally. Restore the prior
  private token configuration only if that prior pilot is still valid and is
  intentionally selected; clear legacy cache strictly and verify that identity.
  Otherwise recover the new pilot. Never restore old unscoped cache across a
  reset. Preserve `.state` and STOP; restoring old tokens cannot revive reset
  history or authorize replaying old mutations.

## Offline evidence and contract inspection

Checked 2026-09-13 against official `SpaceTradersAPI/api-docs` revision
`45fbb04130aca3fa0bd9a634ab77b35fa6c468ab`, OpenAPI **2.3.0**:
[registration contract](https://github.com/SpaceTradersAPI/api-docs/blob/45fbb04130aca3fa0bd9a634ab77b35fa6c468ab/reference/SpaceTraders.json),
[interactive spec](https://docs.spacetraders.io/openapi),
[server resets](https://docs.spacetraders.io/server-resets).

The request requires symbol/faction and AccountToken Bearer authentication;
HTTP 201 wraps agent, contract, faction, **ships array** and token in `data`.
The spec's `required` list still says singular `ship`, inconsistent with its
defined `ships` property. The manual wrapper follows the defined array; generated
Agent, Contract, Faction and Ship fields/requiredness match their official models
and were not hand-edited. Optional reservation email is not exposed by this CLI.

`tests/test_registration.py` rehearses the real CLI/services/HTTP stack with
synthetic non-credential sentinels, including persisted-token verification,
stale-cache removal, failures and atomic file replacement. Run from this checkout
with the existing `.cache/nightly` parent:

```sh
ST_LIVE_TESTS=0 TMPDIR="$PWD/.cache/nightly" \
  ST_CACHE_DIR=.cache/nightly/fos-77-cache \
  .venv/bin/python -m pytest tests/test_registration.py \
  tests/test_services_agent.py tests/test_client_unit.py -q \
  --basetemp=.cache/nightly/fos-77-focused
```
