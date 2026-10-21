import { test } from "node:test";
import assert from "node:assert/strict";
import { ArkServer, runCorner } from "./server.ts";
const params = { lifetimeBlocks: 10, roundInterval: 1, refreshLead: -Infinity, spendLock: "expiry", changeBacking: "retained", recoveryDelayBlocks: 3 } as const;

test("retained forecast commits 600 of a 1000 input and preserves change expiry through delayed recovery", () => {
  const s = new ArkServer(1000, params); s.receive("alice", 1000); s.advance(2);
  assert.ok(s.spendLightning("alice", 600)); assert.equal(s.committed, 600); assert.equal(s.holderValue("alice"), 400);
  s.advance(8); assert.equal(s.committed, 600); s.advance(3); assert.equal(s.committed, 0);
  assert.equal(s.lockedIntegralBlocks(), 6600); assert.equal(s.accountingDiagnostics().activeHolderBackingIntegral, 6400);
  assert.equal(s.accountingDiagnostics().F, 600); assert.equal(s.accountingDiagnostics().C, 600);
  // Disabling refresh leaves a live claim past expiry; do not promote the
  // abstract per-principal recovery forecast to physical root accounting.
  assert.equal(s.accountingDiagnostics().feeFreeRetainedOnchainBackingIntegral, null);
  assert.equal(s.accountingDiagnostics().peakOnchainBacking, 1000);
});
test("physical retained-root accounting deduplicates active and forfeited principal with timely refresh", () => {
  const s = new ArkServer(5000, { ...params, refreshLead: 2 }); s.receive("a", 1000); s.spendLightning("a", 600);
  s.advance(8); s.advance(5); const a = s.accountingDiagnostics();
  assert.equal(a.physicalPartitionValid, true); assert.equal(a.feeFreeRetainedOnchainBackingIntegral, 15000);
  assert.equal(a.peakOnchainBacking, 1400); assert.equal(a.W, 0); assert.equal(a.activeHolderValue, 400);
});
test("retained change refresh keeps original expiry despite later insertion", () => {
  const s = new ArkServer(5000, { ...params, refreshLead: 2 }); s.receive("a", 1000); s.advance(2); s.receive("b", 1000);
  assert.ok(s.spendLightning("a", 600)); s.advance(6);
  assert.equal(s.committed, 1000, "400 retained change refreshed at original expiry minus lead");
  assert.equal(s.accountingDiagnostics().activeHolderValue, 1400);
});
test("coarse and fine retained fronting integration agree across delayed sweep", () => {
  const coarse = new ArkServer(1000, params), fine = new ArkServer(1000, params);
  for (const s of [coarse, fine]) { s.receive("a", 1000); s.spendLightning("a", 600); }
  coarse.advance(20); for (let i = 0; i < 20; i++) fine.advance(1);
  assert.equal(coarse.lockedIntegralBlocks(), 7800); assert.equal(coarse.lockedIntegralBlocks(), fine.lockedIntegralBlocks());
  assert.deepEqual(coarse.accountingDiagnostics(), fine.accountingDiagnostics());
});
test("retained admission is atomic and does not need fresh backing for change", () => {
  const s = new ArkServer(600, params); s.receive("a", 1000); assert.ok(s.spendLightning("a", 600));
  const before = s.accountingDiagnostics(); assert.equal(s.spendLightning("a", 1), false); assert.deepEqual(s.accountingDiagnostics(), before);
  assert.equal(s.holderValue("a"), 400);
  assert.throws(() => new ArkServer(1000, { ...params, spendLock: "round" }), /no proved/);
});
test("matched retained forecast keeps common service denominators and terminal exposures", () => {
  const p = { agents: 3, horizonLifetimes: 2, lifetime: 600, roundBlocks: 6, driftPerRound: 0, burst: { vIn: 5000, vOut: 4000, pIn: .1 },
    margin: .25, forecast: { kind: "oracle" as const }, volume: "both" as const, serverTier: true, seed: 107, hyperedgeSizes: [1, 3] };
  const legacy = runCorner(p), retained = runCorner({ ...p, changeBacking: "retained", recoveryDelayBlocks: 6 });
  assert.equal(retained.events, legacy.events); assert.equal(retained.arkFailures, legacy.arkFailures); assert.equal(retained.chFailures, legacy.chFailures);
  assert.equal(retained.serverFailures, 0); assert.equal(retained.dC, legacy.dC);
  const a = retained.accounting!; assert.equal(a.F - a.C, a.W); assert.equal(a.unrecovered.reduce((n, x) => n + x.amount, 0), a.W);
  assert.ok(a.offeredVolume >= a.deliveredVolume); assert.equal(a.activeHolderValue, retained.finalHolderBalance);
});
