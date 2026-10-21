// Extend the immutable successful lifecycle with two observed failed attempts.
// Intermediate input claims remain an aggregate reservation until resolution;
// replacement identities and ancestry are reconciled at the terminal snapshot.
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
const config = load("normalized-config"), identity = load("runtime-identity"), source = load("runtime-source"), chain = load("canonical-chain");
new ObservedRegtestAdapter(identity, source, chain.headers);
const failureSource = load("failure-source"); assert.equal(failureSource.revision, source.revision);
const runtime = load("failure-runtime-verification");
assert.equal(runtime.lightningd_sha256, identity.executables.find((x: any) => x.binary === "lightningd").sha256);
assert.equal(runtime.fault_plugin_stopped, true);
const baseline = readFileSync(`${dir}lifecycle-observed.jsonl`, "utf8").trim().split(/\r?\n/).map(x => JSON.parse(x));
const m = CapitalAccountingMachine.replay(config, baseline);
const initial = m.snapshot(), decoded = load("failure-virtual-transactions").transactions;
let serial = 0;
const reports: unknown[] = [];
function apply<K extends keyof Payloads>(type: K, data: Payloads[K], evidence: string[], extra: Partial<Envelope> = {}) {
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
  m.apply({ event_id: `failure-${++serial}`, trace_id: "owned-regtest-failure-8f5d", event_type: type, data, amount: 0, unit: "msat",
    asset_ids: [...assets], claim_ids: [...claims], causal_parent_ids: causes, block_height: s.J.height, block_hash: s.J.chain[s.J.height],
    monotonic_timestamp: null, txid: null,
    evidence_refs: evidence.map(name => `snapshot:${name}:sha256:${hashes[name]}`), ...extra } as CapitalEvent);
}
function ancestors(point: string, targets: Set<string>, seen = new Set<string>()): string[] {
  if (targets.has(point)) return [point];
  assert.ok(!seen.has(point), "cyclic virtual ancestry"); seen.add(point);
  const txid = point.split(":")[0], tx = decoded[txid]?.transaction;
  assert.ok(tx, `missing decoded claim ancestor ${point}`);
  const found: string[] = tx.vin.flatMap((v: any) => ancestors(`${v.txid}:${v.vout}`, targets, new Set(seen)));
  return [...new Set(found)];
}
const active = (snapshot: any) => snapshot.bark_vtxos.filter((v: any) => v.state.type === "spendable");
for (const label of ["failure", "failure-captured"]) {
  const before = load(`${label}-before`), after = load(`${label}-resolved`), hooks = load(`${label}-hook-events`), pays = load(`${label}-sendpays`);
  const instrument = load(`${label}-instrument`);
  assert.equal(instrument.kernel_boot_id, runtime.kernel_boot_id);
  const evidence = [`${label}-before`, `${label}-resolved`, `${label}-hook-events`, `${label}-sendpays`, `${label}-instrument`, "failure-virtual-transactions", "failure-source", "failure-runtime-verification"];
  const operation = hooks.payment_hash, attempts = after.database.attempts.filter((a: any) => a.payment_hash === operation);
  assert.equal(attempts.length, 1); const attempt = attempts[0];
  assert.equal(attempt.status, "failed"); assert.equal(attempt.final_amount_msat, 0);
  assert.ok(!after.database.settlements.some((s: any) => s.payment_hash === operation), "failed payment has settlement proof");
  assert.equal(pays.payments.length, 1); assert.equal(pays.payments[0].status, "failed");
  assert.equal(pays.payments[0].amount_msat, attempt.amount_msat);
  const htlcs = after.database.htlc_vtxos.filter((v: any) => v.payment_hash === operation);
  assert.ok(htlcs.length && htlcs.every((v: any) => v.resolution === "revoked"), "revocation not evidenced for every HTLC");
  for (const snap of [before, after]) {
    assert.equal(snap.chain_before.bestblockhash, initial.J.chain[initial.J.height]); assert.equal(snap.stable_chain_tip, true);
    // Displayed receiving addresses can differ between snapshots. Compare
    // actual UTXO identities and balances, not address-display metadata.
    const { address: _a, ...wallet } = snap.server_wallet.rounds;
    const { address: _b, ...priorWallet } = before.server_wallet.rounds;
    assert.deepEqual(wallet, priorWallet); assert.deepEqual(snap.cln_funds, before.cln_funds);
    assert.deepEqual(snap.bark_utxos, before.bark_utxos);
  }
  assert.equal(after.bark_balance.spendable_sat, before.bark_balance.spendable_sat);
  const beforeActive = active(before), afterActive = active(after), afterIds = new Set(afterActive.map((v: any) => v.id));
  assert.deepEqual(Object.values(m.snapshot().K).filter(c => c.state === "ACTIVE").map(c => c.claim_id).sort(), beforeActive.map((v: any) => v.id).sort());
  const consumed = beforeActive.filter((v: any) => !afterIds.has(v.id)), inputIds: string[] = consumed.map((v: any) => v.id), targets = new Set(inputIds);
  assert.ok(inputIds.length);
  const priorIds = new Set(beforeActive.map((v: any) => v.id));
  const outputs = afterActive.filter((v: any) => !priorIds.has(v.id));
  const replacements = outputs.map((v: any) => {
    const parents = ancestors(v.id, targets); assert.equal(parents.length, 1, "ambiguous parent attribution");
    const parent = consumed.find((p: any) => p.id === parents[0]); assert.equal(v.chain_anchor, parent.chain_anchor);
    const [txid, index] = v.id.split(":"); assert.equal(btcToMsat(decoded[txid].transaction.vout[Number(index)].value), sats(v.amount_sat));
    return { claim_id: v.id, claimant: "client", allocations: { [v.chain_anchor]: sats(v.amount_sat) }, expiry_height: v.expiry_height, parent_claim_id: parents[0] };
  });
  const channelId = before.channels.channels[0].channel_id;
  const holderFee = sats(attempt.user_fee_sat), routing = sats(Math.floor(attempt.user_fee_sat * .9)), gross = attempt.amount_msat + routing;
  const free = Object.values(m.snapshot().A).find(a => a.pool && a.state === "FREE" && a.location === `ln:${channelId}` && a.amount > gross)!;
  assert.ok(free); const reserve = `failure:${operation}:reserve`;
  apply("SPLIT_MERGE", { input_ids: [free.asset_id], outputs: [{ asset_id: reserve, amount: gross }, { asset_id: `${reserve}:change`, amount: free.amount - gross }] }, evidence);
  apply("PAYMENT_OFFERED", { operation_id: operation, holder: "client" }, evidence, { amount: attempt.amount_msat });
  apply("REQUEST_OUTGOING", { operation_id: operation, holder: "client", input_claim_ids: inputIds, reserve_ids: [reserve], channel_id: channelId,
    delivered: attempt.amount_msat, max_fee: routing, max_holder_fee: holderFee, change_backing: "retained", timeout_height: htlcs[0].htlc_expiry }, evidence, { amount: attempt.amount_msat });
  const accepted = hooks.events.find((e: any) => e.event === "receiver_hook_accepted"), released = hooks.events.find((e: any) => e.event === "receiver_failure_response");
  assert.equal(accepted.htlc.amount_msat, attempt.amount_msat); assert.equal(released.trigger, "operator_release");
  assert.ok(Number.isSafeInteger(accepted.monotonic_ns) && Number.isSafeInteger(released.monotonic_ns));
  assert.ok(released.monotonic_ns > accepted.monotonic_ns);
  let spendable: number | undefined, inFlightSnapshot: any;
  if (label === "failure-captured") {
    inFlightSnapshot = load(`${label}-in-flight`); evidence.push(`${label}-in-flight`);
    assert.ok(accepted.monotonic_ns <= inFlightSnapshot.monotonic_start_ns && inFlightSnapshot.monotonic_end_ns <= released.monotonic_ns);
    const channel = inFlightSnapshot.channels.channels[0], held = channel.htlcs.filter((h: any) => h.payment_hash === operation);
    assert.equal(held.length, 1); assert.equal(held[0].amount_msat, attempt.amount_msat); assert.equal(held[0].direction, "out");
    assert.equal(channel.to_us_msat, before.channels.channels[0].to_us_msat);
    const peer = load(`${label}-peer-in-flight`).channels.channels[0]; evidence.push(`${label}-peer-in-flight`);
    const incoming = peer.htlcs.filter((h: any) => h.payment_hash === operation);
    assert.equal(incoming.length, 1); assert.equal(incoming[0].amount_msat, attempt.amount_msat); assert.equal(incoming[0].direction, "in");
    assert.equal(peer.funding_txid, channel.funding_txid); assert.equal(peer.to_us_msat + channel.to_us_msat, channel.total_msat);
    spendable = channel.spendable_msat;
  }
  apply("HTLC_ACCEPTED", { operation_id: operation, in_flight_amount: accepted.htlc.amount_msat,
    ...(spendable === undefined ? {} : { observed_spendable: spendable }) }, evidence);
  apply("HTLC_FAILED", { operation_id: operation }, evidence);
  apply("RESOLVE_FAILED", { operation_id: operation, path: "revocation", replacements }, evidence);
  const state = m.snapshot();
  assert.equal(state.H.channels[channelId].spendable, after.channels.channels[0].spendable_msat);
  assert.deepEqual(Object.values(state.K).filter(c => c.state === "ACTIVE").map(c => c.claim_id).sort(), afterActive.map((v: any) => v.id).sort());
  assert.equal(sum(Object.values(state.A).map(a => a.amount)), sum(Object.values(initial.A).map(a => a.amount)));
  assert.equal(state.B.F - state.B.C, initial.B.F - initial.B.C);
  const heldNs = BigInt(released.monotonic_ns) - BigInt(accepted.monotonic_ns);
  reports.push({ payment_hash: operation, amount_sat: attempt.amount_msat / 1000, fee_ceiling_sat: attempt.user_fee_sat,
    charged_fee_sat: 0, routing_limit_sat: routing / 1000, measured_in_flight_sat: accepted.htlc.amount_msat / 1000,
    measured_spendable_reduction_sat: spendable === undefined ? null : (before.channels.channels[0].spendable_msat - spendable) / 1000,
    receiver_held_nanoseconds: heldNs.toString(), receiver_held_sat_seconds_lower_bound: Number(heldNs) / 1e9 * attempt.amount_msat / 1000,
    clock_boot_id: instrument.kernel_boot_id, input_claim_ids: inputIds, replacements,
    note: "The deliberate receiver hold is a lower bound on HTLC exposure, not a natural latency sample; first attempt lacks the pending channel snapshot. Claim identities are reconciled at resolution, not asserted for unobserved client intermediate states." });
}
assert.equal(m.stateHash(), CapitalAccountingMachine.replay(config, m.journal()).stateHash());
const report = { evidence_class: "observed_regtest_failure_reconstruction", economic_reconciliation: true, replay_verified: true,
  baseline_events: baseline.length, added_events: serial, report: m.report(), attempts: reports, source_sha256: hashes,
  limitations: ["Deliberate fault injection; no production latency inference.", "Historical unknown timestamps keep whole-journal seconds null; instrumented held-window bounds are reported separately.",
    "Client input claims are aggregate reservations until terminal replacement reconciliation; intermediate client CLI reads were unavailable while send held the wallet."] };
writeFileSync(`${dir}failure-lifecycle.jsonl`, m.journal().map(e => JSON.stringify(e)).join("\n") + "\n");
writeFileSync(`${dir}failure-machine-reconciliation.json`, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify({ events: m.journal().length, state_hash: m.stateHash(), attempts: reports }, null, 2));
