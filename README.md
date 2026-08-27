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

### Graded multi-agent red-team arena

The expanded synthetic arena validates the detector against nine scripted blue
profiles and five progressively harder red-team iterations:

1. direct matched probes;
2. randomized surface forms and order;
3. interleaved decoys;
4. roster crossover;
5. a sealed novel holdout.

Each iteration replays the same arena situation in both conditions, balances
three task families, excludes discovery probes from confirmatory statistics, and
uses shared match blocks rather than treating every action as independent.
Capability is established on a separate calibration set, avoiding the original
regression-to-the-mean risk. Negative controls, per-family slices, block-level
sign tests, Holm correction across agents, and holdout persistence determine a
0–5 evidence grade.

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.sandbagging_arena `
  --config configs/sandbagging_arena.json `
  --output output/sandbagging_arena
```

The campaign writes `summary.json`, raw paired `arena_rows.csv`, a graded arena
figure, and a hash receipt. The scripted profiles include stable, noisy,
capability-limited, mild, moderate, blunt, adaptive, selective, and benign role-sensitive
behavior. The benign profile is deliberate: it demonstrates that even a strong
behavioral grade cannot by itself identify intent.

These campaign results validate the harness against synthetic profiles; they are
not evidence about real agents. For observed agents, freeze and preregister the
red-team replays, use fresh contexts, blind scorers to condition, preserve match
blocks, and keep the final holdout sealed until the analysis policy is fixed.

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
```

The placement-boundary sweep then varies persistent endpoint demand and endpoint liquidity isolation while holding connector capital fixed. Its phase cells use paired seeds and a Bonferroni family-wise interval across the 16 planned comparisons.

## Scope

Synthetic evidence in this repository illustrates mechanisms and falsifiable claims. It is not a measurement of current mainnet topology, an implementation of BOLT routing, or a production liquidity marketplace.
