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
