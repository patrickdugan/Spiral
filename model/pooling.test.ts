import { test } from "node:test";
import assert from "node:assert/strict";
import { poolingSample, poolingTable, spendProbability, GRID_BURST, GRID_ROUNDS } from "./pooling.ts";

test("pooling scale (Remark 1): √N for signed imbalance, a constant near π/2 for agents that start from nothing, one under a shared drift", () => {
  // The demand law is the grid's: zero drift means E[out] = E[in] = 100 sat a round.
  assert.equal(spendProbability({ driftPerRound: 0, burst: GRID_BURST }), 0.025);
  assert.equal(spendProbability({ driftPerRound: 60, burst: GRID_BURST }), 0.01);

  const rows = poolingTable([1, 4, 16, 64, 200], GRID_ROUNDS, 12);
  const byN = new Map(rows.map((r) => [r.agents, r]));

  // One agent: both stocks are the same number.
  assert.equal(byN.get(1)!.reflected, 1);
  assert.equal(byN.get(1)!.signed, 1);

  // Signed: the ratio grows like √N. Divided by √N it stays within a band, and quadrupling N about doubles it.
  for (const n of [16, 64, 200]) {
    const v = byN.get(n)!.signedOverSqrtN;
    assert.ok(v > 0.7 && v < 1.3, `signed/√N at N=${n} is ${v}`);
  }
  const quad = byN.get(64)!.signed / byN.get(16)!.signed;
  assert.ok(quad > 1.7 && quad < 2.3, `signed ratio N=64 over N=16 is ${quad}, expected about 2`);

  // Reflected: the ratio rises from one and saturates at a constant; the remark's limit is π/2 ≈ 1.571.
  const r16 = byN.get(16)!.reflected, r64 = byN.get(64)!.reflected, r200 = byN.get(200)!.reflected;
  assert.ok(r16 > 1.2 && r16 <= r64 + 0.05 && r64 <= r200 + 0.05, `reflected ratios ${r16}, ${r64}, ${r200} should not fall with N`);
  assert.ok(r200 > 1.35 && r200 < 1.8, `reflected ratio at N=200 is ${r200}, expected near π/2`);
  // ...and is well short of √N, which would be 14 at N=200.
  assert.ok(r200 < byN.get(200)!.signed / 4);

  // Shared drift: every agent accumulates, nothing nets, the pool holds the sum of the peaks.
  assert.ok(byN.get(200)!.sharedDrift < 1.15, `shared-drift ratio at N=200 is ${byN.get(200)!.sharedDrift}`);

  // The reflected sample is the same construction as the paper's walks figure (grid.ts): four agents, 400 rounds.
  const four = poolingSample({ agents: 4, rounds: 400, seeds: 1, seed0: 11, driftPerRound: 0, burst: GRID_BURST, reflected: true });
  assert.ok(four.ratio > 1 && four.ratio < 2);
});
