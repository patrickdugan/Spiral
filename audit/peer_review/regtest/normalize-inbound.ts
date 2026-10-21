// Replay the independently funded receive inventory and one settled receipt.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { CapitalAccountingMachine, sats, sum, type CapitalEvent, type Envelope, type Payloads } from "../../../model/capital.ts";
import { btcToMsat } from "../../../model/capital-adapter.ts";
import { ObservedRegtestAdapter } from "../../../model/capital-observed-adapter.ts";
const dir = "audit/peer_review/regtest/evidence/", hashes: Record<string, string> = {};
function load(name: string) {
  const raw = readFileSync(`${dir}${name}.json`); hashes[name] = createHash("sha256").update(raw).digest("hex"); return JSON.parse(raw.toString());
}
const config = load("normalized-config"), identity = load("runtime-identity"), source = load("runtime-source"), originalChain = load("canonical-chain");
const pin = load("inbound-source-and-chain"), runtime = load("inbound-plugin-runtime");
assert.equal(pin.source_revision, source.revision); assert.equal(pin.genesis, identity.genesis);
assert.equal(runtime.source_commit, pin.hold_revision); assert.equal(runtime.source_tag, "v0.3.3");
assert.equal(runtime.binary_sha256, "f98cd795e68a214b11fe168cc08690a50837dcefc93be6b885cb69d74ef1c1a4");
assert.equal(runtime.cln_binary_sha256, identity.executables.find((x: any) => x.binary === "lightningd").sha256);
const adapter = new ObservedRegtestAdapter(identity, source, [...originalChain.headers, ...pin.headers]);
const baseline = readFileSync(`${dir}failure-lifecycle.jsonl`, "utf8").trim().split(/\r?\n/).map(x => JSON.parse(x));
const m = CapitalAccountingMachine.replay(config, baseline), initial = m.snapshot();
const poolBefore = load("inbound-pool-before"), confirmed = load("inbound-pool-confirmed"), before = load("inbound-before"), accepted = load("inbound-accepted"), after = load("inbound-settled");
const peerAccepted = load("inbound-peer-accepted"), peerAfter = load("inbound-peer-settled"), pays = load("inbound-peer-sendpays"), held = load("inbound-hold-settled");
load("inbound-collection-gap");
let serial = 0;
function apply<K extends keyof Payloads>(type: K, data: Payloads[K], extra: Partial<Envelope> = {}) {
  const s = m.snapshot(), assets = new Set(Object.keys(s.A)), claims = new Set(Object.keys(s.K));
  function walk(v: any, key = "") {
    if (Array.isArray(v)) v.forEach(x => walk(x, key));
    else if (v && typeof v === "object") for (const [k, x] of Object.entries(v)) {
      if (k === "allocations") Object.keys(x as object).forEach(id => assets.add(id)); walk(x, k);
    } else if (typeof v === "string") {
      if (["asset_id", "output_id"].includes(key)) assets.add(v);
      if (["claim_id", "parent_claim_id"].includes(key)) claims.add(v);
    }
  }
  walk(data);
  const causes = [...new Set([...Object.values(s.A), ...Object.values(s.K), ...Object.values(s.H.channels), ...Object.values(s.H.operations), ...Object.values(s.sweeps)].map(x => x.last_event_id))];
  for (const offer of Object.values(s.J.offers)) if (!causes.includes(offer.event_id)) causes.push(offer.event_id);
  m.apply({ event_id: `inbound-${++serial}`, trace_id: "owned-regtest-inbound-8f5d", event_type: type, data, amount: 0, unit: "msat",
    asset_ids: [...assets], claim_ids: [...claims], causal_parent_ids: causes, block_height: s.J.height, block_hash: s.J.chain[s.J.height],
    monotonic_timestamp: null, txid: null, evidence_refs: Object.entries(hashes).map(([name, hash]) => `snapshot:${name}:sha256:${hash}`), ...extra } as CapitalEvent);
}
const active = (snap: any) => snap.bark_vtxos.filter((v: any) => v.state.type === "spendable");
for (const snap of [poolBefore, confirmed, before, accepted, after]) {
  assert.equal(snap.stable_chain_tip, true);
  assert.equal(snap.chain_before.bestblockhash, adapter.headers[snap.chain_after.blocks].hash);
}
assert.equal(poolBefore.chain_after.blocks, initial.J.height);
assert.deepEqual(active(poolBefore).map((v: any) => v.id).sort(), Object.values(initial.K).filter(c => c.state === "ACTIVE").map(c => c.claim_id).sort());
assert.deepEqual(active(before), active(poolBefore));
const height = after.chain_after.blocks;
apply("CHAIN", { blocks: pin.headers.map((h: any) => ({ height: h.height, hash: h.hash, parent_hash: h.previousblockhash })) }, { block_height: height, block_hash: adapter.headers[height].hash });
const newClaims = active(after).filter((v: any) => !active(before).some((p: any) => p.id === v.id));
assert.equal(newClaims.length, 1); const claim = newClaims[0], anchor = claim.chain_anchor, fundingTxid = anchor.split(":")[0];
const transaction = adapter.transaction(after.transactions[fundingTxid]);
assert.equal(transaction.input_ids.length, 1);
assert.equal(initial.A[transaction.input_ids[0]].amount, sats(56171));
assert.equal(transaction.fee, sats(617));
apply("ONCHAIN_TRANSACTION", { ...transaction, outputs: transaction.outputs.map(o => ({ ...o,
  ...(o.asset_id === anchor ? { release_height: claim.expiry_height } : {}) })) }, { txid: fundingTxid,
  evidence_refs: [`snapshot:inbound-settled:sha256:${hashes["inbound-settled"]}`, ...transaction.input_ids.map(id => `spends:${initial.A[id].backing_ref}`)] });
assert.equal(m.snapshot().A[anchor].amount, sats(20000));
const pay = pays.payments[0]; assert.equal(pays.payments.length, 1); assert.equal(pay.status, "complete");
assert.equal(pay.amount_msat, sats(2000)); assert.equal(pay.amount_sent_msat, pay.amount_msat);
assert.equal(pays.payment_preimage_sha256_verified, pay.payment_hash);
const subscription = after.database.subscriptions.find((x: any) => x.payment_hash === pay.payment_hash);
assert.equal(subscription.status, "settled"); assert.equal(subscription.final_amount_msat, pay.amount_msat);
assert.ok(after.database.settlements.some((x: any) => x.payment_hash === pay.payment_hash && x.preimage_sha256_verified === pay.payment_hash));
assert.equal(held.holdinvoices.length, 1); assert.equal(held.holdinvoices[0].state, "paid");
assert.equal(held.holdinvoices[0].payment_hash, pay.payment_hash);
const channel = before.channels.channels[0], channelAfter = after.channels.channels[0];
const pending = accepted.channels.channels[0].htlcs.filter((h: any) => h.payment_hash === pay.payment_hash);
assert.equal(pending.length, 1); assert.equal(pending[0].direction, "in"); assert.equal(pending[0].amount_msat, pay.amount_msat);
assert.ok(peerAccepted.channels[0].htlcs.some((h: any) => h.payment_hash === pay.payment_hash && h.direction === "out" && h.amount_msat === pay.amount_msat));
assert.equal(channelAfter.to_us_msat - channel.to_us_msat, pay.amount_msat);
assert.equal(peerAfter.channels[0].to_us_msat + channelAfter.to_us_msat, channelAfter.total_msat);
assert.equal(channelAfter.htlcs.length, 0); assert.equal(peerAfter.channels[0].htlcs.length, 0);
assert.equal(claim.amount_sat, 1896); assert.equal(after.bark_balance.spendable_sat - before.bark_balance.spendable_sat, 1896);
// Every output on the new claim path must trace through captured signed virtual
// transactions to the already confirmed pool root, never to the LN funding lot.
function ancestry(point: string, seen = new Set<string>()): void {
  if (point === anchor) return;
  assert.ok(!seen.has(point), "cyclic claim ancestry"); seen.add(point);
  const [id, index] = point.split(":"), tx = pin.transactions[id]?.transaction;
  assert.ok(tx && tx.vout[Number(index)], `missing signed ancestry: ${point}`);
  for (const vin of tx.vin) ancestry(`${vin.txid}:${vin.vout}`, new Set(seen));
}
ancestry(claim.id);
assert.equal(btcToMsat(pin.transactions[claim.id.split(":")[0]].transaction.vout[0].value), sats(claim.amount_sat));
const proof = `snapshot:inbound-peer-sendpays:sha256:${hashes["inbound-peer-sendpays"]}`;
apply("RECEIVE_LIGHTNING", { channel_id: channel.channel_id, asset_id: `receipt:${pay.payment_hash}`, fee: 0, service_fee: sats(104),
  backing_mode: "inventory", pool: true, settlement_evidence_ref: proof,
  claim: { claim_id: claim.id, claimant: "client", expiry_height: claim.expiry_height, allocations: { [anchor]: sats(claim.amount_sat) } } }, { amount: pay.amount_msat });
const state = m.snapshot();
assert.equal(sum(Object.values(state.A).map(a => a.amount)), sats(2028761));
for (const asset of Object.values(state.A).filter(a => a.location === "onchain" && a.amount > 0 && a.state !== "TRANSFERRED_OUT")) {
  const output = after.unspent_outputs[asset.backing_ref];
  assert.ok(output, `recorded economic asset is not unspent: ${asset.backing_ref}`);
  assert.equal(btcToMsat(output.value), asset.amount);
}
assert.equal(state.H.channels[channel.channel_id].spendable, channelAfter.spendable_msat);
assert.equal(state.H.channels[channel.channel_id].receivable, channelAfter.receivable_msat);
assert.equal(state.H.channels[channel.channel_id].remote, peerAfter.channels[0].to_us_msat);
assert.equal(sum(Object.values(state.A).map(a => a.amount)), sum(Object.values(initial.A).map(a => a.amount)) + sats(2000 - 617));
assert.equal(state.B.F - state.B.C, initial.B.F - initial.B.C);
assert.deepEqual(Object.values(state.K).filter(c => c.state === "ACTIVE").map(c => c.claim_id).sort(), active(after).map((v: any) => v.id).sort());
const rootLeaves = after.database.vtxos.filter((v: any) => v.anchor_point === anchor && ["pool", "spendable"].includes(v.spend_state));
assert.equal(sum(rootLeaves.map((v: any) => v.amount)), 20000);
const eligible = after.database.pool.filter((v: any) => v.expiry_height > height && v.spent_at === null);
assert.equal(sum(eligible.map((v: any) => v.amount)), 10000);
assert.ok(pin.pool_change_diagnostics.some((x: any) => x.message.includes('exit depth 4 exceeds the maximum of 3')));
assert.equal(m.stateHash(), CapitalAccountingMachine.replay(config, m.journal()).stateHash());
const report = { evidence_class: "observed_regtest_inbound_reconstruction", economic_reconciliation: true, replay_verified: true,
  baseline_events: baseline.length, added_events: serial, report: m.report(), source_sha256: hashes,
  receipt: { payment_hash: pay.payment_hash, gross_received_sat: 2000, routing_fee_sat: 0, holder_service_fee_sat: 104, holder_claim_sat: 1896,
    pool_funding_fee_sat: 617, pool_root_sat: 20000, pool_anchor: anchor, expiry_height: claim.expiry_height,
    pool_eligible_remaining_sat: 10000, pool_depth_excluded_change_sat: 8104, claim_id: claim.id },
  complete_fixture: { initial_sat: 2200000, operator_assets_sat: 2028761, client_onchain_sat: 99845, peer_channel_sat: 58000, miner_fees_sat: 13394 },
  limitations: ['One declared two-leaf inventory configuration; not an empirical batching distribution.',
    'Claim preparation and settlement occur within an unsampled interval. Receiver acceptance is observed; whole-journal seconds remain unknown.',
    'Pool change exists economically but its exit depth exceeds the configured selection cap; it is not immediately usable inventory.',
    'Receipt is additional incoming capital, never recovery of the earlier outstanding fronting.'] };
assert.equal(sum(Object.values(report.complete_fixture).slice(1)), report.complete_fixture.initial_sat);
writeFileSync(`${dir}inbound-lifecycle.jsonl`, m.journal().map(e => JSON.stringify(e)).join("\n") + "\n");
writeFileSync(`${dir}inbound-machine-reconciliation.json`, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify({ events: m.journal().length, state_hash: m.stateHash(), receipt: report.receipt }, null, 2));
