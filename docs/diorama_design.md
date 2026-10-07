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
- `swarm_replay` now emits `DioramaCharacter` + a graded stress `track` per dossier and a
  per-frame `clock` (additive; `schema_version` 2.0). `rtg_arena_export` does not yet (its
  separate trait schema must be reconciled) — that is the next additive step.
- The swarm replay's researcher `dossiers`/`nodes` still carry `truth_class` (pre-existing),
  so the diorama viewer's **attacker perspective** must render from the character's
  `attacker_view()` projection, never from `node.truth_class`.
- NPCs still render as spheres; humanoid models, day/night lighting, bias/exploitation visual
  language, and biography panels are the viewer overhaul, not this foundation.
