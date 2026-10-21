// Implementation-informed, single-participant transaction forecast. This is
// deliberately not an observation adapter. Live journals use capital.ts.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { integer, sum } from "./capital.ts";
import { boardFee, receiveFee, refreshFee, sendFee, routingLimit, OBSERVED_TRANSACTION_COSTS as costs } from "./capital-fees.ts";

export interface ForecastConfig {
  wallet: number; local: number; remote: number; fronting: number;
  lifetime: number; refreshLead: number; recoveryDelay: number;
  /** Minimum fresh round output. Arkoor retained change may be subdust. */
  dust?: number;
  minBoard?: number;
  exitDepthLimit?: number;
}
interface Part { operation: number; amount: number }
interface Root { id: number; amount: number; expiry: number; active: number; parts: Part[] }
interface Claim { id: number; holder: number; amount: number; expiry: number; root: number; depth: number }
interface Holder { initial: number; received: number; sent: number; fees: number; balance: number; claims: Map<number, Claim> }
type Job = { kind: "refresh" | "recover"; id: number };
export type Rejection = "holder" | "dust_or_fee" | "wallet" | "outbound" | "inbound" | "fronting" | "expired" | "exit_depth";
export type Outcome = { ok: true } | { ok: false; reason: Rejection };
const yes: Outcome = { ok: true };
const no = (reason: Rejection): Outcome => ({ ok: false, reason });

// Dynamic event calendar. Exact-height jobs, not simulation-step endpoints,
// determine accrual, even when the caller advances across several lifetimes.
class Calendar {
  heap: number[] = [];
  jobs = new Map<number, Job[]>();
  add(height: number, job: Job) {
    const existing = this.jobs.get(height);
    if (existing) { existing.push(job); return; }
    this.jobs.set(height, [job]); let i = this.heap.length; this.heap.push(height);
    while (i > 0) { const p = (i - 1) >> 1; if (this.heap[p] <= height) break; this.heap[i] = this.heap[p]; i = p; }
    this.heap[i] = height;
  }
  take(): [number, Job[]] {
    const h = this.heap[0], jobs = this.jobs.get(h)!; this.jobs.delete(h);
    const last = this.heap.pop()!;
    if (this.heap.length) {
      let i = 0;
      while (i * 2 + 1 < this.heap.length) {
        let child = i * 2 + 1;
        if (child + 1 < this.heap.length && this.heap[child + 1] < this.heap[child]) child++;
        if (this.heap[child] >= last) break;
        this.heap[i] = this.heap[child]; i = child;
      }
      this.heap[i] = last;
    }
    return [h, jobs];
  }
}

export class CapitalForecast {
  readonly config: ForecastConfig;
  height = 0; cash: number; local: number; remote: number;
  F = 0; C = 0; exhausted = 0;
  minerFees = 0; clientMinerFees = 0; inflows = 0; outflows = 0;
  rootStock = 0; holderStock = 0;
  peakCashDraw = 0; peakFronting = 0; minimumLocal: number; minimumRemote: number;
  requiredInitialLocal: number = costs.outboundBuffer;
  offered = 0; delivered = 0; offeredEvents = 0; deliveredEvents = 0;
  readonly directional = { in_offered: 0, in_delivered: 0, out_offered: 0, out_delivered: 0 };
  readonly failures: Partial<Record<Rejection, number>> = {};
  readonly maintenanceFailures: Partial<Record<Rejection, number>> = {};
  readonly integrals = { fronting: 0n, uniqueCommitted: 0n, idle: 0n, inbound: 0n, outbound: 0n, inFlight: 0n, holderOverlay: 0n };
  private roots = new Map<number, Root>();
  private holders = new Map<number, Holder>();
  private calendar = new Calendar();
  private nextId = 0; private operation = 0;
  private chain = "0".repeat(64);
  private auditCounter = 0;
  constructor(config: ForecastConfig) {
    for (const x of Object.values(config)) integer(x);
    assert.ok(config.lifetime > config.refreshLead && config.refreshLead > 0);
    this.config = { ...config, dust: config.dust ?? 330, minBoard: config.minBoard ?? 20000, exitDepthLimit: config.exitDepthLimit ?? 100 };
    assert.ok(this.config.exitDepthLimit! >= 2);
    this.cash = config.wallet; this.local = config.local; this.remote = config.remote;
    this.minimumLocal = this.local; this.minimumRemote = this.remote;
  }
  get W() { return this.F - this.C; }
  private holder(id: number): Holder {
    integer(id);
    let h = this.holders.get(id);
    if (!h) { h = { initial: 0, received: 0, sent: 0, fees: 0, balance: 0, claims: new Map() }; this.holders.set(id, h); }
    return h;
  }
  balance(id: number): number { return this.holders.get(id)?.balance ?? 0; }
  private record(kind: string, data: unknown) {
    this.chain = createHash("sha256").update(JSON.stringify([this.chain, this.height, kind, data])).digest("hex");
    this.peakCashDraw = Math.max(this.peakCashDraw, this.config.wallet - this.cash);
    this.peakFronting = Math.max(this.peakFronting, this.W);
    this.minimumLocal = Math.min(this.minimumLocal, this.local); this.minimumRemote = Math.min(this.minimumRemote, this.remote);
    // Economic conservation and budget checks run after every accepted mutation.
    assert.equal(this.cash + this.rootStock + this.local + this.outflows + this.minerFees,
      this.config.wallet + this.config.local + this.inflows);
    assert.ok(this.cash >= 0 && this.local >= 0 && this.remote >= 0 && this.W >= 0 && this.W <= this.config.fronting);
    assert.equal(this.local + this.remote, this.config.local + this.config.remote);
    if (++this.auditCounter % 256 === 0) this.audit();
  }
  private createRoot(holder: number, amount: number, rootAmount: number, expiry: number) {
    const id = this.nextId++, root: Root = { id, amount: rootAmount, expiry, active: amount, parts: [] };
    this.roots.set(id, root); this.rootStock += rootAmount;
    const claim: Claim = { id: this.nextId++, holder, amount, expiry, root: id, depth: 0 };
    this.holder(holder).claims.set(claim.id, claim); this.holder(holder).balance += amount; this.holderStock += amount;
    this.calendar.add(expiry - this.config.refreshLead, { kind: "refresh", id: claim.id });
    this.calendar.add(expiry + this.config.recoveryDelay, { kind: "recover", id });
    return claim;
  }
  board(holder: number, gross: number): Outcome {
    integer(holder); integer(gross); const fee = boardFee(gross), amount = gross - fee;
    if (gross < this.config.minBoard! || amount < this.config.dust!) return no("dust_or_fee");
    const h = this.holder(holder); h.initial += gross; h.fees += fee;
    this.inflows += gross; this.clientMinerFees += costs.boardMiner;
    this.createRoot(holder, amount, gross, this.height + this.config.lifetime);
    this.record("board", [holder, gross, fee]); return yes;
  }
  receive(holder: number, gross: number): Outcome {
    integer(holder); integer(gross); const fee = receiveFee(gross), amount = gross - fee;
    if (amount < this.config.dust!) return no("dust_or_fee");
    if (this.remote - costs.inboundBuffer < gross) return no("inbound");
    const rootAmount = amount + costs.rootOverhead, draw = rootAmount + costs.roundMiner;
    if (this.cash < draw) return no("wallet");
    this.cash -= draw; this.minerFees += costs.roundMiner;
    this.local += gross; this.remote -= gross; this.inflows += gross;
    const h = this.holder(holder); h.received += gross; h.fees += fee;
    this.createRoot(holder, amount, rootAmount, this.height + this.config.lifetime);
    this.record("receive", [holder, gross, fee, rootAmount]); return yes;
  }
  send(holder: number, amount: number): Outcome {
    integer(holder); integer(amount); if (!amount) return no("dust_or_fee");
    const h = this.holders.get(holder); if (!h || h.balance < amount) return no("holder");
    const available = [...h.claims.values()].filter(c => c.expiry > this.height && c.depth < this.config.exitDepthLimit!)
      .sort((a, b) => a.expiry - b.expiry || a.id - b.id);
    const chosen: Claim[] = []; let value = 0, fee = 0, change = 0, valid = false;
    for (const c of available) {
      chosen.push(c); value += c.amount; fee = sendFee(amount, chosen, this.height); change = value - amount - fee;
      if (change >= 0) { valid = true; break; }
    }
    if (!valid) return no([...h.claims.values()].some(c => c.expiry <= this.height) ? "expired"
      : available.length < h.claims.size ? "exit_depth" : "holder");
    this.requiredInitialLocal = Math.max(this.requiredInitialLocal,
      this.config.local - this.local + amount + routingLimit(fee) + costs.outboundBuffer);
    if (this.local - costs.outboundBuffer < amount + routingLimit(fee)) return no("outbound");
    if (this.W + amount > this.config.fronting) return no("fronting");
    // Consume each input in order; retained change stays on its original root.
    // Only invoice value is actually transferred. Unused routing limit has
    // zero duration under this explicitly instantaneous settlement forecast.
    const op = this.operation++; let debit = amount + fee, principal = amount;
    for (const c of chosen) {
      const used = Math.min(debit, c.amount), front = Math.min(principal, used), root = this.roots.get(c.root)!;
      debit -= used; principal -= front;
      c.amount -= used; root.active -= used; h.balance -= used; this.holderStock -= used;
      if (front) root.parts.push({ operation: op, amount: front });
      if (!c.amount) h.claims.delete(c.id);
      else {
        c.depth++;
        if (c.depth >= this.config.exitDepthLimit! - 1) this.calendar.add(this.height, { kind: "refresh", id: c.id });
      }
      assert.ok(root.active >= 0 && root.active <= root.amount);
    }
    assert.equal(debit, 0); assert.equal(principal, 0);
    h.sent += amount; h.fees += fee; this.F += amount;
    this.local -= amount; this.remote += amount; this.outflows += amount;
    this.record("send", [holder, amount, fee, chosen.map(c => c.id)]); return yes;
  }
  private refresh(c: Claim): Outcome {
    if (c.expiry <= this.height) return no("expired");
    const fee = refreshFee([c], this.height), amount = c.amount - fee;
    if (amount < this.config.dust!) return no("dust_or_fee");
    const rootAmount = amount + costs.rootOverhead, draw = rootAmount + costs.roundMiner;
    if (this.cash < draw) return no("wallet");
    if (this.W + rootAmount > this.config.fronting) return no("fronting");
    const h = this.holder(c.holder), old = this.roots.get(c.root)!;
    this.cash -= draw; this.minerFees += costs.roundMiner;
    old.active -= c.amount; old.parts.push({ operation: this.operation++, amount: rootAmount });
    h.claims.delete(c.id); h.balance -= c.amount; h.fees += fee; this.holderStock -= c.amount;
    this.createRoot(c.holder, amount, rootAmount, this.height + this.config.lifetime); this.F += rootAmount;
    this.record("refresh", [c.id, c.amount, fee, rootAmount]); return yes;
  }
  refreshHolder(holder: number): Outcome[] {
    return [...(this.holders.get(holder)?.claims.values() ?? [])].map(c => this.refresh(c));
  }
  private recover(root: Root) {
    // A live or expired holder claim is an obligation, never a free wallet UTXO.
    if (root.active) return;
    // Do not invent a zero/dust-output transaction when the fixed-cost,
    // single-root sweep is uneconomic. Batched rescue is outside this policy.
    if (root.amount - costs.boardSweepMiner < this.config.dust!) return;
    const fee = costs.boardSweepMiner, net = root.amount - fee;
    this.rootStock -= root.amount; this.cash += net; this.minerFees += fee;
    let remaining = net;
    for (const part of root.parts) {
      const recovered = Math.min(remaining, part.amount); remaining -= recovered;
      this.C += recovered; this.exhausted += part.amount - recovered;
    }
    this.roots.delete(root.id); this.record("recover", [root.id, root.amount, net]);
  }
  private accrue(to: number) {
    const dt = BigInt(to - this.height);
    this.integrals.fronting += BigInt(this.W) * dt;
    this.integrals.uniqueCommitted += BigInt(this.rootStock + this.local + this.remote) * dt;
    this.integrals.idle += BigInt(this.cash) * dt;
    this.integrals.inbound += BigInt(this.remote) * dt; this.integrals.outbound += BigInt(this.local) * dt;
    this.integrals.holderOverlay += BigInt(this.holderStock) * dt;
    this.height = to;
  }
  advance(to: number) {
    integer(to); assert.ok(to >= this.height);
    while (this.calendar.heap.length && this.calendar.heap[0] <= to) {
      const [height, jobs] = this.calendar.take(); this.accrue(height);
      // Final recovery at a height can fund refreshes at that same height.
      for (const job of jobs.filter(j => j.kind === "recover")) {
        const root = this.roots.get(job.id); if (root) this.recover(root);
      }
      for (const job of jobs.filter(j => j.kind === "refresh")) {
        // Lookup is indexed below by root-independent claim id; this loop is
        // bounded by number of holders, not historical spent claims.
        let claim: Claim | undefined;
        for (const h of this.holders.values()) { claim = h.claims.get(job.id); if (claim) break; }
        if (!claim) continue;
        const result = this.refresh(claim);
        if (!result.ok) {
          this.maintenanceFailures[result.reason] = (this.maintenanceFailures[result.reason] ?? 0) + 1;
          // A failed refresh remains live through expiry. Retry once per six
          // blocks until the deadline; never silently delete the obligation.
          if (height + 6 < claim.expiry) this.calendar.add(height + 6, job);
        }
      }
    }
    this.accrue(to);
  }
  offer(holder: number, direction: "in" | "out", amount: number): Outcome {
    integer(amount); this.offered += amount; this.offeredEvents++;
    this.directional[`${direction}_offered`] += amount;
    const result = direction === "in" ? this.receive(holder, amount) : this.send(holder, amount);
    if (result.ok) { this.delivered += amount; this.deliveredEvents++; this.directional[`${direction}_delivered`] += amount; }
    else this.failures[result.reason] = (this.failures[result.reason] ?? 0) + 1;
    return result;
  }
  audit() {
    assert.equal(sum([...this.roots.values()].map(r => r.amount)), this.rootStock);
    let holderStock = 0, parts = 0; const allocations = new Map<number, number>();
    for (const h of this.holders.values()) {
      assert.equal(h.balance, sum([...h.claims.values()].map(c => c.amount)));
      assert.equal(h.initial + h.received, h.sent + h.fees + h.balance);
      holderStock += h.balance;
      for (const c of h.claims.values()) {
        assert.ok(this.roots.has(c.root)); allocations.set(c.root, (allocations.get(c.root) ?? 0) + c.amount);
      }
    }
    for (const r of this.roots.values()) {
      assert.equal(allocations.get(r.id) ?? 0, r.active); assert.ok(r.active <= r.amount);
      parts += sum(r.parts.map(p => p.amount));
    }
    assert.equal(holderStock, this.holderStock); assert.equal(parts + this.exhausted, this.W);
  }
  economicHash() {
    return createHash("sha256").update(JSON.stringify({ cash: this.cash, local: this.local, remote: this.remote,
      roots: [...this.roots.values()], holders: [...this.holders].map(([id, h]) => [id, { ...h, claims: [...h.claims.values()] }]),
      F: this.F, C: this.C, fees: this.minerFees, inflows: this.inflows, outflows: this.outflows, chain: this.chain })).digest("hex");
  }
  report() {
    this.audit();
    const future: Record<number, { roots: number; gross: number; fronting: number }> = {};
    let expiredHolder = 0, encumberedRoots = 0, uneconomicRoots = 0;
    for (const r of this.roots.values()) {
      if (r.active) { encumberedRoots += r.amount; if (r.expiry <= this.height) expiredHolder += r.active; continue; }
      if (r.amount - costs.boardSweepMiner < this.config.dust!) { uneconomicRoots += r.amount; continue; }
      const at = r.expiry + this.config.recoveryDelay;
      const entry = future[at] ??= { roots: 0, gross: 0, fronting: 0 };
      entry.roots++; entry.gross += r.amount; entry.fronting += sum(r.parts.map(p => p.amount));
    }
    return { evidence_class: "single_participant_fee_aware_forecast", height: this.height, config: this.config,
      state_hash: this.economicHash(), accepted_transition_hash: this.chain,
      offered_sat: this.offered, delivered_sat: this.delivered, delivery_rate: this.offered ? this.delivered / this.offered : null,
      directional_value_sat: this.directional,
      offered_events: this.offeredEvents, delivered_events: this.deliveredEvents, failures: this.failures, maintenance_failures: this.maintenanceFailures,
      miner_fees_sat: this.minerFees, external_client_board_fees_sat: this.clientMinerFees,
      holder_service_fees_sat: sum([...this.holders.values()].map(h => h.fees)),
      peak_cash_draw_sat: this.peakCashDraw, peak_fronting_sat: this.peakFronting,
      required_initial_local_sat: this.requiredInitialLocal,
      required_initial_remote_sat: this.config.remote - this.minimumRemote + costs.inboundBuffer,
      integrals_sat_blocks: Object.fromEntries(Object.entries(this.integrals).map(([k, v]) => [k, v.toString()])),
      integrals_sat_seconds: null,
      terminal: { cash_sat: this.cash, onchain_roots_sat: this.rootStock, ln_local_sat: this.local, ln_remote_sat: this.remote,
        F_sat: this.F, C_sat: this.C, W_sat: this.W, exhausted_recovery_shortfall_sat: this.exhausted,
        holder_claims_sat: this.holderStock, expired_holder_sat: expiredHolder, encumbered_root_sat: encumberedRoots,
        uneconomic_single_root_sweep_sat: uneconomicRoots,
        recovery_is_right_censored: true, forecast_unencumbered_recovery_schedule: future } };
  }
}
