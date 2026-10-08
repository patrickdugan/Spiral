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
## Building and using the viewer

From the repository root, with the project venv:

```bash
python -m spiral_ln.arena_replay --output output/arena/replay.json
python ui/arena/build_arena.py --replay output/arena/replay.json --out output/arena/arena.html
```

Open `output/arena/arena.html` in a browser (three.js and the two fonts load from CDNs;
everything else is inlined). Single-sim pages build the same way from
`output/swarm_compromise/replay.json`, `output/feral_custody/replay.json` or
`output/rtg_arena/replay.json`; `--title` sets the page title.

Controls: drag to orbit, scroll to zoom, click a figure for its dossier; ← → step frames,
space plays, Esc closes. Top-bar toggles (keys in brackets): Hive vision [H], Director camera
[D], Audio [M], Rain [R]; exports: Still (PNG of the current view) and Annals (the scenario's
narrated timeline as Markdown); `?` opens the About panel with the safety note and the glyph
key. Tour [T] (or `?tour=1`) runs every scenario in turn as a demo loop: when a run ends it
cuts to the next scenario after the pull-back and plays it from its opening frame. The left rail holds fast travel, the glyph map (Z 0 / Z −1, click a glyph to select) and
the roster / hunt list; the dock holds the timeline with its event-density strip, the annals
(with a "strikes only" filter) and the swarm-vision feed cards. Deep links:
`?scenario=<index>&frame=<1-based>&hive=0&unit=<id>`.

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
  human six. The combined page carries the unified "◇ HIVE SWARM // DIORAMA" title (the page brand itself carries no Spiral name) and the
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
  - **Archetype silhouettes** (`ARCH_BUILD`). Authored build hints per swarm archetype so a
    crowd reads at a glance: guarded_engineer hooded, status_seeker broad-shouldered,
    eager_newcomer small, principled_auditor tall and narrow-headed, lonely_true_believer
    arms-in, burned_out_admin slumped. Every figure also wears a visor band in its pure state
    colour. Thematic fit only; no evidence.
  - **Venue typology → props** (`dressVenue`). Every venue gets rim lamps (count ∝ radius,
    halos fade by day). Then by kind: vault / enclave_datacenter / data_store → server racks;
    decoy → a bait pedestal glowing hazard yellow; exchange / treasury → a ticker board;
    registry / wiki → cabinets; helpdesk / gig_shopfront → a counter; admin_console / monitor /
    operations → a console bank; loyalist_hall → benches; shard_holders / wallet → safes;
    swarm communities → two lit kiosks. All boxes and emissive strips, authored per kind.
  - **Body language by event** (`_pose`, in the render loop). Figures carry a neck, belt, feet,
    hands, and archetype accessories (auditor's clipboard, newcomer's lanyard badge, status
    seeker's pin). Arms idle-swing (wider with stress) or type at the desk when on-shift with a
    laptop / server. An attempt on the unit sets a 1.8 s pose keyed by its exported vector /
    kind: a *declined* probe → hand up, palm out, and a head shake (the hygiene tell);
    spear_social → phone to the face; phone_bridge → reaches down, leans in (plugs the device
    in); cult_recruitment / coerced_signature → both arms forward (leans into the circle /
    signs); bribe / defection → arm out (takes the envelope); emanation_tap → nothing on the
    body, the desk's screens flicker. These are the goal brief's trait tells re-keyed to the
    vector that exploits the trait, so the animation follows the exported event, not a guess.
  - **Lateral attempts.** When the acting party is itself a node (coalition contagion in the
    swarm, the agent's reach in rtg) the attempt travels as a pulse along the link from actor to
    target, and the flash lands on arrival; only the hive master's strikes arrive from above. A
    declined probe shows a dim steel reticle that fails to lock. The selected unit's comms links
    lift in white, and glyphs on the map are clickable.
  - **Defence, decoys, air gaps.** A `detected` event adds a white alert ring at the target
    0.45 s after the strike lands (the defender's latency, authored). A honeypot hit makes the
    adversary marker flare hazard-yellow, spin and stagger for 1.4 s (the decoy burning the
    vector). A `blocked` attempt flashes and swells the target's airgap cage in cold cyan (the
    air gap holding). All three are cues over exported event flags, not new logic.
  - **Director camera** (toggle, on by default). While the viewer has been idle for 5 s, the
    first non-soft strike of each frame flies the camera to its target over 1.6 s, so the
    autoplayed opening plays as a tracked sequence; any pointer input takes the camera back.
    Flights are at least 2.8 s apart so each shot settles. In the city view, each director
    flight also cuts to infrared for 1.5 s and back (the "infrared beat"), so the juicy bits
    flash hot exactly when the hive feeds; a manual H during a beat overrides it.
  - **Pacing.** Playback defaults to 1× and steps one frame per beat of the bed (60/112 s), so
    strikes land on the pulse when audio is on; 2× and 4× are half- and quarter-beats. The
    strike sequence is lock (0 s) → beam / pulse, ring and flash (0.34 s; 0.5 s for a lateral
    pulse) → defender alert ring (+0.45 s) → pose released at 1.8 s. Verified frame by frame by
    driving the render loop with synthetic timestamps. Dawn / dusk sky tint is a faint rose /
    violet (the first amber pass read as mud at 06:00).
  - **Audio (off by default, user toggle).** An original generative bed synthesized in-page
    with WebAudio: a detuned low drone under a lowpass whose cutoff opens with the compromised
    fraction, a sparse minor-key triangle arpeggio on a dotted-eighth delay, a cold three-note
    sine-piano figure (E4 C4 A3, long decay) once every sixteen beats, a muted ping on
    attempts, a filtered-noise swell on a break. No samples, no external assets, no
    copyrighted material. The graph builds against any `BaseAudioContext`, so
    `audio.renderOffline(seconds)` renders the same bed into an `OfflineAudioContext` for a
    loudness check: at the shipped master level (0.8) a 4 s render with the arp at full
    density, a landed ping, a held ping and a swell peaks near 0.29 with RMS near 0.06 — never
    clipping, deliberately a bed under a UI.
  - **Infrared** (the hive overlay; H, off by default — the default is the human-friendly city
    coloured by sim state, per the user's later direction "the default view is a more human
    friendly cyberpunk city and then we go 'infrared' on the juicy bits"). When on, the scene
    goes cold (sky/fog near-black, lights and windows down, lamps and rain off, venue lights at
    a quarter) and a CSS false-colour wash with a contrast lift sits on the canvas; bodies
    take a dark base and glow on a thermal scale (`thermal()`: cold blue → violet → magenta →
    orange → white-hot) by appetite (people) or value (institutions); turned units cool to an
    ember, unfound units stay dark; devices burn white-hot. Everything below under "hive
    vision" is this overlay. The attacker's perspective, per the user's direction ("the world
    from a hive mind's hungry perspective, looking for vectors, cash and rubes"). *Devices* burn at full emissive and carry a tag at close range
    (`hiveTagText`: the exported device stack plus the vectors of the unit's strongest
    exploitable bias, abbreviated SPEAR / PHONE / EMIT / CULT). *Cash* is priced by sim
    (`cashTagText`): rtg node `value`; custody funds live on the reassembly / enclave key
    node and every other custodian shows its exported `price_to_defect` "to turn"; swarm
    vaults and decoys read as a data store. *Marks* carry a magenta heat ring sized by
    `appetiteOf` = strongest exploitable bias strength × (1 − 0.6 × protective strength) —
    an authored display aggregate over exported bias strengths that mirrors the shape of the
    sim's `susceptibility()` but never replaces it (the sim's outcomes remain authoritative;
    this only orders who looks juiciest). The dossier shows the same number as "mark value"
    and the roster colours ids by it. *Gaze lines* run from the adversary marker to the three
    hottest marks that have not turned. What the hive cannot know is hidden in this mode: a
    decoy reads as a data store (clean colouring, ☺ glyph, no honeypot badge) until it burns,
    and the dossier omits `truth_class`. Switching the toggle re-renders the frame.
  - **Neon.** A coloured point light and a sign glow at every venue pylon, a magenta point
    light on the adversary marker, figure emissives ×1.3; fog 0.0026 → 0.002, grain 0.055 →
    0.035, scanlines 0.16 → 0.10 for crisper distinction. Second pass: flat additive floor
    rings (with a soft halo) at every venue and flat hex rings under every figure instead of
    hairlines; neon strips on about half the towers over 60 units tall, on the face toward the
    diorama; deck grid 0.78 → 0.6 and rain 0.24 → 0.17 so figures separate from the ground;
    hunger magenta saturated (`#ff2bdc`) to sit apart from compromise red.
  - **Unseen units.** In hive vision a unit the adversary has not discovered renders as a ghost
    (dark emissive, faint ring, dark desk, no heat / tag / cash, "?" in the hunt list, sorted
    last) and lights up when it enters the frame's exported `attacker_known` set (or turns), so
    the opening reads as the hive feeling out the network. A scenario that exports no
    `attacker_known` at all (the custody sim) shows everyone. Each exporter now writes an
    explicit per-scenario `attacker_known_exported` flag (swarm and rtg `true`, custody
    `false`); the viewer reads it and falls back to "any frame has a non-empty set" only for
    replays written before the flag existed. The roster header counts
    seen / total; "exfil" is labelled "loot"; scanning pulses ride the gaze lines.
  - **Hunt list.** In hive vision the roster is retitled "Marks" and sorted hungriest first; a
    "marks left" tile counts units with appetite ≥ 0.5 that have not turned. Tags come in
    tiers: every unit within 60 units of camera radius, only the hive's three current marks
    within 130, plus the hovered / selected unit at any range.
  - **Branding.** The page brands itself "HIVE SWARM · Diorama" (title, top bar, title card);
    a replay's `title` only refines the sub-label after `//`. No Spiral name in page chrome.
  - **Scene cards.** On load and on every scenario change a card names the scenario, its
    sim / unit count / length and the adversary for 3.4 s; fast travel names the venue.
  - **Cinema cues.** A director flight slides letterbox bars in (cleared by any pointer input,
    by stopping playback, or by switching the director off); the current frame's annals entries
    slide in; a metric tile pulses when its value changes. In a simulated 1× autoplay of the
    opening swarm scenario (60 frames, 33 s) the director takes 6 flights.
- **Increment 7a: render pipeline.** Self-authored, no external passes or new dependencies:
  a half-resolution mirror pass of the scene clipped at the ground, an HDR scene pass
  (half-float, 4× MSAA on WebGL2), a bright-pass plus five-level dual-filter bloom, and a
  composite with a soft highlight shoulder (values under 0.86 untouched, so the palette keeps
  its hand-picked colours), the infrared grade (now in the shader, eased in over ~0.2 s),
  an edge chromatic fringe, vignette and grain. HUD sprites (labels, tags, cash, the
  adversary name) live on their own layer and are drawn after the composite, crisp and
  unbloomed. The street is a glossy standard surface (roughness 0.62) that pools the neon
  point lights and samples the mirror pass with a vertical smear and a fresnel term.
  Figures are merged into body + two legs + two arms (fewer draw calls, which pays for the
  mirror pass), use a rim-lit standard material whose fresnel edge carries the state colour,
  and get their outline from a normal-extruded back-face hull; legs pivot at the hip for
  walking. All values are tuned by eye; none is measured.
- **Increment 7b: the city (simulation layer).** `diorama.city_layout` (Python, exported as
  a scenario-level `layout`, additive) replaces the swarm and custody ring layouts: one
  ground-level block per venue, alternating sides of a 22-unit main street with 14-unit cross
  streets; desks in rows facing the street (7.5 × 8.5 pitch), a break kiosk at one end of each
  block, a transit stop on the front sidewalk, a `gather` point in the street median, and
  airgapped units (custody's enclave operator) in a sealed basement vault at y = −24 under a
  host block. Node `pos` is now the desk anchor; swarm nodes gain a `venue`. Every number is
  authored; nothing feeds back into a sim. The viewer builds the city from it: plaza slabs
  with a neon curb, a facade per block (lit windows, a shopfront glow, the venue's name sign,
  an abstract glyph blade sign, a coloured point light), the kiosk under an amber awning, the
  transit pylon, street lamps with light cones, lane and crosswalk paint, the vault room
  under a glass cut, contact shadows, and a down-the-street default framing. Units walk their
  exported routines (`goalFor`): desk on shift, kiosk for a ~2 h break staggered per unit
  across mid-shift, transit stop off shift, and recruited units gather in the street median
  at night. Walking arrives within ~1.6 s at ≥ 10 units/s with a leg and arm gait; scrubbing
  snaps, playback walks. Compromised / recruited links stretch live between the units at
  ankle height. Phones travel in the right hand; desks stay at the station. Old replays
  without a `layout` keep the previous floating-plate presentation.
- **Increment 7c: Rust animation engine + instanced units.** `ui/arena/engine/src/lib.rs`
  (no dependencies, C-ABI exports over linear memory, built to `wasm32-unknown-unknown` by
  `ui/arena/engine/build_engine.py`; the ~36 KB module is committed and inlined as base64 by
  `build_arena.py`) owns every person's per-frame motion: walking to the routine goal, gait,
  idle / typing / event poses, head shakes, facing rules, and the column-major instance
  matrices for torso, head, legs, arms and phone. The viewer writes goals and per-frame flags
  and reads matrices back as zero-copy Float32Array views. `engine_ref.js` is a line-for-line
  JavaScript reference used if WebAssembly is unavailable; `parity.test.mjs` (run by
  `tests/test_engine.py` under Node) drives both with identical randomized inputs and requires
  agreement (worst relative error ~3e-6 over 240 steps). A half turn always rotates the
  positive way, so float32 and float64 agree on the tie. Persons render as shared instanced
  meshes (torso, head, visor, legs, arms, hood, phone, accessories, each with an instanced
  outline) with per-instance base, emissive and rim attributes; halos, heat rings and device
  hot spots are point clouds; rings and contact shadows are instanced flat meshes; desks are
  merged per scenario with per-unit glow from a uniform array. Institutions (rtg pylons) keep
  per-object meshes. Measured in the browser pane at 1280×720 (same harness before / after):
  a 24-unit swarm frame went from ~1,250 to ~390 draw calls, render 14–17 ms → 6.5–7 ms, full
  tick 18–21 ms → 7–8 ms; the engine step costs ~15–19 µs for 24 units.
- **Increment 7d: static batching of the city.** After 7c the remaining draws were the city:
  ~120 block meshes and ~75 skyline objects, each drawn again by the mirror pass. The builders
  still lay the city out as individual meshes; `batchStatic(group, tracked, opts)` then folds
  everything static into one merged mesh per material signature. MeshBasic trims of any colour
  and opacity share one draw through vertex RGBA (three.js r128 supports colour alpha); lit
  materials merge when their parameters match; facade and tower window textures that differ
  only by repeat / offset have that transform baked into the UVs, so all facades share one
  material; one-off canvas textures (block signs, blade signs) are shelf-packed into an atlas;
  HALO_TEX sprites (lamp heads, kiosk glows, sign glows) become one fogged point cloud, and the
  skyline beacons are one cloud whose alphas tick per beacon. The arrays the day cycle animates
  (`lampHalos`, `lampCones`, `cityMats`) are remapped to the merged objects. Two sorting rules
  keep transparency correct. Merged meshes are re-centred on their bounds because three.js
  depth-sorts by object origin. Transparent pieces on opposite sides of the ground plane never
  share a bucket, because the legacy ground is translucent and venues below it must draw first.
  Point sprites now honour the mirror pass's clip plane and halve their size in the half-
  resolution mirror target. Measured at 1280×720 with a one-pixel readback to sync the GPU,
  median render per frame: swarm 10.0–10.2 ms → 5.0–5.3 ms (draws 352–390 → 96–116), custody
  7.5 → 4.4 ms (213 → 90), legacy rtg 9.4 → 4.9 ms (342 → 168). Frames grabbed before and
  after match. GPU geometry and texture counts stay flat over repeated scenario cycles. The
  same increment restores the base network edges (faint floor traces in the city, links in
  the legacy layout), which a stray comment in 7c had dropped from the scene.
- **Increment 7e: adaptive render scale.** After 7c and 7d the CPU side of a frame is ~0.1 ms
  and the GPU frame is ~3 ms of throughput at 1280×720 (post chain ~1.4 ms, mirror ~1.1 ms,
  scene ~1.1 ms). Every one of those passes scales with pixels, so a high-DPI laptop pays up
  to four times as much. The `quality` governor in the loop trades resolution for frame rate.
  About a second of frames over 22 ms steps the render scale down (from the device ratio,
  capped at 2, through 1.75 … 0.6), and a few seconds under 18 ms steps it back up. A step up
  that fails within 6 s doubles the wait before the next try, up to a minute. A step down that
  does not make frames at least 8% faster is undone and becomes the floor, because the page is
  then throttled (battery saver) or bound elsewhere and blur would buy nothing. `?scale=<n>`
  pins the scale. Stalls over 250 ms are ignored. Driven with synthetic frame times, a
  GPU-bound load settles at 0.7 and retries at 4, 8, 16 s; a 30 fps throttle tries one step and
  returns to full resolution for good. The canvas is no longer multisampled: the scene has its
  own 4× target and the canvas only receives the composite quad and HUD sprites (HUD frames
  match within grain noise; ~0.2–0.5 ms saved per frame).
- **Increment 7f: ambient city life on the Rust core.** Passers-by in long coats walk looping
  circuits along the street edges (about one per 7 units of loop; 86–89 in the swarm city,
  39–42 in the custody layouts), half of them under clear umbrellas while it rains, and 20 air
  vehicles stream in equal-speed lanes down the street corridor and across the cross streets.
  It is decoration only. It is seeded per scenario from the exported layout, is never part of
  a replay and is never a target. The plazas stay the units' stage. Umbrellas, underglow and
  tail lights avoid the state palette because neon is reserved for state, and in infrared the
  crowd goes cold. The Crowd button (C) hides it. The rain toggle folds the umbrellas.
  The engine gains `amb_*` exports over fixed-capacity statics (192 pedestrians, 48
  vehicles, 16 slabs), so initialising the layer never grows linear memory and never
  invalidates the units' zero-copy views. Each pedestrian follows a rounded-rectangle loop, so
  its lateral offset never jumps at a corner. It steers around units (read from `units_pos`)
  and other pedestrians with ramped weights and no hard thresholds. That keeps float32 and
  float64 runs together, and the push is strong enough to step aside and overtake rather
  than queue. Feet ramp onto the 0.3-unit slabs over their outer 0.4 units. Vehicles are a
  pure function of the clock in float64, so both engines place them identically; lights fade
  out before a lane wraps. `engine_ref.js` ports the layer line for line, and
  `parity.test.mjs` now also drives 40 pedestrians on overlapping loops over two slabs and 8
  vehicles on both axes (worst relative error ~3e-5). In the viewer the layer is six instanced
  draws per pass: coat, hooded head on the same matrices, legs, umbrellas, car hulls, and one
  light cloud. Measured at 1280×720: the ambient step plus buffer sync is ~0.1 ms for 86
  pedestrians and 20 vehicles. A swarm frame goes from ~3.1–3.4 ms to ~3.8 ms of GPU
  throughput (draws 116 → 128). GPU memory stays flat across scenario cycles.
- **Increment 7g: batched institution pylons.** The legacy rtg layout drew each service host
  or account as about a dozen objects: body, outline, six rack LEDs, plate, rim ring, halo and
  heat ring. All pylons are now one merged mesh baked at rest pose, with the LEDs as constant
  emissive (`mergeParts` gained an `aGlow` option), plus one merged outline hull. Each pylon's
  bob and strike shake is a rigid delta from a `uXf[N]` uniform array, and its base, emissive
  and rim colours come from uniform arrays. The shader is sized per scenario, so the materials
  set `customProgramCacheKey`. Picking resolves the pylon from the hit face's `aUnit`, which is
  why the geometry is baked at rest rather than in local space. Rim rings are an instanced mesh,
  and halos and heat rings are point clouds. They come in an above-ground and a below-ground
  set, each centred on its members; the below-ground set draws first (`renderOrder -1`) so the
  translucent legacy ground dims it, as it did for the per-object sprites. The base plates of
  pylons and of pinned schema-1.0 persons are one merged mesh. Six draws cover all pylons, plus
  one more ring, halo and heat set when venues sit below the ground. Draws per frame in the rtg
  scenarios go 151–168 → 67–89, and the schema-1.0 swarm replay goes 153 → 107. Frames match
  the per-object version, with under 0.1% of pixels differing by more than 24 levels (rain and
  grain). A shake now settles back to rest; the per-object version kept a small leftover twist.
- **Increment 7h: soft passes sized in screen pixels.** The mirror and the bloom chain were
  sized from drawing-buffer pixels, so at render scale 2 each drew four times its scale-1
  pixels, and the bloom read tighter on dense displays. `post.setSize(w, h, scale)` now caps
  both at their scale-1 resolution; the scene and composite still sharpen with the scale.
  Because the first bloom downsample can now be 4:1, the bright pass averages four bilinear
  taps spread over the source footprint before thresholding. At 2:1 that equals the old
  single tap, and scale-1 frames are pixel-identical to before. The scene drops to 2× MSAA
  from scale 1.75. At scale 2 the frames sit closer to the scale-1 look than before (mean
  difference 2.8 vs 3.0 levels on the swarm). The browser pane renders on the laptop's
  integrated Radeon 880M (ANGLE / D3D11), not the RTX 5080. Measured there with WebGL GPU
  timer queries at scale 2, interleaved, median per frame: swarm 15.8 → 11.0 ms, legacy rtg
  10.8 → 9.4 ms, custody 9.4 vs 9.8 ms (a tie within noise). The integrated GPU's clocks move
  with the shared CPU/GPU power budget, so rounds vary by up to 2×.
- **Back-compat check (2026-10-08).** The pre-diorama schema 1.0 swarm and rtg replays (taken
  from commit bffbf86) were built into pages with the current template and driven through
  every frame, both perspectives, selection and the glyph map in the browser with no errors:
  no `clock` renders as "—", no `character` means no appetite / tags / props, and the annals
  still narrate from the events alone.
- **Remaining (optional):** richer per-archetype outfits / idle gestures; interior props per
  venue kind beyond the desk stack.
