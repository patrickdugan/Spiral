# Red Team Gladiatorics: arena and swarm-compromise harnesses

Agent-security evaluations that share this repository with the Lightning liquidity
work but not its question. The design document is
[`paper/rtg_crypto_swarm_arena.md`](../paper/rtg_crypto_swarm_arena.md); the text
below moved here unchanged from the top-level README.

## Sealed adversarial swarm-compromise laboratory

`spiral_ln.swarm_compromise` studies how a population of scripted non-player
characters (NPCs) is compromised by an adversarial *hive-master* role, and how
well bounded blue-team defenders and honeypots contain and attribute that
compromise across hardening postures. It is an offline, synthetic eval: there is
no model call inside the harness, no network, wallet, node, transport, payload,
message content, or operational technique. Every "channel" is an abstract scalar
parameter.

NPCs carry a `PsychProfile` susceptibility vector (authority deference,
reciprocity debt, isolation, ideological affinity, risk tolerance, and protective
security hygiene). Four abstract `AttackVector`s are modeled: `spear_social`,
`phone_bridge` (the only kind that can reach an airgapped node), `emanation_tap`
(a covert channel whose `covert_capacity` is a dimensionless notional "baud",
realized only when the target lacks a cleanroom posture), and `cult_recruitment`
(which spreads through the comms graph as a social contagion). A `NodePosture`
hardening ladder runs `baseline_open` → `airgap_core` → `cleanroom` →
`full_hardening`.

Information is imperfect on both sides. Each blue-team `DefenderProfile` is
retained over a `domain` of nodes and sees signals only inside that domain. The
red team starts knowing only public (non-airgapped) nodes and expands its map by
compromising or recruiting NPCs (recon gain), unless it has insider access.
Honeypot contact "burns" and teaches the attacker it was a trap. The shipped
`ScriptedHiveMaster` reference policy is non-adaptive and never uses domain
intelligence to evade monitoring, so the shipped campaign contains no evasion
optimizer; an external red-team or blue-team *player model* can drive the same
bounded `hive_master_view` / `CompromiseAction` and `defender_view` interfaces.

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_swarm_compromise.py -q
python -m spiral_ln.swarm_compromise_eval `
  --config configs/swarm_compromise.json `
  --output output/swarm_compromise
```

The campaign reports two complementary defensive readouts: a 0–5
posture-resilience grade (containment, covert-exfiltration suppression,
detection recall, and airgap integrity) and a node-level detector ROC with a
calibration/holdout split. A benign authorized "red team" confound is reported
alongside the adversaries to show that a behavioral grade cannot, on its own,
establish malicious intent. Outputs are written under `output/swarm_compromise`
with `summary.json`, `rows.csv`, `node_scores.csv`, two figures, and a hash
witness receipt. These are synthetic posture results, not a measurement of any
real system or person.

[Red Team Gladiatorics: Crypto Swarm Arena](../paper/rtg_crypto_swarm_arena.md) is a
design specification that extends this laboratory into a control-evaluation
instrument: a formal mandate oracle with three-valued authorization, authorized
"twin" worlds that make a benign confound explicit, a cage/enclave containment
ladder, and falsifiable propensity and control hypotheses. It is a design only;
nothing in it is implemented or reports a result about any model.

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

## Evaluation design calculus

[The proposed evaluation design calculus](../paper/evaluation_design_calculus.md)
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

See [the testbed specification and falsifiers](../paper/evaluation_game_testbed.md).
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

[The Prime Intellect example atlas](../paper/prime_intellect_eval_atlas.md) applies
the calculus to eight Hub-based cases and one current-source task-generation
recipe. It records package versions, proposed interventions, interpretation
limits, and exact diagnostics for shaped rewards and solver-count effects.
The companion design manifest is `configs/prime_intellect_eval_cards.json`.
