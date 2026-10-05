// Emits the liquidity-duration grid of the paper (paper/tex, tab:grid), its accounting variants (tab:acct),
// the failed events behind each grid row (tab:fail), and the multiparty-channel comparison on the same
// demand (tab:hyper, tab:hyperfail) as LaTeX rows.
// Run: node --experimental-strip-types model/grid.ts > paper/tex/grid.tex
// Every number in those tables comes from here; nothing is hand-edited.

import { runCorner, type CornerParams } from "./server.ts";

const trailing = { kind: "trailing", intervalBlocks: 4032, roundBlocks: 6 } as const;
const oracle = { kind: "oracle" } as const;

const many = (over: Partial<CornerParams>): CornerParams => ({
  agents: 200, horizonLifetimes: 8, driftPerRound: 0, burst: { vIn: 5000, vOut: 4000, pIn: 0.02 },
  margin: 0.25, forecast: trailing, volume: "both", serverTier: true, seed: 1, ...over,
});
const few = (over: Partial<CornerParams>): CornerParams => ({
  agents: 3, horizonLifetimes: 8, driftPerRound: 0, burst: { vIn: 0, vOut: 1, pIn: 0 }, steady: { base: 100, jitter: 10 },
  margin: 0.25, forecast: trailing, volume: "both", serverTier: true, seed: 2, ...over,
});

const cells: Array<[string, CornerParams]> = [
  ["200 agents, bursty, drift $0$, $H=8\\tau$", many({})],
  ["200 agents, bursty, drift $0$, $H=1\\tau$", many({ horizonLifetimes: 1 })],
  ["200 agents, bursty, drift $+60$, $H=8\\tau$", many({ driftPerRound: 60 })],
  ["200 agents, bursty, drift $-30$, $H=8\\tau$", many({ driftPerRound: -30 })],
  ["3 agents, steady, drift $0$, $H=8\\tau$", few({})],
];

const f = (x: number) => (Number.isFinite(x) ? x.toFixed(2) : "$\\infty$");
const n = (x: number) => x.toLocaleString("en-US").replace(/,/g, "\\,"); // thin-space thousands in LaTeX
const lines: string[] = [];
const failLines: string[] = [];
for (const [label, base] of cells) {
  const run = (over: Partial<CornerParams>) => runCorner({ ...base, ...over });
  const eo = run({ spendLock: "expiry", forecast: oracle }), et = run({ spendLock: "expiry", forecast: trailing });
  const ro = run({ spendLock: "round", forecast: oracle }), rt = run({ spendLock: "round", forecast: trailing });
  lines.push(`${label} & ${f(eo.ratio)} & ${f(et.ratio)} & ${f(ro.ratio)} & ${f(rt.ratio)} \\\\`);
  // The failure table carries one column per forecast rule, so what it leaves out has to hold: the recovery
  // rule changes what the server locks and nothing a holder or the server-tier forecast sees, and the oracle
  // rule, which holds the whole-horizon peak, never fails at the server tier. Checked here, not assumed.
  const same = eo.chFailures === ro.chFailures && et.chFailures === rt.chFailures && et.serverFailures === rt.serverFailures &&
    eo.arkFailures === et.arkFailures && eo.events === et.events;
  if (!same) throw new Error(`failure counts depend on the recovery rule on "${label}"; the failure table needs a column per lock rule`);
  if (eo.serverFailures !== 0) throw new Error(`oracle server-tier forecast failed on "${label}"; the failure table caption claims it cannot`);
  failLines.push(`${label} & ${n(eo.events)} & ${n(eo.chFailures)} & ${n(et.chFailures)} & ${n(et.serverFailures)} & ${n(eo.arkFailures)} \\\\`);
}
// Multiparty channels (hyperedges) of k agents and a hub on the same demand (tab:hyper, tab:hyperfail):
// 𝒟_C/𝒟_H(k) under each forecast rule, 𝒟_V/𝒟_H at k = N under each recovery reading, and the failed
// events under the trailing rule, where the gain is in receipts delivered rather than in capital.
const hyperLines: string[] = [];
const hyperFailLines: string[] = [];
for (const [label, base] of cells) {
  const ks = base.agents >= 200 ? [1, 5, 20, base.agents] : [1, base.agents];
  const run = (over: Partial<CornerParams>) => runCorner({ ...base, hyperedgeSizes: ks, ...over });
  const eo = run({ spendLock: "expiry", forecast: oracle }), et = run({ spendLock: "expiry", forecast: trailing });
  const ro = run({ spendLock: "round", forecast: oracle });
  // k = 1 has to be the channel model exactly, or the columns beside it are not a comparison with it.
  for (const r of [eo, et]) {
    if (r.hyperedge[0]!.dH !== r.dC || r.hyperedge[0]!.failures !== r.chFailures) throw new Error(`hyperedge at k = 1 is not the channel model on "${label}"`);
  }
  const pad = (xs: string[]) => (xs.length === 3 ? xs : ["--", "--", xs[0]!]); // few-agent cells have only k = N
  const gain = (r: typeof eo) => pad(r.hyperedge.slice(1).map((h) => f(r.dC / h.dH))).join(" & ");
  const top = eo.hyperedge[eo.hyperedge.length - 1]!; // the hyperedge does not depend on the recovery rule
  hyperLines.push(`${label} & ${gain(eo)} & ${gain(et)} & ${f(eo.dV / top.dH)} & ${f(ro.dV / top.dH)} \\\\`);
  hyperFailLines.push(`${label} & ${n(et.events)} & ${n(et.chFailures)} & ${pad(et.hyperedge.slice(1).map((h) => n(h.failures))).join(" & ")} & ${n(et.arkFailures)} \\\\`);
}
// Accounting-only variants of the drift corner: what the earlier harness reported and why.
const drift = many({ driftPerRound: 60, forecast: oracle, spendLock: "expiry" });
const acct = [
  ["no server-tier term, outbound-only volume", runCorner({ ...drift, serverTier: false, volume: "out" }).ratio],
  ["no server-tier term, two-way volume", runCorner({ ...drift, serverTier: false }).ratio],
  ["server-tier term charged, two-way volume", runCorner(drift).ratio],
] as const;
process.stdout.write("% generated by model/grid.ts; do not edit\n");
process.stdout.write("\\newcommand{\\gridrows}{%\n" + lines.join("\n") + "}\n");
process.stdout.write("\\newcommand{\\acctrows}{%\n" + acct.map(([l, v]) => `${l} & ${f(v)} \\\\`).join("\n") + "}\n");
process.stdout.write("\\newcommand{\\gridfailrows}{%\n" + failLines.join("\n") + "}\n");
process.stdout.write("\\newcommand{\\hyperrows}{%\n" + hyperLines.join("\n") + "}\n");
process.stdout.write("\\newcommand{\\hyperfailrows}{%\n" + hyperFailLines.join("\n") + "}\n");
