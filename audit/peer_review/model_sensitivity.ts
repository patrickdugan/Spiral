// Post hoc sensitivity of the corrected model, 2026-10-21. No node, wallet or network access.
// Reproduce all cells: node --experimental-strip-types audit/peer_review/model_sensitivity.ts
// For parallel jobs, use --cell zero|drain|accumulate|steady, then --combine <four JSON paths>.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runCorner, type CornerParams } from "../../model/server.ts";

const SEEDS = Array.from({ length: 24 }, (_, i) => i + 1);
const CELL_NAMES = ["zero", "drain", "accumulate", "steady"] as const;
type Cell = typeof CELL_NAMES[number];
type Stats = { n: number; mean: number; min: number; max: number; sd: number; mc95: [number, number] };

function summarize(values: number[]): Stats {
  assert.equal(values.length, 24);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const sd = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / (values.length - 1));
  const half = 2.0686576104190406 * sd / Math.sqrt(values.length); // t_23, .975
  return { n: values.length, mean, min: Math.min(...values), max: Math.max(...values), sd, mc95: [mean - half, mean + half] };
}

function params(cell: Cell, seed: number): CornerParams {
  const steady = cell === "steady";
  return {
    agents: steady ? 3 : 200, horizonLifetimes: 8,
    driftPerRound: cell === "drain" ? -30 : cell === "accumulate" ? 60 : 0,
    burst: steady ? { vIn: 0, vOut: 1, pIn: 0 } : { vIn: 5000, vOut: 4000, pIn: 0.02 },
    ...(steady ? { steady: { base: 100, jitter: 10 } } : {}),
    margin: 0.25, forecast: { kind: "oracle" }, volume: "both", serverTier: true, seed,
    spendLock: "expiry", hyperedgeSizes: steady ? [1, 3] : [1, 5, 20, 200],
  };
}

function runCell(cell: Cell) {
  const rows = SEEDS.map(seed => {
    const p = params(cell, seed);
    const expiry = runCorner(p);
    const round = runCorner({ ...p, spendLock: "round", hyperedgeSizes: [] });
    assert.equal(expiry.chFailures, expiry.arkFailures, `${cell}/${seed}: channel rejected extra events`);
    assert.equal(expiry.serverFailures, 0, `${cell}/${seed}: infeasible server forecast`);
    assert.equal(round.serverFailures, 0);
    assert.equal(round.arkFailures, expiry.arkFailures);
    assert.equal(round.chFailures, expiry.chFailures);
    assert.equal(round.events, expiry.events);
    assert.equal(round.dC, expiry.dC);
    for (const h of expiry.hyperedge) assert.equal(h.failures, expiry.arkFailures, `${cell}/${seed}/k${h.k}: pooled extra failures`);
    assert.equal(expiry.hyperedge[0]!.dH, expiry.dC);
    const pool = expiry.hyperedge.at(-1)!;
    const k5 = expiry.hyperedge.find(h => h.k === 5);
    const k20 = expiry.hyperedge.find(h => h.k === 20);
    const pooledGain = expiry.dC / pool.dH;
    const metrics: Record<string, number> = {
      channel_stock_per_agent_sat: expiry.chLocked / p.agents,
      issuance_stock_per_agent_sat: expiry.serverLocked / p.agents,
      C_over_HN: pooledGain,
      C_over_V_expiry: expiry.ratio,
      C_over_V_round_counterfactual: round.ratio,
      V_expiry_over_HN: expiry.dV / pool.dH,
      V_round_counterfactual_over_HN: round.dV / pool.dH,
      common_unaffordable_spend_fraction: expiry.arkFailures / expiry.events,
    };
    if (k5) metrics.C_over_H5 = expiry.dC / k5.dH;
    if (k20) {
      metrics.C_over_H20 = expiry.dC / k20.dH;
      metrics.fraction_of_full_pool_excess_gain_at20 = (metrics.C_over_H20 - 1) / (pooledGain - 1);
    }
    for (const v of Object.values(metrics)) assert.ok(Number.isFinite(v));
    return { seed, events: expiry.events, common_failures: expiry.arkFailures, metrics };
  });
  const keys = Object.keys(rows[0]!.metrics);
  return { cell, params: params(cell, 1), equal_service_checks_passed: true,
    summary: Object.fromEntries(keys.map(key => [key, summarize(rows.map(r => r.metrics[key]!))])), rows };
}

const args = process.argv.slice(2);
let cells: ReturnType<typeof runCell>[];
if (args[0] === "--combine") {
  assert.equal(args.length, 5, "provide the four independent cell JSON files");
  cells = args.slice(1).flatMap(path => JSON.parse(readFileSync(path, "utf8")).cells);
  assert.deepEqual([...cells.map(c => c.cell)].sort(), [...CELL_NAMES].sort());
  cells.sort((a, b) => CELL_NAMES.indexOf(a.cell) - CELL_NAMES.indexOf(b.cell));
} else {
  const selected = args[0] === "--cell" ? [args[1] as Cell] : [...CELL_NAMES];
  for (const cell of selected) assert.ok(CELL_NAMES.includes(cell));
  cells = selected.map(runCell);
}
process.stdout.write(JSON.stringify({
  date: "2026-10-21", status: "post_hoc_model_sensitivity",
  baseline_commit: "6a9df365f727cf2471ae52e00b36e8816d0081bc",
  model: "corrected receipt-first oracle peaks; unaffordable spends rejected in full; exact recovery integration",
  seeds: SEEDS, evidence_class: "synthetic_reference_model",
  interval: "two-sided 95% Student t interval for the model mean across 24 seed replicates (t_23); Monte Carlo precision conditional on this generator and model, not a mainnet estimate",
  caveats: ["Same oracle forecast and offered demand across mechanisms; oracle knows the entire horizon.",
    "All objects reject only the common unaffordable outgoing requests; server sizing diagnostic has zero failed events in every included cell.",
    "The one-round spend-recovery case is counterfactual. Refreshes still lock to expiry.",
    "Service fees, membership churn and correlated faults are not in the capital ratio.",
    "The small-group excess-gain fraction can be unstable when the full-pool gain is near one."],
  cells,
}, null, 2) + "\n");
