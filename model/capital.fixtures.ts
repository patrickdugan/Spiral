import { CapitalAccountingMachine, sats, type CapitalEvent, type Payloads, type Envelope, type MachineConfig, type Request } from "./capital.ts";

export const fixtureConfig: MachineConfig = { operator: "server", genesis_hash: "model-genesis", confirmations: 2, evidence_class: "reference-model" };

/** Synthetic, explicitly labeled observations. Never use these as implementation evidence. */
export class TraceBuilder {
  m = new CapitalAccountingMachine(fixtureConfig);
  serial = 0;
  event<K extends keyof Payloads>(type: K, data: Payloads[K], overrides: Partial<Envelope> = {}): CapitalEvent {
    const s = this.m.snapshot(), id = `e${++this.serial}`;
    const ids = new Set(Object.keys(s.A)), claims = new Set(Object.keys(s.K));
    for (const sw of Object.values(s.sweeps)) ids.add(sw.output_id);
    const walk = (v: unknown, key = "") => {
      if (Array.isArray(v)) { for (const x of v) walk(x, key); }
      else if (v && typeof v === "object") { for (const [k, x] of Object.entries(v)) { if (k === "allocations") for (const a of Object.keys(x as object)) ids.add(a); walk(x, k); } }
      else if (typeof v === "string") {
        if (["asset_id", "output_id"].includes(key)) ids.add(v);
        if (["claim_id", "parent_claim_id"].includes(key)) claims.add(v);
      }
    };
    walk(data);
    // Fixtures deliberately overdeclare dependencies. Production adapters must use
    // the actual read set so unrelated observations survive a branch replacement.
    const causes = [...new Set([...Object.values(s.A), ...Object.values(s.K), ...Object.values(s.H.channels), ...Object.values(s.H.operations), ...Object.values(s.sweeps)].map(x => x.last_event_id))];
    for (const offer of Object.values(s.J.offers)) if (!causes.includes(offer.event_id)) causes.push(offer.event_id);
    return { event_id: id, trace_id: "synthetic-capital-lifecycle", event_type: type, data,
      amount: 0, unit: "msat", asset_ids: [...ids], claim_ids: [...claims], causal_parent_ids: causes,
      block_height: s.J.height, block_hash: null, monotonic_timestamp: s.J.timestamp,
      txid: null, evidence_refs: [`fixture:${id}`], ...overrides } as CapitalEvent;
  }
  add<K extends keyof Payloads>(type: K, data: Payloads[K], overrides: Partial<Envelope> = {}) {
    const e = this.event(type, data, overrides); this.m.apply(e); return e;
  }
  chain(height: number) {
    const s = this.m.snapshot(), blocks = [];
    for (let h = Object.keys(s.J.chain).length; h <= height; h++) blocks.push({ height: h, hash: `block-${h}`, parent_hash: h === 1 ? fixtureConfig.genesis_hash : `block-${h - 1}` });
    this.add("CHAIN", { blocks }, { block_height: height, block_hash: height ? `block-${height}` : fixtureConfig.genesis_hash, monotonic_timestamp: height * 600 });
  }
  fund(id: string, amount: number, pool = false) {
    const s = this.m.snapshot(); this.add("FUND", { asset_id: id, owner: "server", location: "onchain", backing_ref: `fund-${id}:0`, maturity_height: s.J.height, pool },
      { amount, txid: `fund-${id}`, block_hash: s.J.chain[s.J.height] });
  }
  issue(id: string, backing: string, amount: number, expiry = 10, holder = "alice") {
    this.add("ISSUE_VTXO", { claim: { claim_id: id, claimant: holder, allocations: { [backing]: amount }, expiry_height: expiry } }, { amount });
  }
  channel(asset = "reserve", id = "cln", remote = 0) {
    const s = this.m.snapshot(); this.add("OPEN_CHANNEL", { channel_id: id, asset_id: asset, funding_ref: `channel-${id}:0`, remote, spendable: s.A[asset].amount, receivable: remote },
      { txid: `channel-${id}`, block_hash: s.J.chain[s.J.height] });
  }
  request(operation_id = "pay-1", claim = "vtxo", reserve = "reserve", channel = "cln", delivered = sats(600), max_fee = 0): Request {
    const r: Request = { operation_id, holder: "alice", input_claim_ids: [claim], reserve_ids: [reserve], channel_id: channel, delivered, max_fee, timeout_height: this.m.snapshot().J.height + 4 };
    this.add("PAYMENT_OFFERED", { operation_id, holder: "alice" }, { amount: delivered });
    this.add("REQUEST_OUTGOING", r, { amount: delivered }); return r;
  }
  settle(operation_id = "pay-1", fee = 0, change_id = "change") {
    const op = this.m.snapshot().H.operations[operation_id], amount = op.gross - op.delivered - fee;
    this.add("HTLC_ACCEPTED", { operation_id });
    this.add("HTLC_SETTLED", { operation_id, fee, preimage_evidence_ref: "fixture:preimage-verified",
      ...(amount ? { change: { claim_id: change_id, claimant: op.holder, allocations: { [op.reserve_ids[0]]: amount }, expiry_height: 30, parent_claim_id: op.input_claim_ids[0] } } : {}) },
      { amount: op.delivered, evidence_refs: ["fixture:preimage-verified"] });
  }
  sweep(operation_id = "pay-1", fee = 0) {
    this.chain(10); this.add("EXPIRY_REACHED", { operation_id });
    const op = this.m.snapshot().H.operations[operation_id];
    this.add("SWEEP_BROADCAST", { sweep_id: "sweep-1", operation_id, output_id: "recovered", destination: "server-wallet", fee,
      input_outpoints: op.recovery_ids.map(id => this.m.snapshot().A[id].backing_ref) }, { txid: "sweep-tx" });
    this.chain(11);
    this.add("SWEEP_CONFIRMED", { sweep_id: "sweep-1", inclusion_height: 11, inclusion_hash: "block-11" }, { txid: "sweep-tx", block_hash: "block-11", amount: op.gross - fee });
  }
  replayCheck() { return CapitalAccountingMachine.replay(fixtureConfig, this.m.journal()).stateHash() === this.m.stateHash(); }
}
export function funded(delivered = sats(600), fee = 0) {
  const t = new TraceBuilder(); t.fund("backing", sats(1000)); t.fund("reserve", sats(1000), true); t.channel(); t.issue("vtxo", "backing", sats(1000));
  t.request("pay-1", "vtxo", "reserve", "cln", delivered, fee); return t;
}
export function completeLifecycle() {
  const t = funded(); t.settle();
  // A separate client liability exists before the recovery. Its backing is never
  // counted as free reserve. No new funds arrive between recovery and reuse.
  t.fund("backing-2", sats(1000)); t.issue("vtxo-2", "backing-2", sats(1000), 40);
  t.sweep(); t.chain(13);
  t.add("PAYMENT_OFFERED", { operation_id: "pay-2", holder: "alice" }, { amount: sats(1000) });
  t.add("CAPITAL_REUSABLE", { sweep_id: "sweep-1", channel_funding_ref: "recycled-channel:0", funding_height: 12, funding_hash: "block-12", spendable: sats(1000),
    reuse: { operation_id: "pay-2", holder: "alice", input_claim_ids: ["vtxo-2"], reserve_ids: ["recovered"], channel_id: "recycled", delivered: sats(1000), max_fee: 0, timeout_height: 20 } },
    { txid: "recycled-channel", block_hash: "block-13", evidence_refs: ["fixture:independent-reuse", "spends:sweep-tx:0"] });
  t.settle("pay-2"); t.chain(15); return t;
}
