import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { CapitalAccountingMachine, sats, sum, type CapitalEvent, type Envelope, type Payloads, type ClaimSpec, type OnchainTransaction } from "../../../model/capital.ts";
import { ObservedRegtestAdapter, EXECUTED_GENESIS, type ObservedTransactionRecord } from "../../../model/capital-observed-adapter.ts";

// This finite, explicitly scoped normalization is deliberately fail-closed.
// Snapshot milestones supply detection heights, not invented HTLC timestamps.
const dir = "audit/peer_review/regtest/evidence/", hashes: Record<string, string> = {};
function load(name: string) {
  const bytes = readFileSync(`${dir}${name}.json`); hashes[name] = createHash("sha256").update(bytes).digest("hex"); return JSON.parse(bytes.toString());
}
const final = load("recovered-output-reused"), before = load("before-board"), paid = load("payment-result-reconciliation"), board = load("board-confirmed");
const refreshed = load("change-refreshed"), poolConfirmed = load("pool-sweep-confirmed"), quarantine = load("free-reserve-quarantined");
const originalExpiry = load("original-expiry-reached"), originalConfirmed = load("original-sweep-confirmed");
const identity = load("runtime-identity"), source = load("runtime-source"), chain = load("canonical-chain"), reuseProof = load("reuse-proof"), economic = load("economic-reconciliation");
const adapter = new ObservedRegtestAdapter(identity, source, chain.headers);
const config = { operator: "server", genesis_hash: EXECUTED_GENESIS, confirmations: 2, evidence_class: "regtest" as const };
const m = new CapitalAccountingMachine(config), trace: { event_id: string; event_type: string; height: number; state_hash: string; report: ReturnType<CapitalAccountingMachine["report"]> }[] = [];
let serial = 0;
function apply<K extends keyof Payloads>(type: K, data: Payloads[K], evidence: string, extra: Partial<Envelope> = {}) {
  const s = m.snapshot(), assets = new Set(Object.keys(s.A)), claims = new Set(Object.keys(s.K));
  for (const sw of Object.values(s.sweeps)) assets.add(sw.output_id);
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
  // Read sets are deliberately conservative for this one connected lifecycle.
  // Reorgs therefore invalidate dependent snapshots rather than reuse stale data.
  const causes = [...new Set([...Object.values(s.A), ...Object.values(s.K), ...Object.values(s.H.channels), ...Object.values(s.H.operations), ...Object.values(s.sweeps)].map(x => x.last_event_id))];
  for (const offer of Object.values(s.J.offers)) if (!causes.includes(offer.event_id)) causes.push(offer.event_id);
  const event = { event_id: `observed-${++serial}`, trace_id: "owned-regtest-8f5d-reconstructed", event_type: type, data,
    amount: 0, unit: "msat", asset_ids: [...assets], claim_ids: [...claims], causal_parent_ids: causes,
    block_height: s.J.height, block_hash: s.J.chain[s.J.height], monotonic_timestamp: null, txid: null,
    evidence_refs: [`snapshot:${evidence}:sha256:${hashes[evidence]}`, `source:${source.revision}`], ...extra } as CapitalEvent;
  event.evidence_refs = [...new Set(event.evidence_refs)];
  const state_hash = m.apply(event); trace.push({ event_id: event.event_id, event_type: type, height: event.block_height, state_hash, report: m.report() });
}
function advance(height: number, evidence: string) {
  const s = m.snapshot(); assert.ok(height >= s.J.height, "observation order reversed");
  if (height === s.J.height) return;
  const blocks = adapter.headers.slice(s.J.height + 1, height + 1).map(h => ({ height: h.height, hash: h.hash, parent_hash: h.previousblockhash! }));
  apply("CHAIN", { blocks }, evidence, { block_height: height, block_hash: adapter.headers[height].hash });
}
function at(snapshot: any) {
  assert.equal(snapshot.stable_chain_tip, true, "unstable snapshot");
  assert.equal(snapshot.chain_before.bestblockhash, snapshot.chain_after.bestblockhash);
  assert.equal(adapter.headers[snapshot.chain_after.blocks].hash, snapshot.chain_after.bestblockhash);
  advance(snapshot.chain_after.blocks, snapshot.label);
}
const txs: Record<string, ObservedTransactionRecord> = final.transactions;
function transaction(txid: string, evidence: string, additions: Partial<OnchainTransaction> = {}) {
  const data = { ...adapter.transaction(txs[txid]), ...additions };
  assert.ok(data.inclusion_height + config.confirmations - 1 <= m.snapshot().J.height, "transaction not final at observation");
  apply("ONCHAIN_TRANSACTION", data, evidence, { txid, evidence_refs: [`snapshot:${evidence}:sha256:${hashes[evidence]}`,
    `snapshot:recovered-output-reused:sha256:${hashes["recovered-output-reused"]}`, ...data.input_ids.map(id => `spends:${m.snapshot().A[id].backing_ref}`)] });
}
function fund(outpoint: string, pool: boolean, evidence: string) {
  const [txid, index] = outpoint.split(":"), output = txs[txid].transaction.vout.find(o => o.n === Number(index))!;
  const amount = adapter.transaction(txs[txid]).outputs.find(o => o.asset_id === outpoint)!.amount;
  assert.ok(output); apply("FUND", { asset_id: outpoint, owner: "server", location: "onchain", backing_ref: outpoint,
    maturity_height: adapter.transaction(txs[txid]).inclusion_height, pool }, evidence, { amount, txid });
}
function claim(vtxo: any, parent?: string): ClaimSpec {
  return { claim_id: vtxo.id, claimant: "client", allocations: { [vtxo.chain_anchor]: sats(vtxo.amount_sat) }, expiry_height: vtxo.expiry_height,
    ...(parent ? { parent_claim_id: parent } : {}) };
}
const initial = load("initial-funding"), fundingTx = initial.txid;
at(before); fund(`${fundingTx}:0`, true, "before-board"); fund(`${fundingTx}:1`, true, "before-board");
const channel = before.channels.channels[0], channelRef = `${channel.funding_txid}:${channel.funding_outnum}`;
transaction(channel.funding_txid, "before-board");
apply("OPEN_CHANNEL", { channel_id: channel.channel_id, asset_id: channelRef, funding_ref: channelRef, remote: channel.total_msat - channel.to_us_msat,
  spendable: channel.spendable_msat, receivable: channel.receivable_msat }, "before-board", { txid: channel.funding_txid });
const poolRows = final.database.pool, dbVtxos = final.database.vtxos;
const poolAnchors = new Map<string, number>();
for (const row of poolRows) {
  const v = dbVtxos.find((v: any) => v.vtxo_id === row.vtxo_id); assert.ok(v && row.spent_at === null, "fixture has spent pool VTXO");
  poolAnchors.set(v.anchor_point, Math.max(poolAnchors.get(v.anchor_point) ?? 0, row.expiry_height));
}
assert.equal(poolAnchors.size, 2, "unexpected fixture pool ancestry");
const poolTransactions = [...new Set([...poolAnchors.keys()].map(id => id.split(":")[0]))].sort((a, b) => adapter.transaction(txs[a]).inclusion_height - adapter.transaction(txs[b]).inclusion_height);
function poolTransaction(txid: string, evidence: string) {
  const data = adapter.transaction(txs[txid]); transaction(txid, evidence, { outputs: data.outputs.map(o => ({ ...o,
    ...(poolAnchors.has(o.asset_id) ? { release_height: poolAnchors.get(o.asset_id)! } : {}) })) });
}
poolTransaction(poolTransactions[0], "before-board");
at(board); poolTransaction(poolTransactions[1], "board-confirmed");
const original = board.bark_vtxos.find((v: any) => v.policy_type === "pubkey"); assert.ok(original);
fund(original.chain_anchor, false, "board-confirmed");
const boardValue = m.snapshot().A[original.chain_anchor].amount;
apply("ISSUE_VTXO", { claim: claim(original), service_fee: boardValue - sats(original.amount_sat) }, "board-confirmed", { amount: boardValue });
at(paid);
assert.equal(paid.database.attempts.length, 1); assert.equal(paid.database.settlements.length, 1);
const attempt = paid.database.attempts[0], outcome = adapter.settlement(attempt, paid.database.settlements[0], paid.pays);
assert.equal(attempt.block_height, paid.chain_after.blocks);
const change = paid.bark_vtxos.find((v: any) => v.policy_type === "pubkey" && v.state.type === "spendable"); assert.ok(change, "missing retained change");
assert.equal(change.chain_anchor, original.chain_anchor);
// Source-pinned ln/mod.rs applies the configured ppm to holder fee, floored in sats.
const feeSetting = identity.configurations["captaind.toml"].redacted_text.match(/^ln_max_fee_ppm\s*=\s*(\d+)\s*$/m);
assert.ok(feeSetting, "effective routing fee limit missing");
const routingPpm = Number(feeSetting[1]); assert.equal(routingPpm, 900000, "unreviewed routing fee setting");
const feeLimit = sats(Math.floor(attempt.user_fee_sat * routingPpm / 1000000));
const reserve = outcome.delivered + feeLimit;
const routingId = `${channelRef}:routing`, idleId = `${channelRef}:unreserved`;
apply("SPLIT_MERGE", { input_ids: [channelRef], outputs: [{ asset_id: routingId, amount: reserve }, { asset_id: idleId, amount: channel.to_us_msat - reserve }] }, "payment-result-reconciliation");
apply("PAYMENT_OFFERED", { operation_id: attempt.payment_hash, holder: "client" }, "payment-result-reconciliation", { amount: outcome.delivered });
apply("REQUEST_OUTGOING", { operation_id: attempt.payment_hash, holder: "client", input_claim_ids: [original.id], reserve_ids: [routingId], channel_id: channel.channel_id,
  delivered: outcome.delivered, max_fee: feeLimit, max_holder_fee: outcome.holder_fee, timeout_height: paid.database.htlc_vtxos[0].htlc_expiry,
  change_backing: "retained" }, "payment-result-reconciliation", { amount: outcome.delivered });
apply("HTLC_ACCEPTED", { operation_id: attempt.payment_hash }, "payment-result-reconciliation", { evidence_refs: [
  `snapshot:payment-result-reconciliation:sha256:${hashes["payment-result-reconciliation"]}`, "reconstruction:accepted-before-proven-settlement;acceptance-time-not-observed"] });
const proof = `collector-preimage-sha256:${attempt.payment_hash}`;
apply("HTLC_SETTLED", { operation_id: attempt.payment_hash, fee: outcome.fee, service_fee: outcome.service_fee, preimage_evidence_ref: proof, change: claim(change, original.id) },
  "payment-result-reconciliation", { amount: outcome.delivered, evidence_refs: [proof, `snapshot:payment-result-reconciliation:sha256:${hashes["payment-result-reconciliation"]}`] });
const settledChannel = paid.channels.channels[0];
apply("CHANNEL_CAPACITY", { channel_id: channel.channel_id, local: settledChannel.to_us_msat, remote: settledChannel.total_msat - settledChannel.to_us_msat,
  spendable: settledChannel.spendable_msat, receivable: settledChannel.receivable_msat }, "payment-result-reconciliation");
for (const [id, expiry] of [...poolAnchors.entries()].sort((a, b) => a[1] - b[1])) {
  advance(expiry, "recovered-output-reused"); apply("BACKING_EXPIRED", { input_ids: [id] }, "recovered-output-reused");
}
const rounds = final.database.rounds; assert.equal(rounds.length, 2);
function round(snapshot: any, index: number, input: any, reuse?: OnchainTransaction["reuse"]) {
  at(snapshot); const txid = rounds[index].funding_txid;
  const replacement = snapshot.bark_vtxos.find((v: any) => v.chain_anchor.startsWith(`${txid}:`) && v.policy_type === "pubkey"); assert.ok(replacement);
  const root = adapter.transaction(txs[txid]).outputs.find(o => o.asset_id === replacement.chain_anchor); assert.ok(root);
  transaction(txid, snapshot.label, { refresh: { operation_id: `round:${txid}`, input_claim_ids: [input.id], backing_ids: [root.asset_id],
    service_fee: sats(input.amount_sat - replacement.amount_sat), replacement: claim(replacement, input.id) }, ...(reuse ? { reuse } : {}) });
  return replacement;
}
const replacement = round(refreshed, 0, change);
function broadcast(snapshot: any, txid: string, operations: string[]) {
  at(snapshot); const data = adapter.transaction(txs[txid]); assert.equal(data.outputs.length, 1); assert.equal(data.outputs[0].output_index, 0);
  const log = final.watchman_claims.find((l: any) => l.slog_id === "ClaimBroadcast" && l.slog_data.txid === txid); assert.ok(log, "watchman broadcast proof missing");
  assert.equal(sats(log.slog_data.fee), data.fee); assert.equal(sats(log.slog_data.total_output_value), data.outputs[0].amount);
  assert.deepEqual([...log.slog_data.vtxo_ids].sort(), [...data.input_ids].sort());
  apply("RECOVERY_SWEEP", { sweep_id: txid, operation_ids: operations, input_ids: data.input_ids, output_id: data.outputs[0].asset_id, destination: "server-wallet",
    fee: data.fee, input_outpoints: data.input_ids }, snapshot.label, { txid, evidence_refs: [
      `snapshot:${snapshot.label}:sha256:${hashes[snapshot.label]}`, `snapshot:recovered-output-reused:sha256:${hashes["recovered-output-reused"]}`] });
}
function confirm(snapshot: any, txid: string) {
  at(snapshot); const data = adapter.transaction(txs[txid]);
  apply("SWEEP_CONFIRMED", { sweep_id: txid, inclusion_height: data.inclusion_height, inclusion_hash: data.inclusion_hash }, snapshot.label, { txid, amount: data.outputs[0].amount });
}
const poolBroadcast = load("expired-pool-sweep-broadcast");
const poolSweep = final.watchman_claims.find((l: any) => l.slog_id === "ClaimBroadcast").slog_data.txid;
broadcast(poolBroadcast, poolSweep, []); confirm(poolConfirmed, poolSweep);
at(quarantine); const quarantineTx = load("action-quarantine-free-reserve").result.txid;
transaction(quarantineTx, quarantine.label, { reuse: { sweep_id: poolSweep, recovery_allocations: {} } });
at(originalExpiry); apply("BACKING_EXPIRED", { input_ids: [original.chain_anchor] }, originalExpiry.label);
const originalBroadcast = load("original-sweep-broadcast");
broadcast(originalBroadcast, reuseProof.sweep_txid, [attempt.payment_hash, `round:${rounds[0].funding_txid}`]);
confirm(originalConfirmed, reuseProof.sweep_txid);
const recovered = m.snapshot().A[reuseProof.recovered_outpoint].amount;
const finalClaim = round(final, 1, replacement, { sweep_id: reuseProof.sweep_txid,
  recovery_allocations: { [attempt.payment_hash]: outcome.delivered + outcome.fee, [`round:${rounds[0].funding_txid}`]: recovered - outcome.delivered - outcome.fee } });
assert.deepEqual(adapter.transaction(txs[reuseProof.reuse_round_txid]).input_ids, [reuseProof.recovered_outpoint]);
const s = m.snapshot();
assert.equal(s.totals.inflows, sats(economic.initial_operator_funding_and_board_sat));
assert.equal(sum(Object.values(s.A).map(a => a.amount)), sats(economic.operator_remaining_economic_sat));
assert.equal(s.totals.fees, sats(economic.operator_miner_fees_sat)); assert.equal(s.totals.delivered, economic.delivered_msat);
assert.equal(s.K[finalClaim.id].amount, sats(economic.active_client_claims_sat));
for (const a of Object.values(s.A).filter(a => a.amount && a.location === "onchain")) {
  assert.ok(final.unspent_outputs[a.backing_ref]?.confirmations >= config.confirmations, "final asset not independently unspent/final");
}
const replay = CapitalAccountingMachine.replay(config, m.journal()); assert.equal(replay.stateHash(), m.stateHash());
const report = { evidence_class: "observed-regtest-reconstruction", economic_reconciliation: true, replay_verified: true,
  timing_status: "snapshot-detection-height accounting; exact transition times interval-censored; seconds unavailable",
  caveats: ["HTLC acceptance inferred from proven completion; acceptance timestamp and actual in-flight peak not sampled.",
    "Routing reservation is the source-derived admissibility limit, not a sampled CLN in-flight amount.",
    "Transactions enter this journal at confirmed snapshot heights; earlier broadcast/commit intervals need additional instrumentation.",
    "Recovery attribution pays the earlier Lightning commitment first; fungible shared-root attribution is a declared policy.",
    "Unrecovered fronting after exhausted backing is retained in F-C and reported separately; miner fees are not double-counted as economic losses."],
  config, report: m.report(), accounting_state: s, source_sha256: hashes };
writeFileSync(`${dir}normalized-config.json`, JSON.stringify(config, null, 2) + "\n");
writeFileSync(`${dir}lifecycle-observed.jsonl`, m.journal().map(e => JSON.stringify(e)).join("\n") + "\n");
writeFileSync(`${dir}machine-reconciliation.json`, JSON.stringify(report, null, 2) + "\n");
writeFileSync(`${dir}machine-trace.json`, JSON.stringify(trace, null, 2) + "\n");
console.log(JSON.stringify({ events: serial, state_hash: m.stateHash(), operator_assets_sat: sum(Object.values(s.A).map(a => a.amount)) / 1000,
  operator_fees_sat: s.totals.fees / 1000, delivered_sat: s.totals.delivered / 1000, active_claim_sat: s.K[finalClaim.id].amount / 1000,
  F_sat: s.B.F / 1000, C_sat: s.B.C / 1000, W_sat: (s.B.F - s.B.C) / 1000 }, null, 2));
