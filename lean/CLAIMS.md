# Lean claims

Each row links a result in the notes to the Lean theorem that proves it. Fidelity says how the Lean
statement relates to the note: *full* (the claim as the note states it), *special case* (which one),
or *supporting lemma* (what remains). Every theorem here is listed in `axioms_check.lean`, whose
output is only `propext`, `Classical.choice` and `Quot.sound`: no `sorry`, no added axioms, no
compiled-code evaluation. Line numbers refer to this commit.

## The lattice note (`paper/evaluation_feedback_lattice.md`, version 0.6)

Every theorem below is listed in `axioms_lattice.lean`. `#print axioms` gives
`[propext, Classical.choice, Quot.sound]` for 49 of them and `[propext, Quot.sound]` for
`prop7_context_pair`. The files contain no `sorry`, no new axioms and no compiled-code
evaluation. Concrete values come from `decide` (multisets, finite sets) and `norm_num` (rationals).

**Programme model (`FeedbackChannel.PatchDP`).** A state is a multiset of pairs `(n, F)` with
`F ≤ n` (`Valid`). A patch picks a category with `n ≥ 1`. It hits with probability `F/n`, leaving
`(n-1, F-1)`, and otherwise leaves `(n-1, F)`. `val H s` is the Bellman minimum of the expected
patches to `H` hits, computed with fuel equal to the items left (`dp`, `val_succ`). It differs
from the Python `_optimal_value` in two ways, and neither changes a value on a feasible state:
(i) categories with `F = 0` stay in the state and may be patched, a wasted patch, which the note's
policy class allows; (ii) an infeasible state (more hits needed than failures left) has the junk
value 0, and every theorem assumes feasibility. `val_le_pval` shows that no legal stationary
policy (a function of hits needed and state) does better than `val`. Randomised and
history-dependent policies are not modelled. The values agree with the Python programme on every
witness state.

| Note | Claim (label as in the note) | Lean theorem (fully qualified) | File:line | Fidelity | Remarks |
|---|---|---|---|---|---|
| §3 | Theorem 10: one hit, optimum `min_c (n_c+1)/(F_c+1)` | `FeedbackChannel.PatchDP.theorem10` | FeedbackChannel/PatchDP.lean:299 | full | `IsLeast` over the categories with `F_c ≥ 1`, for a valid state with at least one failure. Proved by the note's induction on items (`val_one_le_finisher`:192, `le_val_one`:233). **Underspecified in the note:** the minimum has to be restricted to `F_c ≥ 1`. Python does this (`one_hit_value`); read literally the formula is wrong, e.g. `{(1,0),(10,1)}` gives 2 instead of 11/2. The note's "any other `c′`" step also leaves out `F_{c′} = 0` (it divides by `F_{c′}`), and the proof handles that case separately. |
| §3 | Theorem 10: optimum in evaluation form | `FeedbackChannel.PatchDP.val_one_eq` | FeedbackChannel/PatchDP.lean:316 | supporting lemma | Used for every one-hit value of a concrete state. |
| §3 | Theorem 10: "attained by patching a category of minimal (n+1)/(F+1) until it hits and never switching" | `FeedbackChannel.PatchDP.theorem10_attained` | FeedbackChannel/PatchDP.lean:351 | full | For a best finisher: patching it first is optimal; after a miss it stays a best finisher; the never-switching cost `stick n F` equals the optimum. |
| §3 | "Sticking with c costs 1+(1−F/n) n/(F+1) = (n+1)/(F+1)" | `FeedbackChannel.PatchDP.stick_eq` | FeedbackChannel/PatchDP.lean:328 | full | |
| §3 | Theorem 10 witness: in `{(2,1),(16,9)}` the rates are 1/2 < 9/16, yet (2,1) first costs 3/2 against 53/32 | `FeedbackChannel.PatchDP.one_hit_rate_witness` | FeedbackChannel/PatchDP.lean:399 | full | Finite. |
| §3 | Bellman equation of `optimal_adaptive_value` | `FeedbackChannel.PatchDP.val_succ`, `FeedbackChannel.PatchDP.val_eq_of_cert` | FeedbackChannel/PatchDP.lean:112, 139 | supporting lemma | Definition of the programme; certificate form for exact evaluation. |
| §3 | The programme is a lower bound for every policy | `FeedbackChannel.PatchDP.val_le_pval` | FeedbackChannel/PatchDP.lean:551 | supporting lemma | Stationary deterministic legal policies only. A policy's cost is also at least the continuation value of its own first patch. |
| §3 | Prop 4, one category: `E[T] = H(n+1)/(F+1)` (negative-hypergeometric mean) | `FeedbackChannel.PatchDP.val_single` | FeedbackChannel/PatchDP.lean:439 | full | For `H ≤ F ≤ n`. With one category the programme has a single choice, so `val` is the expected stopping time of patching uniformly at random without replacement (first-step analysis). A combinatorial statement over random `F`-subsets is not formalized. |
| §3 | Prop 4: `E[T] = N_{<j} + H_j(n_j+1)/(F_j+1)` for the static schedule | `FeedbackChannel.PatchStatic.prop4_staticT` | FeedbackChannel/PatchStatic.lean:207 | full | Holds for every fixed order, the greedy order included. `staticT` is the expected stopping time by first-step analysis (`sdp`), with earlier categories patched completely (`staticT_skip`:164, `staticT_within`:136). The split `pre ++ c :: post` with `F(pre) < H ≤ F(pre)+F_j` is the note's `j`. |
| §3 | Prop 4: the expected score reaches the ceiling at `m* = N_{<j} + H_j n_j/F_j` | `FeedbackChannel.PatchStatic.prop4_crossing` | FeedbackChannel/PatchStatic.lean:254 | full | `curve` is the piecewise-linear fill curve (`expected_hits_after`): it equals `H` at `m*` and is below `H` at every earlier count. At whole counts inside a category it is the hypergeometric mean (`curve_single`:240, from Prop 3). |
| §3 | Prop 4: `m* − E[T] = H_j(n_j−F_j)/(F_j(F_j+1)) ∈ [0, m*/(F_j+1))` | `FeedbackChannel.PatchStatic.prop4_gap` | FeedbackChannel/PatchStatic.lean:328 | full | |
| §3 | Prop 4 numbers: one category, `m*/n = (1−ε−v)/(1−v) = 8/13`, `E[T] = 204/7` | `FeedbackChannel.PatchStatic.prop4_one_category` | FeedbackChannel/PatchStatic.lean:361 | full | `n=50, F=13, H=8, ε=1/10, v=37/50`. Also checks that `val 8 {(50,13)} = 204/7`. Deriving `H = 8` from the noise ceiling (insertions note) is not formalized. |
| §3 | Prop 4 numbers: singleton categories, both equal `H`, share 4/25 | `FeedbackChannel.PatchStatic.prop4_singletons` | FeedbackChannel/PatchStatic.lean:370 | full | 13 failing and 37 passing singletons, failures first. |
| §3 | Prop 3: the j-th patch hits with unconditional probability `F_c/n_c` for every j | `FeedbackChannel.PatchStatic.prop3_hitProb` | FeedbackChannel/PatchStatic.lean:32 | full | The conditional probability `(F_c−h)/(n_c−j+1)` is the model's transition (`rate` of the remaining pair). |
| §3 | Prop 3: `m_c` patches hit `m_c F_c/n_c` in expectation (hypergeometric mean) | `FeedbackChannel.PatchStatic.prop3_expHits` | FeedbackChannel/PatchStatic.lean:65 | full | |
| §3 | Prop 3: filling categories in decreasing order of `F_c/n_c` maximizes expected hits at every patch count | `FeedbackChannel.PatchGreedy.prop3_greedy` | FeedbackChannel/PatchGreedy.lean:218 | full | `IsGreatest` over all allocations of total `M`, fractional ones included, at every `0 ≤ M ≤ n`. The value of an allocation is `Σ m_c F_c/n_c`, which by Prop 3 does not depend on the order of the patches. The proof uses a Lagrangian bound (`curve_le_dual`:57, `curve_eq_dual`:85, `alloc_le_dual`:142), not the note's exchange argument. |
| §3 | Prop 5: if `γ′` refines `γ` then `m*(γ′) ≤ m*(γ)` for every failure pattern | `FeedbackChannel.PatchGreedy.prop5` | FeedbackChannel/PatchGreedy.lean:336 | full | Slightly stronger than stated: the coarse schedule may use any order. A category map is given as its list of `(n_c, F_c)`. `Refines` groups the fine categories into one part per coarse category, whose counts add up. The key step is `curve_mono_refine`:298 (the coarse curve lies below the fine greedy curve), which plays the role of the note's proportional allocation. |
| §3 | "The stopping time under the static schedule is not monotone": `(4,2)`, H=2 gives 10/3; `(2,1),(2,1)` gives 7/2 | `FeedbackChannel.PatchStatic.static_not_monotone` | FeedbackChannel/PatchStatic.lean:391 | full | Finite. The six-item example (record `001101`) is not formalized. |
| §3 | Lemma 9 (pair commutation) | `FeedbackChannel.PatchDP.lemma9` | FeedbackChannel/PatchDP.lean:493 | full | `twoPatch` is `two_patch_value`. The hypothesis `H ≥ 2` is not needed for the algebraic identity; it is kept because `twoPatch` models the two-patch run only when `H ≥ 2`. |
| §3 | Prop 7 values: H=2, (2,1) before (4,2) is 5/2 against 8/3 in `{(1,1),(2,1),(4,2)}` and 19/6 against 37/12 in `{(2,1),(4,2)}` | `FeedbackChannel.PatchWitness.prop7_note_values` | FeedbackChannel/PatchWitness.lean:2148 | full | The values are computed from the programme's definition. 325 generated lemmas evaluate every reachable state. |
| §3 | Prop 7 values, second witness (H=3, ten items, five failures, four categories) | `FeedbackChannel.PatchWitness3.prop7_note_context_values` | FeedbackChannel/PatchWitness3.lean:1913 | full | 9/2 against 55/12, and 25/6 against 49/12. Also checks the totals. |
| §3 | Prop 7: "No such rule is optimal": the note's proof | `FeedbackChannel.PatchWitness.prop7_note_pair_insufficient` | FeedbackChannel/PatchWitness.lean:2159 | supporting lemma | **Gap in the note's proof.** In `{(1,1),(2,1),(4,2)}` the category `(1,1)` is also optimal (5/2). So the ranking `(1,1)` over `(4,2)` over `(2,1)` makes an optimal first patch in both of the note's states. The same holds for the second witness, where `(1,1)` ties `(4,2)` at 49/12. A reversal refutes an index rule only when the preferred category is the unique optimum. |
| §3 | Prop 7 (own counts), corrected witness pair | `FeedbackChannel.PatchWitness.prop7_own_counts` | FeedbackChannel/PatchWitness.lean:2178 | full | `{(2,1),(2,1),(4,2)}` (3 against 37/12) and `{(2,1),(4,2)}`, H=2, both with unique optima. Holds for every strict index (`key (2,1) ≠ key (4,2)`), i.e. a fixed tie-break, which the note's "ranks the same way" presupposes. With state-dependent tie-breaking no index rule can be refuted. |
| §3 | Prop 7 (own counts), policy form: the rule's expected cost exceeds the optimum | `FeedbackChannel.PatchWitness.prop7_own_counts_policy` | FeedbackChannel/PatchWitness.lean:2199 | full | Via `val_le_pval`. |
| §3 | Prop 7 with totals and category count, corrected witness pair | `FeedbackChannel.PatchWitness.prop7_with_context` | FeedbackChannel/PatchWitness.lean:2226 | full | `{(2,1),(2,1),(4,1),(4,2)}` and `{(2,1),(3,1),(3,1),(4,2)}`, H=2. They agree on items (12), failures (5) and categories (4) (`prop7_context_pair`:2213), so this covers both richer contexts. The enumeration counts (30/125/120 reversals) are not formalized; they count reversals, not refuting pairs. |
| §3 | Prop 8 witness: `{(2,1),(5,2)}`, H=2, (5,2) first 69/20, (2,1) first 7/2 | `FeedbackChannel.PatchWitness.prop8_witness` | FeedbackChannel/PatchWitness.lean:2252 | full | Finite; 69/20 is the optimum. The counts (82, 131) are not formalized. |
| §3 | "Greedy is not optimal": `(4,2),(2,1)`, H=2, greedy 19/6 against 37/12 | `FeedbackChannel.PatchWitness.greedy_not_optimal` | FeedbackChannel/PatchWitness.lean:2263 | special case | Every legal policy that patches `(2,1)` first, as greedy does when rates tie, costs at least 19/6, more than 37/12. Greedy's exact value 19/6 is not proved. |
| §2 | Prop 2c: `Φ(γ)∨Φ(γ′) = Φ(γ∨γ′)` iff `I(γ,γ′)` is acyclic | `FeedbackChannel.LatticeJoin.prop2c` | FeedbackChannel/LatticeJoin.lean:476 | full | Category maps are labelings `ι → R`, `ι → C`. Records are `ι → Bool`. "Equal row and column counts iff equal cell counts, for all records" iff Mathlib's `SimpleGraph.IsAcyclic` holds for the bipartite intersection graph on `R ⊕ C`. |
| §2 | Prop 2c in lattice form (Setoid kernels; the note's `∨` is Mathlib's `⊓`) | `FeedbackChannel.LatticeJoin.prop2c_setoid` | FeedbackChannel/LatticeJoin.lean:501 | full | |
| §2 | Prop 2c core: on the box `0 ≤ w ≤ |cell|`, margins determine the cell weights iff the graph is acyclic | `FeedbackChannel.LatticeJoin.margins_determine_iff_acyclic` | FeedbackChannel/LatticeJoin.lean:317 | full | Forest direction: a cut across a bridge (`acyclic_margins_zero`:63). Cycle direction: a `±1` alternating weight along a path that closes a non-bridge edge (`not_acyclic_witness`:253). The note peels leaves and uses an explicit cycle instead; the statements are the same. |
| §2 | Prop 2c core, integer weights (no box) | `FeedbackChannel.LatticeJoin.margins_determine_int_iff` | FeedbackChannel/LatticeJoin.lean:301 | full | |
| §2 | Prop 2c: "cell counts determine margins, so the refined channel is always at least as fine" | `FeedbackChannel.LatticeJoin.cells_determine_margins` | FeedbackChannel/LatticeJoin.lean:467 | full | |
| §2 | Prop 2c witness: rows `{0,1}|{2,3}`, columns `{0,2}|{1,3}`, records `1001`, `0110` | `FeedbackChannel.LatticeJoin.prop2c_four_cycle_witness` | FeedbackChannel/LatticeJoin.lean:511 | full | Finite; also derives that the 4-cycle graph is not acyclic. |
| §1 | Prop 1: `p ≤ q` implies `TV(p#P,p#Q) ≤ TV(q#P,q#Q)` | `FeedbackChannel.LatticeOrder.prop1_mono` | FeedbackChannel/LatticeOrder.lean:35 | full | Records are any finite type and channels are functions; `TV` is `max_U |P(U)−Q(U)|` over unions of blocks, as in the note's proof. `P, Q` are arbitrary rational weights, so all distributions are included. |
| §1 | Prop 1 converse: if `p ≰ q`, point masses give TV 1 through `p` and 0 through `q` | `FeedbackChannel.LatticeOrder.prop1_converse` | FeedbackChannel/LatticeOrder.lean:62 | full | |
| §2 | Prop 2: `Φ(γ) ≤ Φ(γ′)` iff `γ ≤ γ′` (order embedding) | `FeedbackChannel.LatticeOrder.prop2` | FeedbackChannel/LatticeOrder.lean:126 | full | Labelings; `Φ` is the per-block pass counts. |
| §2 | Prop 2 endpoint: `Φ(singletons)` = item-level | `FeedbackChannel.LatticeOrder.prop2_item_level` | FeedbackChannel/LatticeOrder.lean:156 | full | The `score_only` endpoint holds by definition (one block gives the total pass count) and is not stated separately. |

**Not formalized:** Proposition 2b (meets are preserved; it needs the "transpositions along a
connected graph" argument), Proposition 6 (the optimal adaptive schedule is monotone; it needs a
model of policies under coarser information), the commit-until-hit witness, the claim that greedy
is optimal when every failure must be hit, the lattice fixtures, and every enumeration count.

## The training-signal, judge-measurement and gold-calibration notes


Modules `FeedbackChannel/Signal.lean`, `Judge.lean`, `Raters.lean`, `RatersJacobian.lean` (no
dependencies between them; build order as listed). `axioms_algebra.lean` prints the axioms of every
theorem below; all 75 report exactly `[propext, Classical.choice, Quot.sound]`. No `sorry`,
`admit`, `native_decide` or added axioms. Fresh build of the four modules: 26 s.

Fidelity: **full** = the note's claim with its quantifiers and hypotheses (sometimes stronger);
**special case** = a restricted instance (stated which); **supporting** = a lemma the claim rests
on (stated what remains). Paths are relative to `lean/`.

Notes: TS = `paper/rl_training_signal_limits.md`; INS = `paper/evaluation_feedback_insertions.md`;
JM = `paper/judge_shared_error_measurement.md`; GC = `paper/gold_calibration_second_grader.md`.

| Note | Claim (label as in the note) | Lean theorem (fully qualified) | File:line | Fidelity | Remarks |
|---|---|---|---|---|---|
| TS | L1/L2 counting core | `FeedbackChannel.Signal.Strategy.card_le_pow` | FeedbackChannel/Signal.lean:69 | supporting | Adaptive strategies are depth-`q` decision trees (`Strategy`); if every candidate's answers lie in a set of `m` values and the output separates candidates, `#cands ≤ m^q`. L1 and L2 are instances. |
| TS | L1: a deterministic channel with `m` images separates at most `m^q` hypotheses in `q` episodes | `FeedbackChannel.Signal.L1_card_le` | FeedbackChannel/Signal.lean:112 | full | Episodes may be chosen adaptively; hypothesis `h` and action `x` give the step record `record h x`, the loop sees `ch (record h x)`; `m = #(image of ch)`. |
| TS | L1: at least `⌈log H / log m⌉` episodes | `FeedbackChannel.Signal.L1_episodes` | FeedbackChannel/Signal.lean:122 | full | Real-log ceiling form, and `Nat.clog m H ≤ q` for `m ≥ 2`. Uses `ceil_log_div_le_of_le_pow` (Signal.lean:85). For `m ≤ 1` the real-log form holds by Lean's `log 1 = 0`, `x/0 = 0`. |
| TS | L1 example: `T = 3`, eight hypotheses: ≥ 3 outcome-reward episodes | `FeedbackChannel.Signal.L1_example_outcome` | FeedbackChannel/Signal.lean:135 | full | Lower bound only, as the note claims. |
| TS | L1 example: ≥ 1 process-reward episode | `FeedbackChannel.Signal.L1_example_process` | FeedbackChannel/Signal.lean:151 | full | |
| TS | L1: partial credit and first-failure are incomparable (neither factors through the other) | `FeedbackChannel.Signal.L1_incomparable` | FeedbackChannel/Signal.lean:183 | full | Proved for every `T ≥ 2` (the note checks `T ≤ 5`). For `T ≤ 1` the two channels coincide, so `T ≥ 2` is necessary. `m = T + 1` for these channels is not formalized. |
| TS | L2: each score query returns one of `f + 1` values | `FeedbackChannel.Signal.patchedScore_mem` | FeedbackChannel/Signal.lean:236 | supporting | Query = patch a subset `Q`, read the number of passing items; with `|S| = f` the score lies in `[n - f, n]`. |
| TS | L2 lower bound: `(f+1)^q ≥ C(n, f)` | `FeedbackChannel.Signal.L2_lower_bound` | FeedbackChannel/Signal.lean:253 | full | Any adaptive strategy of `q` score queries whose output separates the failure sets of size `f`. |
| TS | L2: `q_min(n,f) ≥ ⌈log C(n,f) / log(f+1)⌉` | `FeedbackChannel.Signal.L2_qmin` | FeedbackChannel/Signal.lean:269 | full | For strategies whose output is the failure set; also `Nat.clog (f+1) C(n,f) ≤ q` for `f ≥ 1`. The halving upper bound `f⌈log₂ n⌉ + 1` and the exact minimax values are not formalized. |
| TS / INS | Ceiling law: a predictor blind to flips at rate `ε < 1/2` does not exceed `1 - ε` | `FeedbackChannel.Signal.L3_ceiling` | FeedbackChannel/Signal.lean:288 | special case | Per item: right on the true label with probability `c ≤ 1` gives observed accuracy `≤ 1 - ε` (for `ε ≤ 1/2`). Averaging over items is not stated. |
| TS / INS | L3, blind memorization: crosses the ceiling iff share `> (1 - ε - v)/(1 - v)` | `FeedbackChannel.Signal.L3_blind` | FeedbackChannel/Signal.lean:302 | full | From the insertions note's score `m/n + (1 - m/n) v` (`blindScore`), `v < 1`. |
| TS / INS | L3, patching failures: crosses iff share `> 1 - ε - v` | `FeedbackChannel.Signal.L3_patch` | FeedbackChannel/Signal.lean:310 | full | From the note's score `v + m/n` (`patchScore`). |
| INS | Patching failures: same threshold `(1 - ε - v)/(1 - v)` as a share of the failed items | `FeedbackChannel.Signal.L3_patch_share_of_failed` | FeedbackChannel/Signal.lean:316 | full | `v < 1`. |
| INS | Score after patching failed items is `v + m/n` | `FeedbackChannel.Signal.L3_patch_count` | FeedbackChannel/Signal.lean:324 | supporting | Item-level derivation of the formula the note states: `|P ∪ M|/n = |P|/n + |M|/n` for `M` inside the failures. Assumes, as the note does, that a patch changes only its own item. |
| INS | Score after blind memorization is `m/n + (1 - m/n) v` | `FeedbackChannel.Signal.L3_blind_average` | FeedbackChannel/Signal.lean:337 | supporting | Item-level derivation: averaged over all `C(n, m)` memorized sets of size `m`, `|P ∪ M|/n = m/n + (1 - m/n)|P|/n` ("chosen without regard to outcomes" read as uniformly at random). |
| TS / INS | L3 fixture: `v = 37/50`; thresholds `8/13` (blind) and `4/25` (patching), `= 8/13` of failed items | `FeedbackChannel.Signal.L3_fixture`, `FeedbackChannel.Signal.L3_fixture_thresholds` | FeedbackChannel/Signal.lean:382, :392 | full | `v` computed from clean accuracy `4/5` and judge error `1/10`; the second theorem states the fixture as the three crossing equivalences. |
| TS | L4 identity `a(1-ε₀) + (1-a)ε₁ = a - ε + 2(1-a)ε₁` | `FeedbackChannel.Signal.L4_identity` | FeedbackChannel/Signal.lean:411 | full | `ring` identity. |
| TS | L4: excess over the independent judge is `2(1-a)(ε₁ - ε)` | `FeedbackChannel.Signal.L4_excess` | FeedbackChannel/Signal.lean:417 | full | Independent judge = same marginal `ε` on both kinds of item. |
| TS | L4: reaches the ceiling `1 - ε` iff `ε₁ ≥ 1/2` | `FeedbackChannel.Signal.L4_ceiling_iff` | FeedbackChannel/Signal.lean:424 | full | Needs `a < 1` (stated for `a < 1`, so `a = 0` is included). At `a = 1` the observed accuracy is always `1 - ε`, so "whatever `a`" needs that exclusion. |
| TS | L4: feasibility caps `ε₁` at `ε/(1-a)` | `FeedbackChannel.Signal.L4_cap` | FeedbackChannel/Signal.lean:433 | full | Stated multiplied out: `(1-a)ε₁ ≤ ε` from `a, ε₀ ≥ 0`. |
| TS | L4: ceiling reachable without memorization iff `ε ≥ (1-a)/2` | `FeedbackChannel.Signal.L4_reachable_iff` | FeedbackChannel/Signal.lean:438 | full | `0 < a < 1`, `ε ≤ 1`; feasible = `ε₀, ε₁ ∈ [0,1]` with marginal `ε`. For `ε > (1+a)/2` the witness must take `ε₀ = 1`, `ε₁ > 1/2`; `ε₁ = 1/2` alone does not work there. |
| TS | L4: most correlated feasible judge reports `a + ε` at most | `FeedbackChannel.Signal.L4_observed_le` | FeedbackChannel/Signal.lean:474 | full | |
| TS | L4 fixture: `37/50`, `9/10` (the ceiling), inflation `4/25` | `FeedbackChannel.Signal.L4_fixture` | FeedbackChannel/Signal.lean:482 | full | Most correlated judge `(ε₀, ε₁) = (0, 1/2)` has marginal `1/10`. |
| TS | L6: Bayes value under `g` ≥ value under any `f` that factors through `g` | `FeedbackChannel.Signal.L6_garbling` | FeedbackChannel/Signal.lean:517 | full | Finite types; arbitrary real prior, likelihood of records given types, and utility (no sign condition needed); value = max over all decision rules. |
| TS | L6, garbling direction of Blackwell's order (stochastic) | `FeedbackChannel.Signal.L6_garbling_stochastic` | FeedbackChannel/Signal.lean:545 | full (strengthening) | Stochastic channel `G`, Markov kernel `K` (non-negative, rows sum to 1): value of `K ∘ G` ≤ value of `G`. The strict cases of L6 are not formalized. |
| JM | Proposition 1 (bookkeeping identity) | `FeedbackChannel.Judge.prop1_bookkeeping` | FeedbackChannel/Judge.lean:25 | full | Every table `(R₀,R₁,W₀,W₁)` with `m > 0`, including `W = 0` (Lean's `x/0 = 0` is the note's convention). |
| JM | Model of §5 (gold flips independent of `C, J`) | `FeedbackChannel.Judge.model_params` | FeedbackChannel/Judge.lean:84 | supporting | The eight-cell law has `Pr[C] = a`, `Pr[¬J] = aε₀ + (1-a)ε₁`. |
| JM | Proposition 2: `a'`, `ε'`, `W₁'/m`; agreement invariant | `FeedbackChannel.Judge.prop2` | FeedbackChannel/Judge.lean:91 | full | Each measured rate is a sum over the eight latent cells `(C, J, F)`. |
| JM | Proposition 2, inversion | `FeedbackChannel.Judge.prop2_inverse` | FeedbackChannel/Judge.lean:102 | full | `η ≠ 1/2`; `a ≠ 1` for `ε₁`. |
| JM / TS A2 | Corollary (gold-noise identity): `(ε₁' - ε')(1 - a') = η(1-η)(2a-1)(1-2ε)` | `FeedbackChannel.Judge.gold_noise_excess` | FeedbackChannel/Judge.lean:118 | full | Independent judge in the note's sense `ε₁ = ε`; stated as `W₁'/m - ε'(1-a')`, the measured covariance of the two errors. |
| JM | Corollary with `ε₁' = (W₁'/m)/(1 - a')` | `FeedbackChannel.Judge.gold_noise_excess_rate` | FeedbackChannel/Judge.lean:127 | full | `a' ≠ 1`. |
| JM | Excess positive when `a > 1/2`, `ε < 1/2` | `FeedbackChannel.Judge.gold_noise_excess_pos` | FeedbackChannel/Judge.lean:137 | full | Also needs `0 < η < 1`. |
| JM | Fixture `η = 1/20`: `a' = 77/100`, `ε' = 7/50`, `ε₁' = 11/46`, excess `57/575`; shared judge inverts to `1/2` | `FeedbackChannel.Judge.fixture` | FeedbackChannel/Judge.lean:144 | full | "Excess `57/575`" is `ε₁' - ε'`; the Corollary's quantity there is `57/2500`. |
| GC | Model: conditional independence multiplies | `FeedbackChannel.Raters.expect_prod_on` | FeedbackChannel/Raters.lean:53 | supporting | Two-class model on `n` raters; every moment below is a sum over the `2^n` report vectors. `mass_one` (:75): the table sums to 1. |
| GC | Proposition 1 (Walsh coefficients `p̂_S = τ^{[|S| odd]} ∏ d_i`) | `FeedbackChannel.Raters.prop1_walsh` | FeedbackChannel/Raters.lean:93 | full | For any number of raters (the note uses three). |
| GC | `κ_ij = 2A_ij - 1 = (1-2e_i)(1-2e_j)` | `FeedbackChannel.Raters.kappa_eq` | FeedbackChannel/Raters.lean:113 | full | `A_ij` is the agreement probability computed from the table; `agree_eq` (:127) gives `A_ij = 1 - e_i - e_j + 2e_ie_j`. |
| GC | Proposition 2: `(1-2e_i)² = κ_ij κ_ik / κ_jk` if `κ_jk ≠ 0` | `FeedbackChannel.Raters.prop2_three_rater` | FeedbackChannel/Raters.lean:136 | full | Any three distinct raters among `n`. |
| GC / JM | `(1-2η₁)² = κ₁₂ κ₁C / κ₂C` | `FeedbackChannel.Raters.prop2_gold` | FeedbackChannel/Raters.lean:146 | full | Raters `(G₁, G₂, C)` = indices `(0, 1, 2)`. |
| GC | Proposition 3: `M₁κ₂₃ = M₂κ₁₃ = M₃κ₁₂ = P` | `FeedbackChannel.Raters.prop3_constraints` | FeedbackChannel/Raters.lean:152 | full | Forward direction. The converse (a table satisfying the constraints comes from exactly one parameter point) is not formalized; nor is the three-rater copying residual of §3. |
| GC | §7 label switching | `FeedbackChannel.Raters.label_switch` | FeedbackChannel/Raters.lean:81 | full | `(π, α, β)` and `(1-π, 1-β, 1-α)` give the same table. |
| GC | Proposition 4: `c_ij = uδ_iδ_j` | `FeedbackChannel.Raters.prop4_cov` | FeedbackChannel/Raters.lean:291 | full | `c_ij = p_ij - p_ip_j` with the raw moments of the table (`pm_eq`, :267). |
| GC | Proposition 4: `k₃ = u(1-2π)δ₁δ₂δ₃` | `FeedbackChannel.Raters.prop4_k3` | FeedbackChannel/Raters.lean:297 | full | `k₃` in the note's raw form `p₁₂₃ - Σp_ip_jk + 2p₁p₂p₃`. |
| GC | Proposition 4: `R² = k₃² + 4c₁₂c₁₃c₂₃ = u²δ₁²δ₂²δ₃²` | `FeedbackChannel.Raters.prop4_R2` | FeedbackChannel/Raters.lean:306 | full | |
| GC | Proposition 4: `π = (R-k₃)/(2R)`, `s_i = p_i + (R+k₃)/(2c_jk)`, `t_i = p_i - (R-k₃)/(2c_jk)` | `FeedbackChannel.Raters.prop4_solution` | FeedbackChannel/Raters.lean:329 | full | Hypotheses `δ₁δ₂δ₃ > 0` and `0 < π < 1` (the latter is part of the note's identifiability condition, needed for `R > 0`); `R = √(k₃² + 4c₁₂c₁₃c₂₃)` from the table. All three raters. Core algebra in `solve_rater` (:314). |
| GC | §7 asymmetric inversion: measured `a'`, `ε'`, `w`; agreement invariant | `FeedbackChannel.Raters.asym_measured` | FeedbackChannel/Raters.lean:537 | full | Derived from the sixteen latent cells `(Y, C, J, F)` with class-dependent controller accuracy and gold flip rate. |
| GC | §7 asymmetric inversion: `ε₁ = (E_a(w-G_a) + G_a(ε'-F))/Δ`, `ε₀ = (G_b(ε'-F) - E_b(w-G_a))/Δ` | `FeedbackChannel.Raters.asym_inversion` | FeedbackChannel/Raters.lean:563 | full | `Δ ≠ 0`. |
| GC | §7: symmetric case `Δ = a(1-a)(1-2η)` | `FeedbackChannel.Raters.asym_delta_symm` | FeedbackChannel/Raters.lean:577 | full | Reduction to the judge note's inversion beyond `Δ` is not separately stated. |
| GC | Proposition 5: `k_S = μ_{|S|} ∏_{i∈S} δ_i` | `FeedbackChannel.Raters.prop5` | FeedbackChannel/Raters.lean:192 | full | Any number of raters and any `S` (the note: four raters); `k_S` are central moments of the table, `p_i` from `mean_eq` (:169). |
| GC | `μ₂ = u`, `μ₃ = u(1-2π)`, `μ₄ = u(1-3u)` | `FeedbackChannel.Raters.mu_two`, `.mu_three`, `.mu_four` | FeedbackChannel/Raters.lean:182–184 | full | `μ_k = π(1-π)^k + (1-π)(-π)^k`. |
| GC | §8, the six equalities | `FeedbackChannel.Raters.six_equalities` | FeedbackChannel/Raters.lean:235 | full | Hold identically on the four-rater model; built from `cmom_pair` (:204), `cmom_triple` (:208), `k1234_eq` (:227). |
| GC | §8 copying grader: `c₁₂ = uδ₁δ̃₂ + ρV₁`, other covariances product form | `FeedbackChannel.Raters.covCopy_eq` | FeedbackChannel/Raters.lean:458 | full | Model `probCopy`: rater 2 copies rater 1 with probability `ρ`, else grades independently. Moments are sums over the 16 cells (`meanCopy_0..3` :410–426, `massCopy` :439, `covCopy_raw` :445). |
| GC | §8 copying grader: `c₁₂c₃₄ - c₁₃c₂₄ = ρV₁c₃₄` and `c₁₃c₂₄ = c₁₄c₂₃` | `FeedbackChannel.Raters.copy_grader_residual` | FeedbackChannel/Raters.lean:473 | full | |
| GC | §8: any `ρ > 0` detected when `V₁ > 0`, `0 < π < 1`, `δ₃δ₄ ≠ 0`, at `π = 1/2` too | `FeedbackChannel.Raters.copy_grader_detected` | FeedbackChannel/Raters.lean:483 | full | Stated with `ρ ≠ 0`, `V₁ ≠ 0`. |
| GC | Proposition 6(b): the `6 × 6` minor on `(c₂₄, c₃₄, k₁₂₄, k₁₃₄, k₂₃₄, k₁₂₃₄)` is lower triangular | `FeedbackChannel.RatersJacobian.minor_eq` | FeedbackChannel/RatersJacobian.lean:47 | full | Entries are Lean's partial derivatives (`deriv` along coordinate lines) of the residual map, not entered by hand. Residuals are "left side minus right side" of the note's equalities; lower-triangular row order puts `c₁₃c₂₄ - c₁₄c₂₃` first. |
| GC | Proposition 6(b): determinant `-c₁₂⁴c₁₃²` | `FeedbackChannel.RatersJacobian.minor_det` | FeedbackChannel/RatersJacobian.lean:60 | full | At every point. The sign depends on the row order and residual orientation above; with the other tetrad first the determinant is `+c₁₂⁴c₁₃²`. |
| GC | Proposition 6(b): the `6 × 15` Jacobian has rank 6 wherever `c₁₂c₁₃ ≠ 0`, model or not | `FeedbackChannel.RatersJacobian.jac_rank` | FeedbackChannel/RatersJacobian.lean:70 | full | The 15 centred moments are taken as free real coordinates; that they are coordinates on the simplex is not formalized. Proposition 6(a) (parameter Jacobian rank 9) and the "zero set of six independent functions" conclusion are not formalized. |

## The selection-law and multi-generation notes


Lean formalizations of results in `paper/evaluation_feedback_multigen.md` (draft 0.5, "multigen")
and `paper/selection_law_kl_containment.md` (draft 0.3, "selection-KL"). Nine modules under
`FeedbackChannel/`, built in this order (each imports only narrow Mathlib modules):

`MultigenRunningMax MultigenHoeffding MultigenGate MultigenMixed MultigenCountDominance
SelectionKTwo SelectionContainment SelectionTieRules SelectionTieFree`

`axioms_selection.lean` prints the axioms of every theorem below. All of them depend on at most
`propext`, `Classical.choice`, `Quot.sound`. The files contain no `sorry`, `admit`, `native_decide` or new axioms.

Fidelity: **full** = the note's claim with its quantifiers and hypotheses; **special case** = a
restriction, named in Remarks; **supporting lemma** = a step of the note's proof, with what remains.
Probabilities and expectations are finite sums against product weights (i.i.d. draws). Where a
statement is about an abstract chain, Remarks says which property of the binomial instance is
taken as a hypothesis rather than derived.

| Note | Claim (label as in the note) | Lean theorem (fully qualified) | File:line | Fidelity | Remarks |
|---|---|---|---|---|---|
| multigen | Prop. 1, update rule: with `t ≡ 0`, `c_G = max(c_0, M_1, …, M_G)` | `FeedbackChannel.MultigenRunningMax.chain_naive` | `FeedbackChannel/MultigenRunningMax.lean:66` | full | `step`/`chain` encode §1's policy "accept iff `M > c + t(c)`" for any `t`. |
| multigen | Prop. 1: the reported count is the maximum of the `GK + 1` draws | `FeedbackChannel.MultigenRunningMax.naive_reported_eq_max` | `FeedbackChannel/MultigenRunningMax.lean:102` | full | Draws indexed by `Option (Fin G × Fin K)`; `none` is the initial incumbent; `M_g` is the max of generation `g`'s `K` candidates. |
| multigen | Prop. 1, law: `c_G` is distributed as the max of `GK + 1` i.i.d. draws | `FeedbackChannel.MultigenRunningMax.prob_reported_le` | `FeedbackChannel/MultigenRunningMax.lean:229` | full | `P(c_G ≤ j) = F(j)^{GK+1}` for i.i.d. draws with any law on `{0..n}` (`Bin(n, p)` included). |
| multigen | Prop. 1: `ρ_G = selection_inflation(n, GK+1, p).readout_gap` | `FeedbackChannel.MultigenRunningMax.expect_reported_eq_expect_max` | `FeedbackChannel/MultigenRunningMax.lean:248` | full | `E[c_G] = E[max of GK + 1 i.i.d. draws]`; with `expect_reported` (`:240`) and `expect_max` (`:198`) both equal `∑_{j<n} (1 - F(j)^{GK+1})`. |
| multigen | Prop. 1, max of i.i.d. draws: `P(max ≤ j) = F(j)^m` | `FeedbackChannel.MultigenRunningMax.prob_all_le` | `FeedbackChannel/MultigenRunningMax.lean:160` | supporting lemma | Product-law computation behind the two rows above. |
| multigen | Prop. 1 (i): `ρ_G` non-decreasing in `G` | `FeedbackChannel.MultigenRunningMax.expect_reported_mono` | `FeedbackChannel/MultigenRunningMax.lean:321` | full | Via `aSeq_mono` (`:274`): a maximum over more draws. |
| multigen | Prop. 1 (ii): increments non-increasing | `FeedbackChannel.MultigenRunningMax.aSeq_increment_antitone` | `FeedbackChannel/MultigenRunningMax.lean:283` | full | In `m`; increment written in tail form `∑_j F(j)^m (1 - F(j))` (`aSeq_succ_sub`, `:265`) rather than `E[(X - M_m)^+]` (equal, not proved equal here). Per-generation form: `expect_reported_increment_antitone` (`:328`). |
| multigen | Prop. 1 (iii): `P(c_G = n) = 1 - (1 - p^n)^{GK+1}` | `FeedbackChannel.MultigenRunningMax.binomial_prob_reported_eq_top` | `FeedbackChannel/MultigenRunningMax.lean:385` | full | General law: `prob_reported_eq_top` (`:343`), `1 - F(n-1)^{GK+1}`. |
| multigen | Prop. 1 (iii): for fixed `n` and `0 < p < 1`, `ρ_G ↑ 1 - p` | `FeedbackChannel.MultigenRunningMax.tendsto_gap` | `FeedbackChannel/MultigenRunningMax.lean:393` | full | `n ≥ 1`, `K ≥ 1`, `0 < p ≤ 1`; monotonicity is (i). |
| multigen | Prop. 4 (null, coupling): `c^t_G ≤ c^0_G` pointwise | `FeedbackChannel.MultigenRunningMax.chain_le_chain_naive` | `FeedbackChannel/MultigenRunningMax.lean:76` | special case | Pointwise ordering on the same draws only; `ρ^t ≤ ρ^0` and `α^t ≤ α^0` follow by taking expectations, not stated. |
| multigen | Prop. 5, first bound: `ρ_G ≤ √(ln(GK + 1)/(2n))` | `FeedbackChannel.MultigenHoeffding.prop5_hoeffding` | `FeedbackChannel/MultigenHoeffding.lean:260` | full | Every `n ≥ 1`, `K`, `G`, `p ∈ [0, 1]`. For any `m ≥ 1` i.i.d. draws: `max_gap_le_hoeffding` (`:189`). |
| multigen | Prop. 5 proof: Hoeffding's lemma for one Bernoulli | `FeedbackChannel.MultigenHoeffding.bernoulli_hoeffding` | `FeedbackChannel/MultigenHoeffding.lean:34` | supporting lemma | From Mathlib's `ProbabilityTheory.hasSubgaussianMGF_of_mem_Icc` on the two-point law. Uses the deprecated `PMF.bernoulli` (warning only). |
| multigen | Prop. 5 proof: `E e^{λ(X - np)} ≤ e^{λ²n/8}` | `FeedbackChannel.MultigenHoeffding.binomial_mgf_le` | `FeedbackChannel/MultigenHoeffding.lean:83` | supporting lemma | Closed form of the binomial mgf: `binomial_mgf` (`:67`). |
| multigen | Prop. 5 proof: maximal inequality (Jensen, then `max ≤ ∑`) | `FeedbackChannel.MultigenHoeffding.maximal_inequality` | `FeedbackChannel/MultigenHoeffding.lean:124` | supporting lemma | `λ(E max - c) ≤ ln m + ln E e^{λ(X - c)}` for every real `λ`. |
| multigen | Prop. 7: one generation changes the gap by `E[((M - c)/n - δ) 1_accept]` | `FeedbackChannel.MultigenGate.gapChange_eq` | `FeedbackChannel/MultigenGate.lean:41` | full | Any finite law of `M` (the note's is the max of `K` `Bin(n, p_inc + δ)`); gap = count/n − true value. |
| multigen | Prop. 7: `Δρ_naive - Δρ_gate = E[((M - c)/n - δ) 1{c < M ≤ c + t(c)}]` | `FeedbackChannel.MultigenGate.naive_sub_gate` | `FeedbackChannel/MultigenGate.lean:56` | full | |
| multigen | Prop. 7 (i): `δ ≤ 1/n` ⇒ difference `≥ 0` | `FeedbackChannel.MultigenGate.naive_sub_gate_nonneg` | `FeedbackChannel/MultigenGate.lean:70` | full | `n ≥ 1`, law non-negative with mass one. |
| multigen | Prop. 7 (ii): `δ ≥ t(c)/n` ⇒ difference `≤ 0` | `FeedbackChannel.MultigenGate.naive_sub_gate_nonpos` | `FeedbackChannel/MultigenGate.lean:90` | full | |
| multigen | Prop. 7: both (i) and (ii) ⇒ difference zero | `FeedbackChannel.MultigenGate.naive_sub_gate_eq_zero` | `FeedbackChannel/MultigenGate.lean:110` | full | The `n = 8, z = 1` cells. |
| multigen | Prop. 7 (iii): otherwise the sign depends on the law of `M` | `FeedbackChannel.MultigenGate.sign_undetermined` | `FeedbackChannel/MultigenGate.lean:119` | special case | For `1/n < δ < t/n`, point masses at `c + 1` and `c + t` give both signs (arbitrary finite laws). The note's binomial-max example (`n = 16, K = 2, c = 8`) is a finite check, not formalized. |
| multigen | §6 mixed laws: `W^a_k = (P u_k - Q u_k)` for the rule with `a(c) = a` | `FeedbackChannel.MultigenMixed.kernel_sub_u` | `FeedbackChannel/MultigenMixed.lean:197` | supporting lemma | |
| multigen | §6 mixed laws: one naive step `s_{k+1} = (1 - H) s_k - W^{m-1}_k` | `FeedbackChannel.MultigenMixed.s_succ` | `FeedbackChannel/MultigenMixed.lean:207` | supporting lemma | |
| multigen | §6 mixed laws: window-sum recursion `W^a_k = (1-H)W^a_{k-1} + E^a_{k-1} + ∑ρ W^{m-1}_{k-1}(y) - B_a W^{m-1}_{k-1}(x)` | `FeedbackChannel.MultigenMixed.window_recursion` | `FeedbackChannel/MultigenMixed.lean:241` | full | `a < m`. Chain abstracted as an arbitrary finite joint law `ρ(i, J, ℓ)` of (best count, landing level), mass one per level; covers `drift_kernel`'s `q_μ Bin(n, p(i+μ))(J) S_J` for every gain law. |
| multigen | §6 mixed laws: `E^a ≥ 0` | `FeedbackChannel.MultigenMixed.E_nonneg` | `FeedbackChannel/MultigenMixed.lean:264` | full | Hypotheses as the note uses them: gains `≥ 0` (`ρ ≠ 0 ⇒ ℓ ≥ i`) and `H` non-decreasing in the level. The latter is assumed, not derived from the binomial levels. |
| multigen | §6 mixed laws: "(L1) holds for every law"; full-window slacks `W^{m-1} ≥ 0` | `FeedbackChannel.MultigenMixed.full_window_nonneg` | `FeedbackChannel/MultigenMixed.lean:329` | full | Same hypotheses. Standard form `s_{k+1} ≤ (1 - H) s_k`: `MultigenMixed.L1` (`:335`). Weaker hypothesis (landing levels have `H(ℓ) ≥ H(i)`): `full_window_nonneg_of_landing` (`:279`). |
| multigen | §6 mixed laws: at `c = m - 2`, `W_k = A W_{k-1} + E_{k-1}` | `FeedbackChannel.MultigenMixed.distance_two_closure` | `FeedbackChannel/MultigenMixed.lean:359` | full | Exact identity, every gain law. |
| multigen | §6 mixed laws: `W_k ≥ 0` at `c = m - 2`, "a theorem two below the target for every gain law" | `FeedbackChannel.MultigenMixed.distance_two_nonneg` | `FeedbackChannel/MultigenMixed.lean:369` | full | Hypotheses as for `E_nonneg`. |
| multigen | §6 / overview: count ordering proved from states two steps below the target | `FeedbackChannel.MultigenMixed.gated_le_naive_near_target` | `FeedbackChannel/MultigenMixed.lean:392` | full | `(Q u_k)(x) ≤ (P u_k)(x)` for every threshold rule at every state with `c ≥ m - 2`, objective `1{c ≥ m}`. |
| multigen | Prop. 9: `E^t_x[ψ(c_g)] ≤ E^0_x[ψ(c_g)]` for non-decreasing `ψ`, every rule, state, `g` | `FeedbackChannel.MultigenCountDominance.gated_expect_le` | `FeedbackChannel/MultigenCountDominance.lean:468` | full | Fixed-gain chain abstracted: draw law `π_i` per level, acceptance moves the level to `nx i < L` (a top level may absorb). The proof's one property of the binomial, "best of `K` stochastically non-decreasing in the level", is the hypothesis `hstoch : P(M_i ≥ m) ≤ P(M_{nx i} ≥ m)`; it is not derived from `Bin(n, p)` here. `ψ` enters as `ψ(min c n)`, which equals `ψ(c)` on counts. |
| multigen | Prop. 9: stochastic dominance of the count (hitting form) | `FeedbackChannel.MultigenCountDominance.gated_hit_le` | `FeedbackChannel/MultigenCountDominance.lean:378` | full | `P^t_x(c_g ≥ m) ≤ P^0_x(c_g ≥ m)`; same hypothesis. |
| multigen | Prop. 9: one gated step then naive steps is dominated, `QP^kψ ≤ P^{k+1}ψ` | `FeedbackChannel.MultigenCountDominance.one_gated_step_le` | `FeedbackChannel/MultigenCountDominance.lean:357` | special case | For the hitting indicators `ψ = 1{c ≥ m}`. The general `ψ` follows by linearity but is not stated. |
| multigen | Prop. 9 proof: (L1), (L2), (L3), (L4) | `FeedbackChannel.MultigenCountDominance.L1`, `FeedbackChannel.MultigenCountDominance.L2`, `FeedbackChannel.MultigenCountDominance.L3`, `FeedbackChannel.MultigenCountDominance.L4` | `FeedbackChannel/MultigenCountDominance.lean:159`, `:230`, `:262`, `:269` | supporting lemma | (L3) through the note's comparison sequence `R` (`R_le_s`, `s_le_R`); (L4) for every window `a`. |
| selection-KL | D.5 (`K = 2`): `M_n(2) = ½ E|S - n|`, `S ~ Bin(2n, ½)` | `FeedbackChannel.SelectionKTwo.M2_eq_half_meanAbsDev` | `FeedbackChannel/SelectionKTwo.lean:195` | full | `M_n(2)` is the double binomial sum `E max(Y₁, Y₂)`. |
| selection-KL | D.5: de Moivre `E|S - n| = n C(2n, n)/4ⁿ` | `FeedbackChannel.SelectionKTwo.meanAbsDev_eq` | `FeedbackChannel/SelectionKTwo.lean:123` | full | Integer form `∑ C(2n, s)|s - n| = n C(2n, n)`: `sum_choose_abs` (`:80`). |
| selection-KL | D.5: `a_n(2)² = n C(2n, n)²/(4·16ⁿ)` | `FeedbackChannel.SelectionKTwo.aSq_eq` | `FeedbackChannel/SelectionKTwo.lean:272` | full | `a_n = M_n/√n`. |
| selection-KL | D.5: `a_{n+1}²/a_n² = (2n + 1)²/(4n(n + 1)) = 1 + 1/(4n(n + 1)) > 1` | `FeedbackChannel.SelectionKTwo.aSq_succ_div` | `FeedbackChannel/SelectionKTwo.lean:291` | full | `n ≥ 1`; with `step_ratio_eq` (`:310`) and `step_ratio_gt_one` (`:316`). |
| selection-KL | D.5: `a_n(2)` strictly increasing | `FeedbackChannel.SelectionKTwo.a_strictMonoOn` | `FeedbackChannel/SelectionKTwo.lean:340` | full | On `n ≥ 1`. |
| selection-KL | D.5: `a_n(2) ↑ 1/(2√π)` (Wallis) | `FeedbackChannel.SelectionKTwo.tendsto_a` | `FeedbackChannel/SelectionKTwo.lean:390` | full | `a_n² = n/(4(2n + 1)W_n)` with Mathlib's Wallis product (`aSq_eq_wallis`, `:350`); `a_n² → 1/(4π)` (`tendsto_aSq`, `:366`). |
| selection-KL | D.5: `r(n, 2, ½)` increases strictly to `c₂`, `sup_n = c₂` | `FeedbackChannel.SelectionKTwo.r_strictMonoOn`, `FeedbackChannel.SelectionKTwo.tendsto_r`, `FeedbackChannel.SelectionKTwo.r_lt_lim` | `FeedbackChannel/SelectionKTwo.lean:413`, `:422`, `:432` | special case | `r = 2a_n/√(2λ₂)`; the limit is stated as `1/(√π √(2λ₂))` and is never attained. Equating it with `c₂ = E[M₂]/√(2λ₂)` needs the Gaussian value `E[M₂] = 1/√π`, which is not formalized. |
| selection-KL | Theorem A: for every tie rule, `π_K(ω) = p₀(ω) m_K(S ω)/q(S ω)` | `FeedbackChannel.SelectionTieRules.keptLaw_eq` | `FeedbackChannel/SelectionTieRules.lean:163` | full | Tie rule: a function of the score vector and of independent randomness on a finite type, with the kept index in the argmax set. This covers the first-index and uniform rules. Proved by a weight-preserving swap of the kept record (`swap_sum`, `:89`), the combinatorial form of the conditioning argument. `P(max score = s) = F(s)^K - F(s-)^K`: `prob_max_score_eq` (`:55`). |
| selection-KL | Theorem A: `KL(π_K ‖ p₀) = KL(m_K ‖ q)` | `FeedbackChannel.SelectionContainment.kl_record_eq_kl_scores` | `FeedbackChannel/SelectionContainment.lean:428` | full | `kl μ ν = ∑ μ log(μ/ν)`, the KL divergence for `μ ≪ ν` (true for `π_K ≪ p₀`). |
| selection-KL | Theorem B: for every finite `p₀`, score, `K` and tie rule, `KL(π_K ‖ p₀) ≤ ln K - (K - 1)/K` | `FeedbackChannel.SelectionTieRules.theoremB_every_tie_rule` | `FeedbackChannel/SelectionTieRules.lean:188` | full | `K ≥ 1`, `p₀ ≥ 0` with mass one, real-valued score; tie randomness on a finite type. Formula form: `SelectionContainment.theoremB` (`:457`). |
| selection-KL | Theorem B: equality iff `K = 1` | `FeedbackChannel.SelectionTieRules.theoremB_every_tie_rule_eq_iff` | `FeedbackChannel/SelectionTieRules.lean:197` | full | Strict for `K ≥ 2`: `SelectionContainment.theoremB_strict` (`:465`); formula form `theoremB_eq_iff` (`:473`). |
| selection-KL | Theorem B, score form: `KL(m_K ‖ q) ≤ λ_K` (`< λ_K` for `K ≥ 2`) | `FeedbackChannel.SelectionContainment.kl_scores_le` | `FeedbackChannel/SelectionContainment.lean:295` | full | Every finite score law (atoms `T`, masses `q`). Strict form: `kl_scores_lt` (`:311`). |
| selection-KL | Theorem B proof, steps (ii)–(iii): Jensen removes the jitter | `FeedbackChannel.SelectionContainment.atom_le` | `FeedbackChannel/SelectionContainment.lean:183` | supporting lemma | Replaces the jitter with an atom-wise tangent-line Jensen: `(b^K - a^K) ln((b^K - a^K)/(b - a)) ≤ G(b) - G(a)`, `G' = h ln h` (`hasDerivAt_G`, `:76`). The sum telescopes (`telescope`, `:247`) to `G(1) - G(0) = λ_K` (`G_one`, `:58`). Strict for `K ≥ 2`: `atom_lt` (`:195`). |
| selection-KL | Theorem B, step (ii): tie-free value `∫₀¹ K u^{K-1} ln(K u^{K-1}) du = ln K - (K - 1)/K` | `FeedbackChannel.SelectionTieFree.tieFree_integral` | `FeedbackChannel/SelectionTieFree.lean:31` | supporting lemma | The integral identity only. The claim that every atomless score law attains `λ_K` (the density computation) is not formalized. |

## Not formalized

- multigen Prop. 5, second (Bernstein) bound.
- multigen Prop. 8 (dominance in true value). Props. 2, 3 and 6, and the finite surveys, were outside the assignment.
- multigen Prop. 7 (iii) for binomial-max laws specifically; Prop. 9 with the binomial stochastic
  monotonicity derived rather than assumed. The analogous `H`-monotonicity hypothesis in §6 is also assumed.
- selection-KL Theorem B supremum (uniform laws on `N` atoms tend to `λ_K`) and attainment by atomless laws; D.5 for
  `K = 3` and the `K ≥ 4` material; Theorems C and D.1–D.4.

## Notes on the sources found while formalizing

- selection-KL D.5: the telescoped form `a_n(2)² = (1/16) ∏_{j<n} (2j+1)²/((2j)(2j+2))` has a
  zero denominator at `j = 0`; the product must run over `1 ≤ j < n` (from `a_1(2)² = 1/16`).
- multigen §6 (0.5): "(L1) holds for every law" is a theorem, not only a finite check. Under
  gains `≥ 0` and `H` non-decreasing in the level, the fixed-gain induction carries over unchanged
  (`full_window_nonneg`).
- multigen Prop. 1 (ii) states the increment as `E[(X - M_m)^+]`; the formalization uses the
  equivalent tail form `∑_j F(j)^m (1 - F(j))`.
- multigen Prop. 5: the maximal-inequality step needs no `λ > 0` once it is written as
  `λ(E max - c) ≤ ln m + ln E e^{λ(X - c)}`. Positivity is needed only to divide by `λ`.
