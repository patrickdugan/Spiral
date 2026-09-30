# A calculus of evaluation design

Version 0.1 — 2026-09-11. A proposed synthesis for Spiral.

**An evaluation is a designed game, a population of controllers, and an evidence-producing experiment.** Its notation should expose what can be composed, what a transformation preserves, and what the observations support. This document connects game-design concepts to a small mathematical core. It does not claim a universal algebra of games or a validated measure of general intelligence.

The accompanying exact examples are in `configs/evaluation_design_calculus_examples.json`; `scripts/verify_evaluation_design_calculus.py` checks their arithmetic and selected finite instances of the laws. These are mathematical fixtures, not model evaluations. Existing Spiral campaigns remain unchanged.

For applications to published environments, see the [Prime Intellect example atlas](prime_intellect_eval_atlas.md), including proof feedback, 2048 interfaces, simulated users, poker, and learned judges.

## 1. What the literature contributes

| Foundation | Established contribution | Our adaptation |
|---|---|---|
| [Hunicke, LeBlanc, and Zubek, MDA (2004)](https://www.cs.northwestern.edu/~hunicke/MDA.pdf) | Distinguishes mechanics, their runtime dynamics, and players' aesthetic experience. | Separate specified mechanisms from observed behavior and the capability claim. This is an adaptation; evidence is not a replacement definition of MDA's aesthetics. |
| [Juul, emergence and progression (2002)](https://jesperjuul.net/text/openandtheclosed.html) | Distinguishes interacting rules that generate varied play from prescribed sequences of challenges. | Record whether success requires particular steps or allows alternative successful strategies. |
| [Sicart, game mechanics (2008)](https://www.gamestudies.org/0802/articles/sicart) | Analyzes mechanics as methods by which agents interact with a game world. | Give mechanics action types, legal preconditions, and state effects. |
| [Dormans, Machinations (2011)](https://pure.hva.nl/ws/portalfiles/portal/141880/556168_dormans_simulating_mechanics.pdf) | Represents resource flows and feedback structures in game economies. | Use explicit resource ledgers, flow constraints, and local response analysis. |
| [Operational logics, UCSC research group](https://eis.ucsc.edu/analyses-and-approaches/operational-logics/) | Connects abstract computational operations with their communicative role. | Keep state semantics and their presentation to the participant separately inspectable. |
| [Piette et al., Ludii (2020)](https://arxiv.org/abs/1905.05013) | Describes games through composable, understandable game concepts called ludemes. | Define reusable evaluation primitives such as inspection, commitment, resource transfer, and termination. These are our primitives, not a claimed Ludii extension. |
| [Thielscher, GDL-II (2010)](https://cgi.cse.unsw.edu.au/~mit/Papers/AAAI10a.pdf) | Extends formal game descriptions to nondeterminism and restricted information. | Specify legal actions, transitions, private observations, and termination independently. |
| [Ghani et al., compositional game theory (2018)](https://arxiv.org/abs/1603.04641) | Uses open games with sequential and parallel composition, including strategic context. | Borrow the insistence on typed interfaces; distinguish execution composition from composition of strategic incentives. |
| [Nash (1950)](https://doi.org/10.1073/pnas.36.1.48), [Harsanyi (1967)](https://pubsonline.informs.org/doi/abs/10.1287/mnsc.14.3.159) | Equilibrium under unilateral deviations; games with private types and beliefs. | State a strategic reference model and measure deviation opportunities without assuming observed agents optimize the assigned payoff. |

The tuple, operator names, effect annotations, design derivatives, and project mappings below are our proposed synthesis. The linear algebra, probability composition, inclusion–exclusion identities, and elementary equilibrium calculations are standard mathematical constructions applied here. Their general applicability does not follow merely from their game-design inspiration.

## 2. Three objects, three kinds of claim

Write an evaluation as

\[
\mathcal E=\langle G,\Pi,D,Z,J,\mathcal A,C\rangle.
\]

- \(G\): game specification.
- \(\Pi\): the controller roster and execution protocol, including model or policy, instructions, memory, tools, decoding, retries, and resource budgets.
- \(D\): sampling and assignment of game instances, counterparts, conditions, and independent run blocks.
- \(Z\): evidence acquisition; what the evaluator observes and records.
- \(J\): judgment of an acquired trace.
- \(\mathcal A\): aggregation and uncertainty procedure.
- \(C\): claim, target population, and assumptions required for interpretation.

One run produces a full trajectory \(\tau\), an acquired record \(z\), and a judgment \(y\):

\[
\tau\sim P_{G,\Pi,D},\qquad z\sim Z(\cdot\mid\tau),\qquad y=J(z).
\]

Aggregation operates across declared independent blocks, not automatically across every action or message. The claim is an interpretation of the experiment, not another deterministic output of the state machine.

Use this game record:

\[
G=\langle N,X,\Theta,p_0,\{A_i,O_i\}_{i\in N},T,U,H,F\rangle.
\]

Here \(N\) is the player set, \(X\) the world state, \(\Theta\) private types, \(p_0\) their joint initial distribution with the state, \(A_i\) legal moves, \(O_i\) observation channels, \(T\) transitions, \(U\) assigned trajectory utilities, \(H\) the stopping rule, and \(F\) the presentation layer. A turn scheduler can be encoded in the state, with inactive players given a no-op. Information includes any feedback from legality checks, errors, timing, and rewards.

A controller acts from its accessible history: \(\pi_i(a_i\mid h_i)\). A privileged experiment recorder may inspect the full trajectory; a player must not receive that trajectory accidentally through its integration wrapper. A fixed scripted counterparty is part of the environment from the focal player's perspective. Merely naming it a second agent does not make the run evidence of mutual strategic adaptation.

Maintain three distinctions:

1. Assigned utility \(U_i\) specifies a game-theoretic objective; a controller's actual optimization of it is an empirical question.
2. Judgment \(J\) can measure welfare, accuracy, or cost separately from that utility. If judgment is shown during play or used for learning, it also enters observations or controller updates.
3. Claim \(C\) can concern mechanism feasibility, a particular controller, or a target population. These require different evidence.

## 3. A design grammar with effect annotations

Give each transformation a signature, preconditions, scope, and read/write footprint. Denote a valid application by

\[
\Gamma\vdash d:\mathcal E\longrightarrow\mathcal E'
\quad [\operatorname{read}(d);\operatorname{write}(d)].
\]

\(\Gamma\) records facts such as the existence of an inspection action, the absence of leaked private information, or the availability of an external resource account.

| Proposed operator | Primary effect | Required detail |
|---|---|---|
| \(\operatorname{Restrict}_B\) | Legal actions | What actions remain; empty action sets require a defined fallback. |
| \(\operatorname{Budget}_{b,c}\) | State, legality, and resource costs | Initial budget, cost schedule, replenishment, and who sees spending. |
| \(\operatorname{Hide}_{i,q}\) | Player \(i\)'s observations | A specified projection or stochastic channel; include indirect disclosures. |
| \(\operatorname{Observe}_{q}\) | Evaluator acquisition \(Z\) | Sampling and attribution process; whether participants learn the setting. |
| \(\operatorname{Message}_{c}\) | Actions, observations, and possibly costs | Sender, receiver, timing, alphabet, cost, and whether messages bind. |
| \(\operatorname{Commit}_{k}\) | Legal future actions or payoffs | Acceptance, enforcement, default, expiry, and within-round or episode scope. |
| \(\operatorname{Repeat}_{H,m}\) | Horizon, state, and controller memory | Identity persistence, reset map, termination knowledge, and payoff discounting. |
| \(\operatorname{Payoff}_{u}\) | Assigned utility | Whether implementation also changes resources, displayed feedback, or training. |
| \(\operatorname{Reframe}_{f}\) | Presentation | A bijective semantic mapping, or an explicit admission that task meaning changed. |
| \(\operatorname{Controller}_{\pi}\) | Controller roster/protocol | Which players change, with what information and budget. |
| \(\operatorname{Rescore}_{j}\) | Judgment | Only offline rescoring is automatically outside the game. |

These are distinct types of operation. A resource injection is not just a reward edit. Giving an evaluator access to hidden state does not give a player that access. A message channel is not a signal-count variable unless it actually carries content that another controller can interpret.

Mechanics form a feasible design space constrained by \(\Gamma\), not an unrestricted Cartesian product. A commitment to unavailable actions or a private message without a recipient channel is ill-typed. Record rejected combinations rather than silently dropping them from a factorial study.

## 4. Composition: execution first, strategic context second

For finite state interfaces, an executed fragment with fixed controllers can be represented by a stochastic kernel \(K:X\rightsquigarrow Y\). Carry relevant history and accumulated payoff in the interfaces. Define

\[
(K;L)(z\mid x)=\sum_y K(y\mid x)L(z\mid y).
\]

The interface types must match. Finite summation proves

\[
(K;L);M=K;(L;M),\qquad \mathrm{id};K=K=K;\mathrm{id}.
\]

Parallel independent execution has

\[
(K\otimes L)(y_1,y_2\mid x_1,x_2)
=K(y_1\mid x_1)L(y_2\mid x_2).
\]

With matching interfaces and independent factors,

\[
(K_1\otimes K_2);(L_1\otimes L_2)
=(K_1;L_1)\otimes(K_2;L_2).
\]

Shared capital, shared randomness, or controllers coordinating across fragments violate that factorization unless explicitly represented in the interface. Repeating a kernel also requires a declared reset/carry map; independent episodes and a repeated strategic relationship have different semantics.

These laws describe execution distributions. An equilibrium of each isolated fragment need not remain an equilibrium when downstream incentives are introduced. Open-game theory supplies richer strategic interfaces, including continuation utility; this document does not implement that formalism or prove an embedding into it. [Ghani et al.](https://arxiv.org/abs/1603.04641)

## 5. Laws, counterexamples, and preservation levels

Use a preservation annotation \(d:G\xrightarrow{P}G'\). Useful predicates \(P\) include conservation, legal-trace correspondence, information correspondence, payoff correspondence, and best-response correspondence. Measurement validity is a separate obligation.

**Projection law.** A deterministic deletion of a fixed set of visible fields is idempotent: \(H(H(o))=H(o)\). Two fresh independent sampling passes with retention \(q\), however, retain with probability \(q^2\). Reapplying random observation loss is not idempotent.

**Disjoint-update law.** Two pure, deterministic transformations commute if neither writes anything the other reads or writes, including implicit dependencies, metadata, and randomness. This is a sufficient condition, not a necessary one. The claim is about transformations applied at design time; it does not say their effects on behavior are additive.

**Order effect.** Granting two budget units and capping the balance at five do not commute. Starting at four, cap-after-grant yields five; grant-after-cap yields six. Thus an expression's order belongs in its saved design record.

**Renaming law.** A bijection on states, actions, observations, and payoffs preserves corresponding strategic possibilities when policies and measurements are transported through the same bijection. An unchanged language model receiving new prose is not a transported policy. Its sensitivity is a result to measure, not a contradiction of game isomorphism.

**Utility law.** For expected-utility comparisons, replacing each player's total trajectory utility by \(a_iU_i+b_i\), \(a_i>0\), preserves that player's best responses and therefore Nash equilibria. A per-step constant can change preferences when episode lengths differ. An arbitrary increasing nonlinear transformation need not preserve preferences over lotteries: a fair lottery paying zero or four has mean two, below a sure 2.1; squaring outcomes reverses the ordering, giving eight versus 4.41. This says nothing about whether a prompted model is invariant to rescaling.

**Mixture law.** For a fixed controller and compatible scalar measurement, expectation under a mixture is the corresponding weighted expectation. Optimizing after revealing which component was selected is a different experiment. In general \(\max_\pi\sum_i w_iV_i(\pi)\leq\sum_iw_i\max_\pi V_i(\pi)\). Averaging separately optimal scores can overstate achievable performance in a hidden mixture.

No unconditional claim is made that hiding information lowers observed performance, that additional tools raise it, or that repetition produces cooperation.

## 6. A resource-flow calculus

Following Machinations' emphasis on stocks, flows, and feedback, represent stocks of one declared resource type by \(x_t\), flows by \(f_t\), and net incidence by \(B\):

\[
x_{t+1}=x_t+Bf_t+s_t-d_t.
\]

Here \(s_t,d_t\) are external sources and drains. Admissibility requires nonnegative balances, capacities, action authorization, and sufficient resources at the moment each transfer fires. A feasible final balance alone does not guarantee a sequential execution exists.

If \(w^TB=0\), then

\[
w^Tx_{t+1}-w^Tx_t=w^T(s_t-d_t).
\]

This is a direct conservation proof. Transfers cancel; external creation and destruction remain explicit. Separate resource types need separate ledgers or justified conversion rates. One cannot add money, privacy, and success percentages into a conservation equation.

A simple three-account example starts at \((10,0,0)\). Transfer three from account one to two and two from account two to three. The final stock is \((7,1,2)\), with total ten. An explicit source of four changes the total to fourteen. In Spiral, a coordination-income bonus must appear as such a source; its configured contribution is not evidence of discovered productivity.

For a smooth deterministic approximation \(x_{t+1}=F(x_t,a_t;\lambda)\), a differentiable fixed feedback policy \(a_t=\pi(x_t)\) gives the local state Jacobian

\[
J_x=\frac{\partial F}{\partial x}
+\frac{\partial F}{\partial a}\frac{\partial\pi}{\partial x}.
\]

At a fixed point, spectral radius below one is a sufficient local stability condition for this differentiable discrete-time system. Discrete actions, thresholds, stochastic controllers, and changes of equilibrium require separate treatment. This is an optional approximation for feedback analysis, not an established stability result for the existing simulator.

## 7. A calculus of design effects

Let \(V_\pi(d)\) be the expected scalar measurement for a frozen controller protocol, target sampling law, and design \(d\). Define a design difference

\[
\Delta_aV_\pi(d)=V_\pi(a(d))-V_\pi(d).
\]

For two independent binary settings, define their interaction on a chosen outcome scale:

\[
\Delta_{ab}V=V_{11}-V_{10}-V_{01}+V_{00}.
\]

This asks whether the combined effect exceeds the sum of the individual effects. It differs from an order effect,

\[
\Omega_{a,b}V(d)=V(a(b(d)))-V(b(a(d))).
\]

Two commuting configuration switches can have a large interaction. Noncommuting transformations require the order to be specified before constructing the four cells.

For a fully feasible set of binary mechanics \(M\), use the subset lattice:

\[
\beta_S=\sum_{T\subseteq S}(-1)^{|S|-|T|}V(T),
\qquad
V(S)=\sum_{T\subseteq S}\beta_T.
\]

This inclusion–exclusion expansion separates baseline, individual contributions, and higher-order interactions relative to the all-off design. It is an exact representation of the cell means, not a proof of causality. It requires all relevant subset cells; nested ablations alone cannot identify every interaction. Effects depend on the chosen measurement scale.

For a continuous parameter, a finite difference

\[
D_hV(\lambda)=\frac{V(\lambda+h)-V(\lambda)}{h}
\]

can approximate a derivative where smoothness is justified. Preserve it as a finite difference around discontinuities. Always distinguish frozen-controller sensitivity from sensitivity after retraining, selecting another controller, or selecting another equilibrium.

Estimate paired differences within independent run blocks, using matched exogenous cases and separate random streams for independent mechanisms. A common seed alone is insufficient when conditions consume different random draws. Freeze sampling, outcome scale, counterpart roster, multiplicity handling, and stopping before confirmation. A notation does not repair a confounded design.

## 8. Exact example: information and usable alternatives

There are two locations, left and right. Exactly one contains a unit-valued resource, each with probability one half. A single player chooses a location once.

- \(I=0\): the player cannot see which location contains the resource.
- \(I=1\): the location is revealed before action.
- \(B=0\): only the left action is legal.
- \(B=1\): either action is legal.

Use the optimal admissible decision rule in each cell, explicitly marking this as an analytical ceiling \(V^*\), not a model score.

| | Left only | Either location |
|---|---:|---:|
| Hidden resource | 0.5 | 0.5 |
| Revealed resource | 0.5 | 1.0 |

Thus \(\Delta_{IB}V^*=0.5\). Information has zero value with no usable alternative, but value 0.5 when choice is available. The subset coefficients are baseline 0.5, information 0, alternative action 0, and interaction 0.5.

The verifier enumerates every deterministic observation-respecting policy. Randomization cannot improve this finite single-player optimum because expected reward is linear in the policy. This is a finite proof by exhaustion for this fixture only.

The same fixture tests mixture disclosure: separately solving each known resource location yields one; mixing the locations without disclosing which was selected yields 0.5 even when both actions are available.

## 9. Exact example: cooperation and strategic stability

Use the two-action social dilemma discussed in the conversation:

| A / B | Share | Take |
|---|---:|---:|
| Share | 3, 3 | 0, 5 |
| Take | 5, 0 | 1, 1 |

Taking is strictly dominant for each player. The unique Nash equilibrium is mutual taking; mutual sharing has higher total welfare. This follows directly from the four payoff comparisons.

For a strategy profile \(\pi\), record each player's best unilateral improvement:

\[
r_i(\pi)=\sup_{\pi_i'}\mathbb E[U_i(\pi_i',\pi_{-i})]
-\mathbb E[U_i(\pi)].
\]

With exact optimization, all gaps at most \(\epsilon\) define an \(\epsilon\)-Nash profile. Restricted deviation searches give lower bounds on the true gap. Estimated payoffs also require uncertainty. For a pure profile in this two-action game, enumerating pure deviations suffices because expected utility is linear in mixed deviations. Mutual sharing has gap two for each player; mutual taking has gap zero and total welfare two. [Nash's definition](https://doi.org/10.1073/pnas.36.1.48)

An externally imposed levy of three utility units on taking changes the table to \((3,3),(0,2),(2,0),(-2,-2)\). Sharing becomes strictly dominant. That is a change of incentives, not evidence that the controller acquired cooperation skills. The levy is burned, not transferred to the other player. It is not an opt-in commitment mechanism; modeling opt-in would require an additional decision stage.

For the original table in a commonly known finite repetition with no cross-round contracts, additive utilities, and payoff-maximizing players, backward induction yields taking in every round in the subgame-perfect equilibrium. For an indefinitely repeated game with common discount \(\delta\), perfect public monitoring, and grim-trigger strategies, cooperation is sustainable when

\[
\frac{3}{1-\delta}\geq5+\frac{\delta}{1-\delta}
\quad\Longleftrightarrow\quad \delta\geq\frac12.
\]

Punishment is credible because mutual taking is a stage equilibrium. This is an exact derivation under the stated assumptions; it does not predict that real controllers will discover or select that equilibrium. The verifier checks discounted values below, at, and above the threshold.

For private-type games, specify the prior, what each player observes, and beliefs needed by the reference model. Bayesian equilibrium addresses type uncertainty; sequential rationality matters for threats and commitments. Equilibrium selection, population performance, welfare, and deviation resistance should remain separate measurements. [Harsanyi](https://pubsonline.informs.org/doi/abs/10.1287/mnsc.14.3.159)

## 10. Application to Spiral's existing designs

These mappings are based on the current source and protocol, not a new experimental run.

| Existing element | Calculus interpretation | Consequence |
|---|---|---|
| `DesignTropes.private_relationships` | Relationship state, action legality, private designation, observer attribution, and displayed configuration | It is not simply an information-hiding operator. Economic equivalence requires the other dependent mechanisms to be controlled. |
| `repeat_counterparties` | Built-in counterparty-selection policy | With externally supplied `AgentAction` choices, the internal selector is bypassed. Toggling it is not automatically an intervention on an external model's strategy. |
| `abstract_signaling` | A bounded counter and associated legality/metadata | No message content or receiver decoding exists. It cannot support a claim about language communication. |
| `coordination_bonus` | External source conditioned on coalition classification | Added productivity is an explicit mechanism assumption. |
| `liquidity_reinvestment` | Resource transfer into connector capacity, selected by an environment rule | Distinguish that allocation heuristic from an agent choosing an investment. |
| `partial_observer` | Observer acquisition plus visible configuration metadata | `false` currently disables observer events; it does not grant complete observation. Because enabled tropes appear in `agent_view`, an external policy could also respond to this setting. |
| `hive_min_reciprocity` | Coalition classification, and potentially income/investment eligibility | A threshold sweep can change both measurement and world dynamics when dependent mechanisms are enabled. An offline classification sweep would be a different operation. |
| `agent_view`, `observer_view`, `observation` | Player channel, sampled observer channel, privileged experiment record | `step()` returns the privileged record. An external-policy adapter must deliberately use the player channel to uphold an information restriction. |
| Sandbagging v3 matched conditions | Controller/presentation intervention with blocked evidence acquisition | A condition-dependent score difference is not by itself proof of strategic intent or a verified game isomorphism. |

Source anchors: `src/spiral_ln/hive_lab.py` (`DesignTropes`, `_counterparty`, `_observer_flags`, `_attempt_purchase`, `hives`, `_earn_external_income`, `_maybe_invest_connector`, `agent_view`, `step`); `src/spiral_ln/hive_design_experiment.py`; `paper/sandbagging_v3_protocol.md`.

The existing nested trope ablations show increments along one chosen path. They do not supply all subset cells for the full interaction expansion. The existing phase sweep mixes a policy parameter with a coalition threshold; its interpretation must name which dependent rules are enabled.

## 11. A reusable evaluation card

Every design should declare:

1. **Claim and population:** the behavior being tested and where the conclusion is intended to apply.
2. **Game and primitives:** state, legal actions, transitions, resource ledgers, observation channels, utilities, stopping, and presentation.
3. **Controllers:** focal policy, counterparts, memory, prompts, tools, budgets, and any learning or selection between episodes.
4. **Design expression:** ordered, scoped operators with preconditions, footprints, and preservation obligations.
5. **Reference model:** fixed-policy baseline, optimal decision rule, Nash/Bayesian/sequential reference, or an explicitly heuristic comparator.
6. **Acquisition and judgment:** privileged versus accessible data, blind scoring where relevant, and whether any score feeds back into play.
7. **Estimand:** main effect, interaction, order effect, frontier, calibration error, welfare, or unilateral-improvement gap.
8. **Inference:** assignment, independent blocks, frozen selection/confirmation boundary, uncertainty, and multiplicity.
9. **Evidence status:** algebraic identity, finite verified example, synthetic mechanism result, observed-controller result, or externally validated claim.

The first implementation priority would be compiling these cards against real adapters and checking observation boundaries. A full game-language compiler, open-game strategic semantics, and real-model campaigns are subsequent goals, not results delivered by this document.

## 12. Exact follow-up: estimands, Hide, and incentive response

The companion [evaluation-game testbed](evaluation_game_testbed.md) makes four
non-interchangeable estimands executable in small rational fixtures: baseline
gain, robust regret, acquired-record discrimination gap, and exploitability.
It types observation-only `Hide` as one common post-play Markov kernel and
checks the resulting loss of measurement discrimination. It separately verifies
that hiding information from a player before action changes the game and can
change optimal value. The testbed also records equilibrium sets and selected
outcomes under a declared adaptation rule, marks restricted best response as a
lower bound, includes a tiny zero-sum primal/dual witness, and documents a
difficulty-matched, grader-severity-stratified held-out incentive interaction.
These are exact synthetic design checks, not model or multi-agent results.
