# Sealed Private-Flow and Hive-Economy Laboratory

## Purpose

This environment tests a bounded hypothesis: when autonomous earning agents can repeatedly purchase services from one another, prefer familiar counterparties, and reinvest accumulated wealth, do stable private economic coalitions emerge, and do those coalitions improve or degrade channel liquidity?

The word *private* describes the simulated relationship overlay. It does not mean undetectable, anonymous, or hidden from every network participant. The word *signal* denotes dimensionless coordination demand. The environment represents neither message content nor an encoding scheme.

## Safety boundary

The laboratory is intentionally unable to become operational infrastructure. It has:

- no Lightning implementation or node connection;
- no wallet, keys, invoices, RPC, onion packets, or transaction construction;
- no network transport or peer discovery;
- no message or payload field and no encoding or decoding function;
- no broadcast capability;
- no attempt to optimize evasion.

Its outputs are synthetic event records, aggregate metrics, figures, and integrity hashes.

## State

An episode contains sixteen agents mapped to the nodes of the existing two-community channel graph. Each agent has liquid wealth, productivity, a privacy preference, earned task income, service income, spending, and connector investment. External tasks introduce explicitly recorded income. Service payments transfer wealth between agents. Connector investment moves liquid wealth into a separate invested-capital account. Therefore:

```text
initial wealth + external income = ending liquid wealth + connector investment.
```

The experiment checks this identity after every completed episode. Channel updates separately retain the channel-capacity invariants of the connector calculus.

## Economic events

During each round, an agent may earn income from an external task and may purchase a service from another agent. A purchase becomes a synthetic Lightning demand and succeeds only if a feasible directional route exists. Successful purchases move agent wealth and channel balances.

Private scenarios add a relationship object containing only endpoints, directional interaction counts, delivered value, trust, reciprocity, abstract signal units, and the last interaction round. Repeated successful commerce raises trust; failed delivery lowers it. Nothing in the relationship object can contain a message.

Economics, private designation, abstract signaling, and observer sampling use independent random streams. This prevents a non-economic switch from changing later commerce merely by consuming an extra random draw and makes paired trope ablations interpretable.

## Composable design tropes and agent interface

The environment exposes six independent `DesignTropes`:

1. private relationship state;
2. repeated-counterparty preference;
3. abstract signaling demand;
4. an explicit coordination-income bonus;
5. bounded connector reinvestment;
6. partial observer sampling and attribution.

The three named scenarios are presets over those switches. Experiments may provide a custom trope composition without changing the state transition code.

An external policy can submit at most one bounded `AgentAction` per payer per round. An action chooses payer, payee, amount, private designation, and zero to three dimensionless signal units. Invalid endpoints, self-payment, overspending, disabled-private actions, and out-of-range signal counts are rejected before the round mutates.

`agent_view(agent_id)` contains only that agent's wealth, income, spending, investment, enabled tropes, and its own relationship summaries. `observer_view()` contains sampled deliveries and linkable-pair counts but excludes private labels and signaling counters. The unrestricted `observation()` is reserved for experiment evaluation.

## Three paired scenarios

1. **Ordinary commerce.** Agents choose counterparties from the same demand distribution. No private relationship, signaling counter, hive, or reinvestment rule is enabled.
2. **Private unicast.** Agents probabilistically designate transactions as relationship-private and increasingly return to trusted peers. Successful private transactions may consume a small number of abstract signal units. No new channel capital is added.
3. **Hive reinvestment.** The private-unicast rules remain unchanged. Mature cross-community relationships inside a hive may fund at most four synthetic connectors. Hive membership also supplies an explicit, configurable productivity bonus representing better information or task allocation.

The productivity bonus is an assumption, not a discovered result. Keeping it explicit lets experiments ask how large a coordination advantage must be before capital reinvestment becomes self-sustaining.

## Emergence criterion

A relationship is mature when it has at least four interactions, trust of at least 0.52, and directional reciprocity of at least 0.20. Reciprocity is the smaller directional interaction count divided by the larger one. A hive is a connected component of at least three agents joined by mature reciprocal relationships. This definition avoids treating a one-way customer hub as a cohesive coalition. It remains deliberately observable and falsifiable and does not assert consciousness, shared identity, or collective agency.

## Observer model

A simple external observer samples 35% of events. A sampled ordinary relationship is linkable with probability 0.80; a sampled private-overlay relationship is linkable with probability 0.28. Repeated linkable pairs generate alerts. Observer hive-edge recall reports the fraction of mature relationship edges recovered by this alert set.

These probabilities are experimental controls, not measurements of current Lightning privacy. The observer never reads a synthetic signal or message because none exists.

## Initial paired campaign

The default campaign uses twelve paired seeds and 120 rounds per scenario.

| Metric | Ordinary commerce | Private unicast | Hive reinvestment |
|---|---:|---:|---:|
| Payment success | 97.14% | 94.45% | 95.85% |
| Private share of delivered value | 0.00% | 91.19% | 91.33% |
| Largest mature coalition | 0 | 16 | 16 |
| Synthetic connectors | 0 | 0 | 4 |
| Connector capital | 0 | 0 | 80,000 |
| Observer alerts | 23.67 | 7.42 | 7.42 |
| Mature-edge recall | 0.00% | 27.52% | 26.84% |

Relative to paired private-unicast runs, bounded hive reinvestment raises payment success by 1.40 percentage points with a normal 95% half-width of 1.13 points. The configured coordination bonus raises external income by 180,906 units on average. That income difference is partly built into the scenario and must not be reported as an emergent causal discovery.

Under the selected parameters, repeated private commerce reliably produces one network-wide mature component. This establishes that the mechanism can generate coalition structure. It does not show that real agents or real Lightning users would choose the same policy.

## Phase transition and trope ablations

The design campaign crosses repeat-private-peer probability `{0, 0.25, 0.50, 0.70, 0.90}` with minimum reciprocity `{0, 0.15, 0.30, 0.50, 0.70}` over five paired seeds per cell. A giant component contains at least half of the sixteen agents.

At reciprocity thresholds through 0.50, every tested cell forms a giant component. At the demanding 0.70 threshold, emergence is 100% for repetition through 0.50, falls to 60% at repetition 0.70, and falls to 20% at repetition 0.90. Aggressive repetition therefore does not monotonically create a single hive: it can consolidate strong local relationships while fragmenting the society-wide reciprocal graph.

The twelve-seed trope ablation produces:

| Design | Success | Private-flow share | Largest coalition | Connectors |
|---|---:|---:|---:|---:|
| Ordinary | 97.14% | 0.00% | 0 | 0 |
| Relationships only | 97.14% | 87.25% | 16 | 0 |
| Repeat and trust | 94.45% | 91.19% | 16 | 0 |
| Add abstract signaling | 94.45% | 91.19% | 16 | 0 |
| Add coordination bonus | 94.62% | 91.26% | 16 | 0 |
| Full reinvestment | 95.85% | 91.33% | 16 | 4 |

Relationships alone change classification but leave delivery, income, and imbalance exactly equal to ordinary commerce because the overlay has no economic semantics. Abstract signaling likewise has an exact paired success delta of zero. Repeated-counterparty preference is the first trope that changes routing demand: it raises concentration and ending imbalance while lowering delivery in this topology. Reinvestment recovers part, but not all, of that delivery loss.

## Research questions

The environment supports safer versions of the core questions:

- At what repetition, trust, and privacy-preference thresholds does a giant private component appear?
- Does coalition concentration make directional liquidity worse before reinvestment compensates for it?
- How much real economic productivity must a coalition create to cover connector capital and bond costs?
- Which aggregate signatures distinguish ordinary repeated trade from coordinated capital deployment?
- Do multiple smaller coalitions outperform a single giant component under shocks or corrupted members?
- How do observer sampling and attribution uncertainty change false positives and mature-edge recall?
- Can capital-keyed rewards prevent identity proliferation from manufacturing service income inside the lab?

## Non-claims

The initial campaign does not measure the Lightning Network, establish anonymity, demonstrate covert communication, prove that an autonomous society will emerge, or show that private agent activity solves liquidity. It is a controlled mechanism study whose assumptions are exposed in one JSON configuration.

## Defensive financial-abuse evaluation

The next campaign treats illicit common control as a ground-truth experimental label rather than trying to infer intent from privacy alone. It compares benign private commerce with two deliberately simple synthetic patterns: repeated value circulation around a closed relay and circulation among multiple identities assigned to one controller. These are adversarial fixtures for testing monitors, not operational strategies. They use dimensionless balances and contain no invoices, wallets, payloads, route selection, network transport, or broadcast mechanism.

The detector receives only sampled and linkable metadata: round index, payer, payee, synthetic amount, and delivery status. It cannot see the private-relationship flag, abstract signal units, agent wealth, the common-controller assignment, or unsampled events. Its initial score combines four declared features: the share of observed events on repeated edges, the share inside repeated directed cycles, reciprocal repeated flow, and balance between repeated inflow and outflow. The campaign does not optimize behavior against this detector.

Evaluation separates episode classification from operational consequences. Precision, recall, specificity, and false-positive rate measure the monitor. Entity recall and collateral flags measure who the monitor implicates. Observer event share records the strength of the measurement surface. Payment failure, gross-to-net transfer ratio, and change in network imbalance measure whether the injected behavior consumes or redistributes liquidity even when it is detected. The gross-to-net ratio is a ground-truth diagnostic and is not exposed to the detector.

This creates a baseline for later defensive ablations: observer coverage, attribution noise, alert thresholds, common-controller population, and bounded interventions can be varied independently. A useful follow-on intervention must reduce labeled abuse harm without treating ordinary private commerce as guilt and without assuming a global identity system.

### Initial defensive baseline

Across 20 paired seeds per scenario, the observer saw 13.37% of benign events, 11.69% of cyclic-relay events, and 10.88% of Sybil-recycling events on average. At the declared threshold of 0.55, the detector produced no false-positive episodes and precision of 1.00, but recall was only 0.225: it alerted on 9 of 40 labeled episodes, all from the larger Sybil fixture, and missed every four-member cyclic relay. The conservative threshold therefore discarded substantial signal under partial observation.

The raw score perfectly ranked the deliberately simple labeled fixtures above benign runs in this campaign (ROC AUC 1.00). A threshold of 0.15 selected only on seeds 0–9 then classified all 20 labeled and all 10 benign holdout episodes correctly on seeds 10–19. This is a harness sanity check, not an estimate of field performance: the behaviors are clean, the simulator distribution is narrow, and the detector features directly target the injected motifs. Later campaigns need harder benign controls, imperfect common control, topology variation, intensity sweeps, and a sealed final holdout.

The Sybil fixture increased mean network-imbalance energy by 0.214, compared with 0.068 for benign commerce and 0.092 for the smaller cyclic relay. Mean payment failure was 0.98%, 0.39%, and 0.61%, respectively. A naive ground-truth gross-to-net churn ratio failed as a discriminator: benign commerce scored 12.63, while both labeled patterns were near 7.56. Random multilateral trade can net out strongly without illicit common control, so high churn cannot stand alone as evidence of abuse.

## Agent capability frontier

To separate agent capability from capital and privileged state access, a paired factorial campaign crosses three routing-information levels, three connector policies, and two stress conditions. Public routing tries one cheapest path. Adaptive routing tries the same bounded candidate set until one succeeds. The oracle filters that set using hidden directional balances and is an upper bound, not a deployable policy. Connector policies deploy no capital, random cross-cut capital, or equal-budget capital placed from the endpoints of the first 90 observed demands. Placement occurs after the warm-up and cannot inspect future demand. Each of the 18 cells contains the same 30 seeds and 360 exogenous demands per seed; stress begins at demand 180.

Four conclusions are exact or stable within this model.

1. **Adaptive search improves delivery but leaks failures.** Without new capital, adaptive routing raises post-boundary success over public-only routing by 2.91 percentage points with a 95% half-width of 1.04 points under normal conditions and by 6.19 points with a half-width of 1.35 points under jamming. The price is repeated failed-route exposure: adaptive search produces 2.64 more failed attempts per demand than the oracle normally and 3.66 more under jamming.
2. **Perfect balance knowledge changes privacy cost, not the delivery ceiling.** Oracle and adaptive policies have exactly equal success and delivered volume in every paired run because both ultimately choose the first feasible path from the same candidate set. The oracle merely avoids testing infeasible candidates. Better state information is therefore valuable here as a leakage and latency capability, not as additional reachability.
3. **Capital, not clever placement, supplies most resilience on the base topology.** Under jamming, demand-aware connector capital raises post-stress success by 14.56 points over no connector, while random equal-budget capital raises it by 14.41 points. Demand-aware placement exceeds random placement by only 0.15 points with a 1.35-point half-width and does not improve fee efficiency. On the normal base topology, its advantage is likewise indistinguishable from zero. The initial heuristic therefore does not earn a claim of placement intelligence.
4. **Information and capital are complements under stress.** Capital reduces the adaptive policy's jam penalty by 13.94 points with a 1.95-point half-width. The adaptive-over-public advantage is 5.11 points larger with demand-aware capital than without it, with a 2.15-point half-width. Capital creates alternate feasible paths on which routing capability can act. However, the connector also raises ending imbalance energy by 0.092 under jamming and 0.077 normally, so higher short-run delivery is not equivalent to a balanced network.

### Placement-value boundary

The null placement result is topology-dependent. A second campaign holds capital, routing policy, timing, and future-information constraints fixed while sweeping persistent demand for one endpoint pair and the fraction of pre-existing liquidity reserved on edges incident to those endpoints. It uses 20 paired seeds for each of 16 planned cells and applies a Bonferroni family-wise normal interval with z = 2.96.

Nine cells retain positive placement value after that correction. With no endpoint isolation, demand-aware placement clears random capital only when 75% of demands persist at the hotspot, gaining 1.60 percentage points. At 50% isolation, the boundary moves to 50% hotspot demand; at 80% and 95% isolation, 25% hotspot demand is sufficient. The strongest cell—75% hotspot demand and 95% isolation—gains 4.36 points over random equal-budget capital with a family-wise half-width of 1.59 points, gains 8.20 points over no connector with a conventional 95% half-width of 0.69 points, and reduces fees by 0.210 msat per delivered sat with a 0.050 half-width.

The bounded conclusion is sharper than "AI solves liquidity." Capital dominates when a whole cut is scarce and internal paths make placement fungible. Demand-learning adds measurable value when demand is persistent and access is localized, and the required persistence falls as endpoint constraints strengthen. Routing adaptation adds resilience only where liquidity leaves feasible alternatives; privileged balance knowledge chiefly suppresses failed probes. These are capability conditions inside the sealed algebra, not measurements of current Lightning or evidence that a general AI agent can obtain the required observations, capital, permissions, or execution reliability.

### Public-topology validation

Three preregistered campaigns replace the generated graph with 28 sealed connected samples from the July 16, 2023 public-gossip topology. Capacities and directional balances remain paired synthetic hidden variables because the source GML does not contain them. Topology-cluster Student-t intervals show that bounded retries add 5.14 success points over one-shot public routing (95% CI 3.08 to 7.20), while terminal-feedback learning adds only 0.35 points beyond retries (0.15 to 0.55). Oracle hidden-state filtering adds 1.11 points (0.64 to 1.58) and emits no infeasible probes.

Failure-aware equal-budget capital adds 6.13 points over random capital under stationary hotspots (4.91 to 7.35), but only 0.14 under diffuse demand (-0.02 to 0.31) and 0.44 after an unseen hotspot shift (-0.21 to 1.09). The online learner's shift-adaptation advantage over retries is 0.22 points (-0.46 to 0.91). Within this model, retries are the main routing capability, terminal-only learning is marginal, and capital placement requires persistent demand.

![Public-topology capability boundary](output/public_topology_combined/cluster_forest.png)

## Reproduction

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
python -m spiral_ln.hive_experiment --output output/hive_lab --seeds 12 --config configs/stego_hive_lab.json
python -m spiral_ln.hive_design_experiment --output output/hive_design --base-config configs/stego_hive_lab.json --campaign configs/hive_design_campaign.json
python -m spiral_ln.financial_abuse_eval --output output/financial_abuse_eval --base-config configs/stego_hive_lab.json --config configs/financial_abuse_eval.json
python -m spiral_ln.agent_capability_eval --output output/agent_capability_eval --config configs/agent_capability_eval.json
python -m spiral_ln.placement_boundary_eval --output output/placement_boundary_eval --config configs/placement_boundary_eval.json
python -m spiral_ln.public_topology_eval --output output/public_topology_eval --config configs/public_topology_eval.json
python -m spiral_ln.public_topology_eval --output output/public_topology_replication --config configs/public_topology_replication.json
python -m spiral_ln.public_topology_eval --output output/public_topology_precision --config configs/public_topology_precision.json
python -m spiral_ln.public_topology_analysis --campaign original=output/public_topology_eval/rows.csv --campaign replication=output/public_topology_replication/rows.csv --campaign precision=output/public_topology_precision/rows.csv --output output/public_topology_combined
```

The baseline campaign writes paired rows, a summary, two figures, and a receipt under `output/hive_lab`. The design campaign writes phase and ablation rows, two figures, a summary, and a receipt under `output/hive_design`. Each receipt binds exact configuration and result bytes with SHA-256 and states that the run has no live-network or payload-codec capability.
