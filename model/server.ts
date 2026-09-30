// Server-mediated object (Ark-style VTXO) liquidity model and the directional channel comparison.
// Witnesses Proposition S2 and computes the liquidity-duration ratio of §3.3 on two demand corners.
//
// Lock rule (from the implementer's published description of the three liquidity operations and
// forfeit sweeping): whenever a VTXO is forfeited (spent over Lightning, refreshed, or offboarded), the
// server fronts equivalent value now and recovers it only when that output's absolute expiry passes.
// Boarding and receiving are treated as liquidity-neutral for the server in this aggregate model.
// Parameters default to published values (28 d ≈ 4032 blocks, hourly rounds ≈ 6 blocks) and are inputs.

export interface ServerParams {
  lifetimeBlocks: number;
  roundInterval: number;
  refreshLead: number;
}

export const DEFAULT_SERVER: ServerParams = { lifetimeBlocks: 4032, roundInterval: 6, refreshLead: 288 };

interface Vtxo {
  id: string;
  holder: string;
  value: number;
  expiresAt: number;
  forfeited: boolean;
}

export class ArkServer {
  readonly params: ServerParams;
  readonly capital: number;    // B_S
  committed = 0;               // W_S: forfeited-but-unswept value the server has fronted
  height = 0;
  volumeDelivered = 0;
  private lockedIntegral = 0;  // ∫ W_S dt (value·blocks)
  private lastHeight = 0;
  private nextId = 0;
  private readonly vtxos = new Map<string, Vtxo>();
  readonly outward = new Map<string, number>();
  readonly inward = new Map<string, number>();
  readonly allocated = new Map<string, number>();

  constructor(capital: number, params: ServerParams = DEFAULT_SERVER) {
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
    // W_S is piecewise constant between events; integrate over the interval before applying sweeps.
    this.lockedIntegral += this.committed * blocks;
    this.height += blocks;
    this.lastHeight = this.height;
    for (const [id, v] of this.vtxos) {
      if (v.forfeited && this.height >= v.expiresAt) {
        this.committed -= v.value; // sweep: fronted value recovered
        this.vtxos.delete(id);
      }
    }
    // Holders refresh outputs approaching expiry; a refresh is a forfeit plus a server-funded reissue.
    for (const v of [...this.vtxos.values()]) {
      if (!v.forfeited && v.expiresAt - this.height <= this.params.refreshLead) this.refresh(v.id);
    }
  }

  private newVtxo(holder: string, value: number): Vtxo {
    const v: Vtxo = { id: `v${this.nextId++}`, holder, value, expiresAt: this.height + this.params.lifetimeBlocks, forfeited: false };
    this.vtxos.set(v.id, v);
    return v;
  }

  /** Forfeit an output: the server fronts its value now and sweeps it at the output's expiry. */
  private forfeit(v: Vtxo): boolean {
    if (v.value > this.uncommitted) return false;
    v.forfeited = true;
    this.committed += v.value;
    return true;
  }

  /** Board or receive: a holder gains an output without drawing on server liquidity in this aggregate model. */
  receive(holder: string, value: number): string {
    const v = this.newVtxo(holder, value);
    ArkServer.bump(this.inward, holder, value);
    ArkServer.bump(this.allocated, holder, value);
    return v.id;
  }

  refresh(id: string): boolean {
    const old = this.vtxos.get(id);
    if (!old || old.forfeited) return false;
    if (!this.forfeit(old)) return false;
    this.newVtxo(old.holder, old.value);
    return true;
  }

  holderValue(holder: string): number {
    let s = 0;
    for (const v of this.vtxos.values()) if (v.holder === holder && !v.forfeited) s += v.value;
    return s;
  }

  /** Spend outward over Lightning. The server fronts the HTLC from uncommitted capital (S2 aggregate constraint). */
  spendLightning(holder: string, amount: number): boolean {
    if (!Number.isInteger(amount) || amount <= 0) throw new Error("amount must be a positive integer");
    if (this.holderValue(holder) < amount) return false;
    const inputs: Vtxo[] = [];
    let total = 0;
    for (const v of this.vtxos.values()) {
      if (total >= amount) break;
      if (v.holder === holder && !v.forfeited) { inputs.push(v); total += v.value; }
    }
    if (total > this.uncommitted) return false; // all-or-nothing check before any mutation
    for (const v of inputs) this.forfeit(v);
    const change = total - amount;
    if (change > 0) this.newVtxo(holder, change); // reissued from the fronted value
    ArkServer.bump(this.outward, holder, amount);
    ArkServer.bump(this.allocated, holder, amount); // K^S_A: the server allocated at spend time
    this.volumeDelivered += amount;
    return true;
  }

  /** 𝒟_V = ∫ W_S dt / volume delivered, in blocks. */
  liquidityDuration(): number {
    this.accrue();
    return this.volumeDelivered === 0 ? Infinity : this.lockedIntegral / this.volumeDelivered;
  }

  /** S2, first inequality, per holder: O − I ≤ V(0) + K with V(0)=0. */
  holderBoundHolds(holder: string): boolean {
    return (this.outward.get(holder) ?? 0) - (this.inward.get(holder) ?? 0) <= (this.allocated.get(holder) ?? 0);
  }

  /** S2, second inequality: what the server has allocated in fronting never exceeds capital. */
  aggregateBoundHolds(): boolean {
    return this.committed <= this.capital;
  }
}

/**
 * Directional channel model for the same demand. An operator (LSP) pre-funds inbound capacity toward
 * each agent to a forecast f̂_a = (1 + margin) × the agent's realized peak held balance (running maximum
 * of receipts minus spends), holds that capital for the whole horizon, and the replay fails a receipt
 * that would exceed remaining inbound capacity or a spend that exceeds the agent's balance. Returns
 * 𝒟_C in blocks, the failure count, and the locked capital.
 */
export function channelLiquidityDuration(
  perAgent: Map<string, Array<{ out: number; in: number }>>,
  horizonBlocks: number,
  margin: number,
): { duration: number; failures: number; locked: number } {
  let locked = 0;
  let volume = 0;
  let failures = 0;
  for (const steps of perAgent.values()) {
    let running = 0;
    let peak = 0;
    for (const s of steps) { running = Math.max(0, running + s.in - s.out); peak = Math.max(peak, running); }
    const forecast = Math.ceil(peak * (1 + margin));
    locked += forecast;
    let balance = 0;
    for (const s of steps) {
      if (s.in) { if (s.in > forecast - balance) failures += 1; else { balance += s.in; volume += s.in; } }
      if (s.out) { if (s.out > balance) failures += 1; else { balance -= s.out; volume += s.out; } }
    }
  }
  return { duration: volume === 0 ? Infinity : (locked * horizonBlocks) / volume, failures, locked };
}

/** Deterministic LCG. */
export function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; };
}
