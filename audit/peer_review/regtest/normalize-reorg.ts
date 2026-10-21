// Reconcile a real orphaned/reconfirmed exit without restoring a spent VTXO.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { CapitalAccountingMachine, checkJournal, sats, sum, type CapitalEvent, type Block } from "../../../model/capital.ts";
import { btcToMsat } from "../../../model/capital-adapter.ts";
const dir = "audit/peer_review/regtest/evidence/", hashes: Record<string, string> = {};
function load(name: string) {
  const bytes = readFileSync(`${dir}${name}.json`); hashes[name] = createHash("sha256").update(bytes).digest("hex"); return JSON.parse(bytes.toString());
}
const config = load("normalized-config"), old = load("canonical-chain"), inbound = load("inbound-source-and-chain");
const offboard = load("offboard-source-and-chain"), intent = load("reorg-exit-intent");
const fork = load("reorg-exit-orphaned-headers"), final = load("reorg-exit-final-headers");
const before = load("reorg-exit-before"), pending = load("reorg-exit-orphaned"), after = load("reorg-exit-reconfirmed");
const pendingWallet = load("action-reorg-client-pending-sync").result, finalWallet = load("action-reorg-client-confirmed-sync").result;
const baselineBytes = readFileSync(`${dir}offboard-lifecycle.jsonl`);
hashes["offboard-lifecycle.jsonl"] = createHash("sha256").update(baselineBytes).digest("hex");
const baseline: CapitalEvent[] = baselineBytes.toString().trim().split(/\r?\n/).map(x => JSON.parse(x));
const exit = baseline.at(-1)!;
assert.ok(exit.event_type === "EXIT" && exit.data.funding);
if (exit.event_type !== "EXIT" || !exit.data.funding) throw Error("funded exit checkpoint required");
const txid = exit.txid!, claim = exit.data.claim_id, payout = exit.data.output_id;
assert.equal(intent.txid, txid); assert.equal(intent.payment_resent, false); assert.equal(intent.new_fixture_funding_sat, 0);
assert.equal(intent.common_height, 4442); assert.equal(before.chain_after.blocks, 4445);
assert.equal(pending.chain_after.blocks, 4446); assert.equal(after.chain_after.blocks, 4449);
const prefix = [...old.headers, ...inbound.headers].filter((h: any) => h.height > 0 && h.height <= intent.common_height);
const blocks = (tail: any[]): Block[] => [...prefix, ...tail].map(h => ({ height: h.height, hash: h.hash, parent_hash: h.previousblockhash }));
for (const headers of [fork.old_blocks, final.old_blocks]) {
  assert.deepEqual(headers.map((h: any) => h.hash), offboard.headers.map((h: any) => h.hash));
  assert.ok(headers.every((h: any) => h.confirmations === -1));
}
assert.deepEqual(fork.replacement_headers.map((h: any) => h.hash), final.headers.slice(0, 4).map((h: any) => h.hash));
assert.ok(fork.replacement_headers.every((h: any) => h.nTx === 1));
for (const s of [before, pending, after]) {
  assert.equal(s.stable_chain_tip, true); assert.equal(s.chain_after.chain, "regtest");
  for (const name of ["captaind_tip", "watchmand_tip"]) {
    assert.equal(s.database[name][0].height, s.chain_after.blocks);
    assert.equal(s.database[name][0].hash, s.chain_after.bestblockhash);
  }
  assert.deepEqual(s.database.offboards, before.database.offboards);
  assert.equal(s.database.offboards[0].wallet_commit, true);
  assert.equal(s.database.vtxos.find((v: any) => v.vtxo_id === claim).spend_state, "spent");
  assert.deepEqual(s.database.vtxos.map((v: any) => [v.vtxo_id, v.spend_state, v.amount, v.offboarded_in]),
    before.database.vtxos.map((v: any) => [v.vtxo_id, v.spend_state, v.amount, v.offboarded_in]));
  assert.deepEqual(s.database.virtual_transactions, before.database.virtual_transactions);
  assert.deepEqual(s.database.settlements, before.database.settlements);
  assert.equal(s.channels.channels[0].to_us_msat, before.channels.channels[0].to_us_msat);
  assert.deepEqual(s.bark_balance, before.bark_balance);
  assert.equal(s.transactions[txid].transaction.hex, before.transactions[txid].transaction.hex);
  assert.equal(s.transactions[txid].transaction.hex, s.database.offboards[0].signed_tx);
  assert.equal(s.transactions[txid].transaction.txid, txid);
}
assert.deepEqual(pending.mempool, [txid]); assert.equal(pending.transactions[txid].transaction.confirmations ?? 0, 0);
assert.equal(pending.transactions[txid].transaction.blockhash, undefined);
assert.equal(pendingWallet.confirmed_sat, 99845); assert.equal(pendingWallet.trusted_spendable_sat, 99845);
assert.equal(pendingWallet.untrusted_pending_sat, 15732);
assert.deepEqual(pending.server_wallet.rounds.confirmed_utxos, []);
assert.deepEqual(pending.server_wallet.rounds.unconfirmed_utxos, [`${txid}:2`]);
const tx = after.transactions[txid].transaction, inclusion = final.headers.find((h: any) => h.hash === tx.blockhash);
assert.equal(tx.confirmations, 3); assert.equal(inclusion.height, 4447); assert.equal(tx.in_active_chain, true);
assert.equal(finalWallet.confirmed_sat, 115577); assert.equal(finalWallet.trusted_spendable_sat, 115577);
assert.equal(finalWallet.untrusted_pending_sat, 0); assert.ok(!after.mempool.includes(txid));
assert.equal(after.bark_utxos.find((u: any) => u.outpoint === payout).confirmation_height, inclusion.height);
const m = CapitalAccountingMachine.replay(config, baseline), initial = m.snapshot();
function event(id: string, snap: any, headers: any[]): CapitalEvent & { event_type: "REORG" } {
  return { event_id: id, trace_id: "owned-regtest-exit-reorg-8f5d", event_type: "REORG", amount: 0, unit: "msat",
    asset_ids: [], claim_ids: [], causal_parent_ids: [], block_height: snap.chain_after.blocks, block_hash: snap.chain_after.bestblockhash,
    monotonic_timestamp: null, txid: null, evidence_refs: Object.entries(hashes).map(([n, h]) => `snapshot:${n}:sha256:${h}`), data: { blocks: blocks(headers) } };
}
m.apply(event("exit-reorg-pending", pending, fork.replacement_headers));
const frozen = m.snapshot(), pendingCheck = checkJournal(config, m.journal());
assert.equal(pendingCheck.ok, true); assert.equal(pendingCheck.reconciled, false);
assert.deepEqual(frozen.J.reconciliation_required?.irreversible_event_ids, [exit.event_id]);
for (const key of ["A", "K", "H", "B", "holders", "totals"] as const) assert.deepEqual(frozen[key], initial[key]);
const reconfirmed = event("exit-reorg-reconfirmed", after, final.headers);
reconfirmed.data.reconfirmed_exits = [{ event_id: exit.event_id, txid, inclusion_height: inclusion.height, inclusion_hash: inclusion.hash,
  evidence_ref: `snapshot:reorg-exit-reconfirmed:sha256:${hashes["reorg-exit-reconfirmed"]}` }];
m.apply(reconfirmed);
const state = m.snapshot(); assert.equal(state.J.reconciliation_required, null);
for (const key of ["K", "B", "holders", "totals"] as const) assert.deepEqual(state[key], initial[key]);
for (const a of Object.values(state.A)) {
  assert.equal(a.amount, initial.A[a.asset_id].amount); assert.equal(a.state, initial.A[a.asset_id].state);
  if (a.location === "onchain" && a.amount > 0) {
    assert.ok(after.unspent_outputs[a.backing_ref]); assert.equal(btcToMsat(after.unspent_outputs[a.backing_ref].value), a.amount);
  }
}
assert.equal(sum(Object.values(state.A).map(a => a.amount)), sats(2011056));
assert.deepEqual(m.journal().slice(0, baseline.length), baseline);
assert.equal(m.stateHash(), CapitalAccountingMachine.replay(config, m.journal()).stateHash());
const report = { evidence_class: "observed_regtest_exit_reorg", economic_reconciliation: true, replay_verified: true,
  original_events_unchanged: true, pending_check: pendingCheck, final_check: checkJournal(config, m.journal()),
  original_tip: before.chain_after.bestblockhash, common_height: 4442, orphaned_depth: 3,
  pending_height: 4446, reconfirmed_inclusion_height: inclusion.height, final_height: 4449,
  same_signed_transaction_sha256: createHash("sha256").update(Buffer.from(tx.hex, "hex")).digest("hex"), txid,
  client_pending_sat: 15732, client_final_confirmed_sat: 115577, report: m.report(), source_sha256: hashes,
  complete_fixture: { initial_sat: 2200000, operator_assets_sat: 2011056, client_onchain_sat: 115577, peer_channel_sat: 58000, miner_fees_sat: 15367 },
  limits: ["Observers were paused during fork construction and resumed at a higher tip; this is not an uninterrupted propagation-clock experiment.",
    "During the pending interval the model retains a frozen historical economic checkpoint, not a current spendability assertion.",
    "Reconfirmed exit replay uses the new confirmed observation anchor; branch-local integrals are not wall-clock exposure across the reorg gap.",
    "This terminal-exit reconciliation does not generalize to later economic events, replacement transactions, live sweep reorgs or unilateral exits."] };
assert.equal(sum(Object.values(report.complete_fixture).slice(1)), report.complete_fixture.initial_sat);
writeFileSync(`${dir}reorg-exit-lifecycle.jsonl`, m.journal().map(e => JSON.stringify(e)).join("\n") + "\n");
writeFileSync(`${dir}reorg-exit-machine-reconciliation.json`, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify({ events: m.journal().length, state_hash: m.stateHash(), pending_check: pendingCheck, final_check: report.final_check }, null, 2));
