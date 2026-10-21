# Proposed capital-accounting amendments

These are proposed edits supported by the
[reference machine](../audit/peer_review/capital_state_machine.md), its falsification
tests and [pinned source inspection](../audit/peer_review/capital_adapter.md).
An [owned regtest trace](../audit/peer_review/capital_regtest_report.md) now supplies
transaction-level evidence and an accepted economic reducer replay. Numerical
comparison results now include explicit recovery-clock assumptions and a
separate frozen-budget, fee-aware campaign.

The [paired structural sensitivity](../audit/peer_review/capital_comparison.md)
now reruns the four demand families with retained change and explicit recovery
delays. With a six-block detection-gap assumption, fronting falls relative to
the old model in all four families. At a 144-block stress delay, the accumulating
case instead rises about 24%. Zero initial balances miss the 99% delivery target
in the balanced and draining families despite oracle capacity. These fee-free
component results neither include round overhead nor establish an overall
efficiency ranking.

The [fee-aware comparison](../audit/peer_review/capital_fixed_budget_results.md)
uses committed pilot budgets, fresh holdout seeds, zero/250,000-sat initial
balances, exact holder-fee arithmetic and a declared single-participant
transaction-cost policy. Of 384 Ark runs, 148 meet the 99% value-delivery target.
Balanced pre-funded and both accumulating cells pass on all 24 seeds; the
pre-funded draining cell passes on only two. Small steady receipts cannot
support the fee plus a fresh round output under this policy. On eligible pairs,
Ark's fixed funding per delivered sat is about 3.97–7.16 times the comparator's.
This result is sensitive to the explicitly unamortized receipt/refresh costs,
fixed directional buffers and instantaneous settlement assumption. It does
not establish a general ranking for deployed, batched Ark. Publish the failures,
conditional sample counts, separate fee spend and terminal expired claims with
the ratios; do not promote passing a payment target into a redemption guarantee.

1. **Define the economic boundary before adding capital terms.** A VTXO is a
   claim against backing, not an extra asset. A channel funding output and the
   operator's attributable share cannot both enter total capital. Report
   unique-asset coverage, directional provisioning, and fronting as separate
   categories; add them only after proving their underlying coverage disjoint.
2. **Replace settlement/expiry-as-recovery language.** Payment settlement fixes
   the external outcome. Expiry can make a recovery action eligible. Neither
   proves finality, ownership, spendability or independent reuse. State the
   relevant policy, transaction ancestry, active-chain finality and reuse event.
   Pinned Bark source has distinct expiry and HTLC claim policies; a single
   fixed recovery rule is a forecast parameter until observed.
3. **Use gross inputs and explicit change.** A 600-sat payment consuming a
   1,000-sat VTXO may require 1,000 sats of gross fronting with 400 sats of new
   change backing. Routing fees and retained service fees are separate: only
   external fees leave the operator's economic boundary.
   The observed Bark run instead retained 39,115 sats of change on the original
   board after a 60,000-sat payment and 555-sat service fee. Fresh backing arrived
   only with a later refresh. Do not apply the abstract full-input fronting rule
   to that path. Account for round overhead and miner fees separately as well.
4. **Keep stock and cumulative throughput separate.** `W = F-C <= B` is
   pointwise. The tested reference trace has `B=1000`, `F=2000`, `C=1000`, and
   `W=1000` after a provenance-checked second payment. This is a finite model
   witness of capital recycling, not a measured capital-efficiency gain.
5. **State the cost of failed attempts.** A failed/expired invoice does not
   automatically release reserves. Release needs protocol revocation or a
   proven timeout/chain resolution. Bark's attempt status is not authoritative
   for settlement, so status-only accounting can prematurely release funds.
   The [observed failure extension](../audit/peer_review/capital_failure_report.md)
   now confirms two cooperative revocations with zero charged fees despite
   83/84-sat admission quotes. One 1,001-sat HTLC reduced CLN spendable capacity
   by 1,428 sats; actual principal, routing allowance and channel headroom must
   be recorded separately. New refund/change claim IDs replace the consumed
   inputs, including subdust outputs, while preserving the same backing.
6. **Publish service denominators and terminal exposures.** Record offered
   demand before admission, retain rejected requests in the offered denominator,
   and show achieved delivery alongside every ratio. Keep unresolved recovery
   right-censored. Integrate changes at observed transition times; a coarse
   simulation step must not charge or forgive an entire interval incorrectly.
7. **Separate observations from forecasts.** Current new lifecycle figures are
   synthetic reference-model results. A separate pinned regtest run proves
   original-output recovery and independent round reuse, with every fixture sat
   reconciled. Its blocks were accelerated and sweeps manually triggered. No new
   general Ark-versus-channel efficiency ranking follows from the conditional
   fixed-budget forecast. The
   observed path now passes economic reducer replay, while its exact acceptance
   and commitment times remain interval-censored.
8. **Disclose reorg uncertainty.** Replaying a Bitcoin branch must not undo an
   already executed Lightning payment. Where surviving contingent liabilities
   cannot be reconstructed, publish the unresolved evidence and halt spending;
   do not silently remove outflows to restore a conservation identity.

9. **Distinguish receipt liquidity from pool-backed claims.** The subsequent
   observed inbound path receives 2,000 sats into the server's channel, retains
   a 104-sat service fee, and issues a 1,896-sat holder claim against an existing
   20,000-sat pool root. Its two-leaf funding transaction costs 617 sats and has
   no extra 330-sat root surplus. This differs from the frozen forecast's
   single-participant fresh-round-per-receipt assumption. Do not generalize
   that conditional ranking to inventory-based receives.
10. **Distinguish economic pool change from selectable inventory.** The same
    receive creates 8,104 sats of change that the pinned implementation excludes
    because exit depth 4 exceeds the configured cap of 3. It remains backed and
    locked until recovery; only the untouched 10,000-sat leaf is immediately
    selectable. Incoming channel liquidity is a contribution, not recovery of
    earlier fronting. See [the inbound report](../audit/peer_review/capital_inbound_report.md).
11. **Cooperative exit can require additional fronting.** The observed
    18,632-sat offboard uses server wallet capital to pay 15,732 sats to the
    client, spend 1,973 sats on a miner fee and lock a 330-sat connector. The
    original shared backing remains unspent. Its signed 18,962-sat forfeit is
    a recovery right spanning existing backing and connector value, not a
    second asset. Record 18,035 sats of additional fronting and no recovery
    credit at this event; retain both maturities and unclosed obligations.
    See [the exit report](../audit/peer_review/capital_exit_report.md).
