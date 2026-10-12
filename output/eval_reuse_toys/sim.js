'use strict';
// Eval exhaustion toy. See PREREG.md for the frozen model and predictions.
const fs = require('fs');
const path = require('path');

const SIGMA_B = 1.5;
const SIGMA_U = 1.0;
const SD_TOT = Math.sqrt(SIGMA_B * SIGMA_B + SIGMA_U * SIGMA_U);
const P0 = 0.26;
const K = 16;
const G = 100;
const S0 = 0.06;
const RHO = 0.95;
const SIN_PHI = 0.2;
const COS_PHI = Math.sqrt(1 - SIN_PHI * SIN_PHI);
const NS = [500, 1000, 4000, 16000];
const SEEDS = 20;
const GATE_Z = 3;

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function makeNormal(rand) {
  let spare = null;
  return function () {
    if (spare !== null) { const s = spare; spare = null; return s; }
    let u, v, s;
    do { u = rand() * 2 - 1; v = rand() * 2 - 1; s = u * u + v * v; } while (s >= 1 || s === 0);
    const m = Math.sqrt(-2 * Math.log(s) / s);
    spare = v * m;
    return u * m;
  };
}
function erf(x) {
  const sign = x < 0 ? -1 : 1; x = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * x);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return sign * y;
}
const Phi = (x) => 0.5 * (1 + erf(x / Math.SQRT2));
function PhiInv(p) { // bisection, adequate here
  let lo = -8, hi = 8;
  for (let i = 0; i < 80; i++) { const mid = (lo + hi) / 2; if (Phi(mid) < p) lo = mid; else hi = mid; }
  return (lo + hi) / 2;
}
const A0 = PhiInv(P0) * SD_TOT;
const popAcc = (a) => Phi(a / SD_TOT);

function runReuse(n, seed, gated) {
  const norm = makeNormal(mulberry32(seed));
  const b = new Float64Array(n);
  let u = new Float64Array(n);
  for (let i = 0; i < n; i++) { b[i] = SIGMA_B * norm(); u[i] = SIGMA_U * norm(); }
  let a = A0;
  let score = 0;
  for (let i = 0; i < n; i++) if (a - b[i] + u[i] > 0) score++;
  const rep = new Float64Array(G + 1), tru = new Float64Array(G + 1);
  rep[0] = score / n; tru[0] = popAcc(a);
  let cand = new Float64Array(n), best = new Float64Array(n);
  let accepted = 0;
  for (let g = 1; g <= G; g++) {
    const sg = S0 * Math.pow(RHO, g - 1);
    let bestScore = -1, bestDa = 0;
    for (let k = 0; k < K; k++) {
      const da = sg * norm();
      let sc = 0;
      const aa = a + da;
      for (let i = 0; i < n; i++) {
        const ui = COS_PHI * u[i] + SIN_PHI * SIGMA_U * norm();
        cand[i] = ui;
        if (aa - b[i] + ui > 0) sc++;
      }
      if (sc > bestScore) { bestScore = sc; bestDa = da; const t = best; best = cand; cand = t; }
    }
    const p = score / n;
    const thr = gated ? GATE_Z * Math.sqrt(p * (1 - p) / n) * n : 0;
    if (bestScore > score + thr) {
      a += bestDa; const t = u; u = best; best = t; score = bestScore; accepted++;
    }
    rep[g] = score / n; tru[g] = popAcc(a);
  }
  return { rep, tru, accepted };
}

function runFresh(n, seed) {
  const norm = makeNormal(mulberry32(seed));
  let a = A0;
  const rep = new Float64Array(G + 1), tru = new Float64Array(G + 1);
  tru[0] = popAcc(a);
  rep[0] = tru[0] + Math.sqrt(tru[0] * (1 - tru[0]) / n) * norm();
  const b = new Float64Array(n), u = new Float64Array(n);
  let accepted = 0;
  for (let g = 1; g <= G; g++) {
    const sg = S0 * Math.pow(RHO, g - 1);
    let inc = 0;
    for (let i = 0; i < n; i++) { b[i] = SIGMA_B * norm(); u[i] = SIGMA_U * norm(); if (a - b[i] + u[i] > 0) inc++; }
    let bestScore = -1, bestDa = 0;
    for (let k = 0; k < K; k++) {
      const da = sg * norm();
      const aa = a + da;
      let sc = 0;
      for (let i = 0; i < n; i++) {
        const ui = COS_PHI * u[i] + SIN_PHI * SIGMA_U * norm();
        if (aa - b[i] + ui > 0) sc++;
      }
      if (sc > bestScore) { bestScore = sc; bestDa = da; }
    }
    if (bestScore > inc) { a += bestDa; accepted++; }
    tru[g] = popAcc(a);
    // reported on a second fresh block: unbiased binomial draw, normal approximation
    rep[g] = tru[g] + Math.sqrt(tru[g] * (1 - tru[g]) / n) * norm();
  }
  return { rep, tru, accepted };
}

function meanCurves(runs) {
  const rep = new Array(G + 1).fill(0), tru = new Array(G + 1).fill(0);
  let acc = 0;
  for (const r of runs) { for (let g = 0; g <= G; g++) { rep[g] += r.rep[g]; tru[g] += r.tru[g]; } acc += r.accepted; }
  const m = runs.length;
  const gapFinal = runs.map((r) => r.rep[G] - r.tru[G]);
  const gm = gapFinal.reduce((x, y) => x + y, 0) / m;
  const gsd = Math.sqrt(gapFinal.reduce((x, y) => x + (y - gm) * (y - gm), 0) / (m - 1));
  return { rep: rep.map((x) => x / m), tru: tru.map((x) => x / m), accepted: acc / m, gapFinalMean: gm, gapFinalSE: gsd / Math.sqrt(m) };
}

const t0 = Date.now();
const out = { params: { SIGMA_B, SIGMA_U, P0, K, G, S0, RHO, SIN_PHI, NS, SEEDS, GATE_Z }, cells: {} };
for (const n of NS) {
  const fresh = [], naive = [], gated = [];
  for (let s = 0; s < SEEDS; s++) {
    fresh.push(runFresh(n, 1000 + s));
    naive.push(runReuse(n, 2000 + s, false));
    gated.push(runReuse(n, 2000 + s, true));
  }
  out.cells[n] = { FRESH: meanCurves(fresh), NAIVE: meanCurves(naive), GATED: meanCurves(gated) };
  console.error(`n=${n} done at ${((Date.now() - t0) / 1000).toFixed(1)}s`);
}

// ---- summary and prediction checks ----
const r3 = (x) => Math.round(x * 1000) / 1000;
const rows = [];
for (const n of NS) for (const arm of ['FRESH', 'NAIVE', 'GATED']) {
  const c = out.cells[n][arm];
  const repLate = c.rep[100] - c.rep[50], truLate = c.tru[100] - c.tru[50];
  const repEarly = c.rep[50] - c.rep[0], truEarly = c.tru[50] - c.tru[0];
  rows.push({
    n, arm,
    reported100: r3(c.rep[100]), true100: r3(c.tru[100]),
    gap100: r3(c.gapFinalMean), gapSE: r3(c.gapFinalSE),
    accepted: r3(c.accepted),
    phantomShareLate: repLate > 0 ? r3(1 - truLate / repLate) : null,
    lateEarlyReported: r3(repLate / repEarly), lateEarlyTrue: r3(truLate / truEarly),
  });
}
const cell = (n, arm) => rows.find((r) => r.n === n && r.arm === arm);
// P2 slope
const xs = NS.map((n) => Math.log(n)), ys = NS.map((n) => Math.log(out.cells[n].NAIVE.gapFinalMean));
const mx = xs.reduce((a, b) => a + b) / xs.length, my = ys.reduce((a, b) => a + b) / ys.length;
const slope = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0) / xs.reduce((a, x) => a + (x - mx) * (x - mx), 0);
const n4 = { F: cell(4000, 'FRESH'), N: cell(4000, 'NAIVE'), Gt: cell(4000, 'GATED') };
const checks = {
  P1: { value: n4.N.gap100, range: [0.08, 0.25], pass: n4.N.gap100 >= 0.08 && n4.N.gap100 <= 0.25 },
  P2: { slope: r3(slope), range: [-0.6, -0.4], pass: slope >= -0.6 && slope <= -0.4 },
  P3: { values: [500, 1000, 4000].map((n) => cell(n, 'NAIVE').phantomShareLate), pass: [500, 1000, 4000].every((n) => cell(n, 'NAIVE').phantomShareLate > 0.5) },
  P4a: { gated: n4.Gt.gap100, naive: n4.N.gap100, pass: n4.Gt.gap100 <= 0.5 * n4.N.gap100 },
  P4b: { fresh: n4.F.true100, naive: n4.N.true100, gated: n4.Gt.true100, pass: n4.F.true100 > n4.N.true100 && n4.N.true100 > n4.Gt.true100 },
  P5: { reported: n4.N.lateEarlyReported, true: n4.N.lateEarlyTrue, pass: n4.N.lateEarlyReported >= 2 * n4.N.lateEarlyTrue },
};
out.summary = rows; out.checks = checks;
fs.writeFileSync(path.join(__dirname, 'results.json'), JSON.stringify(out, null, 1));
console.table(rows);
console.log(JSON.stringify(checks, null, 1));
console.error(`total ${((Date.now() - t0) / 1000).toFixed(1)}s`);
