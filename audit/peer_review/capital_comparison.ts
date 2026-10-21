// Paired structural sensitivity, explicitly separate from economic replay and
// from a future frozen-budget service-target experiment. No network access.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { runCorner, type CornerParams } from "../../model/server.ts";
const dir = "audit/peer_review/capital/";
const machineBytes = readFileSync("audit/peer_review/regtest/evidence/machine-reconciliation.json");
const machine = JSON.parse(machineBytes.toString()); assert.equal(machine.economic_reconciliation, true);
const snapshot = JSON.parse(readFileSync("audit/peer_review/regtest/evidence/board-confirmed.json", "utf8"));
const proof = JSON.parse(readFileSync("audit/peer_review/regtest/evidence/reuse-proof.json", "utf8"));
const original = snapshot.bark_vtxos.find((v: any) => v.policy_type === "pubkey");
const detectedGap = proof.reuse_observed_height - original.expiry_height;
assert.equal(detectedGap, 6);
const seeds = Array.from({ length: 24 }, (_, i) => 101 + i);
const cells = ["zero", "drain", "accumulate", "steady"] as const;
type Cell = typeof cells[number];
function parameters(cell: Cell, seed: number): CornerParams {
  const steady = cell === "steady";
  return { agents: steady ? 3 : 200, horizonLifetimes: 8, lifetime: 4320, roundBlocks: 6,
    driftPerRound: cell === "drain" ? -30 : cell === "accumulate" ? 60 : 0,
    burst: steady ? { vIn: 0, vOut: 1, pIn: 0 } : { vIn: 5000, vOut: 4000, pIn: .02 },
    ...(steady ? { steady: { base: 100, jitter: 10 } } : {}), margin: .25, forecast: { kind: "oracle" }, volume: "both",
    serverTier: true, seed, spendLock: "expiry", hyperedgeSizes: steady ? [1, 3] : [1, 5, 20, 200] };
}
function stats(values: number[]) {
  const n = values.length, mean = values.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(values.reduce((s, x) => s + (x - mean) ** 2, 0) / (n - 1));
  const half = 2.0686576104190406 * sd / Math.sqrt(n);
  return { n, mean, min: Math.min(...values), max: Math.max(...values), mc95: [mean - half, mean + half] };
}
function runVariant(delay: number, p: CornerParams, baseline: ReturnType<typeof runCorner>, horizon: number) {
    const result = runCorner({ ...p, changeBacking: "retained", recoveryDelayBlocks: delay });
    assert.equal(result.events, baseline.events); assert.equal(result.arkFailures, baseline.arkFailures);
    assert.equal(result.chFailures, result.arkFailures); assert.equal(result.serverFailures, 0);
    assert.equal(result.dC, baseline.dC); assert.deepEqual(result.hyperedge, baseline.hyperedge);
    const a = result.accounting!; assert.equal(a.F - a.C, a.W);
    assert.equal(a.unrecovered.reduce((n, x) => n + x.amount, 0), a.W);
    const schedule: Record<string, number> = {};
    for (const entry of a.unrecovered) schedule[entry.recoveryHeight] = (schedule[entry.recoveryHeight] ?? 0) + entry.amount;
    const locked = result.dVForfeitOnly * a.deliveredVolume, legacyLocked = baseline.dVForfeitOnly * a.deliveredVolume;
    const channel = result.chLocked * horizon, pooled = result.hyperedge.at(-1)!.locked * horizon;
    // In this fee-free retained model, each onchain root is partitioned into
    // live holder principal and forfeited principal. Their coverage is disjoint.
    // The server's separately provisioned LN funding output is a distinct lot.
    assert.ok(a.physicalPartitionValid && a.feeFreeRetainedOnchainBackingIntegral !== null, "live expiry invalidates physical backing inference");
    const onchain = a.feeFreeRetainedOnchainBackingIntegral, serverChannel = result.serverLocked * horizon;
    const onchainProvisioned = a.peakOnchainBacking * horizon;
    assert.ok(onchainProvisioned >= onchain);
    return { delay_blocks: delay, evidence_class: "fee_free_structural_forecast", offered_sat: a.offeredVolume, delivered_sat: a.deliveredVolume,
      delivery_rate: a.deliveredVolume / a.offeredVolume, minimum_delivery_target: .99, target_met: a.deliveredVolume / a.offeredVolume >= .99,
      common_rejected_events: result.arkFailures, capacity_rejected_events_with_oracle: result.serverFailures,
      fronting_sat_blocks: locked, legacy_fronting_sat_blocks: legacyLocked, paired_fronting_change_sat_blocks: locked - legacyLocked,
      per_offered: { fronting_blocks: locked / a.offeredVolume, channel_blocks: channel / a.offeredVolume, pooled_blocks: pooled / a.offeredVolume },
      per_delivered: { fronting_blocks: locked / a.deliveredVolume, channel_blocks: channel / a.deliveredVolume, pooled_blocks: pooled / a.deliveredVolume },
      legacy_duration_index: baseline.dV, retained_duration_index: result.dV,
      duration_index_is_not_deduplicated_unique_capital: true,
      holder_claim_sat_blocks_not_independent_capital: a.activeHolderBackingIntegral,
      physical_resource_boundary: "onchain backing roots plus whole separately provisioned server LN channel; includes both channel sides, not operator-only ownership",
      unique_committed_resource_sat_blocks: onchain + serverChannel,
      idle_onchain_reserve_sat_blocks: onchainProvisioned - onchain,
      total_provisioned_resource_sat_blocks: onchainProvisioned + serverChannel,
      unique_resource_per_offered_blocks: (onchainProvisioned + serverChannel) / a.offeredVolume,
      unique_resource_per_delivered_blocks: (onchainProvisioned + serverChannel) / a.deliveredVolume,
      physical_channel_over_retained_resource: channel / (onchainProvisioned + serverChannel),
      terminal: { F_sat: a.F, C_sat: a.C, W_sat: a.W, active_holder_sat: a.activeHolderValue,
        unresolved_recovery_is_right_censored: true, forecast_subsequent_recovery_schedule: schedule } };
}
const cell = process.argv[2] as Cell; assert.ok(cells.includes(cell), "select zero|drain|accumulate|steady");
const began = performance.now();
const rows: { seed: number; variants: ReturnType<typeof runVariant>[] }[] = [];
for (const seed of seeds) {
  assert.ok(performance.now() - began < 30 * 60 * 1000, "30-minute per-cell guard: four single-threaded cells fit two-hour campaign cap");
  const p = parameters(cell, seed), baseline = runCorner(p), horizon = p.lifetime! * p.horizonLifetimes;
  const variants = [detectedGap, 144].map(delay => runVariant(delay, p, baseline, horizon));
  rows.push({ seed, variants }); console.log(JSON.stringify({ cell, seed, elapsed_seconds: Math.round((performance.now() - began) / 1000) }));
}
const result = { status: "paired_structural_sensitivity_not_final_matched_budget_acceptance", evidence_class: "implementation_informed_forecast",
  cell, parameters: parameters(cell, seeds[0]), seeds,
  observed_machine_sha256: createHash("sha256").update(machineBytes).digest("hex"), observed_machine_state_hash: machine.report.state_hash,
  observed_semantics: { retained_change: true, original_expiry_does_not_release_capital: true, detected_expiry_to_reuse_gap_blocks: detectedGap },
  interpretation: ["Six blocks is the detection gap in the manually swept regtest, not a sampled operational-delay distribution.",
    "144 blocks is a declared stress assumption; it was not measured.", "Both policies receive identical offered sequences and zero initial holder balances.",
    "Oracle provisioning uses future demand. Fixed pilot budgets and a predeclared service target remain a separate experiment.",
    "Fees and the observed 330-sat round-root overhead are omitted here to isolate change-backing and recovery-clock effects.",
    "The legacy duration index sums fronting and channel provisioning; it is not a deduplicated asset-union estimate.",
    "The separate physical-resource estimate partitions fee-free onchain roots into live and forfeited principal, then adds disjoint server-channel funding once; both sides of that channel are included.",
    "Its idle onchain reserve is the oracle peak backing budget less active backing. This is not the operator-only A boundary or a market funding-cost estimate.",
    "Receipt backing and automatic refresh remain aggregate model assumptions; the completed live trace verifies outgoing retained change and manual refresh.",
    "Future recovery schedule is a forecast, never a claim that terminal obligations have already recovered.",
    "This artifact does not by itself finish the requested capital-efficiency comparison."],
  summaries: [detectedGap, 144].map(delay => { const v = rows.map(r => r.variants.find(v => v.delay_blocks === delay)!); return {
    delay_blocks: delay, delivery_rate: stats(v.map(x => x.delivery_rate)), target_passes: v.filter(x => x.target_met).length,
    retained_over_legacy_fronting: stats(v.map(x => x.fronting_sat_blocks / x.legacy_fronting_sat_blocks)),
    paired_fronting_change_sat_blocks: stats(v.map(x => x.paired_fronting_change_sat_blocks)),
    fronting_per_offered_blocks: stats(v.map(x => x.per_offered.fronting_blocks)), fronting_per_delivered_blocks: stats(v.map(x => x.per_delivered.fronting_blocks)) }; }), rows };
writeFileSync(`${dir}structural-comparison-${cell}.json`, JSON.stringify(result, null, 2) + "\n");
