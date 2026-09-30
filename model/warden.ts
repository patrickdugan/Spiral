// Warden statistics of §6.3–6.4 on synthetic fixtures.
// The naive network-wide gross-to-net ratio is computed alongside the internal-volume ratio over a
// claim's attesting set, so that the failure mode the earlier hive baseline reported (naive churn does
// not discriminate) is reproduced rather than assumed away. These are fixtures, not measurements.

import { rng } from "./server.ts";

export interface Flow { payer: string; payee: string; amount: number; }

/** Naive statistic: gross volume over the sum of absolute net positions. Undefined (Infinity) when everything nets. */
export function naiveGrossToNet(trace: Flow[]): number {
  const net = new Map<string, number>();
  let gross = 0;
  for (const f of trace) {
    gross += f.amount;
    net.set(f.payer, (net.get(f.payer) ?? 0) - f.amount);
    net.set(f.payee, (net.get(f.payee) ?? 0) + f.amount);
  }
  let sumAbs = 0;
  for (const v of net.values()) sumAbs += Math.abs(v);
  return sumAbs === 0 ? Infinity : gross / sumAbs;
}

/**
 * Restricted statistic over the claim's set S = attesters ∪ {claimant}: the share of all volume touching S
 * whose both endpoints lie inside S. Manufactured demand circulates inside S; a merchant's customers mostly
 * transact outside it. Computable by any warden that sees the flows touching S.
 */
export function internalVolumeRatio(trace: Flow[], claimant: string, attesters: Set<string>): number {
  const inside = new Set(attesters); inside.add(claimant);
  let touching = 0;
  let internal = 0;
  for (const f of trace) {
    const a = inside.has(f.payer);
    const b = inside.has(f.payee);
    if (!a && !b) continue;
    touching += f.amount;
    if (a && b) internal += f.amount;
  }
  return touching === 0 ? 0 : internal / touching;
}

/** Counterparties who paid the claimant in the trace: the attesting set a service claim would carry. */
export function attestersOf(trace: Flow[], claimant: string): Set<string> {
  const s = new Set<string>();
  for (const f of trace) if (f.payee === claimant) s.add(f.payer);
  return s;
}

/** Benign multilateral trade: every agent pays random others; nets out strongly by construction. */
export function benignTrace(agents: string[], steps: number, seed = 7): Flow[] {
  const r = rng(seed);
  const out: Flow[] = [];
  for (let i = 0; i < steps; i++) {
    const a = agents[Math.floor(r() * agents.length)]!;
    let b = agents[Math.floor(r() * agents.length)]!;
    while (b === a) b = agents[Math.floor(r() * agents.length)]!;
    out.push({ payer: a, payee: b, amount: 100 });
  }
  return out;
}

/** Coalition fixture: a cyclic relay of k members, embedded in benign background traffic. */
export function coalitionTrace(agents: string[], coalition: string[], steps: number, seed = 11): Flow[] {
  const bg = benignTrace(agents.filter((a) => !coalition.includes(a)), steps, seed);
  const cyc: Flow[] = [];
  for (let i = 0; i < steps; i++) {
    const a = coalition[i % coalition.length]!;
    const b = coalition[(i + 1) % coalition.length]!;
    cyc.push({ payer: a, payee: b, amount: 100 });
  }
  return [...bg, ...cyc];
}

/** Partial observer: keeps each flow with probability p (O_peer-style coverage). */
export function sample(trace: Flow[], p: number, seed = 3): Flow[] {
  const r = rng(seed);
  return trace.filter(() => r() < p);
}

/**
 * Repeated-cycle share: the fraction of the claimant's flows lying on a directed cycle through the
 * claimant of length ≤ maxLen whose every edge recurs at least minMultiplicity times. This is the
 * feature family the earlier hive detector used; it sees a relay of any bounded length, where the
 * direct-attester statistic sees only reciprocal pairs.
 */
export function repeatedCycleShare(trace: Flow[], claimant: string, maxLen = 4, minMultiplicity = 10): number {
  const m = new Map<string, number>();
  const succ = new Map<string, Set<string>>();
  const ek = (u: string, v: string) => `${u}>${v}`;
  for (const f of trace) {
    m.set(ek(f.payer, f.payee), (m.get(ek(f.payer, f.payee)) ?? 0) + 1);
    if (!succ.has(f.payer)) succ.set(f.payer, new Set());
    succ.get(f.payer)!.add(f.payee);
  }
  const heavy = (u: string, v: string) => (m.get(ek(u, v)) ?? 0) >= minMultiplicity;
  // Edges (u→v) that lie on some heavy cycle through the claimant of length ≤ maxLen.
  const onCycle = new Set<string>();
  const walk = (path: string[]) => {
    const last = path[path.length - 1]!;
    for (const nxt of succ.get(last) ?? []) {
      if (!heavy(last, nxt)) continue;
      if (nxt === claimant) {
        if (path.length >= 2) for (let i = 0; i < path.length; i++) onCycle.add(ek(path[i]!, path[i + 1] ?? claimant));
        continue;
      }
      if (path.length < maxLen && !path.includes(nxt)) walk([...path, nxt]);
    }
  };
  walk([claimant]);
  let total = 0;
  let hit = 0;
  for (const f of trace) {
    if (f.payer !== claimant && f.payee !== claimant) continue;
    total += f.amount;
    if (onCycle.has(ek(f.payer, f.payee))) hit += f.amount;
  }
  return total === 0 ? 0 : hit / total;
}
