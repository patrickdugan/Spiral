import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { CapitalAccountingMachine, sats, sum, type CapitalEvent, type MachineConfig } from "./capital.ts";
const root = pathToFileURL(resolve("audit/peer_review/regtest/evidence") + "/");
const config: MachineConfig = JSON.parse(readFileSync(new URL("normalized-config.json", root), "utf8"));
const events: CapitalEvent[] = readFileSync(new URL("inbound-lifecycle.jsonl", root), "utf8").trim().split(/\r?\n/).map(x => JSON.parse(x));

test("observed receive keeps gross LN ownership separate from net inventory-backed holder claim", () => {
  const before = CapitalAccountingMachine.replay(config, events.slice(0, -1)).snapshot();
  const m = CapitalAccountingMachine.replay(config, events), after = m.snapshot();
  const receipt = events.at(-1)!; assert.equal(receipt.event_type, "RECEIVE_LIGHTNING");
  if (receipt.event_type !== "RECEIVE_LIGHTNING") throw Error("receipt missing");
  const d = receipt.data, claim = after.K[d.claim.claim_id];
  assert.equal(after.A[d.asset_id].amount, sats(2000)); assert.equal(after.A[d.asset_id].state, "FREE");
  assert.equal(claim.amount, sats(1896)); assert.ok(!claim.backing_ids.includes(d.asset_id));
  assert.equal(after.holders.client.received - before.holders.client.received, sats(2000));
  assert.equal(after.holders.client.fees - before.holders.client.fees, sats(104));
  assert.equal(after.totals.service_revenue - before.totals.service_revenue, sats(104));
  assert.equal(after.totals.fees, before.totals.fees);
  assert.equal(after.B.C, before.B.C); assert.equal(after.B.F, before.B.F);
  assert.equal(after.B.pool.transfers_in - before.B.pool.transfers_in, sats(2000));
  assert.equal(sum(Object.values(after.A).map(a => a.amount)), sats(2028761));
  assert.equal(m.stateHash(), "459c3166421f6c0deb47009b250e428515415054767dd8a3f86c33f60046e1f8");
});

test("inventory receive rejects unsupported backing, excess allocation, expiry and missing proof atomically", () => {
  for (const mutation of ["liquidity", "excess", "expiry", "proof", "fee"] as const) {
    const m = CapitalAccountingMachine.replay(config, events.slice(0, -1)), hash = m.stateHash();
    const e = structuredClone(events.at(-1)!); assert.equal(e.event_type, "RECEIVE_LIGHTNING");
    if (e.event_type !== "RECEIVE_LIGHTNING") throw Error("receipt missing");
    const d = e.data;
    if (mutation === "liquidity") d.claim.allocations = { [d.asset_id]: sats(1896) };
    if (mutation === "excess") { e.amount = sats(20105); d.claim.allocations[Object.keys(d.claim.allocations)[0]] = sats(20001); }
    if (mutation === "expiry") d.claim.expiry_height++;
    if (mutation === "proof") delete d.settlement_evidence_ref;
    if (mutation === "fee") d.service_fee = sats(2000);
    assert.throws(() => m.apply(e), mutation); assert.equal(m.stateHash(), hash);
  }
});

test("pool preparation spends recorded reserve and retains the entire shared root", () => {
  const m = CapitalAccountingMachine.replay(config, events), s = m.snapshot();
  const rootId = "1579dc43b9c47805b95472f9a4c2ec802e562c0bea654af71a1d08b4ee92c153:1";
  assert.equal(s.A[rootId].amount, sats(20000)); assert.equal(s.A[rootId].state, "COMMITTED");
  assert.equal(s.A[rootId].release_height, 4871);
  assert.equal(sum(Object.values(s.K).filter(c => c.state === "ACTIVE" && c.backing_ids.includes(rootId)).map(c => c.amount)), sats(1896));
  assert.equal(s.B.F - s.B.C, sats(38954));
  const observed = JSON.parse(readFileSync(new URL("inbound-settled.json", root), "utf8"));
  const change = observed.database.vtxos.find((v: any) => v.anchor_point === rootId && v.amount === 8104 && v.spend_state === "pool");
  assert.ok(change); assert.ok(!observed.database.pool.some((v: any) => v.vtxo_id === change.vtxo_id));
});
