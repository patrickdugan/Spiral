import { test } from "node:test";
import assert from "node:assert/strict";
import { Registry, SettledSet, commit, prf, type Statement, type Witness } from "./registry.ts";

// NOTE: the proof system is simulated (see registry.ts). These tests witness the registry logic
// under the assumption that a real knowledge-sound proof would accept exactly what verifyCapClaim accepts.

function claim(set: SettledSet, objId: string, identity: string, v: number, k?: string): [Statement, Witness] {
  const obj = set.get(objId)!;
  const key = k ?? obj.authorityKey;
  const st: Statement = { cm: commit(identity), v, nf: prf(key, obj.id), root: set.root() };
  return [st, { s: identity, k: key, obj: { ...obj } }];
}

test("S3: weight attributed to any settled object is at most its value regardless of identity count", () => {
  const set = new SettledSet();
  set.add({ id: "utxo:1", value: 50_000, authorityKey: "k1" });
  set.add({ id: "vtxo:7", value: 20_000, authorityKey: "k7" });
  const R = new Registry();
  // One controller, 32 identities, one object: only the first claim lands.
  const outcomes = Array.from({ length: 32 }, (_, i) => R.submit(set, ...claim(set, "utxo:1", `id-${i}`, 50_000)));
  assert.equal(outcomes[0], "accepted");
  assert.ok(outcomes.slice(1).every((o) => o === "duplicate"));
  assert.equal(R.weightFor(prf("k1", "utxo:1")), 50_000);
  // A second, distinct object is independent.
  assert.equal(R.submit(set, ...claim(set, "vtxo:7", "id-99", 20_000)), "accepted");
  assert.equal(R.totalWeight(), 70_000);
});

test("S3: a nullifier keyed to a claimant secret would permit splitting; keying to the authority does not", () => {
  const set = new SettledSet();
  set.add({ id: "utxo:2", value: 10_000, authorityKey: "k2" });
  const R = new Registry();
  const [st1, w1] = claim(set, "utxo:2", "alpha", 10_000);
  const [st2, w2] = claim(set, "utxo:2", "beta", 10_000);
  assert.equal(st1.nf, st2.nf); // same object ⇒ same nullifier, whoever claims
  assert.equal(R.submit(set, st1, w1), "accepted");
  assert.equal(R.submit(set, st2, w2), "duplicate");
  // Forging a different nullifier requires a key that does not satisfy the authority: rejected as invalid.
  const [st3, w3] = claim(set, "utxo:2", "gamma", 10_000, "not-k2");
  assert.equal(R.submit(set, st3, w3), "invalid");
});

test("S3: overclaiming value, stale roots, and unsettled objects are rejected", () => {
  const set = new SettledSet();
  set.add({ id: "chan:3", value: 1_000, authorityKey: "k3" });
  const R = new Registry();
  const [over, wo] = claim(set, "chan:3", "x", 1_001);
  assert.equal(R.submit(set, over, wo), "invalid");
  const [st, w] = claim(set, "chan:3", "x", 1_000);
  set.add({ id: "chan:4", value: 5, authorityKey: "k4" }); // root moves
  assert.equal(R.submit(set, st, w), "invalid");
  const fresh = new SettledSet();
  const ghost: Witness = { s: "y", k: "k9", obj: { id: "ghost", value: 10, authorityKey: "k9" } };
  assert.equal(R.submit(fresh, { cm: commit("y"), v: 10, nf: prf("k9", "ghost"), root: fresh.root() }, ghost), "invalid");
});

test("L4 with S3: identity splitting leaves coalition payout invariant and integer pool conserved up to floor", () => {
  const set = new SettledSet();
  set.add({ id: "u:a", value: 100, authorityKey: "ka" });
  set.add({ id: "u:b", value: 100, authorityKey: "kb" });
  for (const m of [1, 2, 8, 32]) {
    const R = new Registry();
    for (let i = 0; i < m; i++) R.submit(set, ...claim(set, "u:a", `a-${i}`, 100)); // one accepted, m−1 duplicates
    R.submit(set, ...claim(set, "u:b", "b", 100));
    const alloc = R.allocate(120);
    const coalitionA = [...alloc.entries()].filter(([cm]) => cm !== commit("b")).reduce((s, [, v]) => s + v, 0);
    assert.equal(coalitionA, 60);
    assert.equal(alloc.get(commit("b")), 60);
  }
});
