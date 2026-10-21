import { test } from "node:test";
import assert from "node:assert/strict";
import { ArkServer, DEFAULT_SERVER, channelLiquidityDuration, hyperedgeLiquidityDuration, runCorner, type CornerParams } from "./server.ts";

test("oracle provisioning covers receipt-first peaks and preserves a rejected spend's balance", () => {
  const roundTrip = new Map([["a", [{ in: 10, out: 10 }]]]);
  assert.deepEqual(channelLiquidityDuration(roundTrip, 1, 0), { duration: 0.5, failures: 0, locked: 10 });
  assert.deepEqual(hyperedgeLiquidityDuration(roundTrip, 1, 1, 0), { duration: 0.5, failures: 0, locked: 10 });
  const rejectedSpend = new Map([["a", [{ in: 5, out: 7 }, { in: 5, out: 5 }]]]);
  // First spend is rejected as a whole, so the second receipt raises holdings from 5 to 10.
  assert.deepEqual(channelLiquidityDuration(rejectedSpend, 2, 0), { duration: 20 / 15, failures: 1, locked: 10 });
  assert.deepEqual(hyperedgeLiquidityDuration(rejectedSpend, 1, 2, 0), { duration: 20 / 15, failures: 1, locked: 10 });
  const trailing = { kind: "trailing", intervalBlocks: 1, roundBlocks: 1 } as const;
  const repeated = new Map([["a", [{ in: 10, out: 10 }, { in: 10, out: 10 }, { in: 10, out: 10 }]]]);
  assert.equal(channelLiquidityDuration(repeated, 3, 0, trailing).failures, 0);
  assert.equal(hyperedgeLiquidityDuration(repeated, 1, 3, 0, trailing).failures, 0);
});

test("oracle forecasts add no receipt failures on exhaustive small demand paths", () => {
  // Independent unconstrained holder ledger: only an unaffordable outgoing request may fail.
  // Every 5-round path over {no event, receipt, spend, both} is checked at zero margin.
  const choices = [{ in: 0, out: 0 }, { in: 2, out: 0 }, { in: 0, out: 3 }, { in: 2, out: 3 }];
  for (let mask = 0; mask < 4 ** 5; mask++) {
    let code = mask, balance = 0, expectedFailures = 0;
    const steps = [];
    for (let i = 0; i < 5; i++) {
      const s = choices[code % 4]!; code = Math.floor(code / 4); steps.push(s);
      balance += s.in;
      if (s.out > balance) expectedFailures += 1; else balance -= s.out;
    }
    const demand = new Map([["a", steps], ["b", [...steps].reverse()]]);
    let secondBalance = 0, secondFailures = 0;
    for (const s of [...steps].reverse()) {
      secondBalance += s.in;
      if (s.out > secondBalance) secondFailures += 1; else secondBalance -= s.out;
    }
    const c = channelLiquidityDuration(demand, 5, 0);
    const h1 = hyperedgeLiquidityDuration(demand, 1, 5, 0);
    const h2 = hyperedgeLiquidityDuration(demand, 2, 5, 0);
    assert.equal(c.failures, expectedFailures + secondFailures, `path ${mask}`);
    assert.deepEqual(h1, c);
    assert.equal(h2.failures, c.failures, `pooled path ${mask}`);
    assert.ok(h2.locked <= c.locked, `pooling stock on path ${mask}`);
  }
});

test("fronted capital recycles and lock integration is invariant to sweep-step size", () => {
  const params = { lifetimeBlocks: 5, roundInterval: 1, refreshLead: Number.NEGATIVE_INFINITY, spendLock: "expiry" } as const;
  const coarse = new ArkServer(10, params), fine = new ArkServer(10, params);
  for (const s of [coarse, fine]) { s.receive("a", 10); assert.ok(s.spendLightning("a", 10)); }
  coarse.advance(10);
  for (let i = 0; i < 10; i++) fine.advance(1);
  assert.equal(coarse.lockedIntegralBlocks(), 50);
  assert.equal(coarse.lockedIntegralBlocks(), fine.lockedIntegralBlocks());
  assert.equal(coarse.committed, 0);
  coarse.receive("a", 10); assert.ok(coarse.spendLightning("a", 10));
  assert.equal(coarse.volumeDelivered, 20); // cumulative delivery can exceed a 10-sat stock
  assert.ok(coarse.aggregateBoundHolds());
  assert.ok(coarse.holderBoundHolds("a"));
});

test("S2: per-holder and aggregate bounds hold; a coalition cannot exceed server capital by coordinating", () => {
  const S = new ArkServer(1_300_000, { ...DEFAULT_SERVER, refreshLead: Number.NEGATIVE_INFINITY }); // holders never refresh: isolate the sweep clock
  const holders = ["a", "b", "c", "d"];
  for (const h of holders) S.receive(h, 400_000);
  // Each holder can spend at most what it holds, and the server can front at most its uncommitted capital.
  let fronted = 0;
  const results = holders.map((h) => { const ok = S.spendLightning(h, 300_000); if (ok) fronted += 300_000; return ok; });
  assert.deepEqual(results, [true, true, true, false]); // fourth spend exceeds B_S − W_S
  assert.equal(S.committed, 3 * 400_000); // full inputs forfeited (300k spent + 100k change reissued from the front)
  assert.ok(S.aggregateBoundHolds());
  for (const h of holders) assert.ok(S.holderBoundHolds(h));
  // Liquidity returns only at expiry: nothing is recoverable before the lifetime passes.
  S.advance(DEFAULT_SERVER.lifetimeBlocks - 1);
  assert.equal(S.committed, 3 * 400_000);
  S.advance(1);
  assert.equal(S.committed, 0);
  assert.ok(S.spendLightning("d", 300_000));
});

test("S2 witness: forfeit locks the fronted value for the residual lifetime; refresh renews the lock", () => {
  const S = new ArkServer(10_000, { lifetimeBlocks: 100, roundInterval: 1, refreshLead: 10 });
  S.receive("h", 1_000);
  S.advance(50);
  assert.ok(S.spendLightning("h", 1_000));
  assert.equal(S.committed, 1_000);
  S.advance(49);
  assert.equal(S.committed, 1_000);
  S.advance(1);
  assert.equal(S.committed, 0);
  // liquidity duration = 1000 × 50 blocks / 1000 delivered = 50 blocks (residual lifetime at forfeit)
  assert.equal(S.liquidityDuration("out"), 50);
  // Under the round-recycle reading the same spend locks the fronted value for one round only.
  const R = new ArkServer(10_000, { lifetimeBlocks: 100, roundInterval: 1, refreshLead: 10, spendLock: "round" });
  R.receive("h", 1_000);
  R.advance(50);
  assert.ok(R.spendLightning("h", 1_000));
  R.advance(1);
  assert.equal(R.committed, 0);
  assert.equal(R.liquidityDuration("out"), 1);
});

/**
 * §3.3 grid (item 2 of §7). Same demand fed to both objects; the channel model uses the stated forecast
 * rule and the VTXO side is charged the server-tier inbound term of §3.4. Two constructed corners plus
 * drift and horizon variation. This is a qualitative witness of the ratio's direction, not a reproduction
 * of any published figure, and the direction it finds is conditional on the spend lock rule.
 */
const trailing = { kind: "trailing", intervalBlocks: 4032, roundBlocks: 6 } as const;
const many = (over: Partial<CornerParams>): CornerParams => ({
  agents: 200, horizonLifetimes: 8, driftPerRound: 0, burst: { vIn: 5000, vOut: 4000, pIn: 0.02 },
  margin: 0.25, forecast: trailing, volume: "both", serverTier: true, seed: 1, ...over,
});
const few = (over: Partial<CornerParams>): CornerParams => ({
  agents: 3, horizonLifetimes: 8, driftPerRound: 0, burst: { vIn: 0, vOut: 1, pIn: 0 }, steady: { base: 100, jitter: 10 },
  margin: 0.25, forecast: trailing, volume: "both", serverTier: true, seed: 2, ...over,
});

test("§3.3 direction under the expiry lock: with the server-tier term charged, the VTXO is not favored on any tested cell", () => {
  const cells = [
    many({ driftPerRound: 60, forecast: { kind: "oracle" } }), // the earlier draft's corner, corrected
    many({ driftPerRound: 60 }),
    many({}),
    many({ horizonLifetimes: 1 }),
    many({ driftPerRound: -30 }),
    few({}),
  ];
  for (const c of cells) {
    const x = runCorner(c);
    assert.ok(Number.isFinite(x.ratio));
    assert.ok(x.ratio < 1.1, `expiry lock, drift ${c.driftPerRound}, H ${c.horizonLifetimes}: ratio ${x.ratio.toFixed(2)}`);
  }
});

test("§3.3 direction under the round lock: VTXO favored on many-bursty with uncorrelated imbalance, not on correlated drift, not on few-steady", () => {
  const r = (c: CornerParams) => runCorner({ ...c, spendLock: "round" }).ratio;
  assert.ok(r(many({})) > 1, `zero drift: ${r(many({}))}`);
  assert.ok(r(many({ horizonLifetimes: 1 })) > 1);
  assert.ok(r(many({ driftPerRound: -30 })) > 1);
  const corr = r(many({ driftPerRound: 60 }));
  assert.ok(corr > 0.9 && corr < 1.2, `correlated drift: pooling has nothing to pool, got ${corr}`); // ≈ 1
  assert.ok(r(few({})) < 1, `few-steady: ${r(few({}))}`);
  assert.ok(r(few({ forecast: { kind: "oracle" } })) < 1);
});

test("§3.3 accounting: dropping the server-tier term or counting only outbound volume manufactures a large ratio on the drift corner", () => {
  const base = many({ driftPerRound: 60, forecast: { kind: "oracle" } });
  const full = runCorner(base).ratio;
  const noServer = runCorner({ ...base, serverTier: false }).ratio;
  const outOnly = runCorner({ ...base, serverTier: false, volume: "out" }).ratio;
  assert.ok(full < 1.1 && noServer > 20 && outOnly > 5, `${full} ${noServer} ${outOnly}`);
});

test("hyperedge (BIP 448 multiparty channel): k = 1 is the channel; the gain grows with group size, saturates near π/2 at zero drift, vanishes under shared drift, and carries no forfeit lock", () => {
  const oracle = { kind: "oracle" } as const;
  const ks = [1, 5, 20, 200];
  const o = runCorner(many({ forecast: oracle, hyperedgeSizes: ks }));
  assert.equal(o.hyperedge[0]!.dH, o.dC); // the same object, operation for operation
  assert.equal(o.hyperedge[0]!.failures, o.chFailures);
  const gain = o.hyperedge.map((h) => o.dC / h.dH);
  assert.ok(gain[1]! > 1.2 && gain[2]! > gain[1]! && gain[3]! > gain[2]!, `gain grows with k: ${gain}`);
  // Agents start from nothing, so balances are reflected at zero and do not net: the limit is π/2, not √N ≈ 14.
  assert.ok(gain[3]! < Math.PI / 2 + 0.05, `gain saturates: ${gain[3]}`);
  const drift = runCorner(many({ driftPerRound: 60, forecast: oracle, hyperedgeSizes: [200] }));
  const g = drift.dC / drift.hyperedge[0]!.dH;
  assert.ok(g > 0.95 && g < 1.1, `shared drift: nothing to pool, got ${g}`);
  // Under the trailing rule the capital is about the same and the gain is in receipts delivered.
  const t = runCorner(many({ hyperedgeSizes: ks }));
  const tGain = t.dC / t.hyperedge[3]!.dH;
  assert.ok(tGain > 0.9 && tGain < 1.1, `trailing capital ratio is about one, got ${tGain}`);
  const fails = t.hyperedge.map((h) => h.failures);
  assert.ok(fails[0]! > fails[1]! && fails[1]! > fails[2]! && fails[2]! > fails[3]! && fails[3]! >= t.arkFailures, `failures fall toward the VTXO's floor: ${fails} vs ${t.arkFailures}`);
  // At k = N the hyperedge pools what the server pools and locks nothing at forfeit.
  const round = runCorner(many({ forecast: oracle, spendLock: "round", hyperedgeSizes: [200] }));
  assert.ok(o.hyperedge[3]!.dH < 0.7 * o.dV, `expiry reading: ${o.hyperedge[3]!.dH} vs ${o.dV}`);
  assert.ok(Math.abs(round.hyperedge[0]!.dH / round.dV - 1) < 0.1, `round reading: ${round.hyperedge[0]!.dH / round.dV}`);
});
