import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CapitalAccountingMachine, checkJournal, sats, type CapitalEvent } from "./capital.ts";
import { ObservedRegtestAdapter } from "./capital-observed-adapter.ts";
const root = "audit/peer_review/regtest/evidence/";
const read = (name: string) => JSON.parse(readFileSync(root + name, "utf8"));
const config = read("normalized-config.json");
const journal: CapitalEvent[] = readFileSync(root + "lifecycle-observed.jsonl", "utf8").trim().split("\n").map(l => JSON.parse(l));

test("observed 34-event regtest replay matches independent graph conservation and retained obligations", () => {
  const m = CapitalAccountingMachine.replay(config, journal), observed = read("machine-reconciliation.json"), graph = read("economic-reconciliation.json");
  assert.equal(m.stateHash(), observed.report.state_hash); assert.equal(checkJournal(config, journal).ok, true);
  assert.equal(Object.values(m.snapshot().A).reduce((n, a) => n + a.amount, 0), sats(graph.operator_remaining_economic_sat));
  assert.equal(m.snapshot().totals.fees, sats(graph.operator_miner_fees_sat));
  assert.equal(m.report().outstanding_fronting, sats(38954));
  assert.equal(m.report().integrals.fronting.msat_seconds, null);
  assert.equal(m.report().delivery_rate, 1); assert.equal(m.journal().length, 34);
});
test("observed sweep reorg rolls back recovery credit and reuse without erasing earlier Lightning delivery", () => {
  const m = CapitalAccountingMachine.replay(config, journal), headers = read("canonical-chain.json").headers;
  const blocks = headers.slice(1).map((h: any) => ({ height: h.height, hash: h.height <= 4433 ? h.hash : `fork-${h.height}`,
    parent_hash: h.height <= 4434 ? h.previousblockhash : `fork-${h.height - 1}` }));
  const e: CapitalEvent = { ...journal.at(-1)!, event_id: "reorg-observed-fixture", event_type: "REORG", data: { blocks },
    block_hash: "fork-4439", evidence_refs: ["fixture:synthetic-reorg-over-observed-prefix"] };
  m.apply(e); assert.equal(m.snapshot().totals.delivered, sats(60000)); assert.equal(m.snapshot().B.C, sats(499));
  assert.equal(m.snapshot().J.reconciliation_required, null);
  assert.ok(Object.keys(m.snapshot().J.orphaned).length > 0);
  assert.equal(CapitalAccountingMachine.replay(config, [...journal, e]).stateHash(), m.stateHash());
});
test("observed checker identifies tampered round fee at the first violating event", () => {
  const changed = structuredClone(journal), index = changed.findIndex(e => e.event_type === "ONCHAIN_TRANSACTION" && e.data.refresh);
  const e = changed[index]; if (e.event_type !== "ONCHAIN_TRANSACTION") throw new Error("fixture"); e.data.fee += 1000;
  const result = checkJournal(config, changed); assert.equal(result.ok, false);
  if (!result.ok) { assert.equal(result.index, index); assert.match(result.error, /value\/fee/); }
});
test("executed adapter rejects wrong binary pin, chain ancestry and settlement attestation", () => {
  const identity = read("runtime-identity.json"), source = read("runtime-source.json"), headers = read("canonical-chain.json").headers;
  const bad = structuredClone(identity); bad.executables[0].sha256 = "0".repeat(64);
  assert.throws(() => new ObservedRegtestAdapter(bad, source, headers), /unsupported executable/);
  const broken = structuredClone(headers); broken[113].previousblockhash = "unrelated";
  assert.throws(() => new ObservedRegtestAdapter(identity, source, broken), /noncontiguous/);
  const adapter = new ObservedRegtestAdapter(identity, source, headers), snapshot = read("payment-result-reconciliation.json");
  const proof = snapshot.database.settlements[0]; proof.preimage_sha256_verified = "0".repeat(64);
  assert.throws(() => adapter.settlement(snapshot.database.attempts[0], proof, snapshot.pays), /attestation mismatch/);
});
