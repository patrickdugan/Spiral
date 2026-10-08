/* JavaScript reference of ui/arena/engine/src/lib.rs (`units_init` / `step`).
   The viewer falls back to it when WebAssembly is unavailable, and
   ui/arena/engine/parity.test.mjs checks that the compiled module matches it.
   Keep the two in lockstep: same input layout, same state, same order of operations. */
(function (root) {
  "use strict";
  const IN = 24, ST = 16;
  const GX = 0, GY = 1, GZ = 2, GYAW = 3, SNAP = 4, WALKABLE = 5, SCALE = 6, HEAD_R = 7, TORSO_R = 8, ARM_OFF = 9,
    GY_OFF = 10, SLUMP = 11, PHASE = 12, STRESS = 13, OFF = 14, HAS_DESK = 15, AT_DESK = 16, NO_TYPE = 17, TURNED = 18,
    LEGACY_TURN = 19, POSE_KIND = 20, POSE_START = 21, SHAKE_START = 22, BASE_ROT = 23;
  const X = 0, Y = 1, Z = 2, YAW = 3, HEADING = 4, WALK = 5, STRIDE = 6, RX0 = 7, RZ0 = 8, RX1 = 9, RZ1 = 10,
    POSE_T = 11, POSE = 12, SHAKE = 13, INIT = 14;

  function compose(p, r, s) {   // T(p) * R(Euler XYZ, as three.js) * S(s), column-major
    const a = Math.cos(r[0]), b = Math.sin(r[0]), c = Math.cos(r[1]), d = Math.sin(r[1]), e = Math.cos(r[2]), f = Math.sin(r[2]);
    const ae = a * e, af = a * f, be = b * e, bf = b * f;
    return [
      c * e * s[0], (af + be * d) * s[0], (bf - ae * d) * s[0], 0,
      -c * f * s[1], (ae - bf * d) * s[1], (be + af * d) * s[1], 0,
      d * s[2], -b * c * s[2], a * c * s[2], 0,
      p[0], p[1], p[2], 1,
    ];
  }
  function mul(a, b) {
    const r = new Array(16);
    for (let col = 0; col < 4; col++) for (let row = 0; row < 4; row++) {
      let v = 0; for (let k = 0; k < 4; k++) v += a[k * 4 + row] * b[col * 4 + k];
      r[col * 4 + row] = v;
    }
    return r;
  }
  function put(out, i, m) { for (let k = 0; k < 16; k++) out[i * 16 + k] = m[k]; }
  const ONE = [1, 1, 1], ZERO = [0, 0, 0];

  function createRefEngine() {
    let n = 0, inp, st, torso, head, leg, arm, phone, pos;
    return {
      kind: "js",
      init(count) {
        n = count;
        inp = new Float32Array(n * IN); st = new Float32Array(n * ST);
        torso = new Float32Array(n * 16); head = new Float32Array(n * 16); leg = new Float32Array(n * 32); arm = new Float32Array(n * 32);
        phone = new Float32Array(n * 16); pos = new Float32Array(n * 4);
        return { inp, torso, head, leg, arm, phone, pos };
      },
      step(dtIn, now, hiveX, hiveZ, hiveVis) {
        const dt = Math.min(0.05, Math.max(0, dtIn));
        for (let i = 0; i < n; i++) {
          const I = i * IN, S = i * ST;
          if (st[S + INIT] === 0 || inp[I + SNAP] !== 0) {
            st[S + X] = inp[I + GX]; st[S + Y] = inp[I + GY]; st[S + Z] = inp[I + GZ];
            if (st[S + INIT] === 0) { st[S + YAW] = inp[I + BASE_ROT]; st[S + HEADING] = inp[I + BASE_ROT]; }
            st[S + WALK] = 0; st[S + INIT] = 1; inp[I + SNAP] = 0;
          }
          let moving = false;
          if (inp[I + WALKABLE] !== 0) {
            const dx = inp[I + GX] - st[S + X], dz = inp[I + GZ] - st[S + Z], dist = Math.sqrt(dx * dx + dz * dz);
            if (dist > 0.2) {
              const stp = Math.min(dist, dt * Math.max(10, dist / 1.6));
              st[S + X] += dx / dist * stp; st[S + Z] += dz / dist * stp; st[S + HEADING] = Math.atan2(dx, dz); moving = true;
            }
            st[S + Y] += (inp[I + GY] - st[S + Y]) * Math.min(1, dt * 6);
          } else { st[S + X] = inp[I + GX]; st[S + Y] = inp[I + GY]; st[S + Z] = inp[I + GZ]; }
          st[S + WALK] += ((moving ? 1 : 0) - st[S + WALK]) * Math.min(1, dt * 8);
          st[S + STRIDE] += dt * 10 * st[S + WALK];
          const walk = st[S + WALK], stride = st[S + STRIDE], ph = inp[I + PHASE], stress = inp[I + STRESS];
          const bob = Math.sin(now * 0.0016 + ph) * 0.18 * (1 - walk) + Math.abs(Math.sin(stride)) * 0.22 * walk;
          const sway = stress !== 0 ? Math.sin(now * 0.016 + ph) * 0.12 * stress * (1 - walk) : 0;
          let ry = inp[I + WALKABLE] !== 0 ? inp[I + GYAW] : inp[I + BASE_ROT];
          if (walk > 0.3) ry = st[S + HEADING];
          else if (inp[I + LEGACY_TURN] !== 0) ry += Math.PI;
          else if (stress > 0.12 && hiveVis !== 0) ry = Math.atan2(hiveX - st[S + X], hiveZ - st[S + Z]);
          const dy = ry - st[S + YAW];
          let w = Math.atan2(Math.sin(dy), Math.cos(dy)); if (w < -Math.PI + 1e-3) w += 2 * Math.PI;   // a half turn always goes the positive way
          st[S + YAW] += w * Math.min(1, dt * 5);
          if (inp[I + SHAKE_START] !== 0) { st[S + SHAKE] = 0.7; inp[I + SHAKE_START] = 0; }
          if (st[S + SHAKE] > 0) { st[S + SHAKE] -= dt; st[S + YAW] += Math.sin(now * 0.045) * 0.09; }
          const idle = Math.sin(now * 0.0018 + ph) * (0.07 + 0.3 * stress);
          let rx = [idle, -idle], rz = [-0.35, 0.35];
          if (inp[I + OFF] === 0 && inp[I + HAS_DESK] !== 0 && inp[I + NO_TYPE] === 0 && inp[I + AT_DESK] !== 0 && walk < 0.3) {
            const j = Math.sin(now * 0.02 + ph) * 0.05; rx = [-0.8 + j, -0.8 - j]; rz = [-0.15, 0.15];
          }
          if (walk > 0.05) { const a = Math.sin(stride) * 0.5 * walk; rx = [-a, a]; rz = [-0.25, 0.25]; }
          let lean = 0;
          if (inp[I + POSE_START] !== 0) { st[S + POSE] = inp[I + POSE_KIND]; st[S + POSE_T] = 1.8; inp[I + POSE_START] = 0; }
          if (st[S + POSE_T] > 0) {
            st[S + POSE_T] -= dt;
            if (st[S + POSE_T] <= 0) st[S + POSE] = 0;
            else switch (Math.trunc(st[S + POSE])) {
              case 1: rx[0] = -1.5; rz[0] = -0.1; break;
              case 2: rx[0] = -2.3; rz[0] = -0.55; break;
              case 3: rx[0] = -1.05; rz[0] = -0.1; lean = 0.12; break;
              case 4: rx = [-0.9, -0.9]; rz = [-0.2, 0.2]; break;
              case 5: rx[0] = -0.6; rz[0] = -1.1; break;
              default: break;
            }
          }
          const k = Math.min(1, dt * 7);
          st[S + RX0] += (rx[0] - st[S + RX0]) * k; st[S + RZ0] += (rz[0] - st[S + RZ0]) * k;
          st[S + RX1] += (rx[1] - st[S + RX1]) * k; st[S + RZ1] += (rz[1] - st[S + RZ1]) * k;
          const s = inp[I + SCALE], pitch = inp[I + SLUMP] + (inp[I + TURNED] !== 0 ? 0.14 : 0) + lean;
          const fig = compose([st[S + X], st[S + Y] + inp[I + GY_OFF] + bob, st[S + Z]], [pitch, st[S + YAW], sway], [s, s, s]);
          const tr = inp[I + TORSO_R], hr = inp[I + HEAD_R];
          put(torso, i, mul(fig, compose(ZERO, ZERO, [tr, 1, tr])));
          put(head, i, mul(fig, compose([0, 2.25, 0], ZERO, [hr, hr, hr])));
          const legsw = Math.sin(stride) * 0.55 * walk;
          put(leg, 2 * i, mul(fig, compose([0.42, -0.6, 0], [legsw, 0, 0], ONE)));
          put(leg, 2 * i + 1, mul(fig, compose([-0.42, -0.6, 0], [-legsw, 0, 0], ONE)));
          const aw = inp[I + ARM_OFF];
          const armR = mul(fig, compose([aw, 1.5, 0], [st[S + RX0], 0, st[S + RZ0]], ONE));
          const armL = mul(fig, compose([-aw, 1.5, 0], [st[S + RX1], 0, st[S + RZ1]], ONE));
          put(arm, 2 * i, armR); put(arm, 2 * i + 1, armL);
          put(phone, i, mul(armR, compose([0.1, -2.25, 0.32], [-0.4, 0, 0], ONE)));
          pos[i * 4] = st[S + X]; pos[i * 4 + 1] = st[S + Y]; pos[i * 4 + 2] = st[S + Z]; pos[i * 4 + 3] = st[S + YAW];
        }
      },
    };
  }
  const api = { createRefEngine, IN, INPUT: { GX, GY, GZ, GYAW, SNAP, WALKABLE, SCALE, HEAD_R, TORSO_R, ARM_OFF, GY_OFF, SLUMP, PHASE, STRESS, OFF, HAS_DESK, AT_DESK, NO_TYPE, TURNED, LEGACY_TURN, POSE_KIND, POSE_START, SHAKE_START, BASE_ROT } };
  root.DioramaEngineRef = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
