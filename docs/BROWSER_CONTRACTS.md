# Browser contracts

Contracts is a manual, browser-playable lifecycle over the same SQLite command
queue, single worker, mutation journal, request IDs and reconciliation rules as
flight and trading. The browser only submits typed intent. The worker refreshes
agent, fleet and contracts immediately before negotiation, acceptance, delivery
or fulfillment and blocks expired or changed state. A dispatched request with
an unknown result is never replayed automatically.

The acceptance preview is explicitly stored-data evidence. It lists dated known
source quotes and cargo across owned ships, while missing sources remain unknown.
It does not buy or fly. Accepted deliverables can be purchased through Markets;
those purchases retain the shared fixed credit floor and fuel reserve. Required
cargo remains protected from sale. Use Explorer for travel and Fleet for cargo.

Acceptance requires fresh detailed sources with enough observed trade volume for
the missing cargo, and credits covering procurement plus the fixed floor and
fuel reserve. Existing uncosted obligations block another acceptance. Cargo is
counted once across repeated-good delivery rows. The command persists a digest
of the reviewed terms, cargo, sources and credits; dispatch recomputes feasibility
and rejects changed evidence. Source estimates are not a live route guarantee.
Purchases subtract cargo already aboard from outstanding procurement needs.
Travel without paid refueling is allowed with active obligations; paid refueling
remains blocked until those obligations are costed.

## Offline walkthrough

Use the existing setup commands in [Flight operations](FLIGHT_OPERATIONS.md) to
create a new demo root, start the dashboard, and start the independent worker.
The synthetic world begins with `DEMO-CONTRACT-1`, a 20-unit IRON_ORE offer.

1. Open **Contracts**, choose the offer, and preview obligations and sourcing.
2. Accept it, then inspect the durable command in **Operations**.
3. In **Markets**, buy IRON_ORE. Use **Explorer** to travel to `X-DEMO-B2`,
   unchecking paid refueling while the obligation is open, and dock. Return to
   Contracts and submit a partial and then final delivery.
4. Fulfill after every row is complete; inspect realized receipts, credits and
   journal evidence in Operations/Reports.
5. To exercise unknown-outcome recovery, stop the worker, run the documented
   `lost-response` demo scenario, submit one mutation, and restart the worker.
   Operations will require reconciliation rather than replaying it.

STOP prevents new dispatch while queued work remains durable. Closing the page
does not stop the worker. Ordinary refresh/navigation preserves component form
state, but authoritative observations always replace safety decisions.

## Current limits and live verification

Source suggestions use only observed detailed markets and do not optimize a
multi-market route. Negotiation eligibility is conservative (owned stationary
ship and no accepted open contract); faction-headquarters behavior and exact
live API error/receipt variants still require credentialed owner verification.
No live calls, autonomous acceptance, procurement, or negotiation are performed
by the offline tests.
