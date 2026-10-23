// The scale of the pooling gain (paper, Remark 1 and tab:pool): sum of per-agent peaks against the peak of
// the sum, on the grid's own demand law. Three regimes are compared on the same increments:
//   reflected  — an agent spends only what it holds (the model's agents, which start from nothing); the ratio
//                should saturate at a constant near π/2 as N grows;
//   signed     — the imbalance may take either sign (agents holding reserves they can spend down); the ratio
//                should grow like √N;
//   shared drift — every agent accumulates together; the ratio should fall to one.
// Nothing here is proved; it is the Monte Carlo the remark's asymptotics are checked against.

import { rng } from "./server.ts";

export interface PoolingParams {
  agents: number;
  /** rounds per sample path; the grid's zero-drift cell runs 8 lifetimes of 4032 blocks at 6 blocks a round, 5,376 rounds */
  rounds: number;
  /** independent sample paths averaged */
  seeds: number;
  /** expected net inflow per agent per round in sat, as in CornerParams */
  driftPerRound: number;
  burst: { vIn: number; vOut: number; pIn: number };
  /** true: a spend from an insufficient balance fails and the balance stays (the model's agents) */
  reflected: boolean;
  seed0?: number;
}

export interface PoolingSample {
  /** mean over seeds of Σ_a max_t balance_a(t) */
  sumOfPeaks: number;
  /** mean over seeds of max_t Σ_a balance_a(t) */
  peakOfSum: number;
  /** ratio of the two means: the pooling gain per-agent stock / pooled stock */
  ratio: number;
}

/** The grid's demand law (server.ts runCorner): inflow vIn with probability pIn, outflow vOut with a probability set by the drift. */
export function spendProbability(p: { driftPerRound: number; burst: { vIn: number; vOut: number; pIn: number } }): number {
  return Math.max(0, Math.min(1, (p.burst.pIn * p.burst.vIn - p.driftPerRound) / p.burst.vOut));
}

export function poolingSample(p: PoolingParams): PoolingSample {
  const pOut = spendProbability(p);
  let sumOfPeaks = 0;
  let peakOfSum = 0;
  for (let s = 0; s < p.seeds; s++) {
    const r = rng((p.seed0 ?? 101) + s);
    const bal = new Array<number>(p.agents).fill(0);
    const peak = new Array<number>(p.agents).fill(0);
    let sumPeak = 0;
    for (let t = 0; t < p.rounds; t++) {
      let total = 0;
      for (let a = 0; a < p.agents; a++) {
        const inn = r() < p.burst.pIn ? p.burst.vIn : 0;
        const out = r() < pOut ? p.burst.vOut : 0;
        let b = bal[a]! + inn;
        if (p.reflected) { if (out <= b) b -= out; } else { b -= out; }
        bal[a] = b;
        if (b > peak[a]!) peak[a] = b;
        total += b;
      }
      if (total > sumPeak) sumPeak = total;
    }
    sumOfPeaks += peak.reduce((x, y) => x + y, 0);
    peakOfSum += sumPeak;
  }
  sumOfPeaks /= p.seeds;
  peakOfSum /= p.seeds;
  return { sumOfPeaks, peakOfSum, ratio: peakOfSum === 0 ? Infinity : sumOfPeaks / peakOfSum };
}

export interface PoolingRow {
  agents: number;
  reflected: number;
  signed: number;
  /** the signed ratio divided by √N; constant if the √N law holds */
  signedOverSqrtN: number;
  /** reflected walks under a shared drift of +60 sat a round, the grid's drift cell */
  sharedDrift: number;
}

export const GRID_BURST = { vIn: 5000, vOut: 4000, pIn: 0.02 } as const;
export const GRID_ROUNDS = (8 * 4032) / 6;

/** One row per population size, on the grid's zero-drift and +60 cells. */
export function poolingTable(sizes: number[], rounds = GRID_ROUNDS, seeds = 20): PoolingRow[] {
  return sizes.map((agents) => {
    const base = { agents, rounds, seeds, burst: GRID_BURST };
    const reflected = poolingSample({ ...base, driftPerRound: 0, reflected: true }).ratio;
    const signed = poolingSample({ ...base, driftPerRound: 0, reflected: false }).ratio;
    const sharedDrift = poolingSample({ ...base, driftPerRound: 60, reflected: true }).ratio;
    return { agents, reflected, signed, signedOverSqrtN: signed / Math.sqrt(agents), sharedDrift };
  });
}
