import { test } from "node:test";
import assert from "node:assert/strict";
import { Registry, SettledSet, commit, prf, settlementCommitment, type Statement, type Witness } from "./registry.ts";

// NOTE: the proof system is simulated (see registry.ts). These tests witness the registry logic
// under the assumption that a real knowledge-sound proof would accept exactly what verifyCapClaim accepts.

function claim(R: Registry, set: SettledSet, objId: string, identity: string, v: number, k?: string): [Statement, Witness] {
  const obj = set.get(objId)!;
  const key = k ?? obj.authorityKey;
  const st: Statement = { cm: commit(identity), v, nf: prf(key, obj.id), root: R.root };
  return [st, { s: identity, k: key, obj: { ...obj } }];
}

test("S3: weight attributed to any settled object is at most its value regardless of identity count", () => {
  const set = new SettledSet();
  set.add({ id: "utxo:1", value: 50_000, authorityKey: "k1" });
  set.add({ id: "vtxo:7", value: 20_000, authorityKey: "k7" });
  const R = new Registry(set);
  // One controller, 32 identities, one object: only the first claim lands.
  const outcomes = Array.from({ length: 32 }, (_, i) => R.submit(...claim(R, set, "utxo:1", `id-${i}`, 50_000)));
  assert.equal(outcomes[0], "accepted");
  assert.ok(outcomes.slice(1).every((o) => o === "duplicate"));
  assert.equal(R.weightFor(prf("k1", "utxo:1")), 50_000);
  // A second, distinct object is independent.
  assert.equal(R.submit(...claim(R, set, "vtxo:7", "id-99", 20_000)), "accepted");
  assert.equal(R.totalWeight(), 70_000);
});

test("S3: a nullifier keyed to a claimant secret would permit splitting; keying to the authority does not", () => {
  const set = new SettledSet();
  set.add({ id: "utxo:2", value: 10_000, authorityKey: "k2" });
  const R = new Registry(set);
  const [st1, w1] = claim(R, set, "utxo:2", "alpha", 10_000);
  const [st2, w2] = claim(R, set, "utxo:2", "beta", 10_000);
  assert.equal(st1.nf, st2.nf); // same object ⇒ same nullifier, whoever claims
  assert.equal(R.submit(st1, w1), "accepted");
  assert.equal(R.submit(st2, w2), "duplicate");
  // Forging a different nullifier requires a key that does not satisfy the authority: rejected as invalid.
  const [st3, w3] = claim(R, set, "utxo:2", "gamma", 10_000, "not-k2");
  assert.equal(R.submit(st3, w3), "invalid");
});

test("S3: overclaiming value, stale roots, and unsettled objects are rejected", () => {
  const set = new SettledSet();
  set.add({ id: "chan:3", value: 1_000, authorityKey: "k3" });
  const R = new Registry(set);
  const [over, wo] = claim(R, set, "chan:3", "x", 1_001);
  assert.equal(R.submit(over, wo), "invalid");
  // An object added after the epoch froze is not in the root the registry accepts claims against.
  set.add({ id: "chan:4", value: 5, authorityKey: "k4" });
  const st4: Statement = { cm: commit("y"), v: 5, nf: prf("k4", "chan:4"), root: set.root() };
  assert.equal(R.submit(st4, { s: "y", k: "k4", obj: set.get("chan:4")! }), "invalid");
  const fresh = new SettledSet();
  const ghost: Witness = { s: "y", k: "k9", obj: { id: "ghost", value: 10, authorityKey: "k9" } };
  assert.equal(R.submit({ cm: commit("y"), v: 10, nf: prf("k9", "ghost"), root: fresh.root() }, ghost), "invalid");
});

test("S3 churn: without the epoch rule one object re-claims under every fresh id; with it, one unit of capital counts once per epoch", () => {
  const set = new SettledSet();
  set.add({ id: "u:0", value: 100, authorityKey: "ka" });
  // Same controller, same key, one identity: spend to a fresh id and claim again, 8 times.
  // Without epochs (a registry re-frozen on every spend) each claim is fresh: the nullifier is a function of id.
  let naive = 0;
  for (let i = 0; i < 8; i++) {
    const Ri = new Registry(set); // stands in for a registry that accepts claims against any current root
    naive += Ri.submit(...claim(Ri, set, `u:${i}`, "ident", 100)) === "accepted" ? 100 : 0;
    set.transfer(`u:${i}`, `u:${i + 1}`, "ka"); // self-transfer: new id, same key, no attested successor link
  }
  assert.equal(naive, 800); // the hole
  // With the epoch rule: claims accepted only against the epoch-start root; the churned objects are not in it,
  // and the one that was is revoked at close because it was spent without an attested successor.
  const set2 = new SettledSet();
  set2.add({ id: "w:0", value: 100, authorityKey: "kb" });
  const R = new Registry(set2);
  assert.equal(R.submit(...claim(R, set2, "w:0", "ident", 100)), "accepted");
  for (let i = 0; i < 8; i++) {
    set2.transfer(`w:${i}`, `w:${i + 1}`, "kb");
    const st: Statement = { cm: commit("ident"), v: 100, nf: prf("kb", `w:${i + 1}`), root: set2.root() };
    assert.equal(R.submit(st, { s: "ident", k: "kb", obj: set2.get(`w:${i + 1}`)! }), "invalid"); // not in the frozen root
  }
  assert.equal(R.closeEpoch(set2), 0); // w:0 is spent with no successor link: revoked
  // Next epoch, the live object w:8 claims once.
  assert.equal(R.submit(...claim(R, set2, "w:8", "ident", 100)), "accepted");
  assert.equal(R.closeEpoch(set2), 100);
});

test("S3 refresh: an attested successor (Ark refresh, same key) keeps a claim; a transfer to another key does not", () => {
  const set = new SettledSet();
  set.add({ id: "v:1", value: 500, authorityKey: "kh" });
  set.add({ id: "v:2", value: 500, authorityKey: "kh" });
  const R = new Registry(set);
  assert.equal(R.submit(...claim(R, set, "v:1", "h", 500)), "accepted");
  assert.equal(R.submit(...claim(R, set, "v:2", "h", 500)), "accepted");
  set.refresh("v:1", "v:1b");            // server-attested refresh: id rotates, key does not
  set.refresh("v:1b", "v:1c");           // and again
  set.transfer("v:2", "v:2b", "kOther"); // a transfer, even to a key the same controller might hold
  assert.equal(R.closeEpoch(set), 500);  // v:1's claim survives through two refreshes; v:2's is revoked
});

test("L4 with S3: identity splitting leaves coalition payout invariant and integer pool conserved up to floor", () => {
  const set = new SettledSet();
  set.add({ id: "u:a", value: 100, authorityKey: "ka" });
  set.add({ id: "u:b", value: 100, authorityKey: "kb" });
  for (const m of [1, 2, 8, 32]) {
    const R = new Registry(set);
    for (let i = 0; i < m; i++) R.submit(...claim(R, set, "u:a", `a-${i}`, 100)); // one accepted, m−1 duplicates
    R.submit(...claim(R, set, "u:b", "b", 100));
    const alloc = R.allocate(120);
    const coalitionA = [...alloc.entries()].filter(([cm]) => cm !== commit("b")).reduce((s, [, v]) => s + v, 0);
    assert.equal(coalitionA, 60);
    assert.equal(alloc.get(commit("b")), 60);
  }
});


test("S3: frozen settled-set roots bind unambiguously to typed object records", () => {
  const a = new SettledSet();
  a.add({ id: "a|1", value: 2, authorityKey: "x" });
  const b = new SettledSet();
  b.add({ id: "a", value: 1, authorityKey: "2|x" });
  // Separator-based concatenation gave both sets the same serialized bytes:
  // "a|1|2|x\n", despite the objects being distinct.
  assert.notEqual(a.root(), b.root());
});

test("S3: a distinct live object cannot be overwritten by id reuse", () => {
  const set = new SettledSet();
  set.add({ id: "a", value: 100, authorityKey: "k" });
  set.add({ id: "b", value: 200, authorityKey: "k" });
  const before = set.root();
  assert.throws(() => set.add({ id: "a", value: 1, authorityKey: "x" }), /duplicate|already/);
  assert.throws(() => set.refresh("a", "b"), /duplicate|already/);
  assert.throws(() => set.transfer("a", "b", "other"), /duplicate|already/);
  assert.equal(set.root(), before);
  assert.equal(set.get("a")?.value, 100);
  assert.equal(set.get("b")?.value, 200);
  set.remove("a");
  assert.throws(() => set.add({ id: "a", value: 100, authorityKey: "k" }), /duplicate|already/);
  const copy = set.snapshot();
  assert.throws(() => copy.add({ id: "a", value: 100, authorityKey: "k" }), /duplicate|already/);
});

test("registry rejects negative, fractional, nonfinite and unsafe weights without consuming the claim", () => {
  const set = new SettledSet();
  set.add({ id: "a", value: 10, authorityKey: "ka" });
  set.add({ id: "b", value: 10, authorityKey: "kb" });
  const R = new Registry(set);
  assert.equal(R.submit(...claim(R, set, "a", "alice", 10)), "accepted");
  for (const invalid of [-9, -1, 0.5, NaN, Infinity, -Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(R.submit(...claim(R, set, "b", "bob", invalid)), "invalid");
    assert.equal(R.totalWeight(), 10);
  }
  assert.equal(R.submit(...claim(R, set, "b", "bob", 10)), "accepted");
  const receipt = R.settleEpoch(set, 100);
  assert.equal(receipt.allocated, 100);
  assert.deepEqual(new Map(receipt.payouts.map((p) => [p.cm, p.amount])), new Map([
    [commit("alice"), 50], [commit("bob"), 50],
  ]));
});

test("registry bounds aggregate weight exactly and leaves an overflowing submission retryable", () => {
  const maximum = Number.MAX_SAFE_INTEGER;
  const set = new SettledSet();
  set.add({ id: "a", value: maximum, authorityKey: "ka" });
  set.add({ id: "b", value: 1, authorityKey: "kb" });
  const R = new Registry(set);
  assert.equal(R.submit(...claim(R, set, "a", "alice", maximum)), "accepted");
  assert.equal(R.submit(...claim(R, set, "b", "bob", 1)), "invalid");
  assert.equal(R.submit(...claim(R, set, "b", "bob", 0)), "accepted");
  assert.equal(R.totalWeight(), maximum);
  const receipt = R.settleEpoch(set, maximum);
  assert.equal(receipt.totalWeight, maximum);
  assert.equal(receipt.allocated, maximum);
  assert.equal(receipt.unallocated, 0);
});

test("allocation keeps exact floors when safe inputs have an unsafe intermediate product", () => {
  const pool = 9_007_199_254_740_990;
  const weights = [1_033_873_937_146_939, 159_637_918_172_065];
  const set = new SettledSet();
  for (let i = 0; i < weights.length; i++) set.add({ id: `u:${i}`, value: weights[i], authorityKey: `k${i}` });
  const R = new Registry(set);
  for (let i = 0; i < weights.length; i++) assert.equal(R.submit(...claim(R, set, `u:${i}`, `id-${i}`, weights[i])), "accepted");
  const receipt = R.settleEpoch(set, pool);
  const payouts = new Map(receipt.payouts.map((p) => [p.cm, p.amount]));
  assert.equal(payouts.get(commit("id-0")), 7_802_443_280_864_630);
  assert.equal(Math.floor(pool * weights[0] / (weights[0] + weights[1])), 7_802_443_280_864_631);
  const total = weights.reduce((sum, value) => sum + BigInt(value), 0n);
  for (let i = 0; i < weights.length; i++) {
    assert.equal(payouts.get(commit(`id-${i}`)), Number(BigInt(pool) * BigInt(weights[i]) / total));
  }
  assert.equal(receipt.allocated + receipt.unallocated, pool);
  assert.ok(receipt.unallocated >= 0);
});

test("empty and zero-weight epochs preserve the entire unallocated pool", () => {
  for (const count of [0, 2]) {
    const set = new SettledSet();
    for (let i = 0; i < count; i++) set.add({ id: `u:${i}`, value: 5, authorityKey: `k${i}` });
    const R = new Registry(set);
    for (let i = 0; i < count; i++) assert.equal(R.submit(...claim(R, set, `u:${i}`, `id-${i}`, 0)), "accepted");
    assert.ok([...R.previewAllocation(7).values()].every((amount) => amount === 0));
    const receipt = R.settleEpoch(set, 7);
    assert.equal(receipt.totalWeight, 0);
    assert.equal(receipt.allocated, 0);
    assert.equal(receipt.unallocated, 7);
    assert.ok(receipt.payouts.every((p) => p.amount === 0));
  }
});

test("failed pool validation preserves the epoch, frozen root, claims and nullifiers", () => {
  const set = new SettledSet();
  set.add({ id: "a", value: 10, authorityKey: "ka" });
  set.add({ id: "b", value: 10, authorityKey: "kb" });
  const R = new Registry(set);
  const first = claim(R, set, "a", "alice", 10);
  const second = claim(R, set, "b", "bob", 10);
  R.submit(...first);
  R.submit(...second);
  const root = R.root;
  set.remove("a");
  for (const invalid of [-1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => R.previewAllocation(invalid), /reward pool/);
    assert.throws(() => R.allocate(invalid), /reward pool/);
    assert.throws(() => R.settleEpoch(set, invalid), /reward pool/);
    assert.equal(R.epoch, 0);
    assert.equal(R.root, root);
    assert.equal(R.totalWeight(), 20);
    assert.equal(R.submit(...first), "duplicate");
    assert.equal(R.lastSettlement, undefined);
  }
  const receipt = R.settleEpoch(set, 10);
  assert.equal(receipt.totalWeight, 10);
  assert.equal(receipt.payouts[0].cm, commit("bob"));
  assert.equal(receipt.payouts[0].amount, 10);
});

test("a failed live snapshot leaves settlement untouched", () => {
  class UnavailableSet extends SettledSet {
    override snapshot(): SettledSet { throw new Error("live snapshot unavailable"); }
  }
  const set = new SettledSet();
  set.add({ id: "a", value: 3, authorityKey: "ka" });
  const R = new Registry(set);
  const input = claim(R, set, "a", "alice", 3);
  R.submit(...input);
  const before = R.root;
  assert.throws(() => R.settleEpoch(new UnavailableSet(), 5), /snapshot unavailable/);
  assert.equal(R.epoch, 0);
  assert.equal(R.root, before);
  assert.equal(R.totalWeight(), 3);
  assert.equal(R.submit(...input), "duplicate");
  assert.equal(R.lastSettlement, undefined);
  assert.equal(R.settleEpoch(set, 5).allocated, 5);
});

test("atomic settlement fixes eligible payouts and revoked decisions before starting the next epoch", () => {
  const set = new SettledSet();
  set.add({ id: "a", value: 3, authorityKey: "ka" });
  set.add({ id: "b", value: 2, authorityKey: "kb" });
  set.add({ id: "c", value: 5, authorityKey: "kc" });
  const R = new Registry(set);
  for (const [id, value] of [["a", 3], ["b", 2], ["c", 5]] as const) R.submit(...claim(R, set, id, id, value));
  const openRoot = R.root;
  set.refresh("a", "a:next");
  set.transfer("b", "b:next", "other");
  set.remove("c");
  const receipt = R.settleEpoch(set, 11);
  assert.equal(receipt.epoch, 0);
  assert.equal(receipt.rootAtOpen, openRoot);
  assert.equal(receipt.rootAtClose, set.root());
  assert.equal(receipt.totalWeight, 3);
  assert.deepEqual(receipt.payouts, [{ cm: commit("a"), amount: 11 }]);
  assert.deepEqual(receipt.claims.filter((c) => c.status === "eligible").map((c) => c.descendantId), ["a:next"]);
  assert.equal(receipt.claims.filter((c) => c.status === "revoked").length, 2);
  assert.equal(R.totalWeight(), 0);
  assert.equal(R.epoch, 1);
  assert.equal(R.lastSettlement, receipt);
  assert.equal(R.submit(...claim(R, set, "a:next", "a", 3)), "accepted");
  const next = R.settleEpoch(set, 7);
  assert.equal(next.epoch, 1);
  assert.equal(next.allocated, 7);
  assert.equal(R.epoch, 2);
  assert.equal(receipt.allocated, 11);
  assert.equal(receipt.commitment, settlementCommitment(receipt));
});

test("settlement preserves per-object flooring and records the undistributed remainder", () => {
  const set = new SettledSet();
  for (let i = 0; i < 3; i++) set.add({ id: `u:${i}`, value: 1, authorityKey: `k${i}` });
  const R = new Registry(set);
  R.submit(...claim(R, set, "u:0", "alice", 1));
  R.submit(...claim(R, set, "u:1", "alice", 1));
  R.submit(...claim(R, set, "u:2", "bob", 1));
  const receipt = R.settleEpoch(set, 5);
  const payouts = new Map(receipt.payouts.map((p) => [p.cm, p.amount]));
  assert.equal(payouts.get(commit("alice")), 2);
  assert.equal(payouts.get(commit("bob")), 1);
  assert.equal(receipt.allocated, 3);
  assert.equal(receipt.unallocated, 2);
});

test("settlement receipts are deeply immutable and canonical across submission order", () => {
  const set = new SettledSet();
  set.add({ id: "a", value: 3, authorityKey: "ka" });
  set.add({ id: "b", value: 2, authorityKey: "kb" });
  const left = new Registry(set);
  const right = new Registry(set);
  for (const [R, ids] of [[left, ["a", "b"]], [right, ["b", "a"]]] as const) {
    for (const id of ids) R.submit(...claim(R, set, id, id, set.get(id)!.value));
  }
  const receipt = left.settleEpoch(set, 7);
  const encoded = JSON.stringify(receipt);
  assert.deepEqual(receipt, right.settleEpoch(set, 7));
  assert.throws(() => Object.assign(receipt, { pool: 100 }), TypeError);
  assert.throws(() => Object.assign(receipt.payouts[0], { amount: 100 }), TypeError);
  assert.throws(() => Object.assign(receipt.claims[0], { value: 100 }), TypeError);
  assert.throws(() => (receipt.payouts as unknown[]).push({}), TypeError);
  assert.throws(() => (receipt.claims as unknown[]).pop(), TypeError);
  assert.equal(JSON.stringify(receipt), encoded);
  assert.equal(left.lastSettlement?.commitment, settlementCommitment(receipt));
  assert.notEqual(settlementCommitment({ ...receipt, unallocated: receipt.unallocated + 1 }), receipt.commitment);
});

test("legacy close followed by allocation fails clearly and retains the zero-reward receipt", () => {
  const set = new SettledSet();
  set.add({ id: "a", value: 10, authorityKey: "ka" });
  const R = new Registry(set);
  R.submit(...claim(R, set, "a", "alice", 10));
  assert.equal(R.closeEpoch(set), 10);
  assert.throws(() => R.allocate(100), /settleEpoch/);
  assert.equal(R.lastSettlement?.pool, 0);
  assert.equal(R.lastSettlement?.totalWeight, 10);
  assert.equal(R.lastSettlement?.allocated, 0);
});

test("settled object accessors cannot mutate stored value, authority, identity or successor state", () => {
  const set = new SettledSet();
  const input = { id: "a", value: 10, authorityKey: "ka" };
  set.add(input);
  const initialRoot = set.root();
  input.value = 999;
  Object.assign(set.get("a")!, { id: "forged", value: -1, authorityKey: "attacker" });
  assert.equal(set.root(), initialRoot);
  assert.deepEqual(set.get("a"), { id: "a", value: 10, authorityKey: "ka" });
  const refreshed = set.refresh("a", "a:next");
  const refreshedRoot = set.root();
  Object.assign(refreshed, { value: 999, authorityKey: "attacker" });
  Object.assign(set.descendant("a")!, { value: -1, id: "forged" });
  assert.equal(set.root(), refreshedRoot);
  assert.deepEqual(set.descendant("a"), { id: "a:next", value: 10, authorityKey: "ka" });
  const transferred = set.transfer("a:next", "a:last", "kb");
  const transferredRoot = set.root();
  Object.assign(transferred, { value: 999, authorityKey: "attacker" });
  assert.equal(set.root(), transferredRoot);
  assert.deepEqual(set.get("a:last"), { id: "a:last", value: 10, authorityKey: "kb" });
});
