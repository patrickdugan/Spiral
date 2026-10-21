import { test } from "node:test";
import assert from "node:assert/strict";
import { CapitalAccountingMachine, sats, checkJournal, type CapitalEvent } from "./capital.ts";
import { TraceBuilder, funded, completeLifecycle, fixtureConfig } from "./capital.fixtures.ts";
import { SettlementLedger } from "./ledger.ts";

function checked(t: TraceBuilder) { t.m.check(); assert.ok(t.replayCheck(), "canonical replay hash"); }
function rejected(t: TraceBuilder, e: CapitalEvent, pattern?: RegExp) {
  const hash = t.m.stateHash(), journal = t.m.journal();
  if (pattern) assert.throws(() => t.m.apply(e), pattern); else assert.throws(() => t.m.apply(e));
  assert.equal(t.m.stateHash(), hash); assert.deepEqual(t.m.journal(), journal); checked(t);
}

test("1: 1000-sat gross input delivers 600 and reissues 400 backed by fresh reserve", () => {
  const t = funded(); t.settle(); const s = t.m.snapshot();
  assert.equal(s.B.F, sats(1000)); assert.equal(s.B.C, 0); assert.equal(s.K.change.amount, sats(400));
  assert.deepEqual(s.K.change.allocations, { reserve: sats(400) }); assert.equal(s.A.backing.amount, sats(1000));
  assert.equal(s.totals.outflows, sats(600)); assert.equal(s.totals.fees, 0); checked(t);
  const fee = funded(sats(600), 1500); fee.settle("pay-1", 1500);
  assert.equal(fee.m.snapshot().K.change.amount, 398500); checked(fee);
});

test("2: accepted failure retains risk until verified revocation or confirmed timeout", () => {
  for (const path of ["revocation", "timeout"] as const) {
    const t = funded(); t.add("HTLC_ACCEPTED", { operation_id: "pay-1" }); t.add("HTLC_FAILED", { operation_id: "pay-1" });
    assert.equal(t.m.report().outstanding_fronting, sats(1000)); assert.equal(t.m.snapshot().A.reserve.state, "COMMITTED");
    rejected(t, t.event("CANCEL_REQUEST", { operation_id: "pay-1" }));
    if (path === "timeout") {
      rejected(t, t.event("RESOLVE_FAILED", { operation_id: "pay-1", path, resolution_height: 3, resolution_hash: "block-3" })); t.chain(5);
    }
    t.add("RESOLVE_FAILED", { operation_id: "pay-1", path, ...(path === "timeout" ? { resolution_height: 4, resolution_hash: "block-4" } : {}) },
      path === "timeout" ? { block_hash: "block-5" } : {});
    assert.equal(t.m.report().outstanding_fronting, 0); assert.equal(t.m.snapshot().K.vtxo.state, "ACTIVE"); checked(t);
  }
});

test("3: immediate settlement and expiry eligibility do not free backing", () => {
  const t = funded(); t.settle(); t.chain(10); t.add("EXPIRY_REACHED", { operation_id: "pay-1" });
  assert.equal(t.m.snapshot().A.backing.state, "RECOVERY_DUE"); assert.equal(t.m.report().outstanding_fronting, sats(1000)); checked(t);
});

test("4: coarse and fine integration agree across an observed mid-interval recovery", () => {
  const source = completeLifecycle().m.journal(); const coarse = CapitalAccountingMachine.replay(fixtureConfig, source);
  const fine = new CapitalAccountingMachine(fixtureConfig); let n = 0;
  for (const e of source) {
    const previous = fine.snapshot().J.height;
    for (let h = previous + 1; h < e.block_height; h++) fine.apply({ ...e, event_type: "TICK", data: {}, event_id: `tick-${++n}`, amount: 0, block_height: h, block_hash: null, monotonic_timestamp: h * 600 });
    fine.apply(e);
  }
  assert.deepEqual(coarse.snapshot().integrals, fine.snapshot().integrals);
  assert.equal(coarse.snapshot().integrals.fronting.msat_blocks, String(sats(1000) * 15));
  assert.equal(CapitalAccountingMachine.replay(fixtureConfig, fine.journal()).stateHash(), fine.stateHash());
});

test("5: competing active claims cannot overallocate the same collateral", () => {
  const t = new TraceBuilder(); t.fund("backing", sats(1000)); t.issue("one", "backing", sats(600));
  rejected(t, t.event("ISSUE_VTXO", { claim: { claim_id: "two", claimant: "bob", allocations: { backing: sats(500) }, expiry_height: 10 } }, { amount: sats(500) }), /I2/);
  t.issue("two", "backing", sats(400), 10, "bob"); checked(t);
});

test("6: refresh uses fresh backing while the original gross encumbrance persists", () => {
  const t = new TraceBuilder(); t.fund("backing", sats(1000)); t.fund("reserve", sats(1000), true); t.issue("old", "backing", sats(1000));
  t.add("REFRESH", { operation_id: "refresh", input_claim_ids: ["old"], reserve_ids: ["reserve"], fee: sats(2),
    replacement: { claim_id: "new", claimant: "alice", allocations: { reserve: sats(998) }, expiry_height: 30, parent_claim_id: "old" } });
  const s = t.m.snapshot(); assert.equal(s.K.old.state, "FORFEITED"); assert.equal(s.K.new.amount, sats(998));
  assert.equal(s.A.backing.state, "COMMITTED"); assert.equal(s.B.F, sats(1000)); checked(t);
});

test("7: reorganization invalidates confirmation and transitively rolls back reuse reservation", () => {
  const t = completeLifecycle(); const beforeSettlement = t.m.journal().findIndex(e => e.event_type === "HTLC_ACCEPTED" && e.data.operation_id === "pay-2");
  t.m = CapitalAccountingMachine.replay(fixtureConfig, t.m.journal().slice(0, beforeSettlement)); const before = t.m.journal();
  const blocks = Array.from({ length: 15 }, (_, i) => ({ height: i + 1, hash: i < 10 ? `block-${i + 1}` : `fork-${i + 1}`,
    parent_hash: i === 0 ? fixtureConfig.genesis_hash : i <= 10 ? `block-${i}` : `fork-${i}` }));
  t.add("REORG", { blocks }, { block_height: 15, block_hash: "fork-15", monotonic_timestamp: 9600 });
  const s = t.m.snapshot(); assert.equal(s.sweeps["sweep-1"].state, "BROADCAST"); assert.equal(s.A.recovered, undefined);
  assert.equal(s.B.C, 0); assert.equal(s.H.operations["pay-2"], undefined);
  assert.ok(Object.keys(s.J.orphaned).length >= 4); assert.equal(t.m.journal().length, before.length + 1); checked(t);
});

test("deep reorg preserves irreversible payment evidence and freezes further spending", () => {
  const t = completeLifecycle(), delivered = t.m.snapshot().totals.delivered;
  const blocks = Array.from({ length: 15 }, (_, i) => ({ height: i + 1, hash: i < 10 ? `block-${i + 1}` : `fork-${i + 1}`,
    parent_hash: i === 0 ? fixtureConfig.genesis_hash : i <= 10 ? `block-${i}` : `fork-${i}` }));
  t.add("REORG", { blocks }, { block_height: 15, block_hash: "fork-15", monotonic_timestamp: 9600 });
  assert.equal(t.m.snapshot().totals.delivered, delivered); assert.ok(t.m.report().reconciliation_required);
  rejected(t, t.event("TICK", {}), /halted/); checked(t);
});

test("offered demand includes unaffordable rejected requests without changing their economic state", () => {
  const t = funded(); t.settle(); t.add("PAYMENT_OFFERED", { operation_id: "unaffordable", holder: "alice" }, { amount: 1000000 });
  rejected(t, t.event("REQUEST_OUTGOING", { operation_id: "unaffordable", holder: "alice", input_claim_ids: ["change"], reserve_ids: ["reserve"], channel_id: "cln", delivered: 1000000, max_fee: 0, timeout_height: 5 }, { amount: 1000000 }));
  assert.equal(t.m.report().totals.offered, 1600000); assert.equal(t.m.report().delivery_rate, 600000 / 1600000);
});

test("8: recovered provenance funds a second settled payment; cumulative F exceeds B", () => {
  const t = completeLifecycle(), s = t.m.snapshot(); assert.equal(s.B.budget, sats(1000)); assert.equal(s.B.F, sats(2000)); assert.equal(s.B.C, sats(1000));
  assert.equal(s.H.operations["pay-2"].state, "SETTLED"); assert.deepEqual(s.A.recovered.parent_ids, ["backing"]);
  assert.equal(s.totals.delivered, sats(1600)); assert.equal(s.totals.inflows, sats(3000)); checked(t);
});

test("9: reuse before canonical finality, forged source, and absent evidence are atomic failures", () => {
  const t = funded(); t.settle(); t.fund("b2", sats(1000)); t.issue("v2", "b2", sats(1000), 40); t.sweep();
  const d = { sweep_id: "sweep-1", channel_funding_ref: "new-channel:0", funding_height: 11, funding_hash: "block-11", spendable: sats(1000),
    reuse: { operation_id: "reuse", holder: "alice", input_claim_ids: ["v2"], reserve_ids: ["recovered"], channel_id: "new", delivered: sats(1000), max_fee: 0, timeout_height: 20 } };
  rejected(t, t.event("CAPITAL_REUSABLE", d, { txid: "new-channel", block_hash: "block-11", evidence_refs: ["spends:sweep-tx:0"] }), /finality/);
  t.chain(12); rejected(t, t.event("CAPITAL_REUSABLE", d, { txid: "new-channel", block_hash: "block-12" }), /proof/);
});

test("10: independently funded second payment adds fronting, never recovers the first", () => {
  const t = funded(); t.settle(); t.fund("b2", sats(1000)); t.fund("r2", sats(1000), true); t.channel("r2", "cln2"); t.issue("v2", "b2", sats(1000));
  t.request("pay-2", "v2", "r2", "cln2", sats(1000)); t.settle("pay-2");
  assert.equal(t.m.snapshot().B.C, 0); assert.equal(t.m.report().outstanding_fronting, sats(2000)); checked(t);
});

test("idempotence, ID collision, unknown types, budget and malformed amounts", () => {
  const t = funded(); const last = t.m.journal().at(-1)!; const hash = t.m.stateHash(); t.m.apply(last); assert.equal(t.m.stateHash(), hash);
  rejected(t, { ...last, amount: last.amount + 1 }, /collision/);
  rejected(t, { ...last, event_id: "unknown", event_type: "MINT" } as unknown as CapitalEvent, /schema/);
  for (const amount of [-1, 0.1, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) rejected(t, t.event("TICK", {}, { amount }));
  rejected(t, t.event("REQUEST_OUTGOING", { ...last.data as any, operation_id: "double" }, { amount: sats(600) }));
  checked(t);
});

test("receipt conserves channel shares, charges fee, and cannot count channel funding twice", () => {
  const t = new TraceBuilder(); t.fund("r", sats(1000), true); t.channel("r", "cln", sats(1000));
  t.add("RECEIVE_LIGHTNING", { channel_id: "cln", asset_id: "receipt", fee: 1250,
    claim: { claim_id: "received", claimant: "bob", allocations: { receipt: 598750 }, expiry_height: 20 } }, { amount: sats(600) });
  assert.equal(t.m.snapshot().H.channels.cln.remote, 401250); assert.equal(t.m.snapshot().K.received.amount, 598750); checked(t);
  rejected(t, t.event("FUND", { asset_id: "duplicate", owner: "server", location: "onchain", backing_ref: "channel-cln:0", maturity_height: 0, pool: true },
    { amount: sats(2000), block_hash: fixtureConfig.genesis_hash, txid: "channel-cln" }), /duplicate underlying/);
});

test("split and merge retain provenance and value; exit output is outside operator boundary", () => {
  const t = new TraceBuilder(); t.fund("a", sats(1000)); t.add("SPLIT_MERGE", { input_ids: ["a"], outputs: [{ asset_id: "a1", amount: sats(400) }, { asset_id: "a2", amount: sats(600) }] });
  t.add("SPLIT_MERGE", { input_ids: ["a1", "a2"], outputs: [{ asset_id: "merged", amount: sats(1000) }] }); t.issue("v", "merged", sats(1000)); t.chain(2);
  t.add("EXIT", { claim_id: "v", fee: sats(1), output_id: "exit", destination: "alice-wallet", mode: "unilateral", inclusion_height: 1, inclusion_hash: "block-1" },
    { txid: "exit-tx", block_hash: "block-2", evidence_refs: ["fixture:ancestry-verified"] });
  assert.equal(t.m.snapshot().A.exit.original_amount, sats(999)); assert.equal(t.m.snapshot().A.exit.amount, 0); checked(t);
});

test("SettlementLedger checkpoint reconciles claims only; invariant CLI identifies first violating event", () => {
  const t = funded(); t.settle(); const oracle = new SettlementLedger(); oracle.fund("V", "alice", sats(1000));
  oracle.initiate({ id: "ln", from: { cls: "V", holder: "alice" }, to: { cls: "C", holder: "recipient" }, amount: sats(600), fee: 0, clock: { kind: "htlc" } });
  oracle.settleHtlc("ln"); oracle.settle("ln"); t.m.reconcile(oracle, ["alice"]);
  const events = t.m.journal(), bad = t.event("TICK", {}, { amount: -1 }); const r = checkJournal(fixtureConfig, [...events, bad]);
  assert.equal(r.ok, false); if (!r.ok) { assert.equal(r.event_id, bad.event_id); assert.equal(r.index, events.length); } checked(t);
});

test("unknown timestamps right-censor seconds; pending recovery survives evaluation horizon", () => {
  const t = funded(); t.settle(); t.add("TICK", {}, { block_height: 5, monotonic_timestamp: null });
  assert.equal(t.m.report().integrals.fronting.msat_seconds, null); assert.equal(t.m.report().exposures[0].right_censored, true); checked(t);
});

test("outbound reserve floors reject a request even when local economic ownership is sufficient", () => {
  const t = new TraceBuilder(); t.fund("backing", sats(1000)); t.fund("reserve", sats(1000), true);
  t.add("OPEN_CHANNEL", { asset_id: "reserve", channel_id: "cln", funding_ref: "ch:0", remote: 0, spendable: sats(500), receivable: 0 }, { txid: "ch", block_hash: fixtureConfig.genesis_hash });
  t.issue("vtxo", "backing", sats(1000)); t.add("PAYMENT_OFFERED", { operation_id: "pay", holder: "alice" }, { amount: sats(600) });
  rejected(t, t.event("REQUEST_OUTGOING", { operation_id: "pay", holder: "alice", input_claim_ids: ["vtxo"], reserve_ids: ["reserve"], channel_id: "cln", delivered: sats(600), max_fee: 0, timeout_height: 4 }, { amount: sats(600) }), /outbound/);
});

test("a failed HTLC can later settle with evidence; onchain amounts cannot contain fractional sats", () => {
  const t = funded(); t.add("HTLC_ACCEPTED", { operation_id: "pay-1" }); t.add("HTLC_FAILED", { operation_id: "pay-1" });
  t.add("HTLC_SETTLED", { operation_id: "pay-1", fee: 0, preimage_evidence_ref: "proof", change: { claim_id: "change", claimant: "alice", allocations: { reserve: sats(400) }, expiry_height: 30 } },
    { amount: sats(600), evidence_refs: ["proof"] }); checked(t);
  rejected(t, t.event("FUND", { asset_id: "fraction", owner: "server", location: "onchain", backing_ref: "fraction:0", maturity_height: 0, pool: false }, { txid: "fraction", amount: 1001, block_hash: fixtureConfig.genesis_hash }), /whole satoshis/);
});
