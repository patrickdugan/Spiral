import { test } from "node:test";
import assert from "node:assert/strict";
import { sats, type CapitalEvent, type OnchainTransaction } from "./capital.ts";
import { TraceBuilder } from "./capital.fixtures.ts";

function transaction(t: TraceBuilder, txid: string, data: Omit<OnchainTransaction, "inclusion_height" | "inclusion_hash">) {
  const s = t.m.snapshot();
  return t.event("ONCHAIN_TRANSACTION", { ...data, inclusion_height: s.J.height - 1, inclusion_hash: `block-${s.J.height - 1}` },
    { txid, block_hash: `block-${s.J.height}`, evidence_refs: data.input_ids.map(id => `spends:${s.A[id].backing_ref}`) });
}
function rejected(t: TraceBuilder, e: CapitalEvent, pattern: RegExp) {
  const hash = t.m.stateHash(); assert.throws(() => t.m.apply(e), pattern); assert.equal(t.m.stateHash(), hash);
}
function beforeRecovery() {
  const t = new TraceBuilder(); t.fund("board", sats(100000));
  t.add("ISSUE_VTXO", { service_fee: sats(330), claim: { claim_id: "input", claimant: "alice", allocations: { board: sats(99670) }, expiry_height: 10 } }, { amount: sats(100000) });
  t.fund("channel-wallet", sats(1000000), true); t.fund("round-wallet", sats(818766), true); t.chain(2);
  t.m.apply(transaction(t, "channel-funding", { input_ids: ["channel-wallet"], outputs: [
    { asset_id: "channel", amount: sats(500000), output_index: 0 }, { asset_id: "wallet-change", amount: sats(499834), output_index: 1 }], fee: sats(166) }));
  t.add("OPEN_CHANNEL", { channel_id: "cln", asset_id: "channel", funding_ref: "channel-funding:0", remote: 0, spendable: sats(490694), receivable: 0 }, { txid: "channel-funding", block_hash: "block-2" });
  t.add("SPLIT_MERGE", { input_ids: ["channel"], outputs: [{ asset_id: "routing", amount: sats(60499) }, { asset_id: "unreserved", amount: sats(439501) }] });
  t.add("PAYMENT_OFFERED", { operation_id: "pay", holder: "alice" }, { amount: sats(60000) });
  t.add("REQUEST_OUTGOING", { operation_id: "pay", holder: "alice", input_claim_ids: ["input"], reserve_ids: ["routing"], channel_id: "cln",
    delivered: sats(60000), max_fee: sats(499), max_holder_fee: sats(555), change_backing: "retained", timeout_height: 8 }, { amount: sats(60000) });
  t.add("HTLC_ACCEPTED", { operation_id: "pay" });
  t.add("HTLC_SETTLED", { operation_id: "pay", fee: 0, service_fee: sats(555), preimage_evidence_ref: "fixture:preimage",
    change: { claim_id: "change", claimant: "alice", allocations: { board: sats(39115) }, expiry_height: 10, parent_claim_id: "input" } }, { amount: sats(60000), evidence_refs: ["fixture:preimage"] });
  t.chain(4);
  t.m.apply(transaction(t, "round-one", { input_ids: ["round-wallet"], outputs: [
    { asset_id: "round-root", amount: sats(38982), output_index: 0 }, { asset_id: "round-change", amount: sats(775927), output_index: 1 }], fee: sats(3857),
    refresh: { operation_id: "refresh-one", input_claim_ids: ["change"], backing_ids: ["round-root"], service_fee: sats(463),
      replacement: { claim_id: "refreshed", claimant: "alice", allocations: { "round-root": sats(38652) }, expiry_height: 20, parent_claim_id: "change" } } }));
  return t;
}
function swept() {
  const t = beforeRecovery(); t.chain(10); t.add("BACKING_EXPIRED", { input_ids: ["board"] });
  t.add("RECOVERY_SWEEP", { sweep_id: "board-sweep", operation_ids: ["pay", "refresh-one"], input_ids: ["board"], output_id: "recovered",
    destination: "server-wallet", fee: sats(1295), input_outpoints: ["fund-board:0"] }, { txid: "sweep" });
  t.chain(12); t.add("SWEEP_CONFIRMED", { sweep_id: "board-sweep", inclusion_height: 11, inclusion_hash: "block-11" },
    { txid: "sweep", block_hash: "block-12", amount: sats(98705) }); return t;
}
function reuse(t: TraceBuilder) {
  return transaction(t, "round-two", { input_ids: ["recovered"], outputs: [
    { asset_id: "reused-root", amount: sats(38677), output_index: 0 }, { asset_id: "reuse-change", amount: sats(56171), output_index: 1 }], fee: sats(3857),
    reuse: { sweep_id: "board-sweep", recovery_allocations: { pay: sats(60000), "refresh-one": sats(38705) } },
    refresh: { operation_id: "refresh-two", input_claim_ids: ["refreshed"], backing_ids: ["reused-root"], service_fee: sats(305),
      replacement: { claim_id: "twice-refreshed", claimant: "alice", allocations: { "reused-root": sats(38347) }, expiry_height: 30, parent_claim_id: "refreshed" } } });
}
test("round transaction separates holder fee, whole backing root, wallet change, and miner fee", () => {
  const t = beforeRecovery(), s = t.m.snapshot();
  assert.equal(s.H.operations["refresh-one"].gross, sats(38982));
  assert.equal(s.K.refreshed.amount, sats(38652)); assert.equal(s.A["round-root"].amount, sats(38982));
  assert.equal(s.A["round-change"].state, "FREE"); assert.equal(s.totals.fees, sats(4023));
  assert.equal(s.totals.service_revenue, sats(1348)); assert.equal(s.holders.alice.received, sats(100000));
  assert.equal(s.H.channels.cln.spendable, sats(430694)); assert.ok(t.replayCheck());
});
test("shared original backing recovery is credited once and exclusively reused by independent round", () => {
  const t = swept(); t.chain(14); t.m.apply(reuse(t)); const s = t.m.snapshot();
  assert.equal(s.B.F, sats(138158)); assert.equal(s.B.C, sats(99204));
  assert.equal(t.m.report().outstanding_fronting, sats(38954));
  assert.equal(s.H.operations["refresh-one"].gross - s.H.operations["refresh-one"].recovered, sats(277));
  assert.equal(s.H.operations["refresh-one"].recovery_complete, true);
  assert.deepEqual(s.A["reused-root"].parent_ids, ["recovered"]); assert.equal(s.K["twice-refreshed"].amount, sats(38347));
  assert.equal(s.A["round-root"].state, "COMMITTED"); assert.equal(s.K.refreshed.state, "FORFEITED");
  assert.equal(s.totals.fees, sats(9175)); assert.ok(t.replayCheck());
});
test("shared recovery rejects overcredit, undercredit, omission, and unrelated fresh input", () => {
  for (const mutation of ["over", "under", "omit", "fresh"] as const) {
    const t = swept(); t.chain(14); const e = reuse(t); if (e.event_type !== "ONCHAIN_TRANSACTION") throw new Error("fixture");
    if (mutation === "over") e.data.reuse!.recovery_allocations.pay += sats(1);
    if (mutation === "under") e.data.reuse!.recovery_allocations.pay -= sats(1);
    if (mutation === "omit") delete e.data.reuse!.recovery_allocations["refresh-one"];
    if (mutation === "fresh") {
      e.data.input_ids.push("round-change"); e.data.outputs[1].amount += sats(775927); e.evidence_refs.push("spends:round-one:1");
    }
    rejected(t, e, /recovery|exclusively/);
  }
});
test("shared sweep must include every linked fronting operation", () => {
  const t = beforeRecovery(); t.chain(10); t.add("BACKING_EXPIRED", { input_ids: ["board"] });
  rejected(t, t.event("RECOVERY_SWEEP", { sweep_id: "s", operation_ids: ["pay"], input_ids: ["board"], output_id: "recovered",
    destination: "wallet", fee: sats(1295), input_outpoints: ["fund-board:0"] }, { txid: "sweep" }), /omits linked/);
});
test("round recovery does not consume live or unexpired obligations", () => {
  const t = beforeRecovery(); rejected(t, t.event("BACKING_EXPIRED", { input_ids: ["board"] }), /unexpired/);
  t.chain(20); rejected(t, t.event("BACKING_EXPIRED", { input_ids: ["round-root"] }), /outstanding holder/);
});
test("transaction value creation, forged inputs, premature confirmation and sliced outputs fail atomically", () => {
  for (const mutation of ["fee", "proof", "finality", "slice"] as const) {
    const t = new TraceBuilder(); t.fund("a", sats(1000), true); t.chain(2);
    if (mutation === "slice") t.add("SPLIT_MERGE", { input_ids: ["a"], outputs: [{ asset_id: "a1", amount: sats(500) }, { asset_id: "a2", amount: sats(500) }] });
    const e = transaction(t, "spend", { input_ids: [mutation === "slice" ? "a1" : "a"], outputs: [{ asset_id: "b", amount: sats(mutation === "slice" ? 499 : 999), output_index: 0 }], fee: sats(1) });
    if (e.event_type !== "ONCHAIN_TRANSACTION") throw new Error("fixture");
    if (mutation === "fee") e.data.fee++;
    if (mutation === "proof") e.evidence_refs = ["fixture:unproven"];
    if (mutation === "finality") { e.data.inclusion_height = 2; e.data.inclusion_hash = "block-2"; }
    rejected(t, e, /value|provenance|finality|whole underlying/);
  }
});
