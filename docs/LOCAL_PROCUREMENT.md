# Stationary Multi-Good Procurement

## Supported Workflow

This executor handles one contract with multiple distinct delivery goods at a
single marketplace. The selected ship must already be stationary there in CRUISE.
Every term's destination and the acquisition source must equal that market.
It can dock, accept, buy, deliver and fulfill through the existing bounded,
journaled Session. It never navigates, changes flight mode, or refuels.

```sh
# Live GET-only preview, not offline:
.venv/bin/python -m py_st auto contract SHIP CONTRACT_ID --seconds 600 --actions 30
# Only after inspecting the complete plan and deliberately clearing STOP:
.venv/bin/python -m py_st auto contract SHIP CONTRACT_ID --execute --seconds 600 --actions 30
```

The CLI selects this service automatically for multiple terms. Remote multi-good
and multi-destination execution remain unsupported. Duplicate terms for the same
good are rejected: the API delivery payload names the good but not a term, so
the service does not invent allocation semantics. Single-good workflows remain
available through the same command.

## Funding and Batches

Before acceptance the service requires positive quotes and volume for every good
still needing acquisition. It preserves 50,000 credits plus a 1,000 allowance
plus all remaining goods priced at original 20% purchase ceilings. It does not
rely on acceptance or fulfillment rewards to finance those obligations. The
complete unaccepted contract must have a positive conservative margin.

Already-owned matching goods are allocated once and reduce acquisition needs.
Unknown goods, excess inventory and inconsistent cargo totals stop the workflow.
Other nonclosed positions or accepted unfulfilled contracts block it. A pending
mutation blocks all further execution until explicit reconciliation.

The ship delivers after each purchase before buying another batch. Consequently,
80 units with a 40-unit hold and 30-unit volume are bought as `30, 30, 20`, not
two completely filled cargo loads. There is no travel fuel cost because the
ship never leaves the market. This is not a fuel-recovery plan for later travel;
the ordinary allowance remains protected.

## Restart and Evidence

The execution position is `procurement:CONTRACT_ID`, marked `local-multi`, and is
persisted before the first mutation. Its original ship, market, required goods,
payments, deadline and per-good ceilings cannot be replaced by a later preview.
An accepted contract without this original multi-good plan stops for review.

Each iteration uses freshly observed contract progress and cargo. It rechecks
eligibility after quote/funding reads and refuses changed terms, cargo, movement,
mode, obligations, positions or inadequate credits. Acquisition requires a
one-hour delivery margin. Evidence age, acceptance expiry and the applicable
deadline also bound transport pacing/retry waits; the original Session deadline
is restored after the mutation attempt. Unknown responses remain pending.

Owned cargo is delivered before requesting further acquisition quotes. Once all
goods are delivered, fulfillment needs neither prices nor purchase liquidity,
but still requires the actual deadline and original identity to be valid.
The service closes the original position after observing fulfillment.

Rerun the original contract command after reviewing a normal interruption, or
opt into `auto pilot SYSTEM --recover-contracts` to recover the original position
under the runner's shared bounds. That option does not choose new contracts and
can accept only the original saved execution intent when execution is authorized.
No offline `contract-model` output or GUI draft is execution authority.

The dashboard shows per-good remaining/held/to-acquire quantities and the saved
intent; `auto doctor` reports procurement recovery rather than treating the
position as an unrecognized strategy. These remain recorded observations, not
proof of live readiness.

## Abandon an Unaccepted Intent

If the original intent has become unsuitable, `auto abandon-procurement` can
release its local reservation without editing SQLite manually. This is not a
game-contract cancellation. It leaves the offer, ship and cargo unchanged.

```sh
# Live GET-only preflight; no closure yet:
.venv/bin/python -m py_st auto abandon-procurement CONTRACT_ID
# Explicit local ledger update after review; still no game POST permission:
.venv/bin/python -m py_st auto abandon-procurement CONTRACT_ID --execute --reason "Expired offer; release the unaccepted procurement intent."
```

The command requires one original open procurement position, a uniquely observed
unaccepted/unfulfilled contract, and its original empty ship stationary at source.
Other nonclosed exposure, accepted obligations or scoped pending actions block it.
Any potentially successful acceptance receipt for this contract in the same scope
also blocks abandonment, including reviewed or unrecognized outcomes. That query
is not limited to the most recent 200 journal rows. Other reset/agent scopes do
not contaminate this decision. Fresh state and the exact saved position are
rechecked before closure; a reason of at least 20 characters is required.
For multi-good intents, both the immutable initial plan and latest per-good
progress must show zero held cargo and the full original quantities still needing
acquisition. Missing, malformed or contradictory saved progress blocks abandonment
even when the latest ship observation says the hold is empty.

Abandonment appends a closed position with its reason and original plan intact.
It never deletes evidence, clears pending actions, or invokes game mutations.
Repeating the operation is harmless. An abandoned intent cannot be resumed by
`auto contract` or pilot, even if reported terms change to another supported
strategy. It releases this intent for other work; it does not create a new plan
or authorize another attempt at the abandoned contract.

## Validation Limits

Synthetic tests exercise interruption after every action, fresh Session recovery,
uncertain outcomes, market/credit/eligibility changes and real HTTP transport
pacing using mock responses. This increment has not been exercised live. No
SQL schema migration is needed. Do not use older code that does not recognize
`local-multi` to recover a new open multi-good position.

## Remote Recovery Follow-Up

Remote execution remains single-good/single-load. Before acquisition it now
revalidates contract identity/terms, other obligations, hauler cargo/fuel/navigation,
destination observer, position records, pending actions and credits after quote
reads. Quote age, acceptance expiry and the delivery-planning margin also bound
transport pacing and retries. Invalid acceptance expiry cannot authorize a POST.
Source-goods and destination-fuel quotes must each be uniquely present with
positive integer prices and trade volume; ambiguous/malformed evidence stops.

Arrival polling discards pre-wait contract evidence. After navigation and docking,
the remote loop reobserves obligations before its next preparation/delivery action.
Delivery and fulfillment transport waits are bounded by the actual contract deadline;
the enclosing Session budget is restored on exit. Conflicting fulfillment progress
and invalid delivery quantities cannot close a saved intent. These are synthetic
regression results; current remote guards still need a fresh bounded live validation.
Closed or unrecognized remote intent and mismatched original contract identity also
stop recovery rather than recreating acquisition authority from fresh offers.
