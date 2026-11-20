// Proof-carrying registry with claim-once nullifiers keyed by the object's authority key, under an
// epoch rule. Witnesses Proposition S3 on finite cases.
//
// The nullifier stops a second claim on the same object id. It does not stop a claim on a successor id:
// spend ρ to a fresh ρ′ under a key you control (a self-transfer, or under Ark every refresh) and the
// nullifier is fresh. Zcash's nullifier argument prevents double-spend; spending is what it permits. So
// claims are epoched: a claim is accepted only against the settled set as frozen at epoch start, and at
// epoch close a claim whose object is no longer settled — spent, without an attested successor — is
// revoked. One unit of capital therefore counts once per epoch whatever its id history. A refresh, which
// under Ark is a spend the server co-signs and can vouch for, is recorded as a successor link by the set
// maintainer so that an honest holder's refresh mid-epoch does not revoke its claim; a transfer to another
// key is not a successor and does revoke.
//
// The proof system is simulated: `verifyCapClaim` checks the single-authority model below. A real
// deployment must bind its proof, canonical authority, chain state and reward transfer to the same
// statement. Epoch settlement here produces an in-memory receipt; it does not transfer funds or
// persist the receipt across a process restart.

import { createHmac, createHash } from "node:crypto";

export interface SettledObject { id: string; value: number; authorityKey: string; }

export interface Statement { cm: string; v: number; nf: string; root: string; }

export interface Witness { s: string; k: string; obj: SettledObject; }

export const commit = (s: string): string => createHash("sha256").update(`cm|${s}`).digest("hex");
export const prf = (k: string, id: string): string => createHmac("sha256", k).update(id).digest("hex");

const validAmount = (value: number): boolean => Number.isSafeInteger(value) && value >= 0;
const MAX_AMOUNT = BigInt(Number.MAX_SAFE_INTEGER);

function requireAmount(value: number, name: string): void {
  if (!validAmount(value)) throw new Error(`invalid ${name}: expected a nonnegative safe integer`);
}

export class SettledSet {
  private readonly objs = new Map<string, SettledObject>();
  private readonly usedIds = new Set<string>();
  /** successor links the set maintainer attests: old id → new id (a refresh, same holder key). */
  private readonly successor = new Map<string, string>();
  private requireFreshId(id: string): void {
    if (this.usedIds.has(id)) throw new Error("duplicate settled object id");
  }
  add(o: SettledObject): void {
    this.requireFreshId(o.id);
    requireAmount(o.value, "settled value");
    this.objs.set(o.id, { ...o });
    this.usedIds.add(o.id);
  }
  remove(id: string): void { this.objs.delete(id); }
  has(id: string): boolean { return this.objs.has(id); }
  get(id: string): SettledObject | undefined {
    const o = this.objs.get(id);
    return o ? { ...o } : undefined;
  }
  /** Spend `id` into a fresh object under the same authority and record the link (a refresh). */
  refresh(id: string, newId: string): SettledObject {
    const o = this.objs.get(id);
    if (!o) throw new Error("not settled");
    this.requireFreshId(newId);
    this.objs.delete(id);
    const n: SettledObject = { id: newId, value: o.value, authorityKey: o.authorityKey };
    this.objs.set(newId, n);
    this.usedIds.add(newId);
    this.successor.set(id, newId);
    return { ...n };
  }
  /** Spend `id` into a fresh object under a different authority: a transfer, no link. */
  transfer(id: string, newId: string, newKey: string): SettledObject {
    const o = this.objs.get(id);
    if (!o) throw new Error("not settled");
    this.requireFreshId(newId);
    this.objs.delete(id);
    const n: SettledObject = { id: newId, value: o.value, authorityKey: newKey };
    this.objs.set(newId, n);
    this.usedIds.add(newId);
    return { ...n };
  }
  /** Follow attested successor links from `id`; returns the live descendant or undefined if spent without one. */
  descendant(id: string): SettledObject | undefined {
    let cur = id;
    const seen = new Set<string>();
    while (!this.objs.has(cur)) {
      const nxt = this.successor.get(cur);
      if (!nxt || seen.has(nxt)) return undefined;
      seen.add(nxt);
      cur = nxt;
    }
    return this.get(cur);
  }
  /** Deterministic digest of typed, unambiguously encoded records.
   * This remains a stand-in for a Merkle commitment, without inclusion proofs.
   */
  root(): string {
    const records = [...this.objs.values()]
      .sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
      .map((o) => [o.id, o.value, o.authorityKey]);
    return createHash("sha256").update(JSON.stringify(records)).digest("hex");
  }
  snapshot(): SettledSet {
    const c = new SettledSet();
    for (const o of this.objs.values()) c.add({ ...o });
    for (const id of this.usedIds) c.usedIds.add(id);
    for (const [oldId, newId] of this.successor) c.successor.set(oldId, newId);
    return c;
  }
}

/** Simulated verifier for R_cap against a fixed root: membership, authority, value bound, nullifier derivation. */
export function verifyCapClaim(frozen: SettledSet, st: Statement, w: Witness): boolean {
  if (!validAmount(st.v)) return false;
  if (st.root !== frozen.root()) return false;
  if (!frozen.has(w.obj.id)) return false;
  const live = frozen.get(w.obj.id)!;
  if (live.value !== w.obj.value || live.authorityKey !== w.obj.authorityKey) return false;
  if (w.k !== live.authorityKey) return false;          // k_ρ satisfies A_ρ (single-signer model)
  if (live.value < st.v) return false;
  if (commit(w.s) !== st.cm) return false;
  return prf(w.k, live.id) === st.nf;                     // nf keyed by the object's authority, not the claimant
}

interface Claim extends Statement { objId: string; }

export interface SettledClaim {
  readonly cm: string;
  readonly nf: string;
  readonly objId: string;
  readonly value: number;
  readonly descendantId: string | null;
  readonly status: "eligible" | "revoked";
}

export interface RewardAllocation {
  readonly cm: string;
  readonly amount: number;
}

/** A canonical, deeply frozen result. Callers must persist it and bind any actual reward transfer. */
export interface EpochSettlement {
  readonly version: "spiral-registry-epoch-v1";
  readonly epoch: number;
  readonly rootAtOpen: string;
  readonly rootAtClose: string;
  readonly totalWeight: number;
  readonly pool: number;
  readonly allocated: number;
  readonly unallocated: number;
  readonly claims: readonly SettledClaim[];
  readonly payouts: readonly RewardAllocation[];
  readonly commitment: string;
}

/** Bind the complete settlement using ordered typed records, including revoked claims and remainders. */
export function settlementCommitment(receipt: Omit<EpochSettlement, "commitment">): string {
  return createHash("sha256").update(JSON.stringify([
    receipt.version, receipt.epoch, receipt.rootAtOpen, receipt.rootAtClose,
    receipt.totalWeight, receipt.pool, receipt.allocated, receipt.unallocated,
    receipt.claims.map((c) => [c.cm, c.nf, c.objId, c.value, c.descendantId, c.status]),
    receipt.payouts.map((p) => [p.cm, p.amount]),
  ])).digest("hex");
}

function allocateClaims(claims: readonly Claim[], pool: number): Map<string, number> {
  requireAmount(pool, "reward pool");
  const total = claims.reduce((sum, c) => sum + BigInt(c.v), 0n);
  const byCommitment = new Map<string, bigint>();
  for (const c of claims) {
    // Keep floor-per-object allocation. Any remainder remains explicitly unallocated.
    const amount = total === 0n ? 0n : (BigInt(pool) * BigInt(c.v)) / total;
    byCommitment.set(c.cm, (byCommitment.get(c.cm) ?? 0n) + amount);
  }
  return new Map([...byCommitment].map(([cm, amount]) => [cm, Number(amount)]));
}

export class Registry {
  private readonly nullifiers = new Set<string>();
  private readonly claims: Claim[] = [];
  private frozen: SettledSet;
  private currentEpoch = 0;
  private latestSettlement: EpochSettlement | undefined;

  /** The registry opens on a frozen view of the settled set; claims in this epoch are against that root. */
  constructor(setAtEpochStart: SettledSet) {
    this.frozen = setAtEpochStart.snapshot();
  }

  get root(): string { return this.frozen.root(); }
  get epoch(): number { return this.currentEpoch; }
  get lastSettlement(): EpochSettlement | undefined { return this.latestSettlement; }

  submit(st: Statement, w: Witness): "accepted" | "invalid" | "duplicate" {
    if (!verifyCapClaim(this.frozen, st, w)) return "invalid";
    if (this.nullifiers.has(st.nf)) return "duplicate";
    // This number-based public model bounds aggregate claimed weight as well as each input.
    // BigInt prevents rounding while checking the boundary; rejection consumes no nullifier.
    if (BigInt(this.totalWeight()) + BigInt(st.v) > MAX_AMOUNT) return "invalid";
    this.nullifiers.add(st.nf);
    this.claims.push({ ...st, objId: w.obj.id });
    return "accepted";
  }

  /**
   * Validate and allocate against one live snapshot, commit an immutable receipt, then advance.
   * All potentially failing work precedes state mutation. The operation is synchronous and in-memory;
   * durable storage and idempotent on-chain payout execution belong to the integration layer.
   */
  settleEpoch(liveSet: SettledSet, pool: number): EpochSettlement {
    requireAmount(pool, "reward pool");
    if (this.currentEpoch === Number.MAX_SAFE_INTEGER) throw new Error("epoch counter exhausted");
    const next = liveSet.snapshot();
    const eligible: Claim[] = [];
    const decisions: SettledClaim[] = [];
    for (const c of [...this.claims].sort((a, b) => a.nf < b.nf ? -1 : a.nf > b.nf ? 1 : 0)) {
      const d = next.descendant(c.objId);
      const original = this.frozen.get(c.objId)!;
      const survives = !!d && d.authorityKey === original.authorityKey && d.value >= c.v;
      if (survives) eligible.push(c);
      decisions.push(Object.freeze({
        cm: c.cm, nf: c.nf, objId: c.objId, value: c.v,
        descendantId: d?.id ?? null, status: survives ? "eligible" : "revoked",
      }));
    }
    const payouts = [...allocateClaims(eligible, pool)]
      .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
      .map(([cm, amount]) => Object.freeze({ cm, amount }));
    const allocated = Number(payouts.reduce((sum, p) => sum + BigInt(p.amount), 0n));
    const contents: Omit<EpochSettlement, "commitment"> = {
      version: "spiral-registry-epoch-v1",
      epoch: this.currentEpoch,
      rootAtOpen: this.root,
      rootAtClose: next.root(),
      totalWeight: Number(eligible.reduce((sum, c) => sum + BigInt(c.v), 0n)),
      pool, allocated, unallocated: pool - allocated,
      claims: Object.freeze(decisions), payouts: Object.freeze(payouts),
    };
    const receipt: EpochSettlement = Object.freeze({
      ...contents, commitment: settlementCommitment(contents),
    });
    this.latestSettlement = receipt;
    this.frozen = next;
    this.nullifiers.clear();
    this.claims.length = 0;
    this.currentEpoch += 1;
    return receipt;
  }

  /** @deprecated Weight-only compatibility operation; use settleEpoch(liveSet, pool) for rewards. */
  closeEpoch(liveSet: SettledSet): number {
    return this.settleEpoch(liveSet, 0).totalWeight;
  }

  /** Total weight the registry attributes to a given nullifier (i.e. to the object behind it). */
  weightFor(nf: string): number {
    return Number(this.claims.filter((c) => c.nf === nf).reduce((a, c) => a + BigInt(c.v), 0n));
  }

  totalWeight(): number {
    return Number(this.claims.reduce((a, c) => a + BigInt(c.v), 0n));
  }

  /** Provisional arithmetic only; this does not check end-of-epoch liveness or authorize a payout. */
  previewAllocation(pool: number): Map<string, number> {
    return allocateClaims(this.claims, pool);
  }

  /** @deprecated Provisional compatibility alias. Settle an epoch before using any reward result. */
  allocate(pool: number): Map<string, number> {
    requireAmount(pool, "reward pool");
    if (this.claims.length === 0) throw new Error("no active claims: use settleEpoch(liveSet, pool) for committed payouts");
    return this.previewAllocation(pool);
  }
}
