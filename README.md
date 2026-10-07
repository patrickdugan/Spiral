# Spiral

Lightning Network liquidity as a capital problem for populations of autonomous agents: a conservation bound on directional channel capacity that no routing policy relaxes, where that bound goes under a server-mediated settlement object of the Ark type and under the multiparty channels that the BIP 448 soft-fork proposal would make practical, a claim-once reward registry that needs no identities, and what a population of agents under common control can do with each. The work is defensive and non-operational. Nothing here connects to a wallet, node, chain RPC, or live Lightning Network; every result is from a simulator on sampled public topology or from a reference model with a simulated proof system.

## What is here

| Path | Contents |
|---|---|
| `paper/tex/` | The current paper, *Where the Capital Bound Moves* (`main.tex`, compiled `main.pdf`). `grid.tex` is generated from the reference model. |
| `model/` | TypeScript reference model behind the paper: clocked settlement ledger, Ark server liquidity ledger under both recovery readings, the multiparty channel (hyperedge) on the same demand, epoched claim-once registry, escrow state machine, warden statistics. Nineteen tests witness the propositions on finite cases. |
| `src/spiral_ln/` | Python simulator: directional balance algebra, typed connectors, routing and placement campaigns on sampled public topology, coalition fixtures. |
| `paper/` | Earlier manuscripts and their audit, plus design documents from other programs; [`paper/README.md`](paper/README.md) says which is which. |
| `audit/` | Reproducible adversarial audit of the first manuscript; start from [`audit/README.md`](audit/README.md). |
| `docs/evaluation_harnesses.md` | Evaluation-design harnesses that share this repository but not the liquidity question. |

## Reproduce

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
python -m spiral_ln.experiment --output output/experiments --seeds 24
python -m spiral_ln.paper --input paper/manuscript.md --output output/pdf/connector_calculus.pdf
```

The generated experiment summary is `output/experiments/summary.json`; the first manuscript's PDF is `output/pdf/connector_calculus.pdf`.

## The paper and its reference model

The propositions of *Where the Capital Bound Moves* are witnessed on finite cases by `model/`, TypeScript with no dependencies (Node 22.6 or later):

```powershell
node --experimental-strip-types --test "model/*.test.ts"
node --experimental-strip-types model/grid.ts > paper/tex/grid.tex
```

The second command regenerates every number in the liquidity-duration grid, its accounting variants, the failed-events table, and the multiparty-channel tables of the BIP 448 section; nothing in those tables is hand-edited, and the generator asserts the facts their layouts rely on, including that a multiparty channel of one agent is the two-party channel exactly. `paper/tex/main.tex` compiles with any current TeX distribution; the committed `main.pdf` was built with Tectonic 0.17. The proof system is simulated: the registry verifies a simulated attestation behind the interface a verifier would expose, and the BitVM3 figures are an implementer's published numbers at a stated date.

`paper/where_the_capital_bound_moves.md` is the superseded working draft and is kept as it was.

## Simulator campaigns

These are the preregistered campaigns the paper's Table 1 reports. They separate three resources that are often blurred together as "agent intelligence": routing information, deployable capital, and placement policy. Each seed runs public-only routing, bounded adaptive retries, and an oracle ceiling; no connector, random equal-budget capital, and past-demand-aware equal-budget capital; and normal and jammed conditions. Demand-aware placement occurs only after a warm-up window and cannot inspect future demand.

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

The placement-boundary sweep varies persistent endpoint demand and endpoint liquidity isolation while holding connector capital fixed. Its phase cells use paired seeds and a Bonferroni family-wise interval across the 16 planned comparisons.

The public-topology sequence uses the hash-bound July 16, 2023 gossip graph with paired synthetic capacities and hidden balances. Across 28 sealed topology clusters, retries add 5.14 success points over one-shot public routing, while terminal-feedback learning adds only 0.35 points beyond retries. Failure-aware equal-budget capital adds 6.13 points over random placement under stationary hotspots, but its diffuse and shifted-demand effects are practically negligible or unresolved around zero. These are topology-conditioned simulator results, not mainnet measurements.

## Coalition and private-flow fixtures

Section 7 of the paper draws its netting statistics, and the record of which ones fail, from these fixtures.

`HiveEconomyEnv` explores whether earning agents develop repeated private economic relationships, mature into connected coalitions, and reinvest wealth into synthetic connector capacity. It compares ordinary commerce, private unicast relationships, and private relationships with bounded liquidity reinvestment.

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.hive_experiment --output output/hive_lab --seeds 12
```

The lab writes paired rows, aggregate results, two figures, and an integrity receipt under `output/hive_lab`. Parameters are in `configs/stego_hive_lab.json`; the environment itself is `src/spiral_ln/hive_lab.py`, and its design is in [`paper/hive_lab.md`](paper/hive_lab.md).

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

The sealed lab also supports a labeled defensive evaluation of suspicious economic-flow structure. It compares benign private commerce with two abstract common-control patterns: a repeated cyclic relay and a Sybil recycling cluster. The detector receives only sampled, linkable event metadata—round, endpoints, synthetic amount, and delivery status—and never receives private labels, signaling counters, wallet data, or route internals.

```powershell
$env:PYTHONPATH = "src"
python -m spiral_ln.financial_abuse_eval `
  --base-config configs/stego_hive_lab.json `
  --config configs/financial_abuse_eval.json `
  --output output/financial_abuse_eval
```

The campaign reports episode precision and recall, false-positive rate, entity recall, collateral flags, observer coverage, payment failure, gross-to-net churn, and change in network imbalance. It contains no evasion optimizer and cannot connect to a wallet, node, transport, or live network.

## The first manuscript and its audit

`paper/manuscript.md` (*Connector Calculus*) is frozen at baseline `a0a3140` and hash-bound by `audit/validate_bundle.py`; corrections are recorded in `paper/manuscript_errata.md` rather than applied in place. The audit's own papers are `paper/liquidity_on_trial.md` and `paper/connector_calculus_critique.md`; its evidence classes, receipts, and scripts are described in [`audit/README.md`](audit/README.md).

## Also in this repository

The blue-team sandbagging evaluation and its graded arena, the evaluation design calculus with its exact testbed, and the Prime Intellect example atlas are evaluation-design work that shares this repository but not the liquidity question. Their run instructions moved unchanged to [`docs/evaluation_harnesses.md`](docs/evaluation_harnesses.md); their design documents remain under `paper/`.

## Scope

Synthetic evidence in this repository illustrates mechanisms and falsifiable claims. It is not a measurement of current mainnet topology, an implementation of BOLT routing, or a production liquidity marketplace. Local zero-knowledge proving is intentionally disabled in the Python package, because the recovered task recorded repeated out-of-memory failures, and the TypeScript model simulates its proof system; no proof in this repository has been generated or verified by a real prover.
