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
// The proof system is NOT implemented: `verify` checks a simulated attestation with the interface a
// verifier would expose (statement + witness → boolean), and the tests say so. Substituting a real SNARK
// changes nothing in the registry logic.

import { createHmac, createHash } from "node:crypto";

export interface SettledObject { id: string; value: number; authorityKey: string; }

export interface Statement { cm: string; v: number; nf: string; root: string; }

export interface Witness { s: string; k: string; obj: SettledObject; }

export const commit = (s: string): string => createHash("sha256").update(`cm|${s}`).digest("hex");
export const prf = (k: string, id: string): string => createHmac("sha256", k).update(id).digest("hex");

export class SettledSet {
  private readonly objs = new Map<string, SettledObject>();
  /** successor links the set maintainer attests: old id → new id (a refresh, same holder key). */
  private readonly successor = new Map<string, string>();
  add(o: SettledObject): void { this.objs.set(o.id, o); }
  remove(id: string): void { this.objs.delete(id); }
  has(id: string): boolean { return this.objs.has(id); }
  get(id: string): SettledObject | undefined { return this.objs.get(id); }
  /** Spend `id` into a fresh object under the same authority and record the link (a refresh). */
  refresh(id: string, newId: string): SettledObject {
    const o = this.objs.get(id);
    if (!o) throw new Error("not settled");
    this.objs.delete(id);
    const n: SettledObject = { id: newId, value: o.value, authorityKey: o.authorityKey };
    this.objs.set(newId, n);
    this.successor.set(id, newId);
    return n;
  }
  /** Spend `id` into a fresh object under a different authority: a transfer, no link. */
  transfer(id: string, newId: string, newKey: string): SettledObject {
    const o = this.objs.get(id);
    if (!o) throw new Error("not settled");
    this.objs.delete(id);
    const n: SettledObject = { id: newId, value: o.value, authorityKey: newKey };
    this.objs.set(newId, n);
    return n;
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
    return this.objs.get(cur);
  }
  /** Deterministic commitment to the set contents; stands in for a Merkle root. */
  root(): string {
    const h = createHash("sha256");
    for (const id of [...this.objs.keys()].sort()) {
      const o = this.objs.get(id)!;
      h.update(`${id}|${o.value}|${o.authorityKey}\n`);
    }
    return h.digest("hex");
  }
  snapshot(): SettledSet {
    const c = new SettledSet();
    for (const o of this.objs.values()) c.add({ ...o });
    return c;
  }
}

/** Simulated verifier for R_cap against a fixed root: membership, authority, value bound, nullifier derivation. */
export function verifyCapClaim(frozen: SettledSet, st: Statement, w: Witness): boolean {
  if (st.root !== frozen.root()) return false;
  if (!frozen.has(w.obj.id)) return false;
  const live = frozen.get(w.obj.id)!;
  if (live.value !== w.obj.value || live.authorityKey !== w.obj.authorityKey) return false;
  if (w.k !== live.authorityKey) return false;          // k_ρ satisfies A_ρ (single-signer model)
  if (live.value < st.v) return false;
  if (commit(w.s) !== st.cm) return false;
  return prf(w.k, live.id) === st.nf;                     // nf keyed by the object's authority, not the claimant
}

interface Claim extends Statement { objId: string; revoked: boolean; }

export class Registry {
  private readonly nullifiers = new Set<string>();
  private readonly claims: Claim[] = [];
  private frozen: SettledSet;
  epoch = 0;

  /** The registry opens on a frozen view of the settled set; claims in this epoch are against that root. */
  constructor(setAtEpochStart: SettledSet) {
    this.frozen = setAtEpochStart.snapshot();
  }

  get root(): string { return this.frozen.root(); }

  submit(st: Statement, w: Witness): "accepted" | "invalid" | "duplicate" {
    if (!verifyCapClaim(this.frozen, st, w)) return "invalid";
    if (this.nullifiers.has(st.nf)) return "duplicate";
    this.nullifiers.add(st.nf);
    this.claims.push({ ...st, objId: w.obj.id, revoked: false });
    return "accepted";
  }

  /**
   * Close the epoch against the live set: a claim survives iff its object, or an attested successor of it
   * under the same key, is still settled. Then re-freeze on the live set and clear nullifiers, so next
   * epoch's claims are against the new ids. Returns the surviving claims' weight.
   */
  closeEpoch(liveSet: SettledSet): number {
    for (const c of this.claims) {
      if (c.revoked) continue;
      const d = liveSet.descendant(c.objId);
      const original = this.frozen.get(c.objId)!;
      if (!d || d.authorityKey !== original.authorityKey || d.value < c.v) c.revoked = true;
    }
    const w = this.totalWeight();
    this.frozen = liveSet.snapshot();
    this.nullifiers.clear();
    this.claims.length = 0;
    this.epoch += 1;
    return w;
  }

  /** Total weight the registry attributes to a given nullifier (i.e. to the object behind it). */
  weightFor(nf: string): number {
    return this.claims.filter((c) => c.nf === nf && !c.revoked).reduce((a, c) => a + c.v, 0);
  }

  totalWeight(): number {
    return this.claims.filter((c) => !c.revoked).reduce((a, c) => a + c.v, 0);
  }

  /** Fixed-pool reward allocation over surviving claims, integer, remainder to no one (L4 without the rounding defect). */
  allocate(pool: number): Map<string, number> {
    const total = this.totalWeight();
    const out = new Map<string, number>();
    for (const c of this.claims) {
      if (c.revoked) continue;
      out.set(c.cm, (out.get(c.cm) ?? 0) + Math.floor((pool * c.v) / total));
    }
    return out;
  }
}
