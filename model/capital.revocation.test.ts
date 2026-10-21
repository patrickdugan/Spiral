import { test } from "node:test";
import assert from "node:assert/strict";
import { funded } from "./capital.fixtures.ts";
import { sats, type ClaimSpec } from "./capital.ts";

test("revocation replaces spent input IDs with conserved refund and retained-change claims", () => {
  const t = funded(); t.add("HTLC_ACCEPTED", { operation_id: "pay-1" }); t.add("HTLC_FAILED", { operation_id: "pay-1" });
  t.add("RESOLVE_FAILED", { operation_id: "pay-1", path: "revocation", replacements: [
    { claim_id: "refund", claimant: "alice", parent_claim_id: "vtxo", expiry_height: 10, allocations: { backing: sats(600) } },
    { claim_id: "change-a", claimant: "alice", parent_claim_id: "vtxo", expiry_height: 10, allocations: { backing: sats(200) } },
    { claim_id: "change-b", claimant: "alice", parent_claim_id: "vtxo", expiry_height: 10, allocations: { backing: sats(200) } },
  ] });
  const s = t.m.snapshot(); assert.equal(s.K.vtxo.state, "FORFEITED"); assert.equal(s.K.vtxo.allocations.backing, 0);
  assert.equal(s.K.refund.amount + s.K["change-a"].amount + s.K["change-b"].amount, sats(1000));
  assert.equal(s.B.F, s.B.C); assert.equal(s.totals.outflows, 0); assert.ok(t.replayCheck());
});

test("revocation rejects value creation, changed backing, holder substitution and expiry extension atomically", () => {
  const changes: Partial<ClaimSpec>[] = [{ allocations: { backing: sats(1001) } }, { allocations: { reserve: sats(1000) } },
    { claimant: "mallory" }, { expiry_height: 11 }, { parent_claim_id: "missing" }];
  for (const change of changes) {
    const t = funded(); t.add("HTLC_ACCEPTED", { operation_id: "pay-1" }); t.add("HTLC_FAILED", { operation_id: "pay-1" });
    const hash = t.m.stateHash();
    assert.throws(() => t.add("RESOLVE_FAILED", { operation_id: "pay-1", path: "revocation", replacements: [
      { claim_id: "refund", claimant: "alice", parent_claim_id: "vtxo", expiry_height: 10, allocations: { backing: sats(1000) }, ...change },
    ] }));
    assert.equal(t.m.stateHash(), hash); assert.ok(t.replayCheck());
  }
});

test("observed HTLC principal, authorization allowance and channel headroom have distinct amounts", () => {
  const t = funded(sats(600), sats(10));
  t.add("HTLC_ACCEPTED", { operation_id: "pay-1", in_flight_amount: sats(600), observed_spendable: sats(350) });
  t.add("TICK", {}, { monotonic_timestamp: 3 });
  assert.equal(t.m.snapshot().integrals.htlc.msat_seconds, String(sats(600) * 3));
  assert.equal(t.m.snapshot().H.operations["pay-1"].capacity_reserved, sats(650));
  t.add("HTLC_FAILED", { operation_id: "pay-1" }); t.add("RESOLVE_FAILED", { operation_id: "pay-1", path: "revocation" });
  assert.equal(t.m.snapshot().H.channels.cln.spendable, sats(1000)); assert.ok(t.replayCheck());
});

test("accepted observations cannot invent spendable capacity or exceed authorized HTLC value", () => {
  for (const observation of [{ in_flight_amount: sats(611) }, { in_flight_amount: sats(600), observed_spendable: sats(401) }]) {
    const t = funded(sats(600), sats(10)); const before = t.m.stateHash();
    assert.throws(() => t.add("HTLC_ACCEPTED", { operation_id: "pay-1", ...observation }));
    assert.equal(t.m.stateHash(), before);
  }
});
