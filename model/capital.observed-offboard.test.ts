import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CapitalAccountingMachine, checkJournal, sats, sum, type CapitalEvent } from "./capital.ts";
const dir = "audit/peer_review/regtest/evidence/";
const config = JSON.parse(readFileSync(`${dir}normalized-config.json`, "utf8"));
const journal: CapitalEvent[] = readFileSync(`${dir}offboard-lifecycle.jsonl`, "utf8").trim().split(/\r?\n/).map(x => JSON.parse(x));

test("observed cooperative exit pays from fresh wallet capital and preserves old backing", () => {
  const before = CapitalAccountingMachine.replay(config, journal.slice(0, -1)).snapshot();
  const m = CapitalAccountingMachine.replay(config, journal), s = m.snapshot(), e = journal.at(-1)!;
  if (e.event_type !== "EXIT" || !e.data.funding) throw Error("funded exit required");
  const d = e.data, f = d.funding!, parent = before.K[d.claim_id], recovery = s.K[f.recovery_claim.claim_id];
  for (const id of parent.backing_ids) {
    assert.equal(s.A[id].amount, before.A[id].amount); assert.equal(s.A[id].state, "COMMITTED");
    assert.equal(s.K[d.claim_id].allocations[id], 0); assert.equal(recovery.allocations[id], parent.allocations[id]);
  }
  assert.equal(s.K[d.claim_id].state, "FORFEITED"); assert.equal(recovery.state, "FORFEITED");
  assert.equal(recovery.amount, sats(18962)); assert.equal(recovery.claimant, "server");
  assert.equal(s.A[d.output_id].owner, "client"); assert.equal(s.A[d.output_id].amount, 0);
  assert.equal(s.A[d.output_id].original_amount, sats(15732));
  assert.equal(s.B.F - before.B.F, sats(18035)); assert.equal(s.B.C, before.B.C);
  assert.equal(s.B.F - s.B.C, sats(56989));
  assert.equal(s.totals.fees - before.totals.fees, sats(1973));
  assert.equal(s.totals.service_revenue - before.totals.service_revenue, sats(927));
  assert.equal(s.holders.client.fees - before.holders.client.fees, sats(2900));
  assert.equal(sum(Object.values(s.A).map(a => a.amount)), sats(2011056));
  assert.ok(checkJournal(config, journal).ok);
  assert.equal(m.stateHash(), "8dfce8a397e35d9330c05146c062abc1cd70ba445dace868cb3659e04f1b49aa");
});

test("funded exit rejects payout, connector, forfeit, fee and finality corruption atomically", () => {
  for (const mutation of ["payout", "connector", "parent", "allocation", "proof", "fee", "finality", "mode"] as const) {
    const m = CapitalAccountingMachine.replay(config, journal.slice(0, -1)), hash = m.stateHash();
    const e = structuredClone(journal.at(-1)!);
    if (e.event_type !== "EXIT" || !e.data.funding) throw Error("funded exit required");
    const d = e.data, f = d.funding!;
    if (mutation === "payout") d.output_id = f.connector_ids[0];
    if (mutation === "connector") f.transaction.outputs.find(o => o.asset_id === f.connector_ids[0])!.release_height = 8755;
    if (mutation === "parent") f.recovery_claim.parent_claim_id = "invented";
    if (mutation === "allocation") f.recovery_claim.allocations[f.connector_ids[0]]++;
    if (mutation === "proof") e.evidence_refs = e.evidence_refs.filter(r => !r.includes("forfeit"));
    if (mutation === "fee") d.fee = f.transaction.fee - 1;
    if (mutation === "finality") d.inclusion_height = e.block_height;
    if (mutation === "mode") d.mode = "unilateral";
    assert.throws(() => m.apply(e), mutation); assert.equal(m.stateHash(), hash);
  }
});

test("cooperative connector remains locked beyond the original claim expiry", () => {
  const m = CapitalAccountingMachine.replay(config, journal), s = m.snapshot(), e = journal.at(-1)!;
  if (e.event_type !== "EXIT" || !e.data.funding) throw Error("funded exit required");
  const connector = s.A[e.data.funding.connector_ids[0]];
  assert.equal(connector.amount, sats(330)); assert.equal(connector.state, "COMMITTED");
  assert.equal(connector.release_height, 8900);
  assert.equal(s.K[e.data.funding.recovery_claim.claim_id].expiry_height, 8756);
  assert.ok(m.report().exposures.find(o => o.operation_id === e.data.funding!.operation_id)?.right_censored);
});
