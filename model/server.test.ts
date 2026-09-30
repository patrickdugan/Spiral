import { test } from "node:test";
import assert from "node:assert/strict";
import { ArkServer, DEFAULT_SERVER, runCorner, type CornerParams } from "./server.ts";

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
