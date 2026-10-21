// Reconstruct one confirmed cooperative exit without releasing old backing.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { CapitalAccountingMachine, sats, sum, type CapitalEvent, type Envelope, type Payloads } from "../../../model/capital.ts";
import { btcToMsat } from "../../../model/capital-adapter.ts";
import { ObservedRegtestAdapter } from "../../../model/capital-observed-adapter.ts";
const dir = "audit/peer_review/regtest/evidence/", hashes: Record<string, string> = {};
function load(name: string) {
  const bytes = readFileSync(`${dir}${name}.json`); hashes[name] = createHash("sha256").update(bytes).digest("hex"); return JSON.parse(bytes.toString());
}
const config = load("normalized-config"), identity = load("runtime-identity"), source = load("runtime-source"), oldChain = load("canonical-chain");
const inbound = load("inbound-source-and-chain"), pin = load("offboard-source-and-chain");
assert.equal(pin.source_revision, source.revision); assert.equal(pin.genesis, identity.genesis);
const adapter = new ObservedRegtestAdapter(identity, source, [...oldChain.headers, ...inbound.headers, ...pin.headers]);
const baseline = readFileSync(`${dir}inbound-lifecycle.jsonl`, "utf8").trim().split(/\r?\n/).map(x => JSON.parse(x));
const m = CapitalAccountingMachine.replay(config, baseline), initial = m.snapshot();
const before = load("offboard-before"), broadcast = load("offboard-broadcast"), confirmed = load("offboard-confirmed"), after = load("offboard-owned-output");
const intent = load("offboard-intent"), action = load("action-offboard-18632"), wallet = load("action-offboard-onchain-sync");
const claimId = intent.claim_id, txid = action.result.offboard_txid, payoutId = `${txid}:0`, connectorId = `${txid}:1`;
assert.equal(intent.external_funding_sat, 0); assert.equal(before.database.offboards.length, 0); assert.equal(after.database.offboards.length, 1);
assert.equal(initial.K[claimId].amount, sats(18632));
for (const snap of [before, broadcast, confirmed, after]) {
  assert.equal(snap.stable_chain_tip, true); assert.equal(snap.chain_after.bestblockhash, adapter.headers[snap.chain_after.blocks].hash);
  assert.equal(snap.channels.channels[0].to_us_msat, before.channels.channels[0].to_us_msat);
  assert.deepEqual(snap.database.settlements, before.database.settlements);
}
assert.ok(broadcast.mempool.includes(txid)); assert.equal(broadcast.transactions[txid].transaction.confirmations ?? 0, 0);
const offboard = after.database.offboards[0]; assert.equal(offboard.txid, txid); assert.equal(offboard.wallet_commit, true); assert.equal(offboard.user_fee_sat, 2900);
const original = after.database.vtxos.find((v: any) => v.vtxo_id === claimId);
assert.equal(original.offboarded_in, txid); assert.equal(original.spend_state, "spent");
const forfeit = after.database.vtxos.find((v: any) => v.spend_state === "offboard-forfeit" && v.anchor_point === original.anchor_point);
const connector = after.database.vtxos.find((v: any) => v.vtxo_id === connectorId);
assert.ok(forfeit); assert.equal(forfeit.amount, 18962); assert.equal(connector.amount, 330);
assert.equal(connector.spend_state, "offboard-connector"); assert.equal(connector.expiry, 8900);
const forfeitTx = pin.transactions[forfeit.vtxo_id.split(":")[0]].transaction;
assert.deepEqual(forfeitTx.vin.map((v: any) => `${v.txid}:${v.vout}`).sort(), [claimId, connectorId].sort());
assert.equal(btcToMsat(forfeitTx.vout[0].value), sats(18962));
const funding = adapter.transaction(after.transactions[txid]);
assert.deepEqual(funding.input_ids, ["1579dc43b9c47805b95472f9a4c2ec802e562c0bea654af71a1d08b4ee92c153:0"]);
assert.equal(funding.fee, sats(1973)); assert.equal(funding.outputs.find(o => o.asset_id === payoutId)!.amount, sats(15732));
assert.ok(after.bark_utxos.some((u: any) => u.outpoint === payoutId && u.amount_sat === 15732 && u.confirmation_height === funding.inclusion_height));
assert.equal(wallet.result.confirmed_sat, 115577); assert.equal(wallet.result.trusted_spendable_sat, 115577);
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
  m.apply({ event_id: `offboard-${++serial}`, trace_id: "owned-regtest-cooperative-exit-8f5d", event_type: type, data, amount: 0, unit: "msat",
    asset_ids: [...assets], claim_ids: [...claims], causal_parent_ids: causes, block_height: s.J.height, block_hash: s.J.chain[s.J.height],
    monotonic_timestamp: null, txid: null, evidence_refs: Object.entries(hashes).map(([name, hash]) => `snapshot:${name}:sha256:${hash}`), ...extra } as CapitalEvent);
}
apply("CHAIN", { blocks: pin.headers.map((h: any) => ({ height: h.height, hash: h.hash, parent_hash: h.previousblockhash })) },
  { block_height: after.chain_after.blocks, block_hash: after.chain_after.bestblockhash });
apply("EXIT", { claim_id: claimId, fee: sats(offboard.user_fee_sat), output_id: payoutId, destination: "client:onchain", mode: "cooperative",
  inclusion_height: funding.inclusion_height, inclusion_hash: funding.inclusion_hash,
  funding: { operation_id: `offboard:${txid}`, transaction: { ...funding, outputs: funding.outputs.map(o => ({ ...o,
    ...(o.asset_id === connectorId ? { release_height: connector.expiry } : {}) })) }, connector_ids: [connectorId],
    recovery_claim: { claim_id: forfeit.vtxo_id, claimant: "server", parent_claim_id: claimId, expiry_height: forfeit.expiry,
      allocations: { ...initial.K[claimId].allocations, [connectorId]: sats(connector.amount) } } } },
  { txid, amount: sats(18632), evidence_refs: [...Object.entries(hashes).map(([name, hash]) => `snapshot:${name}:sha256:${hash}`),
    ...funding.input_ids.map(id => `spends:${initial.A[id].backing_ref}`), `forfeit:${forfeit.vtxo_id}:sha256:${hashes["offboard-source-and-chain"]}`] });
const state = m.snapshot();
for (const asset of Object.values(state.A).filter(a => a.location === "onchain" && a.amount > 0)) {
  assert.ok(after.unspent_outputs[asset.backing_ref], `missing unspent economic asset ${asset.backing_ref}`);
  assert.equal(btcToMsat(after.unspent_outputs[asset.backing_ref].value), asset.amount);
}
assert.equal(sum(Object.values(state.A).map(a => a.amount)), sats(2011056));
assert.equal(state.B.F - initial.B.F, sats(18035)); assert.equal(state.B.C, initial.B.C);
assert.equal(state.A[original.anchor_point].amount, initial.A[original.anchor_point].amount);
assert.equal(state.A[original.anchor_point].state, "COMMITTED");
assert.equal(state.A[connectorId].state, "COMMITTED");
assert.deepEqual(Object.values(state.K).filter(c => c.state === "ACTIVE").map(c => c.claim_id).sort(),
  after.bark_vtxos.filter((v: any) => v.state.type === "spendable").map((v: any) => v.id).sort());
assert.equal(after.bark_balance.spendable_sat, 21611);
assert.equal(m.stateHash(), CapitalAccountingMachine.replay(config, m.journal()).stateHash());
const report = { evidence_class: "observed_regtest_cooperative_exit", economic_reconciliation: true, replay_verified: true,
  baseline_events: baseline.length, added_events: serial, report: m.report(), source_sha256: hashes,
  exit: { claim_id: claimId, gross_claim_sat: 18632, payout_sat: 15732, holder_fee_sat: 2900, miner_fee_sat: 1973, retained_fee_sat: 927,
    connector_sat: 330, new_fronting_sat: 18035, wallet_change_sat: 17519, connector_expiry: connector.expiry,
    original_claim_expiry: original.expiry, original_backing: original.anchor_point, txid, payout_outpoint: payoutId, forfeit_claim: forfeit.vtxo_id },
  complete_fixture: { initial_sat: 2200000, operator_assets_sat: 2011056, client_onchain_sat: 115577, peer_channel_sat: 58000, miner_fees_sat: 15367 },
  limits: ['The exit is reconstructed at confirmed observation height; preparation and mempool exposure are preserved as snapshots, not exact reducer clocks.',
    'The old root and connector remain locked. Their later recovery is censored; no recovery credit or independent reuse is inferred.',
    'The compound forfeit right spans original backing and a connector with different expiry. Separate partial recovery still requires observed evidence.',
    'No unilateral exit, live reorg or testnet4 timing inference follows from this cooperative exit.'] };
assert.equal(sum(Object.values(report.complete_fixture).slice(1)), report.complete_fixture.initial_sat);
writeFileSync(`${dir}offboard-lifecycle.jsonl`, m.journal().map(e => JSON.stringify(e)).join("\n") + "\n");
writeFileSync(`${dir}offboard-machine-reconciliation.json`, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify({ events: m.journal().length, state_hash: m.stateHash(), exit: report.exit }, null, 2));
