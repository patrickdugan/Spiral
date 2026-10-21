import { test } from "node:test";
import assert from "node:assert/strict";
import { sats } from "./capital.ts";
import { TraceBuilder } from "./capital.fixtures.ts";

// Observed amounts, synthetic envelopes: these are model regression fixtures,
// not a substitute for the source-pinned regtest journal.
function retained(input = 99670, routingLimit = 499, holderLimit = 555) {
  const t = new TraceBuilder();
  t.fund("board", sats(100000)); t.issue("input", "board", sats(input), 4433);
  t.fund("routing", sats(60000 + routingLimit), true); t.channel("routing", "cln");
  t.add("PAYMENT_OFFERED", { operation_id: "pay", holder: "alice" }, { amount: sats(60000) });
  t.add("REQUEST_OUTGOING", { operation_id: "pay", holder: "alice", input_claim_ids: ["input"], reserve_ids: ["routing"],
    channel_id: "cln", delivered: sats(60000), max_fee: sats(routingLimit), max_holder_fee: sats(holderLimit),
    timeout_height: 100, change_backing: "retained" }, { amount: sats(60000) });
  return t;
}
function settle(t: TraceBuilder, routingFee = 0, serviceFee = 555, change = 39115) {
  t.add("HTLC_ACCEPTED", { operation_id: "pay" });
  return t.event("HTLC_SETTLED", { operation_id: "pay", fee: sats(routingFee), service_fee: sats(serviceFee),
    preimage_evidence_ref: "fixture:verified", ...(change ? { change: { claim_id: "change", claimant: "alice",
      allocations: { board: sats(change) }, expiry_height: 4433, parent_claim_id: "input" } } : {}) },
    { amount: sats(60000), evidence_refs: ["fixture:verified"] });
}
function atomicReject(t: TraceBuilder, e: ReturnType<typeof settle>, expected: RegExp) {
  const hash = t.m.stateHash(); assert.throws(() => t.m.apply(e), expected); assert.equal(t.m.stateHash(), hash);
}
test("retained change: observed 99,670 input, 60,499 routing limit, 60,000 paid, 555 fee, 39,115 change", () => {
  const t = retained(); t.m.apply(settle(t)); const s = t.m.snapshot();
  assert.equal(s.B.F, sats(60499)); assert.equal(s.B.C, sats(499));
  assert.equal(t.m.report().outstanding_fronting, sats(60000));
  assert.equal(s.A.routing.amount, sats(499)); assert.equal(s.A.routing.state, "FREE");
  assert.equal(s.H.channels.cln.spendable, sats(499));
  assert.equal(s.K.input.amount, sats(99670)); assert.equal(s.K.input.allocations.board, sats(60555));
  assert.equal(s.K.change.allocations.board, sats(39115)); assert.equal(s.A.board.amount, sats(100000));
  assert.equal(s.totals.service_revenue, sats(555)); assert.equal(s.totals.fees, 0);
  assert.ok(t.replayCheck());
});
test("retained holder fee limit includes routing rather than charging the routing limit twice", () => {
  const t = retained(60555); t.m.apply(settle(t, 499, 56, 0));
  assert.equal(t.m.snapshot().B.C, 0); assert.equal(t.m.snapshot().totals.fees, sats(499));
  assert.equal(t.m.snapshot().totals.service_revenue, sats(56)); assert.ok(t.replayCheck());
});
test("retained change cannot move to fresh reserve or extend original expiry", () => {
  for (const kind of ["backing", "expiry"] as const) {
    const t = retained(), e = settle(t); assert.equal(e.event_type, "HTLC_SETTLED");
    if (e.event_type !== "HTLC_SETTLED") throw new Error("fixture");
    if (kind === "backing") e.data.change!.allocations = { routing: sats(39115) };
    else e.data.change!.expiry_height++;
    atomicReject(t, e, kind === "backing" ? /backing policy/ : /extend backing expiry/);
  }
});
test("retained routing and holder fee limits are checked independently and atomically", () => {
  for (const [routing, service, change] of [[500, 55, 39115], [1, 555, 39114]]) {
    const t = retained(); atomicReject(t, settle(t, routing, service, change), /fee\/preimage/);
  }
});
test("retained cancellation and failed resolution release only the actual reservation", () => {
  for (const accepted of [false, true]) {
    const t = retained();
    if (accepted) {
      t.add("HTLC_ACCEPTED", { operation_id: "pay" }); t.add("HTLC_FAILED", { operation_id: "pay" });
      t.add("RESOLVE_FAILED", { operation_id: "pay", path: "revocation" });
    } else t.add("CANCEL_REQUEST", { operation_id: "pay" });
    assert.equal(t.m.snapshot().K.input.state, "ACTIVE"); assert.equal(t.m.snapshot().K.input.allocations.board, sats(99670));
    assert.equal(t.m.snapshot().H.channels.cln.spendable, sats(60499));
    assert.equal(t.m.report().outstanding_fronting, 0); assert.ok(t.replayCheck());
  }
});
