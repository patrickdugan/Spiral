import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CapitalAccountingMachine, checkJournal, sats, sum, type CapitalEvent } from "./capital.ts";
const dir = "audit/peer_review/regtest/evidence/";
const config = JSON.parse(readFileSync(`${dir}normalized-config.json`, "utf8"));
const journal: CapitalEvent[] = readFileSync(`${dir}failure-lifecycle.jsonl`, "utf8").trim().split(/\r?\n/).map(x => JSON.parse(x));

test("two actual failed attempts preserve every asset and replace all client claims without charging fee ceilings", () => {
  const baseline = CapitalAccountingMachine.replay(config, journal.slice(0, 34)).snapshot();
  const m = CapitalAccountingMachine.replay(config, journal), s = m.snapshot();
  assert.ok(checkJournal(config, journal).ok);
  assert.equal(sum(Object.values(s.A).map(a => a.amount)), sum(Object.values(baseline.A).map(a => a.amount)));
  assert.equal(s.totals.fees, baseline.totals.fees); assert.equal(s.totals.service_revenue, baseline.totals.service_revenue);
  assert.equal(s.totals.outflows, baseline.totals.outflows); assert.equal(s.B.F - s.B.C, baseline.B.F - baseline.B.C);
  assert.equal(sum(Object.values(s.K).filter(c => c.state === "ACTIVE").map(c => c.amount)), sats(38347));
  assert.equal(Object.values(s.K).filter(c => c.state === "ACTIVE").length, 6);
  const measured = Object.values(s.H.operations).find(o => o.capacity_reserved !== undefined)!;
  assert.equal(measured.in_flight_amount, sats(1001)); assert.equal(measured.capacity_reserved, sats(1428));
  assert.equal(measured.max_fee, sats(75)); assert.equal(measured.state, "RESOLVED");
  assert.equal(m.stateHash(), CapitalAccountingMachine.replay(config, journal).stateHash());
});

test("observed failure checker stops at the first overallocated refund", () => {
  const changed = structuredClone(journal);
  const index = changed.findIndex(e => e.event_type === "RESOLVE_FAILED");
  const event = changed[index]; assert.equal(event.event_type, "RESOLVE_FAILED");
  if (event.event_type !== "RESOLVE_FAILED") throw new Error("fixture missing revocation");
  const allocations = event.data.replacements![0].allocations;
  allocations[Object.keys(allocations)[0]] += 1;
  const result = checkJournal(config, changed);
  assert.equal(result.ok, false);
  assert.match(JSON.stringify(result), /revocation replacement backing mismatch/);
  assert.match(JSON.stringify(result), new RegExp(event.event_id));
});

test("shared-root revocation cannot move a child's provenance to a different input", () => {
  const changed = structuredClone(journal);
  const event = [...changed].reverse().find(e => e.event_type === "RESOLVE_FAILED")!;
  if (event.event_type !== "RESOLVE_FAILED") throw new Error("fixture missing revocation");
  const replacements = event.data.replacements!, first = replacements[0];
  const otherParent = replacements.find(c => c.parent_claim_id !== first.parent_claim_id)!.parent_claim_id;
  first.parent_claim_id = otherParent;
  const result = checkJournal(config, changed);
  assert.equal(result.ok, false); assert.match(JSON.stringify(result), /revocation parent provenance mismatch/);
});
