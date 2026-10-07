import { test } from "node:test";
import assert from "node:assert/strict";
import { Registry, SettledSet, commit, prf, type Statement, type Witness } from "./registry.ts";

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
