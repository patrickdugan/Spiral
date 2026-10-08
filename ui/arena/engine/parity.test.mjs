// Parity: the compiled Rust engine and the JavaScript reference produce the same outputs.
// Usage: node parity.test.mjs <path to diorama_engine.wasm>
// Drives both with identical randomized inputs (walking to goals, snaps, poses, shakes,
// legacy pinned units, a visible adversary) for 240 steps and compares every output buffer.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { createRefEngine, IN, INPUT } = require(path.join(here, "engine_ref.js"));

const wasmPath = process.argv[2] || path.join(here, "diorama_engine.wasm");
const { instance } = await WebAssembly.instantiate(readFileSync(wasmPath), {});
const ex = instance.exports;

let seed = 7;
const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };

const N = 9;
const ref = createRefEngine(), R = ref.init(N);
ex.units_init(N);
const view = (ptr, len) => new Float32Array(ex.memory.buffer, ptr, len);
const W = { inp: view(ex.units_in(), N * IN), torso: view(ex.units_torso(), N * 16), head: view(ex.units_head(), N * 16),
  leg: view(ex.units_leg(), N * 32), arm: view(ex.units_arm(), N * 32), phone: view(ex.units_phone(), N * 16), pos: view(ex.units_pos(), N * 4) };

function setAll(i, k, v) { R.inp[i * IN + k] = v; W.inp[i * IN + k] = v; }
for (let i = 0; i < N; i++) {
  setAll(i, INPUT.WALKABLE, i % 4 === 3 ? 0 : 1);
  setAll(i, INPUT.SCALE, 0.9 + 0.24 * rnd()); setAll(i, INPUT.HEAD_R, 0.9 + 0.2 * rnd()); setAll(i, INPUT.TORSO_R, 0.85 + 0.4 * rnd());
  setAll(i, INPUT.ARM_OFF, 0.95 + 0.18 * rnd()); setAll(i, INPUT.GY_OFF, -0.2 + 0.4 * rnd()); setAll(i, INPUT.SLUMP, i === 2 ? 0.16 : 0);
  setAll(i, INPUT.PHASE, rnd() * 6.28); setAll(i, INPUT.BASE_ROT, rnd() * 6.28 - 3.14); setAll(i, INPUT.HAS_DESK, i % 2);
  setAll(i, INPUT.GX, rnd() * 80 - 40); setAll(i, INPUT.GY, 3.3); setAll(i, INPUT.GZ, rnd() * 80 - 40); setAll(i, INPUT.GYAW, rnd() * 6.28 - 3.14);
}
let worst = { err: 0, at: "" }, now = 5_000_000;
const check = (step) => {
  for (const key of ["torso", "head", "leg", "arm", "phone", "pos"]) {
    const a = R[key], b = W[key];
    for (let k = 0; k < a.length; k++) {
      const err = Math.abs(a[k] - b[k]) / Math.max(1, Math.abs(a[k]));
      if (err > worst.err) worst = { err, at: `${key}[${k}] step ${step}: js ${a[k]} wasm ${b[k]}` };
    }
  }
};
for (let step = 0; step < 240; step++) {
  if (step % 40 === 20) for (let i = 0; i < N; i++) {   // new goals and per-frame flags, as applyFrame would write
    setAll(i, INPUT.GX, rnd() * 80 - 40); setAll(i, INPUT.GZ, rnd() * 80 - 40); setAll(i, INPUT.GYAW, rnd() * 6.28 - 3.14);
    setAll(i, INPUT.STRESS, rnd() < 0.4 ? rnd() : 0); setAll(i, INPUT.OFF, rnd() < 0.3 ? 1 : 0); setAll(i, INPUT.AT_DESK, rnd() < 0.5 ? 1 : 0);
    setAll(i, INPUT.NO_TYPE, rnd() < 0.2 ? 1 : 0); setAll(i, INPUT.TURNED, rnd() < 0.2 ? 1 : 0); setAll(i, INPUT.LEGACY_TURN, i % 4 === 3 && rnd() < 0.5 ? 1 : 0);
    if (rnd() < 0.5) { setAll(i, INPUT.POSE_KIND, 1 + Math.floor(rnd() * 6)); setAll(i, INPUT.POSE_START, 1); }
    if (rnd() < 0.2) setAll(i, INPUT.SHAKE_START, 1);
    if (rnd() < 0.15) setAll(i, INPUT.SNAP, 1);
  }
  const dt = 1 / 60, hx = 10 * Math.sin(step * 0.05), hz = 10 * Math.cos(step * 0.05), hv = step % 80 < 60 ? 1 : 0;
  now += 16.7;
  ref.step(dt, now, hx, hz, hv);
  ex.step(dt, now, hx, hz, hv);
  check(step);
}
const ok = worst.err < 5e-3;
console.log(JSON.stringify({ ok, units: N, steps: 240, worstRelErr: worst.err, at: worst.at, wasmBytes: readFileSync(wasmPath).length }));
process.exitCode = ok ? 0 : 1;
