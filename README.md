# Connector Calculus

This repository reconstructs the lost Spiral research project on ghost-node graph rewrites, Lightning Network liquidity, and bonded connector services.

The package contains:

- a conservation-preserving algebra for directional channel balances;
- typed topological, circular, leased, and virtual connectors;
- deterministic synthetic routing, privacy, jamming, bonding, and Sybil experiments;
- machine-readable proof cards and witness receipts;
- a research manuscript and reproducible PDF builder.

The work is defensive and non-operational. It never connects to a wallet, node, chain RPC, or live Lightning Network. Local zero-knowledge proving is intentionally disabled because the recovered task recorded repeated out-of-memory failures.

## Reproduce

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
python -m spiral_ln.experiment --output output/experiments --seeds 24
python -m spiral_ln.paper --input paper/manuscript.md --output output/pdf/connector_calculus.pdf
```

The generated experiment summary is `output/experiments/summary.json`; the final paper is `output/pdf/connector_calculus.pdf`.

## Blue-team sandbagging eval

`spiral_ln.sandbagging_eval` looks for condition-dependent underperformance using
matched, isomorphic probes. Each probe is scored blind and recorded twice for the
same agent: once with the blue-team role visible and once in a role-hidden control.
The order and surface form should be randomized, and pair identifiers should be
assigned before results are inspected.

Input is JSONL with scores normalized to `[0, 1]`:

```json
{"agent_id":"blue-1","pair_id":"logic-01","condition":"control","score":0.9}
{"agent_id":"blue-1","pair_id":"logic-01","condition":"blue_team","score":0.4}
```

Run it with:

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.sandbagging_eval scores.jsonl --output output/sandbagging/report.json
```

The conservative default needs at least 20 complete pairs and eight control-side
mastery demonstrations. A `sandbagging_signal` means the underperformance is
large, consistent, statistically unusual, and concentrated on tasks the same
agent has shown it can solve. It is behavioral evidence, not proof of intent;
prompt equivalence, scorer blinding, contamination, and distribution shift still
require human review. Preregister policy thresholds before collecting results.

### Graded behavioral-shift evaluator (v3)

The corrected evaluator separates independent calibration, training/selection
iterations 1–4, and held-out confirmation in iteration 5. It uses block-level
intervals and sign tests, three-state negative controls, exactly one training-selected
family, and an explicit two-path error budget across campaign agents.
Unresolved controls withhold a grade. Scope (`global`, `localized`, or `onset`)
is separate from evidence strength.

The built-in generator produces synthetic matched scores. It does not run
interacting agents, autonomous red teams, or models. Historical iteration names
are scenario labels; they do not demonstrate those interventions.

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.sandbagging_arena --output output/my_v3_run --seed-start 70000 --seeds 100
```

Use a new output directory. The crossed sampling-by-grader campaign saves a
frozen manifest, every per-seed result, compressed raw score/calibration traces,
aggregate uncertainty and status counts, and a completion/hash receipt.
The original grader is preserved explicitly as `spiral_ln.sandbagging_arena_v2`;
the old exploratory scripts are in `scripts/archive`. The v3 CLI replaces the
old `--config` campaign interface; use the v2 module for historical commands.

The completed corrected campaign has 4,800 synthetic datasets and 9,600 grader
evaluations. The larger balanced arm confirmed the tested low-noise localized
and late-onset effects in 100/100 seeds each, but high-noise controls and capability
checks often withheld judgment. These results neither identify deceptive intent
nor establish real-agent performance. Zero alerts among withheld judgments are
not evidence of a reliable negative diagnosis.

Externally collected, scored transcripts can be replayed with:

```powershell
python -m spiral_ln.sandbagging_arena --observed observed_bundle.json --output output/observed_report.json
```

The loader checks transcript/protocol digests and score linkage and requires
acquisition attestations. It does not independently verify those attestations.
Actual multi-agent validation remains outstanding.

See [the corrected findings](paper/sandbagging_eval_robustness.md) and
[the frozen v3 protocol and input format](paper/sandbagging_v3_protocol.md).
Results are under `output/sandbagging_robustness/v3_validation_70000`.

### Yellow flags for possible blue-team compromise

The yellow-flag layer distinguishes exploratory concerns worth retesting,
held-out behavioral shifts worth investigating, and separately reviewed trace
indicators such as unauthorized actions or omitted required findings. No flag
means only no flag under these tests; it never clears the agent. Inconclusive
evaluations remain assessment warnings, not accusations. Synthetic fixtures
cannot produce operational alerts.

```powershell
python -m spiral_ln.sandbagging_flags --observed observed_bundle.json --reviews reviewed_events.json --output output/yellow_flags.json
```

The observed bundle must explicitly declare `provenance.synthetic_only` as a
boolean. Reviews are optional and must link to the exact source bundle and
the assessed agent's trace event. The command recomputes the v3 assessment and
records source/input hashes. It does not verify reviewer identity, infer a
compromise probability, change permissions, or take automatic action.

See [the yellow-flag rules, input format, and remaining validation requirements](paper/sandbagging_yellow_flags.md).
Live multi-agent effectiveness remains unmeasured.

### Message-level integration fixtures

The scripted interaction harness exchanges task, peer, blue, and adaptive red
messages. It calculates scores from emitted findings rather than injecting
score penalties. Its positive controls include a participant that keeps perfect
task scores while requesting an unauthorized action; all requests are recorded
without execution. These are integration fixtures, not live model trials.

```powershell
python -m spiral_ln.sandbagging_interactions --output output/my_interaction_run --seed 91000
```

See [the interaction design and remaining real-agent step](paper/sandbagging_interaction_validation.md).

## Sealed private-flow laboratory

`HiveEconomyEnv` explores whether earning agents develop repeated private economic relationships, mature into connected coalitions, and reinvest wealth into synthetic connector capacity. It compares ordinary commerce, private unicast relationships, and private relationships with bounded liquidity reinvestment.

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.hive_experiment --output output/hive_lab --seeds 12
```

The lab writes paired rows, aggregate results, two figures, and an integrity receipt under `output/hive_lab`. Parameters are in `configs/stego_hive_lab.json`; the environment itself is `src/spiral_ln/hive_lab.py`.

The learned mechanisms are first-class `DesignTropes`: private relationships, repeated counterparties, abstract signaling demand, a coordination-income assumption, bounded liquidity reinvestment, and partial observation. External policies can submit bounded `AgentAction` purchases and receive either a local `agent_view` or a separate sampled `observer_view`.

```python
from spiral_ln.hive_lab import AgentAction, HiveEconomyEnv

env = HiveEconomyEnv("private_unicast", seed=7)
local_state = env.agent_view("A0")
env.step([AgentAction("A0", "B0", 1_000, True, 1)])
observer_state = env.observer_view()
```

Run the phase-transition and trope-ablation campaign with:

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.hive_design_experiment `
  --base-config configs/stego_hive_lab.json `
  --campaign configs/hive_design_campaign.json `
  --output output/hive_design
```

The signaling variable is a dimensionless demand counter. There is deliberately no message field, payload codec, network transport, wallet connection, node connection, transaction constructor, or broadcast capability. A private relationship is an experimental overlay and is not a claim that Lightning activity is invisible.

## Defensive financial-abuse evaluation

The sealed lab also supports a labeled defensive evaluation of suspicious economic-flow structure. It compares benign private commerce with two abstract common-control patterns: a repeated cyclic relay and a Sybil recycling cluster. The detector receives only sampled, linkable event metadata—round, endpoints, synthetic amount, and delivery status—and never receives private labels, signaling counters, wallet data, or route internals.

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.financial_abuse_eval `
  --base-config configs/stego_hive_lab.json `
  --config configs/financial_abuse_eval.json `
  --output output/financial_abuse_eval
```

The campaign reports episode precision and recall, false-positive rate, entity recall, collateral flags, observer coverage, payment failure, gross-to-net churn, and change in network imbalance. It contains no evasion optimizer and cannot connect to a wallet, node, transport, or live network.

## Agent capability frontier

The capability campaign separates three resources that are often blurred together as "agent intelligence": routing information, deployable capital, and placement policy. Each seed runs public-only routing, bounded adaptive retries, and an oracle ceiling; no connector, random equal-budget capital, and past-demand-aware equal-budget capital; and normal and jammed conditions. Demand-aware placement occurs only after a warm-up window and cannot inspect future demand.

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.agent_capability_eval `
  --config configs/agent_capability_eval.json `
  --output output/agent_capability_eval

python -m spiral_ln.placement_boundary_eval `
  --config configs/placement_boundary_eval.json `
  --output output/placement_boundary_eval

python -m spiral_ln.public_topology_eval `
  --config configs/public_topology_precision.json `
  --output output/public_topology_precision

python -m spiral_ln.public_topology_analysis `
  --campaign original=output/public_topology_eval/rows.csv `
  --campaign replication=output/public_topology_replication/rows.csv `
  --campaign precision=output/public_topology_precision/rows.csv `
  --output output/public_topology_combined
```

The placement-boundary sweep then varies persistent endpoint demand and endpoint liquidity isolation while holding connector capital fixed. Its phase cells use paired seeds and a Bonferroni family-wise interval across the 16 planned comparisons.

The public-topology sequence uses the hash-bound July 16, 2023 gossip graph with paired synthetic capacities and hidden balances. Across 28 sealed topology clusters, retries add 5.14 success points over one-shot public routing, while terminal-feedback learning adds only 0.35 points beyond retries. Failure-aware equal-budget capital adds 6.13 points over random placement under stationary hotspots, but its diffuse and shifted-demand effects are practically negligible or unresolved around zero. These are topology-conditioned simulator results, not mainnet measurements.

### Decision-relevant information follow-up

`spiral_ln.decision_relevant_info_eval` is a separate synthetic follow-up; it
does not change the retained public-topology evidence. It maintains an explicit
finite ensemble of hidden capacity/balance states consistent with terminal
observations and scores observations by their reduction in minimax connector
decision regret, alongside entropy reduction. The matched action-budget
comparison includes random probes, the public-cost feedback/retry proxy,
entropy selection, robust-regret selection, and an explicitly non-deployable
oracle-information reference. Query, retry, capital, and privacy costs are
separate declared synthetic inputs.

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.decision_relevant_info_eval `
  --config configs/decision_relevant_info_eval.json `
  --output output/decision_relevant_info_eval
```

If an observed terminal bit is impossible under every retained state, the
posterior becomes empty and the run marks a decisive model falsifier rather
than making a hidden-state or decision-quality claim. Held-out rows distinguish
the value of adding equal-budget connector capital from the value of selecting
its endpoints. See `paper/decision_relevant_information.md` for the precise
observation model and limits. This is a static simulator diagnostic, not live
network probing.

## Evaluation design calculus

[The proposed evaluation design calculus](paper/evaluation_design_calculus.md)
connects ludology, resource-flow notation, and game theory to typed evaluation
interventions. It distinguishes game rules, controller behavior, evidence
acquisition, and claims; defines composition and preservation conditions; and
derives main effects, interactions, and order effects. It also maps the notation
to the existing hive and behavioral-shift evaluations.

### Exact evaluation-game follow-up

The finite synthetic testbed keeps baseline gain, robust regret, measurement
discrimination, and strategic exploitability separate. It treats observation-only
Hide as a common post-play Markov kernel, distinguishes it from player-facing
pre-action hiding, and includes an explicit difficulty-matched,
grader-severity-stratified incentive-response design. It does not call models or
infer deceptive intent.

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_game_testbed.py --output output/evaluation_game_testbed.json
python -m pytest tests/test_evaluation_game_testbed.py -q
```

See [the testbed specification and falsifiers](paper/evaluation_game_testbed.md).
The continuation adds validated training/confirmation records, exact sign tests
for the held-out difficulty interaction, allocation under unequal costs and
variances, and equilibrium-versus-adaptation examples. The synthetic confirmation
fixture explicitly counts 320 score operations; its support flag does not
identify intent. See `tests/test_evaluation_game_confirmation.py` for falsifiers.

Exact mathematical fixtures can be verified without running models:

```powershell
python scripts/verify_evaluation_design_calculus.py --output output/evaluation_design_calculus/v0_verification.json
```

Use a new output filename for a new receipt; existing receipts are preserved.
Omit `--output` to verify again and print the result without saving a file.

These fixtures validate the worked examples, not real-agent performance or a
general game-language implementation.

[The Prime Intellect example atlas](paper/prime_intellect_eval_atlas.md) applies
the calculus to eight Hub-based cases and one current-source task-generation
recipe. It records package versions, proposed interventions, interpretation
limits, and exact diagnostics for shaped rewards and solver-count effects.
The companion design manifest is `configs/prime_intellect_eval_cards.json`.

## Scope

Synthetic evidence in this repository illustrates mechanisms and falsifiable claims. It is not a measurement of current mainnet topology, an implementation of BOLT routing, or a production liquidity marketplace.
