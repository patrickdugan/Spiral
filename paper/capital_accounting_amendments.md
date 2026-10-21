# Proposed capital-accounting amendments

These are proposed edits supported by the
[reference machine](../audit/peer_review/capital_state_machine.md), its falsification
tests and [pinned source inspection](../audit/peer_review/capital_adapter.md).
An [owned regtest trace](../audit/peer_review/capital_regtest_report.md) now supplies
transaction-level evidence. Numerical comparison tables remain unchanged pending
complete normalization and operational-clock measurements.

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
6. **Publish service denominators and terminal exposures.** Record offered
   demand before admission, retain rejected requests in the offered denominator,
   and show achieved delivery alongside every ratio. Keep unresolved recovery
   right-censored. Integrate changes at observed transition times; a coarse
   simulation step must not charge or forgive an entire interval incorrectly.
7. **Separate observations from forecasts.** Current new lifecycle figures are
   synthetic reference-model results. A separate pinned regtest run proves
   original-output recovery and independent round reuse, with every fixture sat
   reconciled. Its blocks were accelerated and sweeps manually triggered. No new
   Ark-versus-channel efficiency ranking follows until the observed path passes
   the reducer and matched-service comparisons are rerun with appropriate clocks.
8. **Disclose reorg uncertainty.** Replaying a Bitcoin branch must not undo an
   already executed Lightning payment. Where surviving contingent liabilities
   cannot be reconstructed, publish the unresolved evidence and halt spending;
   do not silently remove outflows to restore a conservation identity.
