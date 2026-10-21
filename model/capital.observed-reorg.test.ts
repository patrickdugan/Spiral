import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { CapitalAccountingMachine, checkJournal, sats, type CapitalEvent } from "./capital.ts";
const dir = "audit/peer_review/regtest/evidence/";
const config = JSON.parse(readFileSync(`${dir}normalized-config.json`, "utf8"));
const journal: CapitalEvent[] = readFileSync(`${dir}reorg-exit-lifecycle.jsonl`, "utf8").trim().split(/\r?\n/).map(x => JSON.parse(x));
const baseline = journal.slice(0, -2), pending = journal.at(-2)!, confirmed = journal.at(-1)!;
function reconfirmation() {
  const e = structuredClone(confirmed);
  if (e.event_type !== "REORG" || !e.data.reconfirmed_exits) throw Error("reconfirmation required");
  return e;
}
function reject(m: CapitalAccountingMachine, e: CapitalEvent, pattern?: RegExp) {
  const hash = m.stateHash(), original = JSON.stringify(m.journal());
  if (pattern) assert.throws(() => m.apply(e), pattern); else assert.throws(() => m.apply(e));
  assert.equal(m.stateHash(), hash);
  assert.equal(JSON.stringify(m.journal()), original);
}

test("observed orphaned exit freezes spendability without resurrecting its spent claim", () => {
  const m = CapitalAccountingMachine.replay(config, baseline), before = m.snapshot(); m.apply(pending);
  const s = m.snapshot(); assert.deepEqual(s.J.reconciliation_required?.irreversible_event_ids, ["offboard-2"]);
  for (const key of ["A", "K", "H", "B", "totals", "holders"] as const) assert.deepEqual(s[key], before[key]);
  assert.equal(s.B.F - s.B.C, sats(56989));
  reject(m, { ...pending, event_id: "blocked-tick", event_type: "TICK", data: {} }, /halted/);
  assert.equal(checkJournal(config, m.journal()).reconciled, false);
  assert.equal(m.stateHash(), CapitalAccountingMachine.replay(config, m.journal()).stateHash());
});

test("same signed exit reconfirms once with unchanged source journal and conserved economics", () => {
  const m = CapitalAccountingMachine.replay(config, journal), s = m.snapshot();
  const before = CapitalAccountingMachine.replay(config, baseline).snapshot();
  assert.equal(s.J.reconciliation_required, null); assert.deepEqual(s.B, before.B); assert.deepEqual(s.K, before.K);
  assert.deepEqual(s.totals, before.totals); assert.equal(s.J.reconfirmed_exits?.["offboard-2"].inclusion_height, 4447);
  assert.equal(s.J.orphaned["offboard-1"], "orphaned block"); assert.ok(s.J.canonical.includes("offboard-2"));
  assert.equal(JSON.stringify(m.journal().slice(0, baseline.length)), JSON.stringify(baseline));
  const hash = m.stateHash(); m.apply(baseline.at(-1)!); m.apply(confirmed); assert.equal(m.stateHash(), hash);
  assert.equal(checkJournal(config, journal).reconciled, true);
  assert.equal(hash, "a47198789818d3c09b3ca8b74ff52c985c480ed454e866be721613889a7f0bd7");
});

test("exit reconfirmation rejects false identity, evidence, finality and duplicate claims atomically", () => {
  for (const mutation of ["txid", "event", "proof", "depth", "hash", "duplicate"] as const) {
    const m = CapitalAccountingMachine.replay(config, journal.slice(0, -1)), e = reconfirmation(), r = e.data.reconfirmed_exits![0];
    if (mutation === "txid") r.txid = "different-transaction";
    if (mutation === "event") r.event_id = "inbound-3";
    if (mutation === "proof") e.evidence_refs = [];
    if (mutation === "depth") { r.inclusion_height = e.block_height; r.inclusion_hash = e.block_hash!; }
    if (mutation === "hash") r.inclusion_hash = "orphan";
    if (mutation === "duplicate") e.data.reconfirmed_exits!.push(structuredClone(r));
    reject(m, e);
  }
});

test("exit reanchoring rejects a canonical checkpoint or intervening observations", () => {
  const canonical = CapitalAccountingMachine.replay(config, journal), e = reconfirmation(); e.event_id = "redundant-anchor";
  reject(canonical, e, /still canonical/);
  for (const type of ["TICK", "PAYMENT_OFFERED"] as const) {
    const m = CapitalAccountingMachine.replay(config, baseline), state = m.snapshot();
    const next = { ...pending, event_id: `intervening-${type}`, block_height: state.J.height, block_hash: state.J.chain[state.J.height] };
    m.apply(type === "TICK" ? { ...next, event_type: "TICK", data: {} } :
      { ...next, event_type: "PAYMENT_OFFERED", amount: sats(1), data: { operation_id: "later", holder: "client" } });
    reject(m, reconfirmation(), /terminal economic checkpoint/);
  }
});

test("persisted exit anchor survives further replay and freezes on a second orphaning", () => {
  const m = CapitalAccountingMachine.replay(config, journal), stable = reconfirmation();
  stable.event_id = "later-canonical-replay"; delete stable.data.reconfirmed_exits; m.apply(stable);
  assert.equal(m.snapshot().J.reconciliation_required, null);
  assert.equal(m.snapshot().J.reconfirmed_exits?.["offboard-2"].inclusion_height, 4447);
  const fork = structuredClone(stable); fork.event_id = "second-exit-orphaning";
  for (const b of fork.data.blocks.filter(b => b.height >= 4447)) {
    b.hash = `second-fork-${b.height}`; if (b.height > 4447) b.parent_hash = `second-fork-${b.height - 1}`;
  }
  fork.block_hash = "second-fork-4449"; m.apply(fork);
  assert.deepEqual(m.snapshot().J.reconciliation_required?.irreversible_event_ids, ["offboard-2"]);
  assert.equal(m.snapshot().B.F, sats(158343)); assert.equal(m.snapshot().B.C, sats(101354));
  assert.equal(m.stateHash(), CapitalAccountingMachine.replay(config, m.journal()).stateHash());
});
