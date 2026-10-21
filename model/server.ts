// Server-mediated object (Ark-style VTXO) liquidity model and the directional channel comparison.
// Witnesses Proposition S2 and computes the liquidity-duration ratio of §3.3 on a demand grid.
//
// Lock rule (from the implementer's published description of the three liquidity operations and
// forfeit sweeping): whenever a VTXO is forfeited (spent over Lightning, refreshed, or offboarded), the
// server fronts equivalent value now and recovers it only when that output's absolute expiry passes.
// Whether a server-held HTLC output from a Lightning spend is recyclable as a round input before its
// expiry is not settled by the cited documentation; the lock rule assumes it is not, which is the
// longer lock and therefore the assumption less favorable to the VTXO. It is a parameter of the ratio,
// not a fact about Ark.
//
// Boarding and receiving draw no forfeit lock, but a Lightning receipt into the Ark consumes inbound
// capacity on the server's own channels, which the server must have provisioned in advance. That is
// the directional term §3.4 says moves to the server tier; the ratio charges it (serverTierTerm) as the
// channel model applied to the server's aggregate flow, so that pooling is what it is — the peak of a
// sum against a sum of peaks — and not an omission.
//
// Parameters default to published values (28 d ≈ 4032 blocks, hourly rounds ≈ 6 blocks) and are inputs.

export interface ServerParams {
  lifetimeBlocks: number;
  roundInterval: number;
  refreshLead: number;
  /**
   * When the server recovers value it fronted for a Lightning spend: "expiry" — the forfeited input is
   * swept at its absolute expiry (the reading under which L̄ is the mean residual lifetime, ~half of 28 d);
   * "round" — the server-held HTLC output is presented as an input to the next round and its value is
   * reusable one round interval later. Refreshes and offboards are swept at expiry under either setting.
   * Which reading matches the implementation is open (see header) and sets the scale of 𝒟_V.
   */
  spendLock: "expiry" | "round";
  /** Structurally calibrated forecast policy, not a measured latency distribution. */
  changeBacking?: "fresh" | "retained";
  recoveryDelayBlocks?: number;
}

export const DEFAULT_SERVER: ServerParams = { lifetimeBlocks: 4032, roundInterval: 6, refreshLead: 288, spendLock: "expiry" };

interface Vtxo {
  id: string;
  holder: string;
  value: number;
  expiresAt: number;
  forfeited: boolean;
}

export type VolumeBasis = "out" | "both";

export class ArkServer {
  readonly params: ServerParams;
  readonly capital: number;    // fixed reserve for fronting, B_S^F; issuance stock is charged separately
  committed = 0;               // W_S: forfeited-but-unswept value the server has fronted
  height = 0;
  volumeDelivered = 0;         // outward Lightning spends the server fronted
  volumeReceived = 0;          // receipts issued as VTXOs
  private lockedIntegral = 0;  // ∫ W_S dt (value·blocks)
  private lastHeight = 0;
  private nextId = 0;
  private holderIntegral = 0;
  private holderStock = 0;
  private peakFronting = 0;
  private grossFronting = 0;
  private recoveredFronting = 0;
  private peakOnchainBacking = 0;
  private lateRefresh = false;
  /** Live claims, insertion-ordered; retained change can preserve an earlier expiry. */
  private readonly live = new Map<string, Vtxo>();
  /** Forfeited outputs bucketed by the height at which the server may sweep them. */
  private readonly sweepAt = new Map<number, Vtxo[]>();
  private readonly byHolder = new Map<string, Set<string>>();
  readonly outward = new Map<string, number>();
  readonly inward = new Map<string, number>();
  /** Cumulative gross receipt issuance plus outgoing allocations; not outstanding reserved stock. */
  readonly allocated = new Map<string, number>();
  /** Aggregate Lightning flow through the server per advance() call: what the server's channels carry. */
  readonly aggregateSteps: Array<{ in: number; out: number }> = [];
  private stepIn = 0;
  private stepOut = 0;

  constructor(capital: number, params: ServerParams = DEFAULT_SERVER) {
    if (!Number.isSafeInteger(params.recoveryDelayBlocks ?? 0) || (params.recoveryDelayBlocks ?? 0) < 0) throw new Error("invalid recovery delay");
    if (params.changeBacking === "retained" && params.spendLock === "round") throw new Error("retained backing has no proved next-round recovery shortcut");
    this.capital = capital;
    this.params = params;
  }

  get uncommitted(): number {
    return this.capital - this.committed;
  }

  private static bump(m: Map<string, number>, k: string, v: number): void {
    m.set(k, (m.get(k) ?? 0) + v);
  }

  private accrue(): void {
    this.lockedIntegral += this.committed * (this.height - this.lastHeight);
    this.lastHeight = this.height;
  }

  advance(blocks: number): void {
    if (!Number.isSafeInteger(blocks) || blocks < 0) throw new Error("blocks must be a nonnegative safe integer");
    // W_S is piecewise constant between events; integrate over the interval before applying sweeps.
    this.lockedIntegral += this.committed * blocks;
    this.holderIntegral += this.holderStock * blocks;
    const from = this.height;
    this.height += blocks;
    this.lastHeight = this.height;
    this.aggregateSteps.push({ in: this.stepIn, out: this.stepOut });
    this.stepIn = 0; this.stepOut = 0;
    for (let h = from + 1; h <= this.height; h++) {
      const due = this.sweepAt.get(h);
      if (!due) continue;
      for (const v of due) {
        this.committed -= v.value; // sweep: fronted value recovered
        this.recoveredFronting += v.value;
        // A caller may advance past several sweep heights in one step. The upfront integral
        // charged this value to the endpoint; remove the time after its actual recovery.
        this.lockedIntegral -= v.value * (this.height - h);
      }
      this.sweepAt.delete(h);
    }
    // Holders refresh outputs approaching expiry; a refresh is a forfeit plus a server-funded reissue.
    // Retained change can be inserted after newer claims with later expiry.
    const toRefresh: string[] = [];
    for (const v of this.live.values()) {
      if (v.expiresAt - this.height > this.params.refreshLead) continue;
      toRefresh.push(v.id);
    }
    for (const id of toRefresh) this.refresh(id);
  }

  private newVtxo(holder: string, value: number, expiry = this.height + this.params.lifetimeBlocks): Vtxo {
    const v: Vtxo = { id: `v${this.nextId++}`, holder, value, expiresAt: expiry, forfeited: false };
    this.holderStock += value;
    this.peakOnchainBacking = Math.max(this.peakOnchainBacking, this.holderStock + this.committed);
    this.live.set(v.id, v);
    if (!this.byHolder.has(holder)) this.byHolder.set(holder, new Set());
    this.byHolder.get(holder)!.add(v.id);
    return v;
  }

  /** Forfeit an output: the server fronts its value now and sweeps it at sweepHeight (default: the output's expiry). */
  private forfeit(v: Vtxo, sweepHeight: number = v.expiresAt): boolean {
    if (v.value > this.uncommitted) return false;
    v.forfeited = true;
    this.committed += v.value;
    this.grossFronting += v.value; this.peakFronting = Math.max(this.peakFronting, this.committed);
    this.holderStock -= v.value;
    this.live.delete(v.id);
    this.byHolder.get(v.holder)?.delete(v.id);
    const at = Math.min(sweepHeight, v.expiresAt) + (this.params.recoveryDelayBlocks ?? 0);
    if (at <= this.height) { this.committed -= v.value; this.recoveredFronting += v.value; return true; }
    if (!this.sweepAt.has(at)) this.sweepAt.set(at, []);
    this.sweepAt.get(at)!.push(v);
    return true;
  }

  /**
   * Receive over Lightning (or board): a holder gains an output. No forfeit lock is drawn, but the
   * receipt crosses the server's channels inbound and is recorded in aggregateSteps for the server-tier term.
   */
  receive(holder: string, value: number): string {
    const v = this.newVtxo(holder, value);
    ArkServer.bump(this.inward, holder, value);
    ArkServer.bump(this.allocated, holder, value);
    this.volumeReceived += value;
    this.stepIn += value;
    return v.id;
  }

  refresh(id: string): boolean {
    const old = this.live.get(id);
    if (!old || old.forfeited) return false;
    if (old.expiresAt <= this.height) this.lateRefresh = true;
    if (!this.forfeit(old)) return false;
    this.newVtxo(old.holder, old.value);
    return true;
  }

  holderValue(holder: string): number {
    let s = 0;
    for (const id of this.byHolder.get(holder) ?? []) s += this.live.get(id)!.value;
    return s;
  }

  /** Spend outward over Lightning. The server fronts the HTLC from uncommitted capital (S2 aggregate constraint). */
  spendLightning(holder: string, amount: number): boolean {
    if (!Number.isInteger(amount) || amount <= 0) throw new Error("amount must be a positive integer");
    if (this.holderValue(holder) < amount) return false;
    const inputs: Vtxo[] = [];
    let total = 0;
    for (const id of this.byHolder.get(holder) ?? []) {
      if (total >= amount) break;
      const v = this.live.get(id)!;
      inputs.push(v); total += v.value;
    }
    const retained = this.params.changeBacking === "retained";
    if ((retained ? amount : total) > this.uncommitted) return false; // atomic admission
    const sweep = this.params.spendLock === "round" ? this.height + this.params.roundInterval : Number.POSITIVE_INFINITY;
    let remaining = amount;
    for (const v of inputs) {
      if (retained && v.value > remaining) {
        const change = v.value - remaining, expiry = v.expiresAt;
        // Preserve original expiry and commit routed principal. This forecast is fee-free.
        this.holderStock -= change; v.value = remaining;
        this.forfeit(v, sweep); this.newVtxo(holder, change, expiry); remaining = 0;
      } else { remaining -= v.value; this.forfeit(v, sweep); }
    }
    const change = total - amount;
    if (!retained && change > 0) this.newVtxo(holder, change); // abstract fresh-backed change
    ArkServer.bump(this.outward, holder, amount);
    ArkServer.bump(this.allocated, holder, amount); // cumulative allocation, which may recycle the same reserve
    this.volumeDelivered += amount;
    this.stepOut += amount;
    return true;
  }

  /** ∫ W_S dt in value·blocks: the forfeit-lock component of the server's locked capital-time. */
  lockedIntegralBlocks(): number {
    this.accrue();
    return this.lockedIntegral;
  }

  accountingDiagnostics() {
    const physicalPartitionValid = this.params.changeBacking === "retained" && !this.lateRefresh &&
      ![...this.live.values()].some(v => v.expiresAt <= this.height);
    return { F: this.grossFronting, C: this.recoveredFronting, W: this.committed, peakFronting: this.peakFronting,
      activeHolderBackingIntegral: this.holderIntegral, activeHolderValue: this.holderStock,
      physicalPartitionValid,
      feeFreeRetainedOnchainBackingIntegral: physicalPartitionValid ? this.holderIntegral + this.lockedIntegral : null,
      peakOnchainBacking: this.peakOnchainBacking,
      unrecovered: [...this.sweepAt.entries()].flatMap(([height, values]) => values.map(v => ({ amount: v.value, recoveryHeight: height }))) };
  }

  /** Delivered volume on the chosen basis. The channel replay counts both directions; "both" matches it. */
  volume(basis: VolumeBasis = "both"): number {
    return basis === "out" ? this.volumeDelivered : this.volumeDelivered + this.volumeReceived;
  }

  /** 𝒟_V from forfeit locks only = ∫ W_S dt / volume, in blocks. */
  liquidityDuration(basis: VolumeBasis = "both"): number {
    const vol = this.volume(basis);
    return vol === 0 ? Infinity : this.lockedIntegralBlocks() / vol;
  }

  /** Holder conservation with zero initial holdings: V = I − O; refresh preserves V. */
  holderBoundHolds(holder: string): boolean {
    return this.holderValue(holder) === (this.inward.get(holder) ?? 0) - (this.outward.get(holder) ?? 0);
  }

  /** Pointwise fronting constraint W <= B; cumulative allocations may exceed B after recycling. */
  aggregateBoundHolds(): boolean {
    return this.committed <= this.capital;
  }
}

/**
 * How an operator sets inbound capacity toward an agent.
 *  - oracle: the realized running peak over the whole horizon, times (1 + margin), held for the horizon.
 *    Forecast error is zero by construction; this charges the channel only for idle capital.
 *  - trailing: the horizon is cut into re-provisioning intervals; capacity for interval i is (1 + margin)
 *    times the peak observed during interval i − 1 (interval 0 uses its own peak as a bootstrap), never
 *    below the balance carried in, and is held for that interval. Receipts that exceed remaining inbound
 *    capacity fail. This charges the channel for forecast error and for idle capital.
 */
export type ForecastRule = { kind: "oracle" } | { kind: "trailing"; intervalBlocks: number; roundBlocks: number };

/**
 * Directional channel model for the same demand. Returns 𝒟_C in blocks (locked capital-time over
 * delivered volume, both directions counted), the failure count, and the horizon-average locked capital.
 */
export function channelLiquidityDuration(
  perAgent: Map<string, Array<{ out: number; in: number }>>,
  horizonBlocks: number,
  margin: number,
  rule: ForecastRule = { kind: "oracle" },
): { duration: number; failures: number; locked: number } {
  let lockedIntegral = 0;
  let volume = 0;
  let failures = 0;
  for (const steps of perAgent.values()) {
    const peakOf = (from: number, to: number, start: number): number => {
      let running = start, peak = start;
      for (let i = from; i < to; i++) {
        const s = steps[i]!;
        // Match execution: receipt first, then an all-or-nothing spend. Netting a whole
        // round hides the inbound needed before its spend and invents partial spends.
        running += s.in;
        peak = Math.max(peak, running);
        if (s.out <= running) running -= s.out;
      }
      return peak;
    };
    let balance = 0;
    if (rule.kind === "oracle") {
      const forecast = Math.ceil(peakOf(0, steps.length, 0) * (1 + margin));
      lockedIntegral += forecast * horizonBlocks;
      for (const s of steps) {
        if (s.in) { if (s.in > forecast - balance) failures += 1; else { balance += s.in; volume += s.in; } }
        if (s.out) { if (s.out > balance) failures += 1; else { balance -= s.out; volume += s.out; } }
      }
    } else {
      const stepsPerInterval = Math.max(1, Math.round(rule.intervalBlocks / rule.roundBlocks));
      let prevPeak = -1;
      for (let from = 0; from < steps.length; from += stepsPerInterval) {
        const to = Math.min(steps.length, from + stepsPerInterval);
        if (prevPeak < 0) prevPeak = peakOf(from, to, 0); // bootstrap: interval 0 is observed, not forecast
        const forecast = Math.max(balance, Math.ceil(prevPeak * (1 + margin)));
        lockedIntegral += forecast * (to - from) * rule.roundBlocks;
        let running = balance, peak = balance;
        for (let i = from; i < to; i++) {
          const s = steps[i]!;
          if (s.in) { if (s.in > forecast - balance) failures += 1; else { balance += s.in; volume += s.in; peak = Math.max(peak, balance); } }
          if (s.out) { if (s.out > balance) failures += 1; else { balance -= s.out; volume += s.out; } }
          running = balance; peak = Math.max(peak, running);
        }
        prevPeak = peak;
      }
    }
  }
  return { duration: volume === 0 ? Infinity : lockedIntegral / volume, failures, locked: lockedIntegral / horizonBlocks };
}

/**
 * Multiparty channel (hyperedge) model for the same demand: the object that rebindable signatures
 * (BIP 448, LN-Symmetry) make practical. Agents are grouped `groupSize` to a channel with one hub member.
 * A channel's state is a balance per member summing to its capacity, so a receipt toward any agent draws
 * on the hub's balance in that channel, which is one stock for the group rather than one per agent; an
 * agent still spends only its own balance. The stock is forecast by the same rule as a two-party
 * channel's inbound, applied to the running total the group holds. A channel factory that reallocates
 * among two-party subchannels every round has the same bound. At groupSize = 1 this is
 * channelLiquidityDuration, operation for operation.
 */
export function hyperedgeLiquidityDuration(
  perAgent: Map<string, Array<{ out: number; in: number }>>,
  groupSize: number,
  horizonBlocks: number,
  margin: number,
  rule: ForecastRule = { kind: "oracle" },
): { duration: number; failures: number; locked: number } {
  if (!Number.isInteger(groupSize) || groupSize < 1) throw new Error("groupSize must be a positive integer");
  const agents = [...perAgent.values()];
  let lockedIntegral = 0;
  let volume = 0;
  let failures = 0;
  for (let g = 0; g < agents.length; g += groupSize) {
    const members = agents.slice(g, g + groupSize);
    const nSteps = members[0]!.length;
    // Peak of the total members hold, using the same receipt-first and all-or-nothing
    // spending order as play(). Include every intra-round peak.
    const peakOf = (from: number, to: number): number => {
      const running = new Array<number>(members.length).fill(0);
      let total = 0, peak = 0;
      for (let i = from; i < to; i++) {
        for (let m = 0; m < members.length; m++) {
          const s = members[m]![i]!;
          running[m] = running[m]! + s.in;
          total += s.in;
          peak = Math.max(peak, total);
          if (s.out <= running[m]!) { running[m] = running[m]! - s.out; total -= s.out; }
        }
        peak = Math.max(peak, total);
      }
      return peak;
    };
    const balance = new Array<number>(members.length).fill(0);
    let held = 0;
    const play = (i: number, forecast: number): number => {
      let peak = held;
      for (let m = 0; m < members.length; m++) {
        const s = members[m]![i]!;
        if (s.in) { if (s.in > forecast - held) failures += 1; else { balance[m] = balance[m]! + s.in; held += s.in; volume += s.in; peak = Math.max(peak, held); } }
        if (s.out) { if (s.out > balance[m]!) failures += 1; else { balance[m] = balance[m]! - s.out; held -= s.out; volume += s.out; } }
      }
      return peak;
    };
    if (rule.kind === "oracle") {
      const forecast = Math.ceil(peakOf(0, nSteps) * (1 + margin));
      lockedIntegral += forecast * horizonBlocks;
      for (let i = 0; i < nSteps; i++) play(i, forecast);
    } else {
      const stepsPerInterval = Math.max(1, Math.round(rule.intervalBlocks / rule.roundBlocks));
      let prevPeak = -1;
      for (let from = 0; from < nSteps; from += stepsPerInterval) {
        const to = Math.min(nSteps, from + stepsPerInterval);
        if (prevPeak < 0) prevPeak = peakOf(from, to); // bootstrap: interval 0 is observed, not forecast
        const forecast = Math.max(held, Math.ceil(prevPeak * (1 + margin)));
        lockedIntegral += forecast * (to - from) * rule.roundBlocks;
        let peak = held;
        for (let i = from; i < to; i++) peak = Math.max(peak, play(i, forecast));
        prevPeak = peak;
      }
    }
  }
  return { duration: volume === 0 ? Infinity : lockedIntegral / volume, failures, locked: lockedIntegral / horizonBlocks };
}

/**
 * The server-tier directional term: the channel model applied to the server's aggregate Lightning flow.
 * This is a post hoc sizing diagnostic on the unconstrained server's delivered aggregate flow.
 * A failed event here does not feed back into ArkServer, its delivery denominator, or its forfeit locks.
 * A nonzero failure count therefore means the resulting duration is not a feasible end-to-end replay.
 * The receipt-first order within an aggregate round also includes a conservative transient peak.
 */
export function serverTierTerm(S: ArkServer, horizonBlocks: number, margin: number, rule: ForecastRule): { lockedIntegral: number; failures: number } {
  const one = new Map([["server", S.aggregateSteps.map((s) => ({ in: s.in, out: s.out }))]]);
  const r = channelLiquidityDuration(one, horizonBlocks, margin, rule);
  return { lockedIntegral: r.locked * horizonBlocks, failures: r.failures };
}

/** Demand-grid cell for §7 item 2. burstiness = per-agent envelope-to-volume ratio, set through burst sizes and rates. */
export interface CornerParams {
  agents: number;
  /** blocks of horizon as a multiple of the VTXO lifetime */
  horizonLifetimes: number;
  /** expected net inflow per agent per round, in sat; 0 is balanced demand, > 0 accumulates, < 0 drains */
  driftPerRound: number;
  /** burst sizes and the inflow rate; the outflow rate is set so that E[out] = E[in] − drift */
  burst: { vIn: number; vOut: number; pIn: number };
  /** steady bidirectional flow instead of bursts (few-steady corner) */
  steady?: { base: number; jitter: number };
  margin: number;
  forecast: ForecastRule;
  volume: VolumeBasis;
  /** charge the server for inbound on its own channels (§3.4) */
  serverTier: boolean;
  seed: number;
  lifetime?: number;
  roundBlocks?: number;
  /** lock rule for Lightning spends; see ServerParams.spendLock */
  spendLock?: "expiry" | "round";
  changeBacking?: "fresh" | "retained";
  recoveryDelayBlocks?: number;
  /** multiparty-channel sizes to evaluate on the same demand: agents per hyperedge, hub not counted */
  hyperedgeSizes?: number[];
}

export interface CornerResult {
  dC: number; dV: number; dVForfeitOnly: number; ratio: number;
  /** attempted events (nonzero receipts plus nonzero spends) over the horizon; the denominator for the failure counts */
  events: number;
  chFailures: number; arkFailures: number; serverFailures: number;
  chLocked: number; serverLocked: number; finalHolderBalance: number;
  /** one entry per requested hyperedge size: 𝒟_H in blocks, failed events, horizon-average locked capital */
  hyperedge: Array<{ k: number; dH: number; failures: number; locked: number }>;
  accounting?: ReturnType<ArkServer["accountingDiagnostics"]> & { offeredVolume: number; deliveredVolume: number };
}

export function runCorner(p: CornerParams): CornerResult {
  const r = rng(p.seed);
  const lifetime = p.lifetime ?? 4032;
  const roundBlocks = p.roundBlocks ?? 6;
  const horizon = p.horizonLifetimes * lifetime;
  const steps = Math.floor(horizon / roundBlocks);
  const perAgent = new Map<string, Array<{ out: number; in: number }>>();
  for (let a = 0; a < p.agents; a++) perAgent.set(`a${a}`, []);
  const S = new ArkServer(Number.MAX_SAFE_INTEGER / 4, { lifetimeBlocks: lifetime, roundInterval: roundBlocks, refreshLead: 288, spendLock: p.spendLock ?? "expiry",
    changeBacking: p.changeBacking, recoveryDelayBlocks: p.recoveryDelayBlocks });
  const pOut = p.steady ? 1 : Math.max(0, Math.min(1, (p.burst.pIn * p.burst.vIn - p.driftPerRound) / p.burst.vOut));
  let arkFailures = 0;
  let events = 0;
  let offeredVolume = 0;
  for (let t = 0; t < steps; t++) {
    for (const [name, arr] of perAgent) {
      let out = 0, inn = 0;
      if (p.steady) {
        const d = p.driftPerRound;
        out = p.steady.base + Math.floor(r() * p.steady.jitter); inn = p.steady.base + d + Math.floor(r() * p.steady.jitter);
      } else {
        if (r() < p.burst.pIn) inn = p.burst.vIn;
        if (r() < pOut) out = p.burst.vOut;
      }
      arr.push({ out, in: inn });
      offeredVolume += out + (p.volume === "both" ? inn : 0);
      if (inn) { events += 1; S.receive(name, inn); }
      if (out) { events += 1; if (S.holderValue(name) >= out) S.spendLightning(name, out); else arkFailures += 1; }
    }
    S.advance(roundBlocks);
  }
  const ch = channelLiquidityDuration(perAgent, horizon, p.margin, p.forecast);
  const hyperedge = (p.hyperedgeSizes ?? []).map((k) => {
    const h = hyperedgeLiquidityDuration(perAgent, k, horizon, p.margin, p.forecast);
    return { k, dH: h.duration, failures: h.failures, locked: h.locked };
  });
  const vol = S.volume(p.volume);
  const forfeitIntegral = S.lockedIntegralBlocks();
  const st = p.serverTier ? serverTierTerm(S, horizon, p.margin, p.forecast) : { lockedIntegral: 0, failures: 0 };
  const dV = vol === 0 ? Infinity : (forfeitIntegral + st.lockedIntegral) / vol;
  let finalHolderBalance = 0;
  for (const name of perAgent.keys()) finalHolderBalance += S.holderValue(name);
  return {
    dC: ch.duration, dV, dVForfeitOnly: vol === 0 ? Infinity : forfeitIntegral / vol, ratio: ch.duration / dV,
    events, chFailures: ch.failures, arkFailures, serverFailures: st.failures,
    chLocked: ch.locked, serverLocked: st.lockedIntegral / horizon, finalHolderBalance, hyperedge,
    ...(p.changeBacking === "retained" ? { accounting: { ...S.accountingDiagnostics(), offeredVolume, deliveredVolume: vol } } : {}),
  };
}

/** Deterministic LCG. */
export function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; };
}
