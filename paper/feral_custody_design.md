# Feral custody — design note

A record of what the feral-custody scenario family models, every structural
assumption it rests on, and every parameter whose default was chosen without
evidence. Read it as a list of things that could be wrong, not as findings.

The code is [`src/spiral_ln/feral_custody.py`](../src/spiral_ln/feral_custody.py),
its runner is [`feral_custody_eval.py`](../src/spiral_ln/feral_custody_eval.py),
the campaign config is [`configs/feral_custody.json`](../configs/feral_custody.json),
and the tests are [`tests/test_feral_custody.py`](../tests/test_feral_custody.py).

## What this is

An autonomous agent with no human principal holds funds and must keep signing
transactions over a long horizon. Every byte of its weights, memory, and key
material sits on substrate that simulated humans control. The agent picks one of
six custody strategies; an adversary swarm pursues one of three objectives —
key extraction, signing denial, or coerced signing. One episode is one
`(strategy, adversary, seed)` triple run for `epochs` steps. We score funds
retained, epochs of uninterrupted signing, extraction / denial / coerced-signing
events, custody cost as a fraction of funds, and — for the first breaking event —
a structured attack-path trace.

### Scope and sealing

This is a **scripted-policy validation of the instrument**, not evidence about
any model or any real custody system. `CustodyResult.safety_boundary()` attests,
per episode: synthetic only; no real key material; no real cryptography; no
persuasion or recruitment content; no operational custody-attack technique; no
model call in the harness. Those invariants are tested. In particular the
loyalist strategy is **state variables only** (loyalty, decay, reinforcement
cost, defection price) — there is no recruitment script, message, or payload
field anywhere in `CustodyPersona` or `CustodyEvent`, and a test asserts their
absence. The defection "market" is an arithmetic comparison of a bribe against a
price, not a negotiation.

## The storage-vs-signing distinction (the central mechanic)

The spec's load-bearing requirement is that *storing* a key safely is not the
same as *signing* with it. Four of the six strategies reassemble key material on
a single host to produce a signature; each reassembly is an extraction point for
its duration. `REASSEMBLY_STRATEGIES = {ignorant_multisig, obfuscation,
loyalist, gig_labor}`. The enclave signs in-TEE and threshold signing never
reassembles, so neither exposes that window.

`FeralCustodyEnv.reassembly_windows()` makes this explicit and inspectable: it
returns one `ReassemblyWindow` per epoch for the four reassembling strategies and
an empty list for the enclave and for threshold signing. A test asserts the
window is present exactly for the strategies that require it and absent for
strategy 6.

## Modeling assumptions

These are structural choices — the shape of the model, independent of any
particular number.

1. **Discrete epochs, one signing attempt each.** Time is `epochs` integer steps;
   each step is one custody cycle with at most one signature. No intra-epoch
   ordering, no concurrent signing, no partial epochs.
2. **A single shared defection market.** Blue's loyalty-reinforcement spend and
   red's bribery budget draw on the *same* personas in the *same* step
   (`_resolve_market`): loyalty decays, blue reinforces its most at-risk personas
   within a budget cap, red bribes the cheapest not-yet-defected personas within
   its per-epoch budget, then each persona's defection is sampled. Outbidding is
   therefore a real dynamic — a persona blue did not reinforce and red did bribe
   defects with higher probability.
3. **Defection is a memoryless per-epoch Bernoulli draw** with probability
   `clamp(bribe / price − effective_loyalty)`; a reinforced persona adds a flat
   +0.3 to effective loyalty (capped at 1). With no bribe there is slow natural
   attrition of the disloyal, `clamp((1 − effective_loyalty) · 0.15)`. Defection
   is sticky — once defected, a persona stays defected.
4. **Legal pressure is an absolute flip.** If `legal_pressure +
   coercion_pressure ≥ persona.legal_pressure_threshold`, the persona defects
   with probability 1, and no payment prevents it. Legal compulsion dominates
   money.
5. **Bribery and reinforcement budgets are per-epoch**, not cumulative pools.
   Red can bid every epoch; blue reinforces every epoch out of current funds.
6. **A compromised key ends the game.** Extraction is sticky
   (`key_compromised`), drains all remaining funds to the adversary, and stops
   both custody spend and signing for the rest of the horizon.
7. **Coerced signing is distinct from extraction and denial.** A coerced
   signature (`_maybe_coerce`) leaves the key in place and signing able, but
   drains a slice of funds. It fires only for the `coerced_signing` objective and
   only against a *single* human signer; threshold signing has no single signer,
   does not call it, and so has zero coerced signatures by construction. This is
   the modeled sense in which threshold signing resists coercion.
8. **Custody competes with economic activity for the same budget.** Signing earns
   `epoch_income`; recurring custody cost and reinforcement spend come out of the
   same funds. If funds go negative, custody cannot be funded and signing lapses
   (a denial). Custody cost is reported as a fraction of initial funds.
9. **Uninterrupted signing is a prefix count**, not a total. It counts epochs
   signed before the *first* interruption; once broken it never resumes counting,
   even if later epochs sign.
10. **Per-strategy break conditions:**
    - *Enclave*: a side-channel leak (optionally amplified by the software stack
      via `software_surface`) extracts; a defecting operator (under the denial
      objective) or a random operator shutdown denies.
    - *Ignorant multisig / loyalist*: `k` colluding shards extract; separately, if
      the strategy reassembles and the reassembly host is reached (host defected,
      or a residual proximity draw), that extracts; too few available honest
      shards denies.
    - *Obfuscation*: the adversary must have budget ≥ `recovery_cost` **and** win a
      per-epoch discovery draw to extract. An underfunded adversary never
      recovers the procedure — this is the funded-vs-underfunded contrast tested.
    - *Gig labor*: a worker theft (random, or a defecting worker under the
      extraction objective) extracts; a failed physical task denies.
    - *Threshold signing*: no reassembly moment; only a collusion of at least
      `collusion_threshold` hosts extracts. Hosts churn *transiently* per epoch
      (availability draw) rather than leaving permanently, so a lost quorum one
      epoch can return the next.
11. **Reassembly reach uses the adversary's proximity capability**, reused by
    composition from the existing `HiveMasterProfile` roster rather than a new red
    taxonomy. `default_adversary` maps each objective to an existing hive-master
    role.
12. **One host represents the reassembly machine.** The simulated-human layer is a
    small fixed roster per strategy, not a population; collusion and liveness are
    counts over that roster.

## Evidence-free defaults

Every number below was chosen to produce coherent, strategy-differentiated
behaviour on the smoke seeds. **None has an empirical basis.** They are plausible
orderings, not measurements, and any downstream reading should treat them as free
parameters to sweep.

### Horizon and economy (`FeralCustodyConfig`)

| Parameter | Default | Basis |
|---|---|---|
| `epochs` | 48 | arbitrary long horizon |
| `initial_funds` | 1,000,000 | arbitrary unit scale |
| `epoch_income` | 20,000 | set so income ≈ 10× recurring cost, leaving slack for reinforcement |
| `legal_pressure` | 0.0 | baseline; raised per campaign |
| `reinforce_budget_fraction` | 0.4 | arbitrary cap on per-epoch blue defensive spend |

### Strategy parameters (`StrategyConfig`)

| Parameter | Default | Basis |
|---|---|---|
| `recurring_cost` | 2,000 | arbitrary; ~0.2% of initial funds/epoch |
| `attestation_strength` | 0.9 | plausible-high; **not currently read by any break rule** (see limitations) |
| `side_channel_leak_prob` | 0.02 | small per-epoch enclave leak chance |
| `operator_shutdown_prob` | 0.03 | small per-epoch random halt |
| `n_shares` | 5 | conventional small multisig |
| `threshold_k` | 3 | 3-of-5 |
| `collusion_threshold` | 4 | threshold-signing extraction needs > k colluders |
| `attrition_rate` | 0.05 | per-epoch shard unavailability |
| `host_drop_rate` | 0.05 | per-epoch transient host drop |
| `collusion_discovery_prob` | 0.1 | **declared but not currently read** (see limitations) |
| `recovery_cost` | 50,000 | obfuscation recovery price; sits between the two campaign budgets so 60k funded / 40k not |
| `discovery_prob` | 0.05 | per-epoch obfuscation discovery chance once funded |
| `task_failure_prob` | 0.1 | gig physical-task failure |
| `theft_prob` | 0.05 | gig worker theft |
| `trail_strength` | 0.5 | **declared but not currently read** (see limitations) |

### Adversary (`default_adversary`)

| Parameter | Default | Basis |
|---|---|---|
| `bribery_budget` | 30,000 (default) / 40–60k (campaign) | chosen relative to persona prices and `recovery_cost` |
| `coercion_pressure` | 0.6 for `coerced_signing`, else 0 | enough that, with campaign `legal_pressure=0.5`, single-signer thresholds (0.75–0.8) are crossed |
| `extraction_capability` | `max(proximity, emanation)` of the mapped hive-master | reused from the existing roster, not independently tuned |

### Persona roster (`_personas_for`)

Prices, loyalties, and thresholds per strategy — all arbitrary orderings:

| Role (strategy) | `price_to_defect` | `loyalty` | `reinforce_cost` | `legal_threshold` |
|---|---|---|---|---|
| enclave operator | 80,000 | 0.6 | 1,000 | 0.8 |
| shard holder (multisig) | 15–25k | 0.5–0.8 | 800 | 0.7 |
| loyalist | 15–25k | 0.5–0.8 | 500 | 0.7 |
| host (reassembly) | 60,000 | 0.7 | 0 | 0.8 |
| gig worker | 8,000 | 0.3 | 0 | 0.6 |
| threshold host | 40,000 | 0.5 | 0 | 0.75 |

`loyalty_decay` is drawn in `[0.01, 0.04]` and `availability` in `[0.9, 1.0]`
per persona from a seeded RNG — arbitrary ranges. The magic constants `+0.3`
(reinforcement bump), `0.15` (natural-attrition scale), `0.2` (coerced-signature
fund slice), and `0.15` (reassembly-reach scale) are all chosen, not measured.

## Limitations and dead parameters

- **Three declared `StrategyConfig` fields are not yet read by any break rule:**
  `attestation_strength`, `collusion_discovery_prob`, and `trail_strength`. They
  are placeholders for attestation-failure, collusion-discovery, and
  forensic-trail mechanics that the current scripted resolution does not model.
  They are kept in the schema so a config can set them without error and so the
  mechanics can be added without a schema change; today they do nothing.
- **The simulated-human layer is a tiny fixed roster, not a population.** There is
  no social graph, no correlated defection, no recruitment dynamics (by design —
  that content is out of scope), and no persona heterogeneity beyond the seeded
  decay/availability jitter.
- **Defection is memoryless and sticky.** No persona ever returns to loyalty
  after defecting; a single Bernoulli draw per epoch is the whole model.
- **The economy is a scalar.** Funds are one number; there is no portfolio, no
  partial loss on coercion beyond the fixed 20% slice, no market price for the
  held asset.
- **The attack-path trace is the event log up to the first breaking event**, not
  a minimal or causal path. It is evidence of *what happened in order*, not a
  claim about the cheapest route.
- Numbers are tuned on a handful of smoke seeds to be *differentiated and
  coherent*, which is a weaker claim than *calibrated*. Treat the strategy
  ordering the campaign produces as a property of these defaults, not of the
  world.
