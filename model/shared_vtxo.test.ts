import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SharedVtxo, ParentBackingRegistry, canSpendPayout,
  destinationAllowlistOnly, exactEntitlementPolicy, validateEntitlements,
  type Entitlement, type RecoveryBundle,
} from "./shared_vtxo.ts";

const parties: Entitlement[] = [
  { holder: "alice", script: "p2tr:alice", sats: 60_000 },
  { holder: "bob", script: "p2tr:bob", sats: 40_000 },
];

function fixture(mode: "separate" | "joint-2of2" = "separate"): SharedVtxo {
  return new SharedVtxo({
    parentOutpoint: "funding-tx:0", backingSats: 100_000, entitlements: parties,
    payoutMode: mode, jointEscrowScript: mode === "joint-2of2" ? "2of2:alice:bob" : undefined,
    confirmedParentHeight: 100, csvBlocks: 12, expiryHeight: 200, fixedRecoveryFee: 2_500,
  });
}

const spend = (v: SharedVtxo, bundle: RecoveryBundle, height = 120, funds = 2_500) =>
  v.attemptExit(bundle, { height, externalFeeFunds: funds });

test("native destination allowlist permits an illicit reallocation; exact-value policy rejects it", () => {
  const permitted = new Set(["p2tr:alice", "p2tr:bob"]);
  const robbery = [{ script: "p2tr:alice", sats: 100_000 }];
  assert.equal(destinationAllowlistOnly(robbery, permitted), true);
  assert.equal(exactEntitlementPolicy(robbery, parties), false);
  assert.equal(exactEntitlementPolicy([
    { script: "p2tr:alice", sats: 60_000 }, { script: "p2tr:bob", sats: 40_000 },
  ], parties), true);
  assert.equal(exactEntitlementPolicy([
    { script: "p2tr:alice", sats: 61_000 }, { script: "p2tr:bob", sats: 39_000 },
  ], parties), false);
  assert.equal(exactEntitlementPolicy([
    { script: "p2tr:alice", sats: 60_000 }, { script: "p2tr:alice", sats: 40_000 },
  ], parties), false);
});

test("funding admission produces complete, fixed recovery before parent is committed", () => {
  const v = fixture();
  v.setOnline("sapio", false);
  assert.throws(() => v.fundWithPreparedRecovery(), /signers unavailable/);
  assert.throws(() => v.backupFor("alice"), /not funded/);
  v.setOnline("sapio", true);
  const first = v.fundWithPreparedRecovery();
  assert.equal(v.verifyBundle(first), true);
  assert.deepEqual(first.outputs, [
    { script: "p2tr:alice", sats: 60_000 },
    { script: "p2tr:bob", sats: 40_000 },
  ]);
  assert.throws(() => v.fundWithPreparedRecovery(), /already funded/);
});

test("either holder can publish preauthorized split recovery while both online services are dead", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  const aliceCopy = v.backupFor("alice");
  const bobCopy = v.backupFor("bob");
  v.setOnline("sapio", false);
  v.setOnline("ark", false);
  assert.equal(spend(v, aliceCopy, 111).state, "awaiting-maturity");
  assert.equal(spend(v, bobCopy, 120, 2_499).state, "awaiting-fees");
  const result = spend(v, bobCopy);
  assert.equal(result.state, "confirmed");
  assert.deepEqual(result.payouts, aliceCopy.outputs);
  assert.equal(result.payouts?.reduce((n, x) => n + x.sats, 0), 100_000);
  assert.equal(result.feePaid, 2_500);
  assert.equal(v.totalExternalFees, 2_500);
  assert.equal(spend(v, aliceCopy).state, "already-confirmed");
  assert.equal(v.totalExternalFees, 2_500);
});

test("a stale backup stays stale after a new transfer; the new copy is independently retrievable", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  const aliceOld = v.backupFor("alice");
  v.transfer("alice", "bob", 30_000, { approvals: ["alice"] });
  assert.equal(v.currentEpoch, 1);
  assert.deepEqual(v.currentEntitlements.map(x => x.sats), [30_000, 70_000]);
  assert.deepEqual(v.getBackup("alice", 0), aliceOld);
  assert.equal(v.getBackup("alice", 1), undefined);
  const bobNew = v.backupFor("bob");
  assert.equal(bobNew.epoch, 1);
  assert.deepEqual(bobNew.outputs.map(x => x.sats), [30_000, 70_000]);
});

test("a complete obsolete competing claim may win: conservation survives while current ownership fails", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  const old = v.backupFor("alice");
  v.transfer("alice", "bob", 30_000, { approvals: ["alice"] });
  const current = v.backupFor("bob");
  v.setOnline("ark", false);
  v.setOnline("sapio", false);
  const stale = spend(v, old);
  assert.equal(stale.state, "confirmed");
  assert.equal(stale.staleWon, true);
  assert.deepEqual(stale.payouts?.map(x => x.sats), [60_000, 40_000]);
  assert.equal(spend(v, current).state, "conflicted");
  assert.equal(stale.payouts?.reduce((n, x) => n + x.sats, 0), 100_000);
});

test("newer branch can win and irreversibly conflict the stale branch", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  const old = v.backupFor("alice");
  v.transfer("alice", "bob", 20_000, { approvals: ["alice"] });
  const current = v.backupFor("alice");
  assert.equal(spend(v, current).state, "confirmed");
  assert.deepEqual(v.confirmedRecovery?.outputs.map(x => x.sats), [40_000, 60_000]);
  assert.equal(spend(v, old).state, "conflicted");
  assert.throws(() => v.transfer("bob", "alice", 1_000, { approvals: ["bob"] }), /already recovered/);
});

test("no state transition crosses an incomplete or conditional recovery admission barrier", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  for (const nextRecovery of ["prepared", "conditional"] as const) {
    assert.throws(() => v.transfer("alice", "bob", 1_000, {
      approvals: ["alice"], nextRecovery,
    }), /successor recovery incomplete/);
    assert.equal(v.currentEpoch, 0);
    assert.deepEqual(v.currentEntitlements, parties);
  }
});

test("debits need owner's consent; signer outages block transfers without invalidating funded recovery", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  const old = v.backupFor("alice");
  assert.throws(() => v.transfer("alice", "bob", 1_000, { approvals: ["bob"] }), /approval missing/);
  v.setOnline("sapio", false);
  assert.throws(() => v.transfer("alice", "bob", 1_000, { approvals: ["alice"] }), /signers unavailable/);
  assert.equal(v.currentEpoch, 0);
  assert.equal(spend(v, old).state, "confirmed");
});

test("tampered outputs, beneficiary amount, epoch and script cannot replay as issued recovery", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  const bundle = v.backupFor("alice");
  const changes = [
    { ...bundle, outputs: [{ script: "p2tr:alice", sats: 100_000 }] },
    { ...bundle, outputs: [{ script: "p2tr:mallory", sats: 60_000 }, bundle.outputs[1]!] },
    { ...bundle, epoch: 99 },
    { ...bundle, parentOutpoint: "attacker:0" },
    { ...bundle, fixtureDigest: "00".repeat(32) },
  ];
  for (const modified of changes) {
    assert.equal(v.verifyBundle(modified), false);
    assert.equal(spend(v, modified).state, "incomplete");
  }
  assert.equal(v.verifyBundle(bundle), true);
});

test("unavailable ancestors and expired positions prevent a successful simulated recovery", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  const bundle = v.backupFor("bob");
  assert.equal(v.attemptExit(bundle, { height: 120, externalFeeFunds: 2_500, ancestorsAvailable: false }).state, "awaiting-ancestor");
  assert.equal(spend(v, bundle, 200).state, "expired");
  assert.equal(v.confirmedRecovery, undefined);
});

test("split recovery permits each beneficiary to spend only their own payout", () => {
  const v = fixture();
  v.fundWithPreparedRecovery();
  const bundle = v.backupFor("bob");
  assert.equal(spend(v, bundle).state, "confirmed");
  assert.equal(canSpendPayout("separate", new Set(["bob"]), parties, "bob"), true);
  assert.equal(canSpendPayout("separate", new Set(["bob"]), parties, "alice"), false);
  assert.equal(canSpendPayout("separate", new Set(["alice"]), parties, "alice"), true);
});

test("joint escrow exit survives service loss yet an uncooperative signer blocks individual spending", () => {
  const v = fixture("joint-2of2");
  v.fundWithPreparedRecovery();
  const prepared = v.backupFor("alice");
  v.setOnline("sapio", false);
  v.setOnline("ark", false);
  assert.equal(spend(v, prepared).state, "confirmed");
  assert.deepEqual(v.confirmedRecovery?.outputs, [{ script: "2of2:alice:bob", sats: 100_000 }]);
  assert.equal(canSpendPayout("joint-2of2", new Set(["alice"]), parties), false);
  assert.equal(canSpendPayout("joint-2of2", new Set(["alice", "bob"]), parties), true);
});

test("parent and child claims cannot both contribute eligible weight", () => {
  const r = new ParentBackingRegistry();
  r.enroll("p:0", 0, 100_000, parties);
  r.claimChild("p:0", 0, "alice", 60_000);
  r.claimChild("p:0", 0, "bob", 40_000);
  assert.equal(r.totalEligibleWeight(), 100_000);
  assert.throws(() => r.claimParent("p:0", 0), /already allocated/);
  assert.throws(() => r.claimChild("p:0", 0, "alice", 1), /exceeds canonical entitlement/);
});

test("multiple identity claims are capped by the canonical beneficiary allowance", () => {
  const r = new ParentBackingRegistry();
  r.enroll("p:0", 0, 100_000, parties);
  for (let i = 0; i < 60; i++) r.claimChild("p:0", 0, "alice", 1_000);
  assert.equal(r.totalEligibleWeight(), 60_000);
  assert.throws(() => r.claimChild("p:0", 0, "alice", 1), /exceeds canonical entitlement/);
  r.claimChild("p:0", 0, "bob", 40_000);
  assert.equal(r.totalEligibleWeight(), 100_000);
});

test("entitlement revisions require a new registry epoch and revoke old claim eligibility", () => {
  const r = new ParentBackingRegistry();
  r.enroll("p:0", 0, 100_000, parties);
  r.claimParent("p:0", 0);
  assert.equal(r.totalEligibleWeight(), 100_000);
  r.rollEpoch("p:0", 1, [
    { holder: "alice", script: "p2tr:alice", sats: 30_000 },
    { holder: "bob", script: "p2tr:bob", sats: 70_000 },
  ]);
  assert.equal(r.totalEligibleWeight(), 0);
  assert.throws(() => r.claimChild("p:0", 0, "alice", 1), /stale/);
  assert.throws(() => r.claimChild("p:0", 1, "alice", 60_000), /exceeds canonical entitlement/);
  r.claimChild("p:0", 1, "alice", 30_000);
  r.claimChild("p:0", 1, "bob", 70_000);
  assert.equal(r.totalEligibleWeight(), 100_000);
  assert.throws(() => r.rollEpoch("p:0", 3, parties), /incorrect successor epoch/);
});

test("distinct parent allocations sum, while aliases to the same parent are rejected", () => {
  const r = new ParentBackingRegistry();
  r.enroll("p:0", 0, 100_000, parties);
  assert.throws(() => r.enroll("p:0", 0, 100_000, parties), /already registered/);
  r.enroll("q:1", 0, 100_000, parties);
  r.claimParent("p:0", 0);
  r.claimChild("q:1", 0, "alice", 60_000);
  assert.equal(r.totalEligibleWeight(), 160_000);
});

test("exhaustive two-holder reallocation conservation for all 99 positive splits", () => {
  for (let alice = 1; alice < 100; alice++) {
    const x = [
      { holder: "alice", script: "p2tr:alice", sats: alice },
      { holder: "bob", script: "p2tr:bob", sats: 100 - alice },
    ];
    validateEntitlements(x, 100);
    const r = new ParentBackingRegistry();
    r.enroll(`p:${alice}`, 0, 100, x);
    r.claimChild(`p:${alice}`, 0, "alice", alice);
    r.claimChild(`p:${alice}`, 0, "bob", 100 - alice);
    assert.equal(r.totalEligibleWeight(), 100);
  }
});

test("malformed and unsafe satoshi values fail atomically", () => {
  const bad = [-1, 1.5, NaN, Infinity, -Infinity, Number.MAX_SAFE_INTEGER + 1];
  for (const v of bad) assert.throws(() => validateEntitlements([
    { holder: "alice", script: "p2tr:alice", sats: v }, parties[1],
  ], 100_000));
  const state = fixture();
  state.fundWithPreparedRecovery();
  for (const v of bad) {
    assert.throws(() => state.transfer("alice", "bob", v, { approvals: ["alice"] }));
    assert.equal(state.currentEpoch, 0);
  }
});
