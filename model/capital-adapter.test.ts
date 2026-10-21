import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { ReadonlyCapitalAdapter, SOURCE_PINS, btcToMsat, msat } from "./capital-adapter.ts";
import { funded } from "./capital.fixtures.ts";

test("pinned Bark settlement proof overrides stale status and preserves fractional-sat routing fees", () => {
  const a = new ReadonlyCapitalAdapter(SOURCE_PINS), t = funded(600000, 2000); t.add("HTLC_ACCEPTED", { operation_id: "pay-1" });
  const preimage = "12".repeat(32), payment_hash = createHash("sha256").update(Buffer.from(preimage, "hex")).digest("hex");
  const attempt = { id: 1, payment_hash, amount_msat: 600000, final_amount_msat: 601001, status: "failed" as const, user_fee_sat: 2, lightning_htlc_subscription_id: null };
  const pays = { pays: [{ payment_hash, status: "complete" as const, amount_msat: 600000, amount_sent_msat: 601001 }] };
  const change = { claim_id: "change", claimant: "alice", allocations: { reserve: 398000 }, expiry_height: 30 };
  const base = t.event("HTLC_SETTLED", { operation_id: "pay-1", fee: 0, preimage_evidence_ref: "unused", change });
  assert.throws(() => a.settlement(base, "pay-1", attempt, null, pays), /htlc_settlement/);
  const e = a.settlement(base, "pay-1", attempt, { payment_hash, preimage }, pays, change); t.m.apply(e);
  assert.equal(t.m.snapshot().totals.fees, 1001); assert.equal(t.m.snapshot().totals.service_revenue, 999);
  assert.equal(t.m.snapshot().holders.alice.fees, 2000); assert.ok(!JSON.stringify(e).includes(preimage));
  assert.throws(() => a.settlement(base, "pay-1", attempt, { payment_hash, preimage: "34".repeat(32) }, pays), /preimage/);
  assert.throws(() => a.settlement(base, "pay-1", attempt, { payment_hash, preimage }, { pays: [...pays.pays, ...pays.pays] }), /one complete/);
});

test("read-only adapter rejects unknown revisions and unsafe unit conversions", () => {
  assert.throws(() => new ReadonlyCapitalAdapter({ ...SOURCE_PINS, bark: "main" }));
  assert.equal(btcToMsat("0.00000001"), 1000); assert.equal(btcToMsat("1.12345678"), 112345678000);
  assert.equal(msat("1001msat"), 1001);
  for (const bad of ["1e-8", "0.000000001", "-1", "NaN"]) assert.throws(() => btcToMsat(bad));
  for (const bad of ["1.5msat", "-1msat", "9007199254740992"]) assert.throws(() => msat(bad));
});

test("channel snapshots distinguish economic share, HTLCs and usable capacity", () => {
  const a = new ReadonlyCapitalAdapter(SOURCE_PINS);
  const c = a.channelSnapshot({ channel_id: "c", funding_txid: "fund", funding_outnum: 1, state: "CHANNELD_NORMAL", to_us_msat: 1000000,
    total_msat: 2000000, spendable_msat: 700000, receivable_msat: 900000, htlcs: [{ direction: "out", id: 1, amount_msat: 200000, state: "SENT_ADD_HTLC" }] });
  assert.equal(c.owned_msat, 1000000); assert.equal(c.inflight_out_msat, 200000); assert.equal(c.can_initialize_quiescent, false);
});

test("Core adapter verifies canonical inclusion and fails closed on unsupported output shapes", () => {
  const a = new ReadonlyCapitalAdapter(SOURCE_PINS), t = funded(), base = t.event("SWEEP_CONFIRMED", { sweep_id: "s", inclusion_height: 1, inclusion_hash: "h1" }, { block_height: 2, txid: "sweep" });
  const tx = { txid: "sweep", blockhash: "h1", confirmations: 2, in_active_chain: true, vin: [{ txid: "in", vout: 0 }], vout: [{ n: 0, value: "0.00000999", scriptPubKey: { hex: "51" } }] };
  const e = a.sweepConfirmation(base, "s", tx, { "in:0": 1000000 }, 0, "51", 1, "h1", 2); assert.equal(e.amount, 999000);
  assert.throws(() => a.sweepConfirmation(base, "s", { ...tx, in_active_chain: false }, { "in:0": 1000000 }, 0, "51", 1, "h1", 2), /active chain/);
  assert.throws(() => a.sweepConfirmation(base, "s", tx, { "in:0": 1000000 }, 1, "51", 1, "h1", 2), /shape/);
});
