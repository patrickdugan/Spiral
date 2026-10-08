//! Per-frame animation core for the Hive Swarm diorama viewer, compiled to WebAssembly.
//!
//! Presentation only. The viewer derives each unit's goal (desk, kiosk, transit stop,
//! night gathering spot) from the exported replay; this core walks the units there, runs
//! the gait, the idle / typing / event poses and the facing rules, and writes column-major
//! 4x4 instance matrices that three.js draws with instancing. It reads nothing from, and
//! writes nothing to, the sims.
//!
//! ABI: plain C exports over linear memory, no bindings generator. Per scenario the viewer
//! calls `units_init(n)`, writes `IN` floats per unit into `units_in()`, then calls `step()`
//! every animation frame and reads the outputs (`units_torso()`, `units_head()`,
//! `units_leg()`, `units_arm()`, `units_phone()`, `units_pos()`) as Float32Array views.
//! All buffers are allocated in `units_init`; nothing allocates afterwards, so the views
//! stay valid until the next `units_init` (the viewer rebuilds them then).
//!
//! `ui/arena/engine/engine_ref.js` is a line-for-line JavaScript reference of `step`; the
//! viewer falls back to it if WebAssembly is unavailable, and a Node test checks parity.

use core::f32::consts::PI;

/// Floats per unit in the input block.
pub const IN: usize = 24;
/// Floats per unit in the private state block.
const ST: usize = 16;

// ---- input layout (written by the viewer) ----
const GX: usize = 0; // goal: rig centre (feet at -3)
const GY: usize = 1;
const GZ: usize = 2;
const GYAW: usize = 3; // yaw to face once arrived
const SNAP: usize = 4; // 1 = teleport to the goal this step (scrubbing); cleared by the core
const WALKABLE: usize = 5; // 1 = walks to goals (city layout); 0 = pinned (legacy layout)
const SCALE: usize = 6; // overall figure scale
const HEAD_R: usize = 7; // head size relative to the shared head geometry
const TORSO_R: usize = 8; // shoulder width relative to the shared torso geometry
const ARM_OFF: usize = 9; // shoulder x offset
const GY_OFF: usize = 10; // figure's local y inside the rig (feet on the ground)
const SLUMP: usize = 11; // archetype posture pitch
const PHASE: usize = 12; // per-unit phase for idle motion
const STRESS: usize = 13; // graded pressure, 0..1
const OFF: usize = 14; // off shift
const HAS_DESK: usize = 15; // has a laptop / server to type at
const AT_DESK: usize = 16; // the routine says "desk" this frame
const NO_TYPE: usize = 17; // compromised or recruited: no typing
const TURNED: usize = 18; // compromised (not a decoy): slumps forward
const LEGACY_TURN: usize = 19; // legacy layout: off shift turns away from the desk
const POSE_KIND: usize = 20; // 1 declined, 2 phone to face, 3 plug in, 4 both arms, 5 envelope, 6+ no arm change
const POSE_START: usize = 21; // 1 = start POSE_KIND now; cleared by the core
const SHAKE_START: usize = 22; // 1 = head shake now; cleared by the core
const BASE_ROT: usize = 23; // yaw at the station

// ---- private state ----
const X: usize = 0;
const Y: usize = 1;
const Z: usize = 2;
const YAW: usize = 3;
const HEADING: usize = 4;
const WALK: usize = 5;
const STRIDE: usize = 6;
const RX0: usize = 7;
const RZ0: usize = 8;
const RX1: usize = 9;
const RZ1: usize = 10;
const POSE_T: usize = 11;
const POSE: usize = 12;
const SHAKE: usize = 13;
const INIT: usize = 14;

type M4 = [f32; 16];

/// T(p) * R(Euler XYZ, as three.js) * S(s), column-major.
fn compose(p: [f32; 3], r: [f32; 3], s: [f32; 3]) -> M4 {
    let (a, b) = (r[0].cos(), r[0].sin());
    let (c, d) = (r[1].cos(), r[1].sin());
    let (e, f) = (r[2].cos(), r[2].sin());
    let (ae, af, be, bf) = (a * e, a * f, b * e, b * f);
    [
        c * e * s[0], (af + be * d) * s[0], (bf - ae * d) * s[0], 0.0,
        -c * f * s[1], (ae - bf * d) * s[1], (be + af * d) * s[1], 0.0,
        d * s[2], -b * c * s[2], a * c * s[2], 0.0,
        p[0], p[1], p[2], 1.0,
    ]
}

fn mul(a: &M4, b: &M4) -> M4 {
    let mut r = [0.0f32; 16];
    for col in 0..4 {
        for row in 0..4 {
            let mut v = 0.0;
            for k in 0..4 {
                v += a[k * 4 + row] * b[col * 4 + k];
            }
            r[col * 4 + row] = v;
        }
    }
    r
}

fn put(out: &mut [f32], i: usize, m: &M4) {
    out[i * 16..i * 16 + 16].copy_from_slice(m);
}

fn s64(x: f64) -> f32 {
    x.sin() as f32
}

struct Engine {
    n: usize,
    inp: Vec<f32>,
    st: Vec<f32>,
    torso: Vec<f32>,
    head: Vec<f32>,
    leg: Vec<f32>,
    arm: Vec<f32>,
    phone: Vec<f32>,
    pos: Vec<f32>,
}

static mut ENGINE: Engine = Engine {
    n: 0,
    inp: Vec::new(),
    st: Vec::new(),
    torso: Vec::new(),
    head: Vec::new(),
    leg: Vec::new(),
    arm: Vec::new(),
    phone: Vec::new(),
    pos: Vec::new(),
};

fn eng() -> &'static mut Engine {
    // wasm32-unknown-unknown is single-threaded; the viewer is the only caller.
    unsafe { &mut *core::ptr::addr_of_mut!(ENGINE) }
}

#[no_mangle]
pub extern "C" fn engine_version() -> u32 {
    1
}

#[no_mangle]
pub extern "C" fn in_stride() -> u32 {
    IN as u32
}

/// Allocate every buffer for `n` units (zeroed). Views taken before this call are invalid.
#[no_mangle]
pub extern "C" fn units_init(n: u32) -> u32 {
    let e = eng();
    let n = n as usize;
    e.n = n;
    e.inp = vec![0.0; n * IN];
    e.st = vec![0.0; n * ST];
    e.torso = vec![0.0; n * 16];
    e.head = vec![0.0; n * 16];
    e.leg = vec![0.0; n * 2 * 16];
    e.arm = vec![0.0; n * 2 * 16];
    e.phone = vec![0.0; n * 16];
    e.pos = vec![0.0; n * 4];
    n as u32
}

#[no_mangle]
pub extern "C" fn units_in() -> *mut f32 {
    eng().inp.as_mut_ptr()
}
#[no_mangle]
pub extern "C" fn units_torso() -> *const f32 {
    eng().torso.as_ptr()
}
#[no_mangle]
pub extern "C" fn units_head() -> *const f32 {
    eng().head.as_ptr()
}
#[no_mangle]
pub extern "C" fn units_leg() -> *const f32 {
    eng().leg.as_ptr()
}
#[no_mangle]
pub extern "C" fn units_arm() -> *const f32 {
    eng().arm.as_ptr()
}
#[no_mangle]
pub extern "C" fn units_phone() -> *const f32 {
    eng().phone.as_ptr()
}
#[no_mangle]
pub extern "C" fn units_pos() -> *const f32 {
    eng().pos.as_ptr()
}

/// Advance every unit by `dt` seconds at wall-clock `now` (ms) and write all outputs.
/// `hive_*` is the adversary marker: pressed units turn to watch it when it is visible.
#[no_mangle]
pub extern "C" fn step(dt: f32, now: f64, hive_x: f32, hive_z: f32, hive_vis: f32) {
    let e = eng();
    let dt = dt.clamp(0.0, 0.05);
    for i in 0..e.n {
        let inp = &mut e.inp[i * IN..(i + 1) * IN];
        let st = &mut e.st[i * ST..(i + 1) * ST];

        if st[INIT] == 0.0 || inp[SNAP] != 0.0 {
            st[X] = inp[GX];
            st[Y] = inp[GY];
            st[Z] = inp[GZ];
            if st[INIT] == 0.0 {
                st[YAW] = inp[BASE_ROT];
                st[HEADING] = inp[BASE_ROT];
            }
            st[WALK] = 0.0;
            st[INIT] = 1.0;
            inp[SNAP] = 0.0;
        }

        // walking: head for the goal, arriving within ~1.6 s at no less than 10 units/s
        let mut moving = false;
        if inp[WALKABLE] != 0.0 {
            let (dx, dz) = (inp[GX] - st[X], inp[GZ] - st[Z]);
            let dist = (dx * dx + dz * dz).sqrt();
            if dist > 0.2 {
                let stp = dist.min(dt * 10.0f32.max(dist / 1.6));
                st[X] += dx / dist * stp;
                st[Z] += dz / dist * stp;
                st[HEADING] = dx.atan2(dz);
                moving = true;
            }
            st[Y] += (inp[GY] - st[Y]) * (dt * 6.0).min(1.0);
        } else {
            st[X] = inp[GX];
            st[Y] = inp[GY];
            st[Z] = inp[GZ];
        }
        st[WALK] += (if moving { 1.0 } else { 0.0 } - st[WALK]) * (dt * 8.0).min(1.0);
        st[STRIDE] += dt * 10.0 * st[WALK];
        let (walk, stride) = (st[WALK], st[STRIDE]);
        let ph = inp[PHASE] as f64;
        let stress = inp[STRESS];
        let bob = s64(now * 0.0016 + ph) * 0.18 * (1.0 - walk) + stride.sin().abs() * 0.22 * walk;
        let sway = if stress != 0.0 { s64(now * 0.016 + ph) * 0.12 * stress * (1.0 - walk) } else { 0.0 };

        // facing: where you're going, else the station / adversary rules
        let mut ry = if inp[WALKABLE] != 0.0 { inp[GYAW] } else { inp[BASE_ROT] };
        if walk > 0.3 {
            ry = st[HEADING];
        } else if inp[LEGACY_TURN] != 0.0 {
            ry += PI;
        } else if stress > 0.12 && hive_vis != 0.0 {
            ry = (hive_x - st[X]).atan2(hive_z - st[Z]);
        }
        let dy = ry - st[YAW];
        let mut w = dy.sin().atan2(dy.cos());
        if w < -PI + 1e-3 {
            w += 2.0 * PI; // a half turn always goes the positive way (deterministic across f32 / f64)
        }
        st[YAW] += w * (dt * 5.0).min(1.0);
        if inp[SHAKE_START] != 0.0 {
            st[SHAKE] = 0.7;
            inp[SHAKE_START] = 0.0;
        }
        if st[SHAKE] > 0.0 {
            st[SHAKE] -= dt;
            st[YAW] += s64(now * 0.045) * 0.09;
        }

        // arms: idle swing -> typing at the desk -> walking swing -> the event pose
        let idle = s64(now * 0.0018 + ph) * (0.07 + 0.3 * stress);
        let (mut rx, mut rz) = ([idle, -idle], [-0.35f32, 0.35]);
        if inp[OFF] == 0.0 && inp[HAS_DESK] != 0.0 && inp[NO_TYPE] == 0.0 && inp[AT_DESK] != 0.0 && walk < 0.3 {
            let j = s64(now * 0.02 + ph) * 0.05;
            rx = [-0.8 + j, -0.8 - j];
            rz = [-0.15, 0.15];
        }
        if walk > 0.05 {
            let a = stride.sin() * 0.5 * walk;
            rx = [-a, a];
            rz = [-0.25, 0.25];
        }
        let mut lean = 0.0;
        if inp[POSE_START] != 0.0 {
            st[POSE] = inp[POSE_KIND];
            st[POSE_T] = 1.8;
            inp[POSE_START] = 0.0;
        }
        if st[POSE_T] > 0.0 {
            st[POSE_T] -= dt;
            if st[POSE_T] <= 0.0 {
                st[POSE] = 0.0;
            } else {
                match st[POSE] as i32 {
                    1 => { rx[0] = -1.5; rz[0] = -0.1; }
                    2 => { rx[0] = -2.3; rz[0] = -0.55; }
                    3 => { rx[0] = -1.05; rz[0] = -0.1; lean = 0.12; }
                    4 => { rx = [-0.9, -0.9]; rz = [-0.2, 0.2]; }
                    5 => { rx[0] = -0.6; rz[0] = -1.1; }
                    _ => {}
                }
            }
        }
        let k = (dt * 7.0).min(1.0);
        st[RX0] += (rx[0] - st[RX0]) * k;
        st[RZ0] += (rz[0] - st[RZ0]) * k;
        st[RX1] += (rx[1] - st[RX1]) * k;
        st[RZ1] += (rz[1] - st[RZ1]) * k;

        // instance matrices
        let s = inp[SCALE];
        let pitch = inp[SLUMP] + if inp[TURNED] != 0.0 { 0.14 } else { 0.0 } + lean;
        let fig = compose([st[X], st[Y] + inp[GY_OFF] + bob, st[Z]], [pitch, st[YAW], sway], [s, s, s]);
        let tr = inp[TORSO_R];
        put(&mut e.torso, i, &mul(&fig, &compose([0.0; 3], [0.0; 3], [tr, 1.0, tr])));
        let hr = inp[HEAD_R];
        put(&mut e.head, i, &mul(&fig, &compose([0.0, 2.25, 0.0], [0.0; 3], [hr, hr, hr])));
        let legsw = stride.sin() * 0.55 * walk;
        put(&mut e.leg, 2 * i, &mul(&fig, &compose([0.42, -0.6, 0.0], [legsw, 0.0, 0.0], [1.0; 3])));
        put(&mut e.leg, 2 * i + 1, &mul(&fig, &compose([-0.42, -0.6, 0.0], [-legsw, 0.0, 0.0], [1.0; 3])));
        let aw = inp[ARM_OFF];
        let arm_r = mul(&fig, &compose([aw, 1.5, 0.0], [st[RX0], 0.0, st[RZ0]], [1.0; 3]));
        let arm_l = mul(&fig, &compose([-aw, 1.5, 0.0], [st[RX1], 0.0, st[RZ1]], [1.0; 3]));
        put(&mut e.arm, 2 * i, &arm_r);
        put(&mut e.arm, 2 * i + 1, &arm_l);
        put(&mut e.phone, i, &mul(&arm_r, &compose([0.1, -2.25, 0.32], [-0.4, 0.0, 0.0], [1.0; 3])));
        e.pos[i * 4] = st[X];
        e.pos[i * 4 + 1] = st[Y];
        e.pos[i * 4 + 2] = st[Z];
        e.pos[i * 4 + 3] = st[YAW];
    }
}
