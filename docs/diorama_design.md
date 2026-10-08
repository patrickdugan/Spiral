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
- **Remaining (optional):** venue set-dressing / interiors; attacker avatars (the hive master
  as an embodied figure); richer per-archetype outfits.
