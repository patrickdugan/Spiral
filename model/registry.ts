// Proof-carrying registry with claim-once nullifiers keyed by the object's authority key.
// Witnesses Proposition S3 on finite cases. The proof system is NOT implemented: `verify` checks a
// simulated attestation with the interface a verifier would expose (statement + witness → boolean),
// and the tests say so. Substituting a real SNARK changes nothing in the registry logic.

import { createHmac, createHash } from "node:crypto";

export interface SettledObject { id: string; value: number; authorityKey: string; }

export interface Statement { cm: string; v: number; nf: string; root: string; }

export interface Witness { s: string; k: string; obj: SettledObject; }

export const commit = (s: string): string => createHash("sha256").update(`cm|${s}`).digest("hex");
export const prf = (k: string, id: string): string => createHmac("sha256", k).update(id).digest("hex");

export class SettledSet {
  private readonly objs = new Map<string, SettledObject>();
  add(o: SettledObject): void { this.objs.set(o.id, o); }
  has(id: string): boolean { return this.objs.has(id); }
  get(id: string): SettledObject | undefined { return this.objs.get(id); }
  /** Deterministic commitment to the set contents; stands in for a Merkle root. */
  root(): string {
    const h = createHash("sha256");
    for (const id of [...this.objs.keys()].sort()) {
      const o = this.objs.get(id)!;
      h.update(`${id}|${o.value}|${o.authorityKey}\n`);
    }
    return h.digest("hex");
  }
}

/** Simulated verifier for R_cap: membership, authority, value bound, nullifier derivation. */
export function verifyCapClaim(set: SettledSet, st: Statement, w: Witness): boolean {
  if (st.root !== set.root()) return false;
  if (!set.has(w.obj.id)) return false;
  const live = set.get(w.obj.id)!;
  if (live.value !== w.obj.value || live.authorityKey !== w.obj.authorityKey) return false;
  if (w.k !== live.authorityKey) return false;          // k_ρ satisfies A_ρ (single-signer model)
  if (live.value < st.v) return false;
  if (commit(w.s) !== st.cm) return false;
  return prf(w.k, live.id) === st.nf;                     // nf keyed by the object's authority, not the claimant
}

export class Registry {
  private readonly nullifiers = new Set<string>();
  readonly claims: Statement[] = [];

  submit(set: SettledSet, st: Statement, w: Witness): "accepted" | "invalid" | "duplicate" {
    if (!verifyCapClaim(set, st, w)) return "invalid";
    if (this.nullifiers.has(st.nf)) return "duplicate";
    this.nullifiers.add(st.nf);
    this.claims.push({ ...st });
    return "accepted";
  }

  /** Total weight the registry attributes to a given nullifier (i.e. to the object behind it). */
  weightFor(nf: string): number {
    return this.claims.filter((c) => c.nf === nf).reduce((a, c) => a + c.v, 0);
  }

  totalWeight(): number {
    return this.claims.reduce((a, c) => a + c.v, 0);
  }

  /** Fixed-pool reward allocation, integer, remainder to no one (L4 without the rounding defect). */
  allocate(pool: number): Map<string, number> {
    const total = this.totalWeight();
    const out = new Map<string, number>();
    for (const c of this.claims) out.set(c.cm, (out.get(c.cm) ?? 0) + Math.floor((pool * c.v) / total));
    return out;
  }
}
