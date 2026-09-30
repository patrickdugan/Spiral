import { test } from "node:test";
import assert from "node:assert/strict";
import { ArkServer, DEFAULT_SERVER, channelLiquidityDuration, rng } from "./server.ts";

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
  assert.equal(S.liquidityDuration(), 50);
});

/**
 * §3.3 corner test. Same demand fed to both objects. This is a qualitative witness of the ratio's
 * direction on two constructed corners, not a reproduction of any published figure.
 */
function corner(kind: "many-bursty" | "few-steady", seed: number) {
  const r = rng(seed);
  const lifetime = 4032;
  const horizon = 8 * lifetime;         // long against the VTXO lifetime
  const roundBlocks = 6;
  const steps = horizon / roundBlocks;
  const agents = kind === "many-bursty" ? 200 : 3;
  const perAgent = new Map<string, Array<{ out: number; in: number }>>();
  for (let a = 0; a < agents; a++) perAgent.set(`a${a}`, []);
  const S = new ArkServer(Number.MAX_SAFE_INTEGER / 4, { lifetimeBlocks: lifetime, roundInterval: roundBlocks, refreshLead: 288 });
  for (let t = 0; t < steps; t++) {
    for (const [name, arr] of perAgent) {
      let out = 0, inn = 0;
      if (kind === "many-bursty") {
        // Rare, large, idiosyncratic outflows funded by earlier inflows; per-agent envelope ≫ per-agent volume per step.
        if (r() < 0.02) inn = 5_000;
        if (r() < 0.01) out = 4_000;
      } else {
        // Steady bidirectional flow with fixed counterparties, recycling within the day.
        out = 100 + Math.floor(r() * 10); inn = 100 + Math.floor(r() * 10);
      }
      arr.push({ out, in: inn });
      if (inn) S.receive(name, inn);
      if (out && S.holderValue(name) >= out) S.spendLightning(name, out);
    }
    S.advance(roundBlocks);
  }
  const ch = channelLiquidityDuration(perAgent, horizon, 0.25);
  return { dV: S.liquidityDuration(), dC: ch.duration, failures: ch.failures };
}

test("§3.3 direction: Ark favored on many-bursty-long, channel favored on few-steady-recycling", () => {
  const mb = corner("many-bursty", 1);
  const fs = corner("few-steady", 2);
  assert.ok(Number.isFinite(mb.dV) && Number.isFinite(mb.dC) && Number.isFinite(fs.dV) && Number.isFinite(fs.dC));
  assert.ok(mb.dC / mb.dV > 1, `expected ratio > 1 on many-bursty, got ${mb.dC / mb.dV}`);
  assert.ok(fs.dC / fs.dV < 1, `expected ratio < 1 on few-steady, got ${fs.dC / fs.dV}`);
});
