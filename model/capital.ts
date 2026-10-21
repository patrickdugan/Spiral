// Deterministic reference accounting. Evidence is supplied by a trusted observer;
// this reducer is not a Bitcoin, script, database, or Lightning verifier.
import { createHash } from "node:crypto";
import type { SettlementLedger } from "./ledger.ts";
import { validateEventShape } from "./capital-schema.ts";

export type CapitalState = "FREE" | "RESERVED" | "COMMITTED" | "RECOVERY_DUE" |
  "RECOVERING" | "CONFIRMING" | "FREE_AGAIN" | "TRANSFERRED_OUT";
export interface AssetLot {
  asset_id: string; amount: number; owner: string; location: string; backing_ref: string;
  state: CapitalState; created_at: string; last_event_id: string;
  parent_ids: string[]; original_amount: number; maturity_height: number; pool: boolean;
  release_height?: number;
}
export interface Claim {
  claim_id: string; amount: number; claimant: string; backing_ids: string[];
  allocations: Record<string, number>; expiry_height: number;
  state: "ACTIVE" | "RESERVED" | "FORFEITED" | "RECOVERED" | "EXITED";
  parent_claim_id: string | null; last_event_id: string;
}
export interface ClaimSpec {
  claim_id: string; claimant: string; allocations: Record<string, number>;
  expiry_height: number; parent_claim_id?: string;
}
export interface Channel {
  channel_id: string; funding_ref: string; capacity: number; remote: number;
  spendable: number; receivable: number;
  last_event_id: string;
}
export interface Request {
  operation_id: string; holder: string; input_claim_ids: string[]; reserve_ids: string[];
  channel_id: string; delivered: number; max_fee: number; timeout_height: number;
  change_backing?: "retained"; max_holder_fee?: number;
}
export interface Operation extends Request {
  gross: number; state: "RESERVED" | "ACCEPTED" | "FAILED" | "SETTLED" | "RESOLVED";
  recovered: number; fee: number; recovery_ids: string[]; last_event_id: string;
  committed_at: number | null; recovered_at: number | null;
  kind: "payment" | "refresh"; resolution?: "revocation" | "timeout";
  recovery_complete?: boolean;
  in_flight_amount?: number;
  capacity_reserved?: number;
}
export interface Block { height: number; hash: string; parent_hash: string }
export interface Sweep {
  sweep_id: string; operation_id: string; input_ids: string[]; output_id: string;
  destination: string; fee: number; txid: string; state: "BROADCAST" | "CONFIRMED" | "REUSED";
  inclusion_height: number | null; inclusion_hash: string | null; last_event_id: string;
  operation_ids?: string[];
}
export interface RoundRefresh {
  operation_id: string; input_claim_ids: string[]; backing_ids: string[];
  service_fee: number; replacement: ClaimSpec;
}
export interface OnchainTransaction {
  input_ids: string[];
  outputs: { asset_id: string; amount: number; output_index: number; release_height?: number }[];
  fee: number; inclusion_height: number; inclusion_hash: string;
  refresh?: RoundRefresh;
  reuse?: { sweep_id: string; recovery_allocations: Record<string, number> };
}
export interface Payloads {
  FUND: { asset_id: string; owner: string; location: string; backing_ref: string; maturity_height: number; pool: boolean };
  OPEN_CHANNEL: { channel_id: string; asset_id: string; funding_ref: string; remote: number; spendable: number; receivable: number };
  CHANNEL_CAPACITY: { channel_id: string; local: number; remote: number; spendable: number; receivable: number };
  ISSUE_VTXO: { claim: ClaimSpec; service_fee?: number };
  RECEIVE_LIGHTNING: { channel_id: string; asset_id: string; fee: number; claim: ClaimSpec };
  PAYMENT_OFFERED: { operation_id: string; holder: string };
  REQUEST_OUTGOING: Request;
  CANCEL_REQUEST: { operation_id: string };
  HTLC_ACCEPTED: { operation_id: string; in_flight_amount?: number; observed_spendable?: number };
  HTLC_SETTLED: { operation_id: string; fee: number; service_fee?: number; preimage_evidence_ref: string; change?: ClaimSpec };
  HTLC_FAILED: { operation_id: string };
  RESOLVE_FAILED: { operation_id: string; path: "revocation" | "timeout"; resolution_height?: number; resolution_hash?: string; replacements?: ClaimSpec[] };
  REFRESH: { operation_id: string; input_claim_ids: string[]; reserve_ids: string[]; fee: number; replacement: ClaimSpec };
  EXPIRY_REACHED: { operation_id: string };
  SWEEP_BROADCAST: { sweep_id: string; operation_id: string; output_id: string; destination: string; fee: number; input_outpoints: string[] };
  SWEEP_CONFIRMED: { sweep_id: string; inclusion_height: number; inclusion_hash: string };
  CAPITAL_REUSABLE: { sweep_id: string; reuse: Request; channel_funding_ref: string; funding_height: number; funding_hash: string; spendable: number };
  MOVE_TO_CHANNEL: { asset_id: string; channel_id: string; funding_ref: string; remote: number; spendable: number; receivable: number };
  SPLIT_MERGE: { input_ids: string[]; outputs: { asset_id: string; amount: number }[] };
  ONCHAIN_TRANSACTION: OnchainTransaction;
  BACKING_EXPIRED: { input_ids: string[] };
  RECOVERY_SWEEP: { sweep_id: string; operation_ids: string[]; input_ids: string[]; output_id: string; destination: string; fee: number; input_outpoints: string[] };
  EXIT: { claim_id: string; fee: number; output_id: string; destination: string; mode: "cooperative" | "unilateral"; inclusion_height: number; inclusion_hash: string };
  CHAIN: { blocks: Block[] };
  TICK: Record<string, never>;
  REORG: { blocks: Block[] };
}
export interface Envelope {
  event_id: string; trace_id: string; amount: number; unit: "msat";
  asset_ids: string[]; claim_ids: string[]; causal_parent_ids: string[];
  block_height: number; block_hash: string | null; monotonic_timestamp: number | null;
  txid: string | null; evidence_refs: string[];
}
export type CapitalEvent = { [K in keyof Payloads]: Envelope & { event_type: K; data: Payloads[K] } }[keyof Payloads];
export interface Integral { msat_blocks: string; msat_seconds: string | null }
export const categories = ["fronting", "unique_committed", "htlc", "inbound", "outbound", "idle"] as const;
export type Category = typeof categories[number];
export interface AccountingState {
  A: Record<string, AssetLot>; K: Record<string, Claim>;
  H: { channels: Record<string, Channel>; operations: Record<string, Operation> };
  B: { budget: number; F: number; C: number; reserved: number; pool: { funded: number; transfers_in: number; outflows: number; fees: number } };
  J: { chain: Record<string, string>; funding_refs: string[]; offers: Record<string, { amount: number; holder: string; event_id: string }>; canonical: string[]; orphaned: Record<string, string>; height: number; timestamp: number | null;
    reconciliation_required: null | { reorg_event_id: string; irreversible_event_ids: string[]; observed_tip: string } };
  sweeps: Record<string, Sweep>;
  holders: Record<string, { received: number; outgoing: number; fees: number }>;
  totals: { inflows: number; outflows: number; fees: number; service_revenue: number; losses: number; offered: number; delivered: number };
  integrals: Record<Category, Integral>;
}
export interface MachineConfig { operator: string; genesis_hash: string; confirmations: number; evidence_class: "reference-model" | "regtest" | "testnet4" }
function demand(ok: unknown, message: string): asserts ok { if (!ok) throw new Error(message); }
export function integer(n: number, name = "amount"): number {
  demand(Number.isSafeInteger(n) && n >= 0, `${name} must be a nonnegative safe integer`); return n;
}
export function sats(n: number): number { return integer(integer(n) * 1000); }
export function sum(xs: number[]): number { return xs.reduce((a, b) => integer(a + integer(b)), 0); }
export function canonicalJSON(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJSON).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonicalJSON((value as Record<string, unknown>)[k])}`).join(",")}}`;
  return JSON.stringify(value);
}
export function digest(value: unknown): string { return createHash("sha256").update(canonicalJSON(value)).digest("hex"); }
const unique = (xs: string[]) => demand(new Set(xs).size === xs.length, "duplicate reference");
const free = (a: AssetLot) => a.state === "FREE" || a.state === "FREE_AGAIN";
const active = (c: Claim) => c.state === "ACTIVE" || c.state === "RESERVED";

function empty(config: MachineConfig): AccountingState {
  return { A: {}, K: {}, H: { channels: {}, operations: {} }, B: { budget: 0, F: 0, C: 0, reserved: 0, pool: { funded: 0, transfers_in: 0, outflows: 0, fees: 0 } },
    J: { chain: { 0: config.genesis_hash }, funding_refs: [], offers: {}, canonical: [], orphaned: {}, height: 0, timestamp: 0, reconciliation_required: null },
    sweeps: {}, holders: {}, totals: { inflows: 0, outflows: 0, fees: 0, service_revenue: 0, losses: 0, offered: 0, delivered: 0 },
    integrals: Object.fromEntries(categories.map(k => [k, { msat_blocks: "0", msat_seconds: "0" }])) as Record<Category, Integral> };
}

export class CapitalAccountingMachine {
  private state: AccountingState;
  private events: CapitalEvent[] = [];
  readonly config: MachineConfig;
  constructor(config: MachineConfig) {
    demand(config.operator && config.genesis_hash, "operator and genesis required");
    demand(["reference-model", "regtest", "testnet4"].includes(config.evidence_class), "invalid evidence class");
    demand(integer(config.confirmations) > 0, "positive confirmation requirement");
    this.config = Object.freeze(structuredClone(config)); this.state = empty(config);
  }
  snapshot(): AccountingState { return structuredClone(this.state); }
  journal(): CapitalEvent[] { return structuredClone(this.events); }
  stateHash(): string { return digest({ config: this.config, state: this.state }); }
  static replay(config: MachineConfig, events: CapitalEvent[]): CapitalAccountingMachine {
    const m = new CapitalAccountingMachine(config); for (const e of events) m.apply(e); return m;
  }
  apply(event: CapitalEvent): string {
    const e = structuredClone(event);
    const previous = this.events.find(x => x.event_id === e.event_id);
    if (previous) { demand(canonicalJSON(previous) === canonicalJSON(e), "event ID collision"); return this.stateHash(); }
    demand(!this.state.J.reconciliation_required || e.event_type === "REORG", "accounting halted: reconcile irreversible orphaned settlement");
    this.validateEnvelope(e);
    // Copy-on-write: even a late invariant failure has zero observable effect.
    const draft = new CapitalAccountingMachine(this.config);
    draft.state = structuredClone(this.state); draft.events = structuredClone(this.events);
    if (e.event_type === "REORG") draft.reorg(e); else draft.reduce(e);
    draft.check(); draft.events.push(e);
    this.state = draft.state; this.events = draft.events; return this.stateHash();
  }
  private validateEnvelope(e: CapitalEvent): void {
    validateEventShape(e);
    demand(e.event_id && e.trace_id && e.unit === "msat", "invalid event envelope");
    integer(e.amount); integer(e.block_height); if (e.monotonic_timestamp !== null) integer(e.monotonic_timestamp, "timestamp");
    for (const xs of [e.asset_ids, e.claim_ids, e.causal_parent_ids, e.evidence_refs]) { demand(Array.isArray(xs), "reference array required"); unique(xs); }
    demand(e.event_type in eventTypes, "unknown event type");
    demand(e.event_type === "TICK" || e.evidence_refs.length > 0, "evidence reference required");
    for (const p of e.causal_parent_ids) demand(this.state.J.canonical.includes(p), `missing canonical cause ${p}`);
  }
  private depends(e: CapitalEvent, last: string): void { demand(last === e.event_id || e.causal_parent_ids.includes(last), `missing causal parent ${last}`); }
  private asset(e: CapitalEvent, id: string): AssetLot {
    const a = this.state.A[id]; demand(a && e.asset_ids.includes(id), `unknown/unlisted asset ${id}`); this.depends(e, a.last_event_id); return a;
  }
  private claim(e: CapitalEvent, id: string): Claim {
    const c = this.state.K[id]; demand(c && e.claim_ids.includes(id), `unknown/unlisted claim ${id}`); this.depends(e, c.last_event_id); return c;
  }
  private operation(e: CapitalEvent, id: string): Operation {
    const op = this.state.H.operations[id]; demand(op, `unknown operation ${id}`); this.depends(e, op.last_event_id); return op;
  }
  private channel(e: CapitalEvent, id: string): Channel {
    const ch = this.state.H.channels[id]; demand(ch, `unknown channel ${id}`); this.depends(e, ch.last_event_id); return ch;
  }
  private holder(id: string) { return this.state.holders[id] ??= { received: 0, outgoing: 0, fees: 0 }; }
  private newAsset(e: CapitalEvent, id: string, amount: number, location: string, backing: string, parents: string[], pool: boolean, state: CapitalState = "FREE"): AssetLot {
    demand(id && !this.state.A[id] && e.asset_ids.includes(id), `duplicate/unlisted asset ${id}`);
    demand(integer(amount) > 0 && backing, "positive value and backing required");
    demand(location !== "onchain" || amount % 1000 === 0, "onchain assets require whole satoshis");
    const a: AssetLot = { asset_id: id, amount, original_amount: amount, owner: this.config.operator, location, backing_ref: backing,
      state, created_at: e.event_id, last_event_id: e.event_id, parent_ids: parents, maturity_height: e.block_height, pool };
    this.state.A[id] = a; return a;
  }
  private issue(e: CapitalEvent, spec: ClaimSpec, expected: number, received: boolean): void {
    const s = this.state;
    demand(spec.claim_id && !s.K[spec.claim_id] && e.claim_ids.includes(spec.claim_id), "duplicate/unlisted claim");
    demand(spec.claimant && integer(spec.expiry_height) > e.block_height, "invalid claim expiry/holder");
    const ids = Object.keys(spec.allocations); demand(ids.length && sum(Object.values(spec.allocations)) === expected && expected > 0, "claim allocation mismatch");
    for (const id of ids) {
      const a = s.A[id]; demand(a && e.asset_ids.includes(id) && a.amount >= integer(spec.allocations[id]) && spec.allocations[id] > 0, "invalid backing");
      if (a.last_event_id !== e.event_id) this.depends(e, a.last_event_id);
      demand(a.owner === this.config.operator && (free(a) || a.state === "COMMITTED"), "backing unavailable");
      a.state = "COMMITTED"; a.last_event_id = e.event_id;
    }
    if (spec.parent_claim_id) demand(s.K[spec.parent_claim_id] && e.claim_ids.includes(spec.parent_claim_id), "unknown parent claim");
    s.K[spec.claim_id] = { ...spec, amount: expected, backing_ids: ids, parent_claim_id: spec.parent_claim_id ?? null, state: "ACTIVE", last_event_id: e.event_id };
    if (received) this.holder(spec.claimant).received += expected;
  }
  private stocks(): Record<Category, number> {
    const s = this.state, assets = Object.values(s.A), channels = Object.values(s.H.channels);
    return { fronting: s.B.F - s.B.C,
      unique_committed: sum(assets.filter(a => !free(a) && a.state !== "TRANSFERRED_OUT").map(a => a.amount)),
      htlc: sum(Object.values(s.H.operations).filter(o => o.state === "ACCEPTED" || o.state === "FAILED").map(o => o.in_flight_amount ?? o.delivered + o.max_fee)),
      inbound: sum(channels.map(c => c.remote)), outbound: sum(assets.filter(a => a.location.startsWith("ln:")).map(a => a.amount)),
      idle: sum(assets.filter(a => a.pool && free(a)).map(a => a.amount)) };
  }
  private accrue(e: CapitalEvent): void {
    const s = this.state; demand(e.block_height >= s.J.height, "height reversal requires REORG");
    if (e.monotonic_timestamp !== null && s.J.timestamp !== null) demand(e.monotonic_timestamp >= s.J.timestamp, "nonmonotonic time");
    const stock = this.stocks();
    for (const k of categories) {
      const i = s.integrals[k]; i.msat_blocks = String(BigInt(i.msat_blocks) + BigInt(stock[k]) * BigInt(e.block_height - s.J.height));
      i.msat_seconds = i.msat_seconds === null || e.monotonic_timestamp === null || s.J.timestamp === null ? null :
        String(BigInt(i.msat_seconds) + BigInt(stock[k]) * BigInt(e.monotonic_timestamp - s.J.timestamp));
    }
    s.J.height = e.block_height; s.J.timestamp = e.monotonic_timestamp;
  }
  private finality(e: CapitalEvent, height: number, hash: string): void {
    integer(height); demand(e.block_hash && this.state.J.chain[e.block_height] === e.block_hash, "canonical tip evidence required");
    demand(this.state.J.chain[height] === hash && e.block_height - height + 1 >= this.config.confirmations, "insufficient canonical finality");
  }
  private request(e: CapitalEvent, r: Request): void {
    const s = this.state; demand(r.operation_id && !s.H.operations[r.operation_id], "duplicate operation");
    const offer = s.J.offers[r.operation_id]; demand(offer && offer.amount === r.delivered && offer.holder === r.holder, "request requires prior offered demand"); this.depends(e, offer.event_id);
    unique(r.input_claim_ids); unique(r.reserve_ids); demand(r.input_claim_ids.length && r.reserve_ids.length, "empty inputs");
    const claims = r.input_claim_ids.map(id => this.claim(e, id));
    demand(claims.every(c => c.claimant === r.holder && c.state === "ACTIVE" && c.expiry_height > e.block_height), "client inputs unavailable");
    const inputValue = sum(claims.map(c => c.amount)); integer(r.max_fee);
    const holderLimit = integer(r.max_holder_fee ?? r.max_fee);
    demand(r.change_backing === "retained" || r.max_holder_fee === undefined, "separate holder fee limit requires retained backing");
    demand(holderLimit >= r.max_fee, "routing subsidy requires explicit accounting");
    demand(integer(r.delivered) > 0 && sum([r.delivered, holderLimit]) <= inputValue, "unaffordable payment");
    const gross = r.change_backing === "retained" ? sum([r.delivered, r.max_fee]) : inputValue;
    demand(integer(r.timeout_height) > e.block_height, "invalid HTLC timeout");
    demand(s.B.F - s.B.C + s.B.reserved + gross <= s.B.budget, "fronting budget exhausted");
    const assets = r.reserve_ids.map(id => this.asset(e, id));
    demand(assets.every(a => a.owner === this.config.operator && a.pool && free(a) && a.maturity_height <= e.block_height && a.location === `ln:${r.channel_id}`), "reserve not spendable on requested channel");
    demand(sum(assets.map(a => a.amount)) === gross, "gross reserve does not match declared backing policy; split first");
    const channel = this.channel(e, r.channel_id);
    demand(channel.spendable >= r.delivered + r.max_fee, "insufficient outbound channel capacity");
    channel.spendable -= r.delivered + r.max_fee; channel.last_event_id = e.event_id;
    for (const a of assets) { a.state = "RESERVED"; a.last_event_id = e.event_id; }
    for (const c of claims) { c.state = "RESERVED"; c.last_event_id = e.event_id; }
    s.B.reserved += gross;
    s.H.operations[r.operation_id] = { ...r, gross, state: "RESERVED", recovered: 0, fee: 0,
      recovery_ids: [...new Set(claims.flatMap(c => c.backing_ids))], last_event_id: e.event_id, committed_at: null, recovered_at: null, kind: "payment" };
  }
  private debit(e: CapitalEvent, ids: string[], amount: number): void {
    let remaining = integer(amount);
    for (const id of ids) { const a = this.state.A[id]; const take = Math.min(a.amount, remaining);
      demand(a.location !== "onchain" || take % 1000 === 0, "onchain debit requires whole satoshis"); a.amount -= take; remaining -= take;
      a.last_event_id = e.event_id; a.state = a.amount ? "FREE" : "TRANSFERRED_OUT"; }
    demand(remaining === 0, "insufficient debit assets");
  }
  private roundRefresh(e: CapitalEvent, d: RoundRefresh): void {
    const s = this.state;
    unique(d.input_claim_ids); unique(d.backing_ids);
    demand(!s.H.operations[d.operation_id] && d.input_claim_ids.length && d.backing_ids.length, "invalid round refresh");
    const claims = d.input_claim_ids.map(id => this.claim(e, id));
    const assets = d.backing_ids.map(id => this.asset(e, id));
    demand(claims.every(c => c.state === "ACTIVE" && c.claimant === d.replacement.claimant && c.expiry_height > e.block_height), "round inputs unavailable");
    demand(assets.every(a => a.pool && free(a) && a.location === "onchain" && a.created_at === e.event_id), "round requires new transaction backing");
    const value = sum(claims.map(c => c.amount)), gross = sum(assets.map(a => a.amount));
    demand(value > d.service_fee && Object.keys(d.replacement.allocations).every(id => d.backing_ids.includes(id)), "invalid round replacement");
    demand(s.B.F - s.B.C + s.B.reserved + gross <= s.B.budget, "round budget exhausted");
    for (const c of claims) { c.state = "FORFEITED"; c.last_event_id = e.event_id; }
    this.issue(e, d.replacement, value - d.service_fee, false);
    // Entire fresh root is committed, including value above the holder claim.
    for (const a of assets) { a.state = "COMMITTED"; a.last_event_id = e.event_id; }
    this.holder(d.replacement.claimant).fees += d.service_fee; s.totals.service_revenue += d.service_fee; s.B.F += gross;
    s.H.operations[d.operation_id] = { operation_id: d.operation_id, holder: d.replacement.claimant,
      input_claim_ids: d.input_claim_ids, reserve_ids: d.backing_ids, channel_id: "", delivered: 0, max_fee: 0, timeout_height: 0,
      gross, state: "SETTLED", recovered: 0, fee: 0, recovery_ids: [...new Set(claims.flatMap(c => c.backing_ids))],
      last_event_id: e.event_id, committed_at: e.block_height, recovered_at: null, kind: "refresh" };
  }
  private onchainTransaction(e: CapitalEvent, d: OnchainTransaction): void {
    const s = this.state; unique(d.input_ids); unique(d.outputs.map(o => o.asset_id)); unique(d.outputs.map(o => String(o.output_index)));
    demand(e.txid && d.input_ids.length && d.outputs.length, "onchain transaction missing inputs/outputs");
    this.finality(e, d.inclusion_height, d.inclusion_hash);
    const inputs = d.input_ids.map(id => this.asset(e, id));
    demand(inputs.every(a => a.location === "onchain" && a.pool === inputs[0].pool && a.maturity_height <= d.inclusion_height && e.evidence_refs.includes(`spends:${a.backing_ref}`)), "onchain input provenance mismatch");
    demand(new Set(inputs.map(a => a.backing_ref)).size === inputs.length, "transaction cannot spend partial slices twice");
    demand(inputs.every(a => !Object.values(s.A).some(other => other.asset_id !== a.asset_id && other.amount > 0 && other.backing_ref === a.backing_ref)), "transaction requires whole underlying outputs");
    demand(sum(inputs.map(a => a.amount)) === sum(d.outputs.map(o => o.amount)) + d.fee, "onchain transaction value/fee mismatch");
    if (d.reuse) {
      const sw = s.sweeps[d.reuse.sweep_id]; demand(sw && sw.state === "CONFIRMED" && sw.operation_ids !== undefined, "reuse needs generalized confirmed sweep");
      this.depends(e, sw.last_event_id); this.finality(e, sw.inclusion_height!, sw.inclusion_hash!);
      const recovered = inputs.find(a => a.asset_id === sw.output_id);
      demand(recovered && recovered.state === "CONFIRMING" && d.inclusion_height >= sw.inclusion_height!, "reuse does not spend confirmed recovery");
      demand(sw.operation_ids.length === 0 || (inputs.length === 1 && d.refresh), "fronting reuse must exclusively spend recovered output in independent round");
      const allocations = d.reuse.recovery_allocations;
      demand(Object.keys(allocations).length === sw.operation_ids.length && sw.operation_ids.every(id => Object.hasOwn(allocations, id)), "recovery allocation operation mismatch");
      const outstanding = sum(sw.operation_ids.map(id => s.H.operations[id].gross - s.H.operations[id].recovered));
      demand(sum(Object.values(allocations)) === Math.min(outstanding, recovered.amount), "recovery must credit available value exactly once");
      for (const id of sw.operation_ids) {
        const op = this.operation(e, id), amount = allocations[id];
        demand(integer(amount) <= op.gross - op.recovered && op.recovery_ids.every(a => sw.input_ids.includes(a)), "recovery overcredits commitment or omits backing");
        op.recovered += amount; s.B.C += amount; op.recovered_at = e.block_height; op.recovery_complete = true; op.last_event_id = e.event_id;
      }
      recovered.state = "FREE_AGAIN"; sw.state = "REUSED"; sw.last_event_id = e.event_id;
    }
    demand(inputs.every(a => free(a)), "onchain inputs not spendable");
    for (const a of inputs) { a.amount = 0; a.state = "TRANSFERRED_OUT"; a.last_event_id = e.event_id; }
    for (const o of d.outputs) {
      const ref = `${e.txid}:${o.output_index}`; demand(!s.J.funding_refs.includes(ref), "duplicate transaction output"); s.J.funding_refs.push(ref);
      const a = this.newAsset(e, o.asset_id, o.amount, "onchain", ref, d.input_ids, inputs[0].pool);
      if (o.release_height !== undefined) {
        demand(o.release_height > e.block_height, "pool backing expiry must be future"); a.release_height = o.release_height; a.state = "COMMITTED";
      }
    }
    s.totals.fees += d.fee; if (inputs[0].pool) s.B.pool.fees += d.fee;
    if (d.refresh) this.roundRefresh(e, d.refresh);
  }
  private backingExpired(e: CapitalEvent, ids: string[]): void {
    const s = this.state; unique(ids); demand(ids.length, "empty expiry inputs");
    for (const id of ids) {
      const a = this.asset(e, id); demand(a.state === "COMMITTED" && a.location === "onchain", "backing not committed onchain");
      const claims = Object.values(s.K).filter(c => c.state !== "RECOVERED" && c.state !== "EXITED" && (c.allocations[id] ?? 0) > 0);
      demand(claims.length || a.release_height !== undefined, "backing release conditions unknown");
      demand(a.release_height === undefined || e.block_height >= a.release_height, "pool backing not expired");
      for (const c of claims) { this.claim(e, c.claim_id); demand(c.state === "FORFEITED" && e.block_height >= c.expiry_height, "backing has outstanding holder claim or unexpired right"); }
      a.state = "RECOVERY_DUE"; a.last_event_id = e.event_id;
    }
  }
  private reduce(e: CapitalEvent): void {
    const s = this.state; this.accrue(e);
    if (e.event_type !== "CHAIN" && e.block_hash !== null) demand(s.J.chain[e.block_height] === e.block_hash, "event anchor is not canonical");
    switch (e.event_type) {
      case "FUND": {
        const d = e.data; demand(!s.J.funding_refs.includes(d.backing_ref), "duplicate underlying representation");
        demand(d.location === "onchain" && d.owner === this.config.operator && integer(d.maturity_height) <= e.block_height, "funding must be mature owned onchain value");
        demand(e.txid && e.block_hash && d.backing_ref.startsWith(`${e.txid}:`), "funding requires chain transaction evidence");
        const a = this.newAsset(e, d.asset_id, e.amount, d.location, d.backing_ref, [], d.pool); a.maturity_height = d.maturity_height;
        s.J.funding_refs.push(d.backing_ref); s.totals.inflows += e.amount; if (d.pool) { s.B.budget += e.amount; s.B.pool.funded += e.amount; } break;
      }
      case "OPEN_CHANNEL": case "MOVE_TO_CHANNEL": {
        const d = e.data, a = this.asset(e, d.asset_id); integer(d.remote);
        demand(free(a) && a.location === "onchain" && a.maturity_height <= e.block_height, "channel input unavailable");
        demand(!s.H.channels[d.channel_id] && !Object.values(s.H.channels).some(c => c.funding_ref === d.funding_ref), "duplicate channel funding");
        demand(e.txid && e.block_hash && d.funding_ref.startsWith(`${e.txid}:`), "channel funding transaction required");
        demand(integer(d.spendable) <= a.amount && integer(d.receivable) <= d.remote, "invalid directional capacity");
        demand(d.funding_ref === a.backing_ref || !s.J.funding_refs.includes(d.funding_ref), "duplicate underlying representation");
        if (!s.J.funding_refs.includes(d.funding_ref)) s.J.funding_refs.push(d.funding_ref);
        a.location = `ln:${d.channel_id}`; a.backing_ref = d.funding_ref; a.last_event_id = e.event_id;
        s.H.channels[d.channel_id] = { channel_id: d.channel_id, funding_ref: d.funding_ref, capacity: sum([a.amount, d.remote]), remote: d.remote, spendable: d.spendable, receivable: d.receivable, last_event_id: e.event_id }; break;
      }
      case "ISSUE_VTXO": {
        const fee = integer(e.data.service_fee ?? 0); demand(e.amount > fee, "issuance fee exceeds value");
        this.issue(e, e.data.claim, e.amount - fee, true);
        this.holder(e.data.claim.claimant).received += fee; this.holder(e.data.claim.claimant).fees += fee; s.totals.service_revenue += fee; break;
      }
      case "CHANNEL_CAPACITY": {
        const d = e.data, ch = this.channel(e, d.channel_id);
        demand(!Object.values(s.H.operations).some(o => o.channel_id === d.channel_id && ["RESERVED", "ACCEPTED", "FAILED"].includes(o.state)), "capacity observation requires quiescent channel");
        demand(d.local === sum(Object.values(s.A).filter(a => a.location === `ln:${d.channel_id}`).map(a => a.amount)) && d.remote === ch.remote, "capacity observation ownership mismatch");
        demand(d.spendable <= d.local && d.receivable <= d.remote, "invalid observed capacity");
        ch.spendable = d.spendable; ch.receivable = d.receivable; ch.last_event_id = e.event_id; break;
      }
      case "ONCHAIN_TRANSACTION": this.onchainTransaction(e, e.data); break;
      case "BACKING_EXPIRED": this.backingExpired(e, e.data.input_ids); break;
      case "RECOVERY_SWEEP": {
        const d = e.data; unique(d.input_ids); unique(d.operation_ids); unique(d.input_outpoints);
        demand(e.txid && !s.sweeps[d.sweep_id] && d.input_ids.length, "invalid recovery sweep");
        const assets = d.input_ids.map(id => this.asset(e, id));
        demand(assets.every(a => a.state === "RECOVERY_DUE" && a.location === "onchain"), "recovery inputs not eligible");
        demand(canonicalJSON(assets.map(a => a.backing_ref).sort()) === canonicalJSON([...d.input_outpoints].sort()), "recovery input outpoint mismatch");
        demand(d.fee < sum(assets.map(a => a.amount)), "recovery fee exceeds inputs");
        for (const op of Object.values(s.H.operations).filter(o => !o.recovery_complete && o.committed_at !== null && o.recovered < o.gross && o.recovery_ids.some(id => d.input_ids.includes(id))))
          demand(d.operation_ids.includes(op.operation_id), "recovery omits linked commitment");
        for (const id of d.operation_ids) {
          const op = this.operation(e, id); demand(op.state === "SETTLED" && !op.recovery_complete && op.recovered < op.gross && op.recovery_ids.every(a => d.input_ids.includes(a)), "recovery commitment mismatch");
        }
        for (const c of Object.values(s.K).filter(c => c.state !== "RECOVERED" && c.state !== "EXITED" && c.backing_ids.some(id => d.input_ids.includes(id)))) {
          this.claim(e, c.claim_id); demand(c.state === "FORFEITED" && c.expiry_height <= e.block_height && c.backing_ids.every(id => d.input_ids.includes(id)), "sweep violates claim");
        }
        for (const a of assets) { a.state = "RECOVERING"; a.last_event_id = e.event_id; }
        s.sweeps[d.sweep_id] = { ...d, operation_id: d.operation_ids[0] ?? "", txid: e.txid, state: "BROADCAST", inclusion_height: null, inclusion_hash: null, last_event_id: e.event_id }; break;
      }
      case "RECEIVE_LIGHTNING": {
        const d = e.data, ch = this.channel(e, d.channel_id); integer(d.fee);
        demand(ch.receivable >= e.amount && e.amount > d.fee, "insufficient inbound capacity");
        demand(sum(Object.values(d.claim.allocations)) === e.amount - d.fee && Object.keys(d.claim.allocations).length === 1 && d.claim.allocations[d.asset_id] === e.amount - d.fee, "receipt backing mismatch");
        this.newAsset(e, d.asset_id, e.amount - d.fee, `ln:${d.channel_id}`, ch.funding_ref, [], false);
        ch.remote -= e.amount - d.fee; ch.receivable -= e.amount - d.fee; ch.spendable += e.amount - d.fee; ch.last_event_id = e.event_id;
        s.totals.inflows += e.amount; s.totals.fees += d.fee;
        this.issue(e, d.claim, e.amount - d.fee, true); break;
      }
      case "PAYMENT_OFFERED": {
        demand(e.amount > 0 && !s.J.offers[e.data.operation_id], "invalid/duplicate offered demand");
        s.J.offers[e.data.operation_id] = { amount: e.amount, holder: e.data.holder, event_id: e.event_id }; s.totals.offered += e.amount; break;
      }
      case "REQUEST_OUTGOING": demand(e.amount === e.data.delivered, "request amount mismatch"); this.request(e, e.data); break;
      case "HTLC_ACCEPTED": {
        const op = this.operation(e, e.data.operation_id); demand(op.state === "RESERVED", "HTLC not reserved");
        if (e.data.in_flight_amount !== undefined) {
          const actual = integer(e.data.in_flight_amount);
          demand(actual >= op.delivered && actual <= op.delivered + op.max_fee, "in-flight amount outside authorized envelope");
          op.in_flight_amount = actual;
        }
        if (e.data.observed_spendable !== undefined) {
          demand(!Object.values(s.H.operations).some(o => o.operation_id !== op.operation_id && o.channel_id === op.channel_id &&
            ["RESERVED", "ACCEPTED", "FAILED"].includes(o.state)), "capacity attribution requires isolated channel attempt");
          const ch = this.channel(e, op.channel_id), before = ch.spendable + op.delivered + op.max_fee;
          const spendable = integer(e.data.observed_spendable);
          demand(spendable + (op.in_flight_amount ?? op.delivered + op.max_fee) <= before, "capacity observation ignores in-flight value");
          op.capacity_reserved = before - spendable;
          ch.spendable = spendable; ch.last_event_id = e.event_id;
        }
        op.state = "ACCEPTED"; op.committed_at = e.block_height; op.last_event_id = e.event_id;
        s.B.reserved -= op.gross; s.B.F += op.gross;
        for (const id of op.reserve_ids) { const a = this.asset(e, id); a.state = "COMMITTED"; a.last_event_id = e.event_id; } break;
      }
      case "CANCEL_REQUEST": case "RESOLVE_FAILED": {
        const d = e.data, op = this.operation(e, d.operation_id);
        if (e.event_type === "CANCEL_REQUEST") { demand(op.state === "RESERVED", "cannot cancel committed HTLC"); s.B.reserved -= op.gross; }
        else {
          demand(op.state === "FAILED", "failure not recorded"); const resolution = e.data;
          if (resolution.path === "timeout") {
            demand(e.block_height >= op.timeout_height && resolution.resolution_height !== undefined && resolution.resolution_height >= op.timeout_height && resolution.resolution_hash, "timeout resolution evidence missing");
            this.finality(e, resolution.resolution_height, resolution.resolution_hash);
          } else demand(resolution.path === "revocation", "invalid resolution path");
          op.resolution = resolution.path; op.recovered = op.gross; op.recovered_at = e.block_height; s.B.C += op.gross;
        }
        for (const id of op.reserve_ids) { const a = this.asset(e, id); a.state = "FREE"; a.last_event_id = e.event_id; }
        const inputs = op.input_claim_ids.map(id => this.claim(e, id));
        if (e.event_type === "RESOLVE_FAILED" && e.data.replacements) {
          demand(e.data.path === "revocation" && e.data.replacements.length > 0, "replacement claims require revocation");
          const available: Record<string, number> = {};
          for (const c of inputs) for (const [id, amount] of Object.entries(c.allocations)) available[id] = sum([available[id] ?? 0, amount]);
          const assigned: Record<string, number> = {};
          const assignedByParent: Record<string, Record<string, number>> = {};
          for (const c of e.data.replacements) {
            demand(c.claimant === op.holder && c.parent_claim_id && op.input_claim_ids.includes(c.parent_claim_id), "revocation replacement holder/parent mismatch");
            demand(c.expiry_height <= Math.min(...inputs.map(c => c.expiry_height)), "revocation cannot extend backing expiry");
            for (const [id, amount] of Object.entries(c.allocations)) assigned[id] = sum([assigned[id] ?? 0, amount]);
            const parentAllocation = assignedByParent[c.parent_claim_id] ??= {};
            for (const [id, amount] of Object.entries(c.allocations)) parentAllocation[id] = sum([parentAllocation[id] ?? 0, amount]);
          }
          demand(Object.keys(assigned).length === Object.keys(available).length && Object.keys(available).every(id => assigned[id] === available[id]), "revocation replacement backing mismatch");
          for (const c of inputs) demand(Object.keys(assignedByParent[c.claim_id] ?? {}).length === Object.keys(c.allocations).length &&
            Object.entries(c.allocations).every(([id, amount]) => assignedByParent[c.claim_id]?.[id] === amount), "revocation parent provenance mismatch");
          for (const c of inputs) {
            c.state = "FORFEITED"; c.last_event_id = e.event_id;
            for (const id of Object.keys(c.allocations)) c.allocations[id] = 0;
          }
          for (const c of e.data.replacements) this.issue(e, c, sum(Object.values(c.allocations)), false);
        } else for (const c of inputs) { c.state = "ACTIVE"; c.last_event_id = e.event_id; }
        const ch = this.channel(e, op.channel_id); ch.spendable += op.capacity_reserved ?? op.delivered + op.max_fee; ch.last_event_id = e.event_id;
        op.state = "RESOLVED"; op.last_event_id = e.event_id; break;
      }
      case "HTLC_FAILED": {
        const op = this.operation(e, e.data.operation_id); demand(op.state === "ACCEPTED", "HTLC not accepted");
        op.state = "FAILED"; op.last_event_id = e.event_id; break;
      }
      case "HTLC_SETTLED": {
        const d = e.data, op = this.operation(e, d.operation_id);
        demand(op.state === "ACCEPTED" || op.state === "FAILED", "HTLC not in flight"); integer(d.fee); const serviceFee = integer(d.service_fee ?? 0);
        demand((op.change_backing === "retained" ? d.fee <= op.max_fee && d.fee + serviceFee <= (op.max_holder_fee ?? op.max_fee) :
          d.fee + serviceFee <= op.max_fee) && e.evidence_refs.includes(d.preimage_evidence_ref), "fee/preimage evidence mismatch");
        demand(e.amount === op.delivered, "settled amount mismatch");
        demand(op.in_flight_amount === undefined || op.in_flight_amount === op.delivered + d.fee, "settlement disagrees with observed in-flight amount");
        const ch = this.channel(e, op.channel_id);
        for (const id of op.reserve_ids) this.asset(e, id);
        this.debit(e, op.reserve_ids, op.delivered + d.fee); ch.remote += op.delivered + d.fee;
        ch.receivable += op.delivered + d.fee;
        ch.spendable += (op.capacity_reserved ?? op.delivered + op.max_fee) - op.delivered - d.fee; ch.last_event_id = e.event_id;
        const inputs = op.input_claim_ids.map(id => this.claim(e, id));
        for (const c of inputs) { c.state = "FORFEITED"; c.last_event_id = e.event_id; }
        const change = sum(inputs.map(c => c.amount)) - op.delivered - d.fee - serviceFee;
        if (change) {
          const allowed = op.change_backing === "retained" ? op.recovery_ids : op.reserve_ids;
          demand(d.change && d.change.claimant === op.holder && Object.keys(d.change.allocations).every(id => allowed.includes(id)), "change backing policy mismatch");
          if (op.change_backing === "retained") {
            demand(d.change.expiry_height <= Math.min(...inputs.map(c => c.expiry_height)), "retained change cannot extend backing expiry");
            // Reassign an existing backing allocation, never add a second claim
            // over the same value. FORFEITED amounts retain historical input
            // value; their residual allocations are recovery encumbrances.
            for (const [id, amount] of Object.entries(d.change.allocations)) {
              let remaining = amount;
              for (const c of inputs) {
                const take = Math.min(c.allocations[id] ?? 0, remaining);
                if (take) { c.allocations[id] -= take; remaining -= take; }
              }
              demand(remaining === 0, "retained change exceeds input allocation");
            }
          }
          this.issue(e, d.change, change, false);
        }
        else demand(!d.change, "unexpected change");
        if (op.change_backing === "retained") {
          // The unused routing limit remains on the same, now spendable channel.
          // Only that released slice is recovered here; the paid amount stays W.
          const released = op.max_fee - d.fee;
          op.recovered += released; s.B.C += released;
        }
        s.totals.outflows += op.delivered; s.totals.fees += d.fee; s.totals.service_revenue += serviceFee; s.totals.delivered += op.delivered;
        s.B.pool.outflows += op.delivered; s.B.pool.fees += d.fee;
        this.holder(op.holder).outgoing += op.delivered; this.holder(op.holder).fees += d.fee + serviceFee;
        op.state = "SETTLED"; op.fee = d.fee; op.last_event_id = e.event_id; break;
      }
      case "REFRESH": {
        const d = e.data; unique(d.input_claim_ids); unique(d.reserve_ids); integer(d.fee);
        demand(!s.H.operations[d.operation_id] && d.input_claim_ids.length, "invalid refresh operation");
        const claims = d.input_claim_ids.map(id => this.claim(e, id)), assets = d.reserve_ids.map(id => this.asset(e, id));
        demand(claims.every(c => c.state === "ACTIVE" && c.claimant === d.replacement.claimant && c.expiry_height > e.block_height), "refresh inputs unavailable");
        const gross = sum(claims.map(c => c.amount)); demand(gross > d.fee && sum(assets.map(a => a.amount)) === gross && assets.every(a => a.pool && free(a)), "refresh reserves unavailable");
        demand(s.B.F - s.B.C + s.B.reserved + gross <= s.B.budget, "refresh budget exhausted");
        demand(Object.keys(d.replacement.allocations).every(id => d.reserve_ids.includes(id)), "refresh must use fresh backing");
        for (const c of claims) { c.state = "FORFEITED"; c.last_event_id = e.event_id; }
        this.debit(e, d.reserve_ids, d.fee); this.issue(e, d.replacement, gross - d.fee, false);
        // Fees debited from channel shares leave the tracked boundary and increase remote share.
        for (const a of assets) if (a.location.startsWith("ln:")) {
          const ch = this.channel(e, a.location.slice(3));
          const total = sum(Object.values(s.A).filter(x => x.location === a.location).map(x => x.amount));
          const debit = ch.capacity - total - ch.remote; demand(ch.spendable >= debit, "refresh fee exceeds channel capacity");
          ch.remote += debit; ch.receivable += debit; ch.spendable -= debit; ch.last_event_id = e.event_id;
        }
        this.holder(d.replacement.claimant).fees += d.fee; s.totals.fees += d.fee; s.B.pool.fees += d.fee; s.B.F += gross;
        s.H.operations[d.operation_id] = { operation_id: d.operation_id, holder: d.replacement.claimant, input_claim_ids: d.input_claim_ids, reserve_ids: d.reserve_ids,
          channel_id: "", delivered: 0, max_fee: d.fee, timeout_height: 0, gross, state: "SETTLED", recovered: 0, fee: d.fee,
          recovery_ids: [...new Set(claims.flatMap(c => c.backing_ids))], last_event_id: e.event_id, committed_at: e.block_height, recovered_at: null, kind: "refresh" }; break;
      }
      case "EXPIRY_REACHED": {
        const op = this.operation(e, e.data.operation_id); demand(op.state === "SETTLED" && op.recovered === 0, "no outstanding settled commitment");
        for (const id of op.input_claim_ids) { const c = this.claim(e, id); demand(c.state === "FORFEITED" && e.block_height >= c.expiry_height, "expiry not reached"); }
        for (const id of op.recovery_ids) { const a = this.asset(e, id); demand(a.state === "COMMITTED", "backing not committed"); a.state = "RECOVERY_DUE"; a.last_event_id = e.event_id; }
        op.last_event_id = e.event_id; break;
      }
      case "SWEEP_BROADCAST": {
        const d = e.data, op = this.operation(e, d.operation_id); integer(d.fee);
        demand(!s.sweeps[d.sweep_id] && e.txid && op.state === "SETTLED", "invalid sweep");
        const assets = op.recovery_ids.map(id => this.asset(e, id));
        demand(assets.every(a => a.state === "RECOVERY_DUE" && a.location === "onchain"), "sweep inputs not eligible onchain lots");
        demand(canonicalJSON(assets.map(a => a.backing_ref).sort()) === canonicalJSON([...d.input_outpoints].sort()), "sweep outpoint mismatch");
        demand(sum(assets.map(a => a.amount)) === op.gross && d.fee < op.gross, "sweep must cover exact gross commitment");
        for (const c of Object.values(s.K)) if (c.state !== "RECOVERED" && c.state !== "EXITED" && c.backing_ids.some(id => op.recovery_ids.includes(id))) demand(op.input_claim_ids.includes(c.claim_id), "sweep would violate another claim");
        for (const a of assets) { a.state = "RECOVERING"; a.last_event_id = e.event_id; }
        s.sweeps[d.sweep_id] = { ...d, input_ids: op.recovery_ids, txid: e.txid, state: "BROADCAST", inclusion_height: null, inclusion_hash: null, last_event_id: e.event_id }; break;
      }
      case "SWEEP_CONFIRMED": {
        const d = e.data, sw = s.sweeps[d.sweep_id]; demand(sw && sw.state === "BROADCAST", "sweep not pending"); this.depends(e, sw.last_event_id);
        demand(e.txid === sw.txid && e.block_hash && s.J.chain[d.inclusion_height] === d.inclusion_hash && d.inclusion_height <= e.block_height, "sweep inclusion not canonical");
        const inputs = sw.input_ids.map(id => this.asset(e, id)); const amount = sum(inputs.map(a => a.amount)) - sw.fee;
        demand(e.amount === amount, "observed sweep output/fee mismatch");
        s.B.pool.transfers_in += sum(inputs.filter(a => !a.pool).map(a => a.amount)); s.B.pool.fees += sw.fee;
        for (const a of inputs) { a.amount = 0; a.state = "TRANSFERRED_OUT"; a.last_event_id = e.event_id; }
        this.newAsset(e, sw.output_id, amount, "onchain", `${sw.txid}:0`, sw.input_ids, true, "CONFIRMING");
        demand(!s.J.funding_refs.includes(`${sw.txid}:0`), "duplicate sweep outpoint"); s.J.funding_refs.push(`${sw.txid}:0`);
        s.totals.fees += sw.fee; sw.state = "CONFIRMED"; sw.inclusion_height = d.inclusion_height; sw.inclusion_hash = d.inclusion_hash; sw.last_event_id = e.event_id;
        const claimIds = sw.operation_ids === undefined ? s.H.operations[sw.operation_id].input_claim_ids :
          Object.values(s.K).filter(c => c.state !== "RECOVERED" && c.state !== "EXITED" && c.backing_ids.some(id => sw.input_ids.includes(id))).map(c => c.claim_id);
        for (const id of claimIds) { const c = this.claim(e, id); c.state = "RECOVERED"; c.last_event_id = e.event_id; } break;
      }
      case "CAPITAL_REUSABLE": {
        const d = e.data, sw = s.sweeps[d.sweep_id]; demand(sw && sw.state === "CONFIRMED", "no confirmed recovery"); this.depends(e, sw.last_event_id);
        this.finality(e, sw.inclusion_height!, sw.inclusion_hash!);
        const a = this.asset(e, sw.output_id), op = this.operation(e, sw.operation_id);
        demand(a.state === "CONFIRMING" && a.amount === op.gross - sw.fee && op.recovered === 0, "recovery amount/provenance mismatch");
        // Recovery plus independently admissible reservation is one atomic event.
        // A new, confirmed channel funding transaction must actually spend this
        // recovered output. The observer supplies its input proof in evidence_refs.
        demand(d.reuse.reserve_ids.length === 1 && d.reuse.reserve_ids[0] === a.asset_id, "reuse must name recovered output");
        demand(e.txid && d.channel_funding_ref.startsWith(`${e.txid}:`) && e.evidence_refs.includes(`spends:${a.backing_ref}`), "recovered-output funding proof missing");
        this.finality(e, d.funding_height, d.funding_hash);
        demand(d.funding_height >= sw.inclusion_height! && !s.H.channels[d.reuse.channel_id] && !Object.values(s.H.channels).some(c => c.funding_ref === d.channel_funding_ref), "invalid reuse channel");
        demand(!s.J.funding_refs.includes(d.channel_funding_ref), "duplicate reuse funding"); s.J.funding_refs.push(d.channel_funding_ref);
        s.B.C += a.amount; op.recovered = a.amount; op.recovered_at = e.block_height; op.last_event_id = e.event_id;
        a.state = "FREE_AGAIN"; a.last_event_id = e.event_id;
        demand(integer(d.spendable) <= a.amount, "invalid recycled channel capacity");
        a.location = `ln:${d.reuse.channel_id}`; a.backing_ref = d.channel_funding_ref;
        s.H.channels[d.reuse.channel_id] = { channel_id: d.reuse.channel_id, funding_ref: d.channel_funding_ref, capacity: a.amount, remote: 0, spendable: d.spendable, receivable: 0, last_event_id: e.event_id };
        this.request(e, d.reuse);
        sw.state = "REUSED"; sw.last_event_id = e.event_id; break;
      }
      case "SPLIT_MERGE": {
        const d = e.data; unique(d.input_ids); unique(d.outputs.map(o => o.asset_id)); demand(d.input_ids.length && d.outputs.length, "empty split/merge");
        const inputs = d.input_ids.map(id => this.asset(e, id)), first = inputs[0];
        demand(inputs.every(a => free(a) && a.location === first.location && a.pool === first.pool && a.backing_ref === first.backing_ref && a.owner === first.owner), "only free slices of one backing can split/merge");
        demand(sum(inputs.map(a => a.amount)) === sum(d.outputs.map(o => o.amount)), "split/merge value mismatch");
        for (const a of inputs) { a.amount = 0; a.state = "TRANSFERRED_OUT"; a.last_event_id = e.event_id; }
        for (const o of d.outputs) this.newAsset(e, o.asset_id, o.amount, first.location, first.backing_ref, d.input_ids, first.pool); break;
      }
      case "EXIT": {
        const d = e.data, c = this.claim(e, d.claim_id); integer(d.fee); demand(c.state === "ACTIVE" && d.fee < c.amount && e.txid, "invalid exit");
        this.finality(e, d.inclusion_height, d.inclusion_hash);
        const assets = c.backing_ids.map(id => this.asset(e, id)); demand(assets.every(a => a.location === "onchain" && a.amount === c.allocations[a.asset_id]), "exit needs exclusive onchain backing");
        // Mixed pool/nonpool exits need explicit fee attribution; reject rather than guess.
        demand(assets.every(a => a.pool === assets[0].pool), "mixed exit pool attribution unsupported");
        if (assets[0].pool) { s.B.pool.outflows += c.amount - d.fee; s.B.pool.fees += d.fee; }
        if (d.mode === "unilateral") demand(e.evidence_refs.some(r => r.includes("ancestry")), "unilateral exit ancestry required");
        this.debit(e, c.backing_ids, c.amount); c.state = "EXITED"; c.last_event_id = e.event_id;
        s.totals.outflows += c.amount - d.fee; s.totals.fees += d.fee;
        this.holder(c.claimant).outgoing += c.amount - d.fee; this.holder(c.claimant).fees += d.fee;
        // Output is outside the operator boundary, retained as a zero-valued provenance receipt.
        const out = this.newAsset(e, d.output_id, c.amount - d.fee, d.destination, `${e.txid}:0`, c.backing_ids, false, "TRANSFERRED_OUT");
        out.owner = c.claimant; out.amount = 0; break;
      }
      case "CHAIN": {
        for (const b of e.data.blocks) {
          demand(integer(b.height) > 0 && b.hash && s.J.chain[b.height - 1] === b.parent_hash, "noncontiguous chain");
          demand(!s.J.chain[b.height] || s.J.chain[b.height] === b.hash, "chain replacement requires REORG"); s.J.chain[b.height] = b.hash;
        }
        demand(e.block_hash && s.J.chain[e.block_height] === e.block_hash, "chain tip mismatch"); break;
      }
      case "TICK": break;
      case "REORG": throw new Error("REORG must use replay");
      default: throw new Error("unknown event type");
    }
    s.J.canonical.push(e.event_id); this.check();
  }
  private reorg(e: Extract<CapitalEvent, { event_type: "REORG" }>): void {
    const chain: Record<string, string> = { 0: this.config.genesis_hash };
    for (const b of e.data.blocks) { demand(b.height > 0 && chain[b.height - 1] === b.parent_hash && !chain[b.height], "invalid replacement chain"); chain[b.height] = b.hash; }
    demand(chain[e.block_height] === e.block_hash, "replacement tip mismatch");
    const old = this.state.J, prior = this.events.filter(x => old.canonical.includes(x.event_id));
    demand(e.monotonic_timestamp === null || old.timestamp === null || e.monotonic_timestamp >= old.timestamp, "reorg timestamp reversal");
    const invalid = new Set<string>();
    for (const ev of prior) if ((ev.block_hash !== null && chain[ev.block_height] !== ev.block_hash) || ev.causal_parent_ids.some(p => invalid.has(p))) invalid.add(ev.event_id);
    const irreversible = prior.filter(ev => invalid.has(ev.event_id) && (ev.event_type === "HTLC_SETTLED" || ev.event_type === "RECEIVE_LIGHTNING"));
    if (irreversible.length) {
      // Offchain payment outcomes cannot be rolled back with a Bitcoin branch.
      // Retain the last reconciled economic checkpoint and append the observation,
      // but freeze all spending. A new canonical trace or explicit liability
      // instrumentation is needed; inventing a debit would be worse than stopping.
      this.state.J.reconciliation_required = { reorg_event_id: e.event_id, irreversible_event_ids: irreversible.map(x => x.event_id), observed_tip: e.block_hash! }; return;
    }
    this.state = empty(this.config); this.state.J.chain = chain; this.state.J.orphaned = { ...old.orphaned };
    for (const ev of prior) {
      const reason = ev.block_hash !== null && chain[ev.block_height] !== ev.block_hash ? "orphaned block" :
        ev.causal_parent_ids.some(p => this.state.J.orphaned[p]) ? "orphaned causal ancestor" : null;
      if (reason) { this.state.J.orphaned[ev.event_id] = reason; continue; }
      if (ev.event_type === "REORG") { this.state.J.canonical.push(ev.event_id); continue; }
      // Chain observations are retained as evidence; the replacement chain is authoritative.
      if (ev.event_type === "CHAIN") { this.accrue(ev); this.state.J.canonical.push(ev.event_id); continue; }
      this.reduce(ev);
    }
    // An orphaned branch may have reached a higher height. Block-time is recomputed
    // on surviving observations, never integrated backwards.
    this.accrue({ ...e, block_height: Math.max(this.state.J.height, e.block_height) });
    this.state.J.height = e.block_height; this.state.J.canonical.push(e.event_id);
  }
  check(): void {
    const s = this.state, assets = Object.values(s.A), claims = Object.values(s.K), ops = Object.values(s.H.operations);
    for (const a of assets) { integer(a.amount); demand(a.state !== "TRANSFERRED_OUT" || a.amount === 0, "I1 retired asset has value"); }
    demand(sum(assets.map(a => a.amount)) + s.totals.outflows + s.totals.fees + s.totals.losses === s.totals.inflows, "I1 economic conservation");
    for (const ch of Object.values(s.H.channels)) {
      const local = sum(assets.filter(a => a.location === `ln:${ch.channel_id}`).map(a => a.amount));
      demand(local + ch.remote === ch.capacity, "I1 channel share reconciliation");
      demand(integer(ch.spendable) <= local && integer(ch.receivable) <= ch.remote, "I1 directional channel capacity");
    }
    for (const a of assets) {
      const allocated = sum(claims.filter(c => c.state !== "RECOVERED" && c.state !== "EXITED").map(c => c.allocations[a.asset_id] ?? 0));
      demand(allocated <= a.amount, `I2 overallocated backing ${a.asset_id}`);
      demand(!allocated || !free(a), "I2 encumbered backing marked free");
    }
    demand(s.B.F === sum(ops.filter(o => o.committed_at !== null).map(o => o.gross)) && s.B.C === sum(ops.map(o => o.recovered)), "I3 commitment journal mismatch");
    demand(s.B.reserved === sum(ops.filter(o => o.state === "RESERVED").map(o => o.gross)), "I3 reservation mismatch");
    demand(sum(assets.filter(a => a.pool).map(a => a.amount)) + s.B.pool.outflows + s.B.pool.fees === s.B.pool.funded + s.B.pool.transfers_in, "I3 dedicated pool conservation");
    demand(s.B.F >= s.B.C && s.B.F - s.B.C + s.B.reserved <= s.B.budget, "I3 fronting bound");
    for (const o of ops) demand(o.recovered <= o.gross && (o.recovered === 0 || o.committed_at !== null), "I3 recovery without commitment");
    for (const [h, account] of Object.entries(s.holders)) demand(sum(claims.filter(c => c.claimant === h && active(c)).map(c => c.amount)) + account.outgoing + account.fees === account.received, `I4 holder conservation ${h}`);
    for (const n of [s.B.budget, s.B.F, s.B.C, s.B.reserved, ...Object.values(s.B.pool), ...Object.values(s.totals)]) integer(n);
  }
  reconcile(oracle: SettlementLedger, holders: string[]): void {
    // Defined checkpoint: no pending holder HTLC. Oracle tracks K, not A+K.
    demand(!this.state.J.reconciliation_required, "oracle checkpoint is unreconciled after reorg");
    demand(!Object.values(this.state.H.operations).some(o => o.state === "RESERVED" || o.state === "ACCEPTED" || o.state === "FAILED"), "oracle checkpoint has pending HTLC");
    for (const h of holders) demand(oracle.balance("V", h) === sum(Object.values(this.state.K).filter(c => c.claimant === h && active(c)).map(c => c.amount)), `oracle holder mismatch ${h}`);
  }
  report() {
    const s = this.state;
    return { evidence_class: this.config.evidence_class, state_hash: this.stateHash(), totals: s.totals, budget: s.B,
      reconciliation_required: s.J.reconciliation_required,
      outstanding_fronting: s.B.F - s.B.C, integrals: s.integrals, stocks: this.stocks(),
      free_budget: s.B.budget - (s.B.F - s.B.C) - s.B.reserved,
      pool_inventory: Object.fromEntries([...new Set(Object.values(s.A).map(a => a.state))].map(state => [state, sum(Object.values(s.A).filter(a => a.pool && a.state === state).map(a => a.amount))])),
      delivery_rate: s.totals.offered ? s.totals.delivered / s.totals.offered : null,
      per_offered_msat: Object.fromEntries(categories.map(k => [k, s.totals.offered ? Number(s.integrals[k].msat_blocks) / s.totals.offered : null])),
      per_delivered_msat: Object.fromEntries(categories.map(k => [k, s.totals.delivered ? Number(s.integrals[k].msat_blocks) / s.totals.delivered : null])),
      exposures: Object.values(s.H.operations).filter(o => o.committed_at !== null).map(o => ({ operation_id: o.operation_id,
        outstanding: o.gross - o.recovered, right_censored: o.recovered_at === null, recovery_height: o.recovered_at,
        ...(o.recovery_complete ? { recovery_complete: true, unrecovered_after_exhausted_backing: o.gross - o.recovered } : {}) })) };
  }
}
export const eventTypes: Record<keyof Payloads, true> = { FUND: true, OPEN_CHANNEL: true, ISSUE_VTXO: true, RECEIVE_LIGHTNING: true,
  CHANNEL_CAPACITY: true,
  PAYMENT_OFFERED: true,
  REQUEST_OUTGOING: true, CANCEL_REQUEST: true, HTLC_ACCEPTED: true, HTLC_SETTLED: true, HTLC_FAILED: true, RESOLVE_FAILED: true,
  REFRESH: true, EXPIRY_REACHED: true, SWEEP_BROADCAST: true, SWEEP_CONFIRMED: true, CAPITAL_REUSABLE: true,
  MOVE_TO_CHANNEL: true, SPLIT_MERGE: true, ONCHAIN_TRANSACTION: true, BACKING_EXPIRED: true, RECOVERY_SWEEP: true,
  EXIT: true, CHAIN: true, TICK: true, REORG: true };

export function checkJournal(config: MachineConfig, events: CapitalEvent[]) {
  const m = new CapitalAccountingMachine(config);
  for (let index = 0; index < events.length; index++) {
    try { m.apply(events[index]); } catch (error) { return { ok: false as const, index, event_id: events[index].event_id, error: String(error), state_hash: m.stateHash() }; }
  }
  return { ok: true as const, reconciled: m.snapshot().J.reconciliation_required === null, events: events.length, state_hash: m.stateHash() };
}
