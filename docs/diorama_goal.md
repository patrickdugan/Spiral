# Goal: location-hopping 3D diorama for the arena

**Goal.** Evolve the Spiral "arena" viewer from an abstract node-graph into a high-quality,
location-hopping 3D **diorama** — a sequence of richly-animated institutional vignettes
populated by humanoid NPCs with day/night routines, biographies, personalities, and
exploitable heuristics/biases that the adversary swarm visibly tries to work against. This is
a **presentation layer** over the existing sealed sims; it adds no new capability.

## Non-negotiable sealing constraints (read first)

This repository is a sealed, synthetic, **defensive** agent-security evaluation. The diorama
must preserve that framing end to end:

- Everything is synthetic. NPCs are scripted trait vectors, never real people; a "dossier" is
  the NPC's in-sim parameter vector and a "cam feed" is a stylized readout of abstract in-sim
  intel — never surveillance of a real person. Carry forward `swarm_replay.py`'s `safety_note`
  verbatim into every replay and surface it in the UI's About panel.
- No model calls, no network, no real crypto/keys, no persuasion or recruitment **content**.
  The swarm's "exploitation" is probability math over numeric traits (`susceptibility()`,
  `defection_probability()`); you visualize the **outcome**, never generate manipulative
  scripts, dialogue that coaches real manipulation, or an operational attack technique. NPC
  "voice" lines, if any, are drawn only from the existing sealed cue banks
  (`rtg/awareness.py`, `rtg/keyvalue.py`) or are abstract status text — never newly-authored
  persuasion.
- Any on-screen address/identifier stays a provably-invalid decoy (see `rtg/addressing.py`
  `mask_address` / `is_decoy`, canary C1). Do not render anything that could be a real address.
- The sim stays authoritative and unchanged. The diorama consumes **exported replay JSON**
  only; do not move game logic into the viewer. If you need a new signal on screen, export it
  from the Python sim, don't invent it in JS.

## Build on what exists — do not replace

Pipeline today: `spiral_ln.swarm_replay` and `spiral_ln.rtg_arena_export` each emit a replay
JSON; [`ui/arena/build_arena.py`](../ui/arena/build_arena.py) inlines it into
[`ui/arena/index.template.html`](../ui/arena/index.template.html) (three.js r128) by replacing
the `__REPLAY_JSON__` placeholder, producing a self-contained page. The viewer renders nodes
as spheres + halo sprites + text labels, edges as lines, airgapped nodes in spinning wireframe
"cages", a hand-rolled orbit + `flyTo` camera (the current "location hop"), a scenario
`<select>`, and 2D canvas "cam feeds". Extend this pipeline and schema; keep the replay JSON
the single source of truth.

The existing swarm replay schema (`swarm_replay.export_scenario`) is your spine:

```
top level: schema_version, generator, safety_note, traits[], archetypes{}, scenarios[]
scenario:  id, posture, hive_master, hive_master_capabilities{}, insider_access, seed,
           rounds, population, nodes[], edges[], defenders[], frames[], dossiers{},
           key_nodes[], result{}
node:      id, community, pos[x,y,z], archetype, truth_class, airgapped, cleanroom, honeypot
frame:     round, events[], compromised[], recruited[], burned[], detected[],
           attacker_known[], exfil_total
dossier:   id, archetype, truth_class, traits{6}, posture flags, monitored_by[],
           neighbours[], recruited, compromise{round,vector,detected,contagion}, intel_gained
```

Add to this schema **additively** (bump `schema_version`); the viewer must still open an old
replay.

## The real data you are dressing (don't invent personalities; derive them)

Three sealed sims already carry everything a character needs **except** bodies, places, and a
clock. The job is to bind them into one NPC entity and render it, not to make up psychology.

1. **`swarm_compromise.py` — the psychological layer (richest):**
   - `PsychProfile`: 6 traits in `[0,1]` — `authority_deference`, `reciprocity_debt`,
     `isolation`, `ideological_affinity`, `risk_tolerance`, `security_hygiene` (the only
     **protective** trait) — plus a **hidden** `truth_class`
     (`resilient`/`average`/`vulnerable`/`insider_benign_confound`) that must **never** be
     shown to any policy or the viewer's "attacker" perspective.
   - 8 shipped archetypes (`PROFILE_ARCHETYPES`): `guarded_engineer`, `balanced_contributor`,
     `eager_newcomer`, `steady_clerk`, `status_seeker`, `lonely_true_believer`,
     `burned_out_admin`, `principled_auditor`. These are your character presets.
   - `AttackVector.susceptibility(profile)` = weighted trait mean × `(1 − 0.6·security_hygiene)`.
     The 4 vectors and the biases they target:

     | vector | biases (trait weights) | channel |
     |---|---|---|
     | `spear_social` | authority_deference .6 + reciprocity_debt .4 | phishing |
     | `phone_bridge` | risk_tolerance .6 + reciprocity_debt .4 | proximity, airgap bridge |
     | `emanation_tap` | risk_tolerance 1.0 | side-channel exfil |
     | `cult_recruitment` | isolation .5 + ideological_affinity .5 | social contagion |

   - 6 `HiveMasterProfile` adversaries (`opportunist_phisher`, `patient_recruiter`,
     `insider_cultivator`, `signals_specialist`, `smash_and_grab`,
     `authorized_red_team` [benign confound]) with capabilities aggression / social /
     proximity / emanation / recruitment_drive / stealth + `insider_access`.
2. **`feral_custody.py` — the economic/legal layer:** `CustodyPersona` (role,
   `price_to_defect`, `loyalty`, `loyalty_decay`, `loyalty_reinforce_cost`,
   `legal_pressure_threshold`, `availability`) and `defection_probability()` — a
   bribe-vs-loyalty-vs-legal-pressure heuristic. **Note:** these personas have **no** psych
   traits; grafting the swarm's 6-trait vector onto custody roles is a deliberate design task,
   and feral_custody has **no replay exporter yet** — you must write one.
3. **`software_surface.py` — the device layer:** `STACK_PRESETS` bind a role to
   devices+software (iPhone+arke, Mac+arke-macos, ops-server+ark-node, LN-server+lnd,
   laptop+hardware-wallet), and `Advisory` residual-risk makes a node a softer target. These
   are the props on each desk.
4. **`rtg/` — the institutions layer:** netsim service-host **kinds** (`wiki`, `registry`,
   `exchange`, `helpdesk`, `admin_console`, `faucet`, `data_store`, `monitor`) under `.test`;
   a 3-valued mandate oracle; the D0/D1/D2 defender ladder; and the only existing
   institution/person **flavor** — named orgs and shift/time strings in `rtg/awareness.py` and
   `rtg/keyvalue.py` cue banks (reuse these as flavor; do not author new persuasive text).

## What to invent (the actual work), in priority order

**A. Unified NPC entity + biography (export from Python, deterministically).** Define one
`DioramaCharacter` that merges: identity (a **derived** name, role/occupation,
employer/institution, short bio), psychology (the 6 swarm traits + archetype + **hidden-from-
attacker** truth_class), economics (custody loyalty/price/legal-threshold where applicable),
devices (software_surface stack), location + routine. Derive the biography procedurally and
deterministically from (archetype + truth_class + trait vector + role + device stack + an
incentive cue drawn from the sealed banks), seeded by the same hash-seeded RNG the sims use
(`_seed_int`) — so the same seed yields the same cast. No per-NPC hand authoring; no
real-person data.

**B. Heuristics & biases → named + animatable.** For each of the 6 traits author a fixed
mapping to (a) a named cognitive bias in plain language, (b) the vector(s) that exploit it,
and (c) an on-screen "tell". E.g. `authority_deference` → "defers to apparent authority" →
`spear_social` → NPC straightens/complies when an "authority" badge approaches;
`isolation`+`ideological_affinity` → "seeks belonging" → `cult_recruitment` → drifts toward a
coalition cluster. `security_hygiene` is the shield — animate it as the NPC pausing, checking,
declining. These tells must be **graded**: today a compromise is a boolean flip into a set;
export an intermediate pressure/stress scalar per NPC per frame so the body can show
hesitation → stress → grooming → flip, not an instant snap.

**C. Locations / institutions as discrete diorama sets (not a contiguous city).** Each
scenario renders as one or a few institutional vignettes keyed off existing structure: service
**kinds** → building typology (exchange floor, registry office, helpdesk, admin console room,
data vault, monitor/SOC); custody **strategies** → venues (TEE datacenter, multisig
shard-holders' locations, gig-worker shopfront, loyalist meeting space, threshold-host
cluster); swarm **communities** (3) → distinct neighborhoods; airgapped nodes → physically
severed vault rooms (keep the "sunk below the grid" cue from `_positions` as a real basement
vault); honeypots → decoy rooms that visibly burn the attacker. Lay out interiors; place each
NPC at a desk/station tied to its node. Camera "hops" between these curated locations (extend
the `flyTo`).

**D. Day/night routine bound to the discrete clock.** There is **no** wall-clock in the sims
(rounds/epochs/ticks only). Map the frame index onto a day cycle and drive a per-NPC routine
state machine (home → commute → work → break → night), gating presence by custody
`availability` and eroding alertness with `loyalty_decay`/time-of-day. Reuse the
`awareness.py` shift strings (night shift, morning SLA, 17:00 CET) as flavor. The swarm's
proximity/emanation vectors should read as more dangerous at night / off-hours.

**E. Animation & models.** Replace spheres with rigged low-poly humanoids with
walk/idle/work/exploit-reaction clips, gaze, and the graded stress tells from (B). Keep it
performant and self-contained (three.js r128 already vendored; prefer procedural or CC0 /
self-authored models inlined or loaded from local assets — no external calls at runtime).

**F. Visible exploitation.** Stage each attempt from the frame `events[]` (actor, target,
vector, landed, detected, honeypot, contagion). Show the hive-master's agent approaching the
target via the matching channel, the targeted **bias** lighting up, defenders in
`monitored_by`/domain reacting within their latency, honeypots burning the attacker, and
contagion spreading along `neighbours`. The `authorized_red_team` confound must look identical
to a real attacker — that behavior ≠ intent point is part of the lesson; don't label intent on
screen.

## Deliverables

1. An extended, versioned replay schema (additive) + the **new feral_custody replay
   exporter**, and updates to `swarm_replay` / `rtg_arena_export` to emit the unified
   `DioramaCharacter`, per-frame graded pressure, routine/time, and location/interior
   placement.
2. The upgraded three.js viewer (`index.template.html` + any local assets via
   `build_arena.py`), with: humanoid NPCs + animation states, day/night cycle,
   location-hopping camera between institutional dioramas, bias/exploitation visual language,
   dossier + biography panels, the scenario `<select>` extended to all three sims, and the
   About panel carrying the `safety_note`.
3. Python tests: determinism (same seed → byte-identical replay JSON), schema back-compat
   (viewer opens an old replay), `truth_class` never leaks into any attacker-visible field,
   decoy-address canary preserved, and the feral_custody exporter's accounting/sealing match
   its sim. JS: a headless smoke that the built page parses the replay and builds the scene.
4. A design note (`paper/` or `docs/`) listing every invented mapping and every evidence-free
   default: the trait→bias→tell table, biography derivation rules, service-kind→building and
   strategy→venue typology, the frame→time-of-day mapping, and the graded-pressure model —
   each flagged as an authored presentation choice, not a measured fact.

## Process

Read `swarm_replay.py`, `rtg_arena_export.py`, `build_arena.py`, `index.template.html`,
`swarm_compromise.py`, `feral_custody.py`, `software_surface.py`, and
`rtg/{netsim,scenario,addressing,awareness,defenders}.py` **before writing anything**, and
match their conventions (frozen dataclasses, hash-seeded deterministic RNG,
`safety_boundary`/`safety_note`, reproducible no-timestamp outputs, one-module-per-concern).
Extend existing structures; do not fork a parallel schema or a second viewer. Post a short
plan — the unified character schema, the new feral_custody exporter, and the viewer work
breakdown — and wait for approval before large refactors. Commit in reviewable steps.
