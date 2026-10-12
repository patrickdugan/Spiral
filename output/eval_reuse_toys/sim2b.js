'use strict';
// Eval exhaustion, run 2: item-level feedback with a real learner. See PREREG_2.md.
const fs = require('fs');
const path = require('path');

const D = 6, EPS = 0.10, N0 = 100, M = 10, G = 100, KC = 16, T = 5000;
const NS = [250, 1000, 4000, 16000];
const SEEDS = 10;
const ARMS = ['CLEAN', 'SCORE', 'LEAK', 'MIXED', 'LEAKSEL'];

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
function gen(rand, norm, count) {
  const X = new Float64Array(count * D), Y = new Int8Array(count);
  for (let i = 0; i < count; i++) {
    const o = i * D;
    for (let j = 0; j < D; j++) X[o + j] = norm();
    const clean = (X[o] + 0.7 * X[o + 1] * X[o + 2] - 0.3) > 0 ? 1 : -1;
    Y[i] = rand() < EPS ? -clean : clean;
  }
  return { X, Y, count };
}
function makeEval(set) {
  const nd = new Float64Array(set.count * 3).fill(Infinity);
  const nl = new Int8Array(set.count * 3);
  return { X: set.X, Y: set.Y, count: set.count, nd, nl };
}
function addPoints(E, bx, by, bcount) {
  const { X, nd, nl, count } = E;
  for (let i = 0; i < count; i++) {
    const o = i * D, b3 = i * 3;
    for (let b = 0; b < bcount; b++) {
      const p = b * D;
      let d2 = 0;
      for (let j = 0; j < D; j++) { const df = X[o + j] - bx[p + j]; d2 += df * df; }
      if (d2 < nd[b3 + 2]) {
        if (d2 < nd[b3 + 1]) {
          nd[b3 + 2] = nd[b3 + 1]; nl[b3 + 2] = nl[b3 + 1];
          if (d2 < nd[b3]) { nd[b3 + 1] = nd[b3]; nl[b3 + 1] = nl[b3]; nd[b3] = d2; nl[b3] = by[b]; }
          else { nd[b3 + 1] = d2; nl[b3 + 1] = by[b]; }
        } else { nd[b3 + 2] = d2; nl[b3 + 2] = by[b]; }
      }
    }
  }
}
function tentativeScore(E, bx, by, bcount) {
  const { X, Y, nd, nl, count } = E;
  let correct = 0;
  for (let i = 0; i < count; i++) {
    const o = i * D, b3 = i * 3;
    let d0 = nd[b3], d1 = nd[b3 + 1], dd2 = nd[b3 + 2];
    let l0 = nl[b3], l1 = nl[b3 + 1], l2 = nl[b3 + 2];
    for (let b = 0; b < bcount; b++) {
      const p = b * D;
      let d2 = 0;
      for (let j = 0; j < D; j++) { const df = X[o + j] - bx[p + j]; d2 += df * df; }
      if (d2 < dd2) {
        if (d2 < d1) {
          dd2 = d1; l2 = l1;
          if (d2 < d0) { d1 = d0; l1 = l0; d0 = d2; l0 = by[b]; }
          else { d1 = d2; l1 = by[b]; }
        } else { dd2 = d2; l2 = by[b]; }
      }
    }
    if ((l0 + l1 + l2 > 0 ? 1 : -1) === Y[i]) correct++;
  }
  return correct;
}
function accuracy(E) {
  let c = 0;
  for (let i = 0; i < E.count; i++) { const b3 = i * 3; if ((E.nl[b3] + E.nl[b3 + 1] + E.nl[b3 + 2] > 0 ? 1 : -1) === E.Y[i]) c++; }
  return c / E.count;
}
function failed(E) {
  const out = [];
  for (let i = 0; i < E.count; i++) { const b3 = i * 3; if ((E.nl[b3] + E.nl[b3 + 1] + E.nl[b3 + 2] > 0 ? 1 : -1) !== E.Y[i]) out.push(i); }
  return out;
}
function pickFailed(S, rand, want, bx, by, at) {
  const f = failed(S);
  const take = Math.min(want, f.length);
  for (let t = 0; t < take; t++) {
    const j = t + Math.floor(rand() * (f.length - t));
    const tmp = f[t]; f[t] = f[j]; f[j] = tmp;
    const src = f[t] * D, dst = (at + t) * D;
    for (let q = 0; q < D; q++) bx[dst + q] = S.X[src + q];
    by[at + t] = S.Y[f[t]];
  }
  return take;
}
function fillFresh(rand, norm, bx, by, from, to) {
  if (to <= from) return;
  const g = gen(rand, norm, to - from);
  bx.set(g.X, from * D);
  by.set(g.Y, from);
}

function run(n, seed, arm) {
  const dRand = mulberry32(seed * 7919 + 17), dNorm = makeNormal(dRand);
  const train0 = gen(dRand, dNorm, N0);
  const S = makeEval(gen(dRand, dNorm, n));
  const Tt = makeEval(gen(dRand, dNorm, T));
  addPoints(S, train0.X, train0.Y, N0);
  addPoints(Tt, train0.X, train0.Y, N0);
  const aRand = mulberry32(seed * 104729 + ARMS.indexOf(arm) * 31 + n), aNorm = makeNormal(aRand);
  const rep = new Float64Array(G + 1), tru = new Float64Array(G + 1);
  rep[0] = accuracy(S); tru[0] = accuracy(Tt);
  let patches = 0, noisyPatches = 0;
  for (let g = 1; g <= G; g++) {
    let bx = new Float64Array(M * D), by = new Int8Array(M);
    if (arm === 'CLEAN') {
      fillFresh(aRand, aNorm, bx, by, 0, M);
    } else if (arm === 'SCORE') {
      let best = -1, bbx = null, bby = null;
      for (let k = 0; k < KC; k++) {
        const c = gen(aRand, aNorm, M);
        const sc = tentativeScore(S, c.X, c.Y, M);
        if (sc > best) { best = sc; bbx = c.X; bby = c.Y; }
      }
      bx = bbx; by = bby;
    } else if (arm === 'LEAKSEL') {
      let best = -1, bbx = null, bby = null, btook = 0;
      for (let k = 0; k < KC; k++) {
        const cx = new Float64Array(M * D), cy = new Int8Array(M);
        const took = pickFailed(S, aRand, M, cx, cy, 0);
        fillFresh(aRand, aNorm, cx, cy, took, M);
        const sc = tentativeScore(S, cx, cy, M);
        if (sc > best) { best = sc; bbx = cx; bby = cy; btook = took; }
      }
      bx = bbx; by = bby; patches += btook;
    } else {
      const want = arm === 'LEAK' ? M : M / 2;
      const took = pickFailed(S, aRand, want, bx, by, 0);
      patches += took;
      for (let t = 0; t < took; t++) {
        const o = t * D;
        const clean = (bx[o] + 0.7 * bx[o + 1] * bx[o + 2] - 0.3) > 0 ? 1 : -1;
        if (by[t] !== clean) noisyPatches++;
      }
      fillFresh(aRand, aNorm, bx, by, took, M);
    }
    addPoints(S, bx, by, M);
    addPoints(Tt, bx, by, M);
    rep[g] = accuracy(S); tru[g] = accuracy(Tt);
  }
  return { rep, tru, patches, noisyPatches };
}

function agg(runs) {
  const m = runs.length;
  const rep = new Array(G + 1).fill(0), tru = new Array(G + 1).fill(0);
  let patches = 0, noisy = 0;
  for (const r of runs) { for (let g = 0; g <= G; g++) { rep[g] += r.rep[g] / m; tru[g] += r.tru[g] / m; } patches += r.patches / m; noisy += r.noisyPatches / m; }
  const gaps = runs.map((r) => r.rep[G] - r.tru[G]);
  const gm = gaps.reduce((a, b) => a + b, 0) / m;
  const se = Math.sqrt(gaps.reduce((a, b) => a + (b - gm) * (b - gm), 0) / (m - 1) / m);
  const tg = runs.map((r) => r.tru[G] - r.tru[0]);
  const tgm = tg.reduce((a, b) => a + b, 0) / m;
  const tgse = Math.sqrt(tg.reduce((a, b) => a + (b - tgm) * (b - tgm), 0) / (m - 1) / m);
  return { rep, tru, gap: gm, gapSE: se, trueGain: tgm, trueGainSE: tgse, patches, noisyShare: patches > 0 ? noisy / patches : null };
}

const t0 = Date.now();
// POST HOC, not preregistered: item-level proposals with score-based selection.
const out = { note: 'post hoc exploratory arm', cells: {} };
const r3 = (x) => Math.round(x * 1000) / 1000;
const rows = [];
for (const n of NS) {
  const runs = [];
  for (let s = 0; s < SEEDS; s++) runs.push(run(n, 100 + s, 'LEAKSEL'));
  const c = agg(runs); out.cells[n] = c;
  rows.push({ n, start: r3(c.tru[0]), reported50: r3(c.rep[50]), true50: r3(c.tru[50]), reported100: r3(c.rep[100]), true100: r3(c.tru[100]), gap100: r3(c.gap), gapSE: r3(c.gapSE), trueGain: r3(c.trueGain), repLate: r3(c.rep[100]-c.rep[50]), truLate: r3(c.tru[100]-c.tru[50]), patches: r3(c.patches) });
  console.error('n=' + n + ' done at ' + ((Date.now() - t0) / 1000).toFixed(1) + 's');
}
out.summary = rows;
fs.writeFileSync(path.join(__dirname, 'results2b.json'), JSON.stringify(out, null, 1));
console.table(rows);
