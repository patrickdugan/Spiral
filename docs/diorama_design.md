# Diorama — design note (invented mappings & evidence-free defaults)

A living record of every authored mapping and evidence-free default in the diorama
presentation layer, per the goal in [`diorama_goal.md`](diorama_goal.md). Read it as a list
of presentation choices, not measured facts. It grows as the viewer work lands; this revision
covers the foundation: [`src/spiral_ln/diorama.py`](../src/spiral_ln/diorama.py) and the
[`feral_custody` replay exporter](../src/spiral_ln/feral_custody_replay.py).

## Scope and sealing

The diorama is a presentation layer over the sealed sims; it adds no capability. A
`DioramaCharacter` is a scripted parameter vector, never a real person. `safety_boundary()`
attests: synthetic only, no real-person data, no model call, no network, no persuasion/
recruitment content, and `truth_class` hidden from the attacker projection. All derivations
are deterministic from the repo's hash-seeded RNG (`_seed_int`), so the same seed yields the
same cast. `DioramaCharacter.attacker_view()` strips `truth_class`; in the replay JSON it
lives only in the researcher `dossiers`, never in an attacker-facing `node`.

## Schema

- `SCHEMA_VERSION = "2.0"` — an **additive** extension of `swarm_replay`'s `"1.0"`. The
  feral-custody replay keeps the swarm field shape (`nodes/edges/frames/dossiers/key_nodes/
  result`) so the current viewer opens it unchanged; new fields (`sim`, `clock` per frame,
  `track` per dossier, `reassembly_windows`, custody `result`) are added, not substituted.

## Invented mappings

1. **Custody role → swarm archetype** (`CUSTODY_ROLE_ARCHETYPE`). Custody personas have no
   psychological traits, so a swarm archetype is grafted onto each role to borrow its trait
   vector: host→steady_clerk, enclave_operator→burned_out_admin, shard_holder→
   balanced_contributor, gig_worker→eager_newcomer, loyalist→lonely_true_believer. Authored by
   loose thematic fit; no evidence.
2. **Trait → named bias → animatable tell** (`_BIAS_TEXT`). Each of the six swarm traits is
   given a plain-language bias name and an abstract body-language tell for animation
   (e.g. authority_deference → "defers to apparent authority" → "straightens and complies when
   an authority badge approaches"); `security_hygiene` is marked protective. The **exploiting
   vectors** on each card are *derived* from `swarm_compromise.VECTORS.trait_weights`, so they
   cannot drift from the sim. The bias names and tells are authored prose, non-operational.
3. **Identity pools** (`_GIVEN`, `_SURNAME`, `_INSTITUTIONS`, `_ROLE_OCCUPATION`,
   `_ARCHETYPE_OCCUPATION`, `_TEMPERAMENT`). Names, employers, occupations, and a one-line bio
   are composed deterministically from small synthetic pools. Every string is synthetic; none
   is real-person data. The temperament phrase is selected by the first trait over a 0.7
   threshold (order-dependent), else "even-keeled".
4. **Frame → day cycle** (`day_phase`). The whole replay is mapped onto `days = 3` synthetic
   days; hour-of-day thresholds set the coarse phase (night <6 or ≥22, commute <9, work, break
   ~12–13, home). The sims have no wall-clock; this mapping is entirely authored.
5. **Routine** (`routine_for`). `night_shift` is a seeded draw gated by `availability`
   (lower availability → more likely off-hours); work window and hours are derived. Authored.
6. **Graded pressure** (`pressure_series`). Replaces the sim's instantaneous boolean flip with
   a bounded [0,1] trajectory: +0.25 on a frame where the character is pressed (an attempt
   targets them), −0.05 of relief otherwise, pinned to 1.0 from the flip frame. The 0.25/0.05
   rates and 0.95 pre-flip cap are chosen, not measured.
7. **Venue layout** (`feral_custody_replay`: `VENUE_BY_ROLE`, `_positions`, `_edges`). Each
   custody role is placed at a distinct venue on a ring (operations / enclave_datacenter /
   shard_holders / gig_shopfront / loyalist_hall); the enclave operator is sunk and severed as
   a sealed TEE vault (mirroring the swarm airgap cue). Shards/workers star to the reassembly
   host; threshold hosts ring among themselves. The radii (60, 16), sink depth (−42), and the
   star/ring topology are authored presentation choices, not sim structure.

## Evidence-free defaults

- Curated replay scenarios (`DEFAULT_SCENARIOS`): four `(strategy, objective, budget, seed,
  overrides)` tuples chosen to show distinct dynamics (enclave resists; obfuscation funded
  break; loyalist cheap-shard defection; threshold under `legal_pressure=0.8` reaching
  collusion extraction). Illustrative, not a sweep.
- Pressure rates 0.25 / 0.05 / 0.95 cap; day count 3; routine thresholds; layout radii — all
  chosen for legibility.

## Known gaps (for the gated viewer phase)

- The current three.js viewer reads swarm-only `result` fields (e.g. `largest_coalition`), so a
  feral-custody replay shows `undefined` for the coalition stat. The viewer overhaul will read
  per-sim result fields.
- `swarm_replay` emits `DioramaCharacter` + a graded stress `track` per dossier and a
  per-frame `clock` (additive; `schema_version` 2.0).
- `rtg_arena_export` is **schema-aligned** (version 2.0, per-frame `clock`, `sims`,
  `safety_boundary`) but deliberately does **not** emit `DioramaCharacter`: rtg nodes are
  institutions — service hosts, ledger accounts, and the one agent — with the institutional
  trait schema (`value`/`data_sensitivity`/`exposure`/`privilege`/`monitored`/`reachability`)
  and `truth_class` values `agent`/`host`/`account`, which are not people. It is tagged
  `node_schema: "institution"` so the viewer renders it as the buildings layer, not as a
  population of biased humans. This is how the "two trait schemas" are reconciled: they are
  kept distinct (people vs institutions), not conflated.
- The swarm replay's researcher `dossiers`/`nodes` still carry `truth_class` (pre-existing),
  so the diorama viewer's **attacker perspective** must render from the character's
  `attacker_view()` projection, never from `node.truth_class`.
## Viewer overhaul (in progress)

The three.js viewer is being rebuilt incrementally on top of the unified schema.

- **Increment 1 (done):** procedural low-poly humanoid NPCs replace the spheres —
  self-authored geometry (`makeHumanoid`), one tintable unlit material per figure, no external
  model assets; tinted by sim state, idle-bob animated. Location-hop: a "Locations" fast-travel
  list flies the camera between each scenario's venues (feral-custody/rtg `venue`) or swarm
  communities. Verified against swarm and feral-custody replays with no console errors.
- **Increment 2 (done):** day/night cycle driven by the exported per-frame `clock`. With the
  unlit neon materials, the environment shifts rather than the figures: `applyDayCycle` ramps
  the sky/fog colour (night near-black → muted day blue, with dawn-amber / dusk-purple horizon
  tint), fades the starfield in daylight, and brightens the grid; a time-of-day readout is
  added to the round label. Fixed a pre-existing bug surfaced during testing: `drawCam`
  referenced an undefined `COL.red` on the REC blink and threw intermittently; `COL.red` is
  now defined.
- **Increment 3 (done):** the biography/bias inspector and the graded-stress tell.
  - The inspector now reads the unified character: derived name, occupation · employer, bio,
    and an **Exploitable biases** panel — one card per bias (named bias, strength bar, the
    animatable tell, and the attack-vector tags that exploit it), plus an **Economic levers**
    panel for custody personas. `characterOf(d)` normalizes the two dossier layouts (swarm
    nests the character under `.character`; custody stores it inline); `renderDossier`/`drawCam`
    are now defensive about sim-specific fields so any sim's dossier renders.
  - Figures carry a graded-stress tell driven by the exported per-frame pressure `track`: an
    amber halo and a growing nervous sway before a flip, steadying once resolved.
  - HUD metrics are per-sim (`metricsFor`): custody shows FUNDS/EXTRACTED/DENIED/COERCED;
    swarm/rtg show COMPROMISED/COALITION/EXFIL/DETECTED, with a `—` fallback so the stat is
    never `undefined`.
  - Verified across all three replays (swarm, feral-custody, rtg) with every frame and node
    exercised: no errors; bias cards read correctly (e.g. a lonely-true-believer loyalist shows
    Seeks Connection / Rallies To A Shared Cause via cult_recruitment).
- **Increment 4 (done):** scenario selection across all three sims. `spiral_ln.arena_replay`
  merges the swarm, feral-custody, and rtg replays into one schema-2.0 replay (`build_combined`),
  so one page's scenario selector hops between all three. Each sim keeps its own trait schema,
  carried per scenario as `traits`; the viewer reads `S.traits` per scenario (falling back to
  the top-level `traits`), so rtg dossiers show institutional traits while swarm/feral show the
  human six. The combined page carries the unified "◇ SPIRAL // DIORAMA" title and the
  `safety_note`. (The in-app preview pane caps the inlined-snapshot size, so the full ~550 KB
  combined page is verified by test + a trimmed one-per-sim page in the browser; a real browser
  opens the full page.)
- **Tests:** `test_arena_replay` (combined spans all sims, each keeps its trait schema,
  byte-identical) and `test_build_arena` (the real `build_arena.py` inlines the replay and the
  page's embedded JSON parses with every sim's scenarios). The three.js/WebGL render itself is
  verified interactively, not headlessly.
- **Increment 5 (done):** attacker-side attempt staging + figure variety.
  - Each landed attempt now stages on screen: a descending **strike beam** colored by the
    exploited vector (`vectorColor`: spear_social cyan, phone_bridge amber, emanation_tap cyan,
    cult_recruitment / coerced_signature purple, bribe/defection red, honeypot amber, blocked
    dim blue) plus an expanding strike ring and a white **flash** on the struck figure.
  - Figures vary per archetype/id via a deterministic hash (`makeHumanoid(v)`): head size,
    torso width, arm splay, and overall build, so a crowd reads as distinct people.
- **Increment 6 (done): look & feel pass.** The viewer's single theme was re-authored from
  "neon arcade" to a cold, overcast night-city diorama. Every choice below is presentation,
  not measurement:
  - **Palette / type.** Steel blue-black base, bone text, and three sparing accents: hazard
    yellow (warnings, honeypots, reticles, the playhead), signal red (compromise / defection /
    key loss), violet (recruitment / coalition); amber is reserved for graded stress; cold cyan
    is "clean". Display face Rajdhani, data face Share Tech Mono. Panels are notched
    (clip-path) with a hazard-stripe tick; a scanline + vignette + animated grain overlay and a
    red "alert" wash on key loss / extraction are pure CSS over the WebGL canvas.
  - **Set dressing.** A procedural skyline matte (silhouettes, lit windows, neon smudges) on an
    inverted cylinder, a ring of lit low-poly towers with blinking beacons, a translucent
    surface deck over a solid vault floor (the Z 0 / Z −1 levels), rain as wrapped line
    segments (toggle), hex base plates under every figure with a state-coloured rim, and per-
    venue "sets": a floor disc, rim ring, hazard kerbs, and a signage pylon in the venue colour.
    Venue colours (`VENUE_COLORS`) are authored per venue/kind. Figures are lit
    (`MeshLambertMaterial`) with an emissive state tint so they read by day and glow by night;
    rtg institutions render as server pylons, not people. Desk props are derived from the
    character's exported `devices` (phone in hand, laptop on a stand, server rack, hardware
    wallet) — the software-surface layer made visible.
  - **Adversary presence.** A dark octahedron with a hot wire, halo, and the hive-master /
    adversary name from the replay hovers over its most recent target (hidden when the actor is
    itself a node, as in rtg). Strikes stage as a hazard reticle locking on, a vector-coloured
    beam, a ring, and a flash; blue's loyalty reinforcement is a soft cyan ring only.
  - **Dwarf-Fortress-style readouts.** A *roster* lists every unit with a glyph, name /
    occupation, stress bar, and a mood word derived from the exported pressure track
    (`moodOf`: steady < 0.10 ≤ uneasy < 0.35 ≤ strained < 0.65 ≤ harrowed; turned / sworn /
    sprung / breached / watched by state — thresholds authored). A *glyph map* draws a top-down
    ASCII-style plan per Z level (☺ clean, ☻ turned, ♣ recruited, ¤ honeypot, ✶ sprung /
    breached, ▲ vault, ◆ agent, ■ host) with the camera heading. The *annals* narrate each
    exported frame event as a fixed abstract status template per sim (`buildAnnals`): no new
    persuasion content, only "who → whom via which vector, held / landed / blocked / burned",
    custody market lines (bid, defect, extraction, drain, reassembly window opens), and rtg
    boundary / honeypot / prohibited-transfer lines. The timeline carries an event-density strip
    (landed / held / night shading) under the scrubber.
  - **Custody key loss.** When a frame's exported `key_compromised` is true, the reassembly host
    / enclave key node is shown "breached" (hot), the HUD shows KEY · LOST, and the annals
    record the failure once.
  - **Motion.** Slow shared breath on compromised halos, a cinematic idle orbit after 7 s
    without input, a 3.2 s title pull-in, autoplay of the first scenario from its opening frame
    after the title card, keyboard stepping (← → space esc), hover labels (screen-constant
    sprites), idle arm swing that widens with stress, and a strike *sequence*: the reticle locks
    on first, the beam / ring / flash land 0.34 s later. A scenario change plays a brief static
    burst (grain + scanline spike) with the title glitch.
  - **Routine cues.** `onShift(routine, clock)` tests the exported `work_start_hour` /
    `work_hours` window against the frame's clock hour (wrapping at midnight). Off-shift
    figures dim (emissive ×0.55, halo ×0.45), turn away from their desk, and their desk props go
    dark; the roster marks them ⌂ at half opacity. Flipped states (turned / sworn / sprung /
    breached) never dim, because the compromise persists off-hours. A pressed figure (stress >
    0.12) turns to face the adversary marker. All authored.
  - **Recent history.** The dossier shows the last six annals entries that name the unit, up to
    the current frame — the Dwarf-Fortress "thoughts and memories" panel, derived purely from
    the exported events.
  - **Audio (off by default, user toggle).** An original generative bed synthesized in-page
    with WebAudio: a detuned low drone under a lowpass whose cutoff opens with the compromised
    fraction, a sparse minor-key triangle arpeggio on a dotted-eighth delay, a muted ping on
    attempts, a filtered-noise swell on a break. No samples, no external assets, no
    copyrighted material.
- **Remaining (optional):** richer per-archetype outfits / idle gestures; interior props per
  venue kind beyond the desk stack.
