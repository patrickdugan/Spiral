# Partial leakage as a lattice of feedback channels

Version 0.7 — 2026-10-14. Exact fixtures for the gap named in
[evaluation_feedback_insertions.md](evaluation_feedback_insertions.md) §H:
feedback that reveals failure *categories* and not items. Files:
`src/spiral_ln/evaluation_feedback_lattice.py`, `tests/test_evaluation_feedback_lattice.py`
(105 tests), `output/evaluation_feedback_lattice/lattice_v0_7.json` (48 checks). No model was called.
Version 0.7 settles two hits: committing to one category until it hits is
optimal at every state exactly when at most two hits are needed (Theorem 11,
Corollary 14), so the two-hit optimum is a closed form computable in time
linear in the item count. It states the complexity question precisely and
says what is now known, finds a commit gap of one part in 739, above the
tenth of a percent that version 0.6 saw on its grid, and checks two
categories and at most two failures per category far beyond the grid
without a proof. It also corrects two statements found wrong by the Lean
formalization and confirmed with the module's own programme: Theorem 10's
minimum runs over categories with failures, and Proposition 7's witnesses
are replaced by ones whose preferred category is the unique optimum.
Version 0.6 tests the last natural structure for the optimal policy beyond
one hit, committing to a category until it hits, and finds it suboptimal
by at most a tenth of a percent on the grid.
Version 0.4 added the pair-commutation lemma (Lemma 9) and a survey of what
structure the optimal first patch does not have; version 0.5 refutes the two
regularities that survey left standing and records the one two-category
pattern that holds on every state enumerated.
Version 0.2 settled the two items version 0.1 left as finite checks: the
category map preserves meets (Proposition 2b), preserves joins exactly when
the intersection graph is a forest (Proposition 2c), and the optimal adaptive
patch schedule is monotone along refinement (Proposition 6) while the greedy
one is not optimal. Version 0.3 answers whether an index rule can replace
the dynamic programme: it cannot (Propositions 7 and 8).
Evidence levels follow the calculus card (§11): *algebraic identity* (proved
for all inputs) or *finite verified example* (checked on the enumerated cases
only); no synthetic mechanism result is claimed.

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_feedback_lattice.py --output output/evaluation_feedback_lattice/lattice_v0_7.json
python -m pytest tests/test_evaluation_feedback_lattice.py -q
```

## 1. Channels are partitions; the lattice data-processing law

A deterministic feedback channel on records \(\{0,1\}^n\) is a function \(f\);
two channels carry the same information exactly when \(\ker f\) agrees, so a
channel *is* a partition of the record set. Convention: \(p\le q\) when \(q\)
refines \(p\); the one-block partition (`sealed`) is the bottom, the discrete
partition (`item_level`) the top, \(p\vee q\) the common refinement (observing
both) and \(p\wedge q\) the finest common coarsening (components of the union
of the two relations). This is the partition lattice, orientation reversed.

**Proposition 1 (lattice data-processing law and converse).** For all
distributions \(P,Q\) on records, \(p\le q\) implies
\(\mathrm{TV}(p_\#P,p_\#Q)\le\mathrm{TV}(q_\#P,q_\#Q)\); and if \(p\not\le q\)
there are point masses \(P,Q\) reversing the inequality.

*Proof.* \(\mathrm{TV}(p_\#P,p_\#Q)=\max_U|P(U)-Q(U)|\) over unions \(U\) of
blocks of \(p\). When \(q\) refines \(p\), every block of \(p\) is a union of
blocks of \(q\), so the maximum for \(p\) ranges over a subset of the sets
available to \(q\). If \(q\) does not refine \(p\), some block of \(q\) holds
\(x,y\) that \(p\) separates; \(P=\delta_x,Q=\delta_y\) give \(\mathrm{TV}\)
one through \(p\) and zero through \(q\). \(\square\)

So \(\mathrm{TV}\) through \(p\vee q\) is at least the larger of the two and
through \(p\wedge q\) at most the smaller; the testbed's one-kernel contraction
is one comparable pair. *Evidence status: algebraic identity.* Fixture
`lattice_fixture(2, 2)`: all 15 partitions of \(\{0,1\}^2\), 225 ordered pairs,
100 pairs of grid distributions; the law holds on every comparable pair, fails
somewhere on every non-comparable pair, join and meet satisfy their lattice
definitions, and `access_kernel`'s three classes are bottom, middle, top.

## 2. Category leakage is an order embedding, not a scale

A category map, a partition \(\gamma\) of the items \([n]\), induces the channel
\(\Phi(\gamma)\): the per-category pass-count vector.

**Proposition 2.** \(\Phi(\gamma)\le\Phi(\gamma')\) iff \(\gamma\le\gamma'\),
so \(\Phi\) is an order embedding; \(\Phi(\text{one block})=\)`score_only` and
\(\Phi(\text{singletons})=\)`item_level`.

*Proof.* If \(\gamma'\) refines \(\gamma\), each \(\gamma\)-count is a sum of
\(\gamma'\)-counts, so equal \(\gamma'\)-counts force equal \(\gamma\)-counts.
If not, some \(\gamma'\)-block holds items \(i,j\) that \(\gamma\) separates;
the records failing only \(i\) and only \(j\) have equal \(\gamma'\)-counts and
unequal \(\gamma\)-counts. The endpoints are the definitions. \(\square\)
*Evidence status: algebraic identity*, checked exhaustively on all 5 maps of
\([3]\) and 15 maps of \([4]\) in `category_order_fixture`.

The image is order-isomorphic to the partition lattice of \([n]\), not a chain
for \(n\ge3\), so "how much leaks" has no scalar. On \([3]\), with
\(A=\{0,1\}|\{2\}\) and \(B=\{0\}|\{1,2\}\): \(B\) separates "fail item 0" from
"fail item 1" (\(\mathrm{TV}=1\)) while \(A\) gives 0, and conversely for "fail 1" vs "fail 2".

**Proposition 2b (meets are preserved).** \(\Phi(\gamma\wedge\gamma')=
\Phi(\gamma)\wedge\Phi(\gamma')\) for all \(\gamma,\gamma'\).

*Proof.* \(\Phi\) is an order embedding, so \(\Phi(\gamma\wedge\gamma')\le
\Phi(\gamma)\wedge\Phi(\gamma')\). Conversely let \(r,s\) have equal pass
counts on every block of \(\gamma\wedge\gamma'\). Those blocks are the
connected components of the graph on items whose edges join two items lying
in a common \(\gamma\)-block or a common \(\gamma'\)-block. Swapping the bits
at two items of one \(\gamma\)-block preserves every \(\gamma\)-count, so a
record and its swap share a \(\Phi(\gamma)\)-block, hence a block of the
meet; likewise for \(\gamma'\). The edge transpositions of a connected graph
generate its symmetric group, so within each component every arrangement of
a fixed number of passes is reached from every other by such swaps. Hence
\(r\) and \(s\) share a block of the meet. \(\square\)
*Evidence status: algebraic identity*, checked on all 25, 225 and 2704
ordered pairs of maps on 3, 4 and 5 items (`category_lattice_fixture`).

**Proposition 2c (joins are preserved iff the intersection graph is a
forest).** Let \(I(\gamma,\gamma')\) be the bipartite graph on the blocks of
\(\gamma\) and of \(\gamma'\) with an edge where two blocks intersect; its
edges are the cells of \(\gamma\vee\gamma'\). Then
\(\Phi(\gamma)\vee\Phi(\gamma')=\Phi(\gamma\vee\gamma')\) iff
\(I(\gamma,\gamma')\) is acyclic.

*Proof.* \(\Phi(\gamma\vee\gamma')\) identifies records with equal cell
counts, \(\Phi(\gamma)\vee\Phi(\gamma')\) those with equal row and column
margins; cell counts determine margins, so the refined channel is always at
least as fine. If \(I\) has a cycle \(A_1B_1A_2B_2\cdots A_kB_k\), put one
pass in each cell \(A_i\cap B_i\) for one record and one in each
\(A_{i+1}\cap B_i\) for the other: every block on the cycle then holds
exactly one pass in both records, so the margins agree while the cells
differ. If \(I\) is a forest, peel leaves: a leaf block has a single
nonempty cell, whose count is that block's margin; remove it and recurse,
so the margins determine every cell. \(\square\)

For rows \(\{0,1\}|\{2,3\}\) and columns \(\{0,2\}|\{1,3\}\) the graph is a
4-cycle and `1001`, `0110` is the witness: two separate category leaks are
strictly coarser than one leak with the refined categories. On \([4]\) the
six failing ordered pairs are the three pairings into two pairs taken
crosswise; on \([5]\) 210 of 2704 ordered pairs fail, and
`join_failure_witness` builds a valid witness from a cycle for each.
*Evidence status: algebraic identity*, checked exhaustively on 3, 4, 5 items.

## 3. Cost of a leak, exact

Setting of `noise_ceiling_fixture`: clean accuracy \(4/5\), flip \(1/10\), so
\(v=37/50\), ceiling \(9/10\); on \(n=50\) items 13 fail and \(H=8\) hits are
needed. Under \(\Phi(\gamma)\) the loop knows \((n_c,F_c)\) per category and
patches uniformly at random without replacement; a patch on a passed item gains nothing.

**Proposition 3 (expected gain is exact; greedy is optimal).** The \(j\)-th
patch in category \(c\) hits with conditional probability
\((F_c-h)/(n_c-j+1)\) given \(h\) earlier hits, and with unconditional
probability \(F_c/n_c\) for every \(j\) (exchangeability). So \(m_c\) patches
hit exactly \(m_cF_c/n_c\) in expectation: the expected-value formula of the
insertions note is the hypergeometric mean, not an approximation. Every patch
in \(c\) has the same marginal value, so filling categories in decreasing order
of \(F_c/n_c\) maximizes expected hits at every patch count. *Algebraic
identity*; checked against every allocation and every patch order.

**Proposition 4 (patches to the ceiling).** With \(c_1,c_2,\dots\) the greedy
order, \(j\) the first index with \(\sum_{i\le j}F_{c_i}\ge H\),
\(N_{<j}=\sum_{i<j}n_{c_i}\) and \(H_j=H-\sum_{i<j}F_{c_i}\in[1,F_{c_j}]\):
the expected score reaches the ceiling at \(m^*=N_{<j}+H_jn_{c_j}/F_{c_j}\),
and the realized score first reaches it at a stopping time \(T\) with
\(\mathbb E[T]=N_{<j}+H_j(n_{c_j}+1)/(F_{c_j}+1)\) (negative-hypergeometric
mean; earlier categories are patched completely, so their hits are fixed). Hence
\(m^*-\mathbb E[T]=H_j(n_{c_j}-F_{c_j})/(F_{c_j}(F_{c_j}+1))\in[0,m^*/(F_{c_j}+1))\):
the expected-score crossing never understates the expected patch count. One
category: \(m^*/n=(1-\varepsilon-v)/(1-v)=8/13\), \(\mathbb E[T]=204/7\).
Singleton categories: both equal \(H\), share \(4/25\). *Algebraic identity*,
cross-checked by enumerating every patch order on three category shapes and
against `ceiling_detection_threshold` and `targeted_ceiling_detection_threshold`.

**Proposition 5 (monotonicity of \(m^*\)).** If \(\gamma'\) refines \(\gamma\)
then \(m^*(\gamma')\le m^*(\gamma)\) for every failure pattern. *Proof.* Each
\(\gamma\)-rate is the size-weighted mean of its \(\gamma'\)-sub-rates, so the
\(\gamma\) expected-hit curve is attainable under \(\gamma'\) by proportional
(fractional) allocation, and the \(\gamma'\)-greedy curve is at least it.
\(\square\) *Algebraic identity*; checked over all 203 maps of \([6]\), 2268
refining pairs, 63 patterns, two requirements each.

**The stopping time under the static schedule is not monotone.**
\(\mathbb E[T]\) under the static greedy schedule can rise along refinement:
one block \((4,2)\), \(H=2\), gives \(10/3\); \((2,1),(2,1)\) gives \(7/2\).
On \([6]\): record `001101`, \(H=3\), \(21/4\) against \(11/2\). *Finite
verified example*, a proof by witness.

**Proposition 6 (the optimal adaptive schedule is monotone).** Let
\(V^*(\gamma)\) be the minimum, over adaptive policies that re-query the
channel after each patch and patch a uniformly random unpatched item of a
category they choose, of the expected patches to \(H\) hits. If \(\gamma'\)
refines \(\gamma\) then \(V^*(\gamma')\le V^*(\gamma)\).

*Proof.* A \(\gamma\)-policy's information, the coarse counts, is a function
of the \(\gamma'\)-information, and patching a uniformly random unpatched
item of a coarse block is the same as choosing a sub-block with probability
proportional to its unpatched items and patching at random there. So every
\(\gamma\)-policy is a \(\gamma'\)-policy with the same law of patch
outcomes, and the minimum over \(\gamma'\)-policies is no larger. \(\square\)
`optimal_adaptive_value` computes \(V^*\) by dynamic programming on the
multiset of (remaining, failures) pairs. *Evidence status: algebraic
identity*; checked on all 2268 refining pairs of \([6]\), 162 cases each
(`greedy_vs_optimal_fixture`).

**Theorem 10 (one hit: the best finisher, in closed form).** With one hit
needed the optimal expected patch count is the minimum of
\((n_c+1)/(F_c+1)\) over the categories with \(F_c\ge1\), attained
by patching a category of minimal \((n_c+1)/(F_c+1)\) until it hits and never
switching. *Proof.* Induct on the total number of items. Sticking with
\(c\) costs \(1+(1-F_c/n_c)\,n_c/(F_c+1)=(n_c+1)/(F_c+1)\). A miss in \(c\)
lowers its value to \(n_c/(F_c+1)\) and changes nothing else, so if \(c\)
was a best finisher it still is, and by induction continuing with it is
optimal from the new state. A first patch in a category without failures
is a sure miss that leaves every finisher unchanged, so it costs
\(1+v>v\) with \(v\) the best finisher's value. Starting in any other
\(c'\), now with \(F_{c'}\ge1\), costs at least
\(1+(1-F_{c'}/n_{c'})\min(n_{c'}/(F_{c'}+1),\,v)\); the first branch gives \((n_{c'}+1)/(F_{c'}+1)\ge v\), and
the second gives \(1+(1-F_{c'}/n_{c'})v\ge v\) because
\(v\le(n_{c'}+1)/(F_{c'}+1)\le n_{c'}/F_{c'}\), which needs \(F_{c'}\ge1\). \(\square\) *Algebraic
identity*; `one_hit_fixture` checks the closed form against the dynamic
programme on every state with at most four categories of size at most
eight. *Correction in version 0.7* (found by the Lean formalization): versions
0.5 and 0.6 wrote the minimum over all categories, which is wrong when one
has no failure: \(\{(1,0),(10,1)\}\) costs \(11/2\), while
\((1+1)/(0+1)=2\). `one_hit_value` always took the minimum over categories
with failures, so only the statement changes; the receipt now carries this
state as a guard. The highest current rate is therefore *not* the right rule at one hit:
in \(\{(2,1),(16,9)\}\) the rates are \(\tfrac12<\tfrac9{16}\) but the
finishers are \(\tfrac32<\tfrac{17}{10}\), and patching \((2,1)\) first costs
\(3/2\) against \(53/32\) for the higher rate. The exchange argument that
version 0.2 offered for "greedy is optimal at one hit" only compares
policies that would patch the other category next; it does not cover a
policy that stays in a category whose rate rose after a miss. On the
exhaustive grid the two rules happen to agree, which is why the error
survived the checks.

**Greedy is not optimal.** The greedy rule (highest current rate, ties to
the smaller category) is one adaptive policy, so \(V^*\le\) greedy \(\le\)
static everywhere. It agrees with the optimum at one hit on the grid, but
not in general (Theorem 10's witness), and it is optimal when every failure
must be hit, since any policy that never patches an exhausted category needs
\(\sum_cF_c(n_c+1)/(F_c+1)\) patches, the sum of the last-failure positions.
It is not optimal in general: with categories
\((4,2)\) and \((2,1)\) and two hits needed, greedy patches the smaller
category first and needs \(19/6\) patches; patching the larger first needs
\(37/12\). On six items greedy is strictly worse in 180 of 32,886 cases; on
four and five items it is optimal in every case. The greedy value was
monotone on every enumerated refining pair, which Proposition 6 does not
imply; what it implies is that the right cost of a leak, the optimal
expected stopping time, is monotone everywhere. Chain with block sizes
50, 25, 10, 5, 2, 1 and failures at items \(0,4,\dots,48\):
\(m^*/n=8/13,7/12,8/15,1/2,8/25,4/25\);
\(\mathbb E[T]_{\text{static}}=204/7,201/7,51/2,23,31/2,8\);
greedy adaptive \(\approx29.14,25.64,21.17,18,12,8\).

**Proposition 7 (no index rule is optimal).** An index rule scores each
category by a function of its own \((n_c,F_c)\), the requirement \(H\), and
possibly global summaries (total items, total failures, number of
categories), and patches a maximizer, ties broken by a fixed order on those
same inputs; it therefore ranks two categories the
same way in any two states that agree on those inputs. No such rule is
optimal. With \(H=2\), \((2,1)\) is the unique optimal first patch of
\(\{(2,1),(2,1),(4,2)\}\) (\(3\) against \(37/12\)) and \((4,2)\) the unique
optimal first patch of \(\{(2,1),(4,2)\}\) (\(37/12\) against \(19/6\)); an
optimal index rule would have to rank \((2,1)\) above \((4,2)\) in the first
state and below it in the second. With the totals and the category count
added to the index, \((2,1)\) is uniquely optimal in
\(\{(2,1),(2,1),(4,1),(4,2)\}\) (at \(3\)) and \((4,2)\) in
\(\{(2,1),(3,1),(3,1),(4,2)\}\) (at \(37/12\)), both with twelve items, five
failures, four categories and \(H=2\). *Proof.* By witness; the values are exact
dynamic-programme continuations (`first_patch_values`, `optimal_first_choices`). \(\square\)
A reversal, \(A\) before \(B\) strictly better in one state and strictly worse
in another, refutes an index rule only when the preferred category is the
unique optimum in both states: otherwise a third category can tie for the
optimum and a rule that ranks it first is optimal there. `preference_reversals`
finds 30 reversals for own-count indices over all 33,915 states with at most
four categories of size at most five, and 125 and 120 with the two richer
contexts; of these, 8, 18 and 12 are *refuting pairs*, with the preferred
category the unique optimum on both sides. *Evidence status: algebraic identity*
(a counterexample proves the universal negative); the counts are a finite
verified example. *Correction in version 0.7* (found by the Lean
formalization): version 0.6's witnesses did not refute. In
\(\{(1,1),(2,1),(4,2)\}\) with \(H=2\) the first-patch values are \(5/2\),
\(5/2\), \(8/3\), so \((1,1)\) is optimal too, and in the totals witness
\(\{(1,1),(2,1),(3,1),(4,2)\}\) with \(H=3\), \((1,1)\) and \((4,2)\) tie at
\(49/12\); its counts of 30, 125 and 120 counted reversals, not refutations.
The proposition stands on the witnesses above; Theorem 11 explains them at
two hits.

**Proposition 8 (the optimal first patch need not have the highest hit
probability).** In \(\{(2,1),(5,2)\}\) with \(H=2\) the rates are
\(\tfrac12\) and \(\tfrac25\); patching \((5,2)\) first needs \(69/20\)
patches, \((2,1)\) first \(7/2\). So beyond \(H=1\) the optimal policy is not
"a highest-rate category with the right tie-break": `rate_violations` finds
82 states among the 33,915 in which every optimal first patch has a strictly
sub-maximal rate, none with \(H=1\) on that grid, where the highest-rate and
best-finisher orders never strictly disagree (they do at larger sizes,
Theorem 10). The same enumeration puts greedy's first patch off the optimum
in 131 states, and no \(H\)-dependent tie-break repairs the 82.
*Evidence status: algebraic identity* for the witness; *finite verified
example* for the counts. What remains open is a structural description of
the optimal policy; the dynamic programme is exact and cheap on these grids,
so the gap is one of understanding (version 0.7: closed for two hits by
Theorem 11; for three or more the programme's state count is exponential
in the number of categories, see the complexity paragraph).

**Lemma 9 (pair commutation).** With at least two hits still needed,
patching category \(A\) and then \(B\ne A\), each followed by an optimal
continuation, costs the same in expectation as \(B\) and then \(A\).
*Proof.* Patches in different categories have independent outcomes, and
the state after both is the same multiset whichever came first; the run
cannot stop before the second patch, since two hits were needed; and the
continuation is a function of the state. \(\square\) *Algebraic identity*;
checked on all 114,835 ordered pairs over the 33,915 states
(`pair_commutation_check`). So the order of the next two patches is
immaterial unless one of them could finish the run, which is why the
exchange argument settles \(H=1\) and nothing beyond it; Theorem 11 settles \(H=2\)
by a different route (Lemma 12).

**What the enumeration rules out** (`policy_structure_fixture`, sizes at
most five, at most four categories). No extremal rule covers the optimal
first patch: in 54 states it is none of the highest-rate, the largest, the
best-finisher (smallest \((n+1)/(F+1)\)) or the worst-finisher category.
Equal rates do not favour the larger category: in
\(\{(2,1),(2,1),(4,2)\}\) with two hits needed the optimal first patch is a
\((2,1)\), against the two-category witness of Proposition 7, in four such
states. Two regularities survived every state of that grid and fail just
beyond it (`conjecture_refutations`): with exactly two categories of equal
rate the larger is *not* always optimal first for \(H\ge2\), since in
\(\{(3,2),(6,4)\}\) with two hits needed the smaller costs \(13/5\) against
\(121/45\) (58 such pairs among 1,044 with sizes at most twelve); and the
lowest of three or more distinct rates *can* be the unique optimal first
patch, as in \(\{(5,3),(8,5),(9,6)\}\) with three hits needed, where the
rate-\(\tfrac35\) category costs \(21/5\) against \(1675/392\) and
\(443/105\). Each refutation is an exact state; neither regularity is a
theorem, and the earlier conjecture is withdrawn.

**Committing until a hit.** Theorem 10 suggests one more candidate shape:
commit to a category until it hits, then re-decide, never switching on a
miss. That class contains the one-hit optimum and is exact there, and it
is *not* optimal in general: in \(\{(4,2),(4,2),(6,3)\}\) with four hits
needed the best committing policy costs \(509/80\) against the optimum
\(763/120\), and `commit_until_hit_fixture` finds 82 such states among
the 39,060 with at most three categories of size at most seven, all with
four to eleven hits needed. The gap
is small everywhere on that grid, below one part in a thousand (one part in
1,526 at most), so an
optimal policy does switch categories after a miss, and gains almost
nothing by it. *Finite verified example.* Version 0.7 sharpens all three
clauses: the class is exact at two hits as well (Theorem 11), fails at three
and at every larger requirement (Corollary 14), and its gap exceeds one part
in a thousand one size class beyond this grid (below).

### Two hits in closed form; where committing stops (version 0.7)

Write \(g(n,F)=(n+1)/(F+1)\) for the finisher of a category with \(F\ge1\).
Patched in uniformly random order, its first failure sits at \(T\) with
\(P(T=t)=\binom{n-t}{F-1}/\binom nF\) for \(t=1,\dots,n-F+1\)
(`first_hit_law`); \(\mathbb E[T]=g(n,F)\). After a first hit at \(T\) the
category is \((n-T,F-1)\), with finisher \(\varphi(T)=(n-T+1)/F\)
(\(+\infty\) when \(F=1\)), and \(\mathbb E[\varphi(T)]=g(n,F)\): the
finisher has the same mean before and after a commitment. \(K_c(s)\) is the
cost of committing to \(c\) until it hits and playing optimally afterwards
(`commit_first_value`); \(V^*_h\) is the optimum with \(h\) hits needed; in
a state \(s\), \(c'\) is \(c\) after a miss, \(c^*\) is \(c\) after a hit,
and \(s'\), \(s^{\rm hit}_c\) the corresponding states.

**Theorem 11 (two hits: commit until the first hit).** With two hits needed,
\[
V^*_2=\min_c\kappa(n_c,F_c,M_{-c}),\qquad
\kappa(n,F,M)=\frac{n+1}{F+1}+\mathbb E\bigl[\min(\varphi(T),M)\bigr],
\]
the minimum over categories with \(F_c\ge1\), where \(M_{-c}\) is the best
finisher among the *other* categories with failures (\(+\infty\) if there is
none). The optimal first patches are exactly the minimizers: an optimal
policy commits to one until it hits, then commits to the best finisher.

*Proof.* \(\kappa(n_c,F_c,M_{-c})=K_c(s)\), by Theorem 10 after the hit, so
\(V^*_2\le\min_cK_c\). Induct on the total number of items. Let \(c\) be an
optimal first patch with \(p=F_c/n_c\). If \(F_c=n_c\) the patch is a sure
hit, a commitment of length one. Otherwise, by induction
\(V^*_2(s')=\min_eK_e(s')\). If \(c'\) attains it, \(V^*_2(s)=1+pV^*_1(s^{\rm hit}_c)+(1-p)K_{c'}(s')=K_c(s)\).
If instead \(K_d(s')<K_{c'}(s')\) for some \(d\ne c\), then
\(V^*_2(s)=1+pV^*_1(s^{\rm hit}_c)+(1-p)K_d(s')\), and three facts give a
contradiction: (i) \(K_d(s)-K_d(s')=\mathbb E[\min(g_c,Z)-\min(g_{c'},Z)]\le g_c-g_{c'}=1/(F_c+1)\),
with \(Z\) the best other finisher after \(d\)'s first hit; (ii)
\(K_{c'}(s')\le g_{c'}+V^*_1(s^{\rm hit}_c)\), because \(c'\) after its first
hit has the failures of \(c^*\) and fewer items, hence a smaller finisher;
(iii) \(p\,g_{c'}=F_c/(F_c+1)\). So
\[
V^*_2(s)-K_d(s)=1+pV^*_1(s^{\rm hit}_c)-pK_d(s')-\bigl(K_d(s)-K_d(s')\bigr)
>1-p\,g_{c'}-\tfrac1{F_c+1}=0,
\]
against \(V^*_2(s)\le K_d(s)\). Hence \(V^*_2(s)=K_c(s)\) for every optimal
\(c\), and every minimizer of \(K\) is optimal because \(K_c\ge V^*_2\).
\(\square\)

With \(r=n-T\) the items left after the first hit,
\(P(r)=\binom r{F-1}/\binom nF\), and the hockey-stick identities give
\(\mathbb E[\min(\varphi,M)]=\bigl(\binom{R+2}{F+1}+M(\binom nF-\binom{R+1}F)\bigr)/\binom nF\)
with \(R\) the largest \(r\le n-1\) such that \((r+1)/F\le M\)
(`two_hit_score_closed_form`). So `two_hit_value` needs one pass over the
categories and one first-hit law each: time linear in the number of items,
where the dynamic programme's state count is exponential in the number of
categories. *Evidence status: algebraic identity.* The receipt checks the
value, the set of optimal first patches and the committing value against the
programme on all 4,487 two-hit states with at most three categories of size
at most seven, three larger states, and the closed form on 3,186 cases;
one-off exact runs of `two_hit_fixture(10, 4)` and `two_hit_fixture(16, 3)`
agree on all 455,115 and 437,972 states.

At two hits the optimal first patch is therefore an index rule once the
index may see the two smallest finishers: \(M_{-c}\) is the smallest
finisher overall unless \(c\) is the only category attaining it, and then
the second smallest. Proposition 7's contexts do not contain them, which is
why rules on those contexts fail. The corrected
witness reads off directly: in \(\{(2,1),(4,2)\}\) the scores are
\(19/6\) and \(37/12\); a second \((2,1)\) lowers the first one's best other
finisher from \(5/3\) to \(3/2\) and its score to \(3\).

**Lemma 12 (the price of one switch).** For any requirement \(h\ge1\), any
state \(s\), a category \(c=(n,F)\) with \(F<n\), \(p=F/n\), and another
category \(d\): let \(\Pi\) be the policy that patches \(c\) once, plays
optimally after a hit, and after a miss commits to \(d\) until it hits and
then plays optimally. Then
\[
\Pi-K_d(s)=\tfrac1{F+1}+p\bigl(K_{c'}(s')-K_d(s')\bigr)+p\,\mathbb E[\rho]-\mathbb E[\delta],\qquad
\Pi-K_c(s)=(1-p)\bigl(K_d(s')-K_{c'}(s')\bigr),
\]
where \(\delta=V^*_{h-1}(c,W,\dots)-V^*_{h-1}(c',W,\dots)\), averaged over
\(d\)'s state \(W\) after its first hit, is what one pass of \(c\) is worth
once \(d\) has hit, and
\(\rho=V^*_{h-1}(c^*,d,\dots)-V^*_{h-1}(c^*\text{ less }T'\text{ passes},d,\dots)\),
averaged over the first-failure position \(T'\) of \(c'\), is what the passes
that \(c'\) misses before its first hit are worth once \(c\) has hit.
*Proof.* Committing to \(c\) is patching it once and committing to \(c'\)
after a miss, which gives the second line. For the first, \(K_d(s)-K_d(s')=\mathbb E[\delta]\)
by definition, \(K_{c'}(s')=g_{c'}+V^*_{h-1}(s^{\rm hit}_c)-\mathbb E[\rho]\)
because \(c'\) after its first hit is \(c^*\) less \(T'\) passes, and
\(p\,g_{c'}=F/(F+1)\); substitute into
\(\Pi-K_d(s)=1+pV^*_{h-1}(s^{\rm hit}_c)-pK_d(s')-(K_d(s)-K_d(s'))\). \(\square\)
*Algebraic identity*; `switch_after_miss` checks it exactly on all 15,650
ordered triples \((s,c,d)\) with at most three categories of size at most
five.

Call \(\sigma=1/(F+1)+p\,\mathbb E[\rho]-\mathbb E[\delta]\) the slack. If
\(\sigma\ge0\), \(\Pi\ge\min(K_c(s),K_d(s))\): when
\(K_{c'}(s')\ge K_d(s')\) the first line gives \(\Pi\ge K_d(s)\), otherwise
the second gives \(\Pi>K_c(s)\). So patching \(c\) once and switching after a
miss beats both commitments only if \(\sigma<0\): one pass of \(c\), after
\(d\)'s hit, must be worth more than \(1/(F+1)\), which is what a pass is
worth to \(c\)'s next hit alone. Theorem 11's step is the case \(h=2\),
where \(\delta\le1/(F+1)\) and \(\rho\ge0\). Beyond two hits the slack can be
negative without a profitable switch (\(-1/12\) in
\(\{(3,1),(4,2),(5,2)\}\) with three hits, \(c=(4,2)\), \(d=(3,1)\)).

*Corollary (one failure).* If \(F=1\) then \(\delta\le1/2\), so
\(\sigma\ge0\). *Proof.* Make \(c\) from \(c'\) by marking one of \(c\)'s
passes, uniformly at random, as extra; a policy for \(c\) can mark online,
declaring each newly seen pass extra with probability one over the number of
\(c\)'s passes not yet seen, and so run an optimal policy for the state with
\(c'\), paying one more patch exactly when the extra pass lies among the
items it patches. The extra pass is equally likely to sit in each of the
\(n\) slots around \(c'\)'s items, independently of \(c'\)'s order, so the
expected extra cost is the expected number of \(c'\)-items patched over
\(n\), at most \(\mathbb E[T_{c'}]/n=1/2\), since \(c'\) has one failure and is
spent at its hit. \(\square\) When *every* category has one failure,
committing is therefore optimal for every requirement, by Theorem 11's
induction with \(\sigma\ge0\) in place of facts (i)–(iii), and each
commitment spends its category at expected cost \((n_c+1)/2\) and leaves
the others unchanged, so \(V^*_H\) is the sum of the \(H\) smallest
\((n_c+1)/2\) (`single_failure_value`). *Algebraic identity*; the receipt
checks \(\delta\le1/2\) on all 5,300 single-failure rows and the closed form on
all 1,760 single-failure states with at most four categories of size at
most eight.

**Lemma 13 (a sure hit goes first).** For any state \(s\) and \(h\ge1\),
\(V^*_h(s\cup\{(1,1)\})=1+V^*_{h-1}(s)\), and the same holds for the best
committing value. *Proof.* Patching \((1,1)\) first gives \(\le\). From any
policy for \(s\cup\{(1,1)\}\), delete its patch of \((1,1)\) if it makes one
and stop as soon as \(h-1\) hits are in: this is a policy for \(s\)
(committing if the original was), and on every path it is at least one
patch shorter, since either the deleted patch was one of the original's
hits or the original's \((h-1)\)-th hit came at least one patch before its
\(h\)-th. \(\square\) *Algebraic identity*;
checked on the padded states below.

**Corollary 14 (where committing is exact).** Committing until a hit is
optimal at every state exactly when at most two hits are needed. *Proof.*
Theorems 10 and 11 for \(H\le2\). For \(H=3\),
\(\{(4,2),(5,2),(14,7)\}\) has \(V^*=1055429/205920\) and best committing
value \(351823/68640\), a gap of \(1/5148\) (one part in 26,386); the optimum
patches \((4,2)\) and after a miss switches to \((14,7)\)
(\(46727/10296<15577/3432\)), and Lemma 12's slack there is
\(-2291/205920\) (\(\mathbb E[\delta]=6157/10296\),
\(\mathbb E[\rho]=5801/11440\)). Lemma 13 with \(H-3\) copies of \((1,1)\)
carries the same gap to every \(H\ge3\). \(\square\) *Algebraic identity*
(witness plus padding, checked for \(H=4,5,6\) in `commit_boundary_fixture`).
The three-hit failure needs size fourteen: a one-off exact scan of all
204,023 three-hit states with at most three categories of size at most
fourteen finds this one state and no other, and none among the 91,338 with
at most four categories of size at most eight. It is another regularity that
held on every smaller grid and failed one size beyond.

**The complexity question, stated.** *PATCH:* given categories
\((n_c,F_c)\), \(1\le F_c\le n_c\), with sizes in unary, a requirement
\(1\le H\le\sum_cF_c\), and a rational \(\theta\) in binary, is
\(V^*_H\le\theta\)? The input length is of order \(\sum_cn_c\) plus the bits
of \(\theta\). What is known (*algebraic identities*, by counting and the
results above): (i) the dynamic programme on per-category progress has at
most \(\prod_c(n_c+1)(F_c+1)\) states, each solved with \(O(C)\) work, so
PATCH is polynomial for every fixed number \(C\) of categories; on the
multiset of remaining pairs it has at most \(\binom{C+T}T\) states with
\(T=N(N+1)/2\) and \(N=\max_cn_c\), so it is polynomial for every fixed
maximum size. A hardness proof must let both grow. (ii) \(H=1\) takes
\(O(C)\) time (Theorem 10), \(H=2\) time linear in the item count (Theorem
11), \(H=\sum_cF_c\) is the sum of last-failure positions, and instances
with one failure per category are a sort (Corollary to Lemma 12). (iii) The
best committing value is polynomial for every fixed \(H\): at its decision
times at most \(H-1\) categories have been touched, each in at most
\((N+1)^2\) states, so it visits at most \(\sum_{k<H}C^k(N+1)^{2k}\) states
with \(O(CN)\) work each; it equals \(V^*\) at every state for \(H\le2\)
and, for each \(H\ge3\), not at every state. (iv) Open: whether \(V^*_3\) is polynomial (after Theorem 11 the
three-hit problem is a single path to the first hit with explicit costs
after it, but the witness's path already uses two categories), and whether
PATCH is hard when \(H\) is part of the input. No reduction was attempted;
nothing here suggests NP-, #P- or PSPACE-hardness, and nothing rules it out.

**How far committing is from the optimum.** *Finite verified example only;
no bound is proved.* Version 0.6's "below one part in a thousand" held on its
grid and fails beyond it: \(\{(10,2),(12,2),(19,3)\}\) with four hits
needed has \(V^*=7477604/479655\approx15.590\) and best committing value
\(22463159/1438965\approx15.611\), a relative gap of \(30347/22432812\),
one part in 739 (`commit_boundary_fixture`). A one-off exact run of
`commit_until_hit_fixture(24, 3, max_failures=3)` finds it the largest among
all 347,616 states with at most three categories of at most three failures
and size at most 24, of which 2,006 have a gap, all with four to six hits
needed. Doubling every size, \(\{(20,2),(24,2),(38,3)\}\), gives
\(4311523/4400921494\), one part in 1,021 (one-off exact run), so the gap
does not simply grow with size; whether it is bounded at all is open.

**Two categories.** *Finite verified example; not a theorem.* With two
categories, committing is optimal and every optimal first patch stays
optimal after a miss in it, on all 782,600 two-category states with sizes at
most 24 (one-off exact run of `two_category_commit_fixture(24)`; the receipt
covers size eight), and Lemma 12's slack is nonnegative for both orders on
all 59,360 states with sizes at most fourteen (98,735 slacks). Theorem 11's
argument would extend to every requirement given exactly that inequality,
\(\mathbb E[\delta]\le1/(F+1)+p\,\mathbb E[\rho]\), for two categories; it is
false with three. With two hits, two categories are covered by Theorem 11.
A switching curve is therefore a curve between two commitments, but it is
not characterized here.

**At most two failures per category.** *A stressed regularity, not a
theorem.* Committing is optimal on every state checked in which each
category has at most two failures: one-off exact runs of
`commit_until_hit_fixture` with `max_failures=2` over all 391,878 states
with at most three categories of size at most 40, 715,778 with four of size
at most twenty, 696,150 with five of size at most twelve and 447,678 with six
of size at most eight; the receipt covers four categories of size at most
eight. Every committing gap found has a category with at least three
failures. Only the one-failure case is proved (Corollary to Lemma 12); the
two-failure case can have negative slack, as in the example above, so a proof
needs more than Lemma 12.

## 4. Ledger wrapper

`audit_category_ledger` accepts a `category_feedback` event carrying the
partition used, records it with its position (`score_only`, `category`,
`item_level`), and forwards to `audit_ledger` one `score_query` per block of
two or more items plus one `item_feedback` naming the singleton items (a count
on a singleton is that item's outcome), so the base access rules apply. An
optional declared partition per set bounds the leak in the lattice; a finer
event is a recorded breach. `audit_ledger` is wrapped, not edited.

## Boundaries

Deterministic channels only: a stochastic channel is a Markov kernel, for which
the \(\mathrm{TV}\) contraction survives (`_pushforward`) but which has no
partition, no lattice position, and no converse of Proposition 1; the Blackwell
preorder on kernels is not treated. Items are independent and a patch changes
its own item only, which the nearest-neighbour learner in `output/eval_reuse_toys`
violated. Greedy ties break by index; \(\mathbb E[T]_{\text{static}}\) depends
on that choice when two categories share a rate. The optimal adaptive policy
is characterized for one hit (Theorem 10), two hits (Theorem 11) and one
failure per category (Corollary to Lemma 12), and only computed beyond:
Proposition 7 rules out index rules on the contexts it names, Lemma 9 and
the survey rule out the obvious extremal rules, Corollary 14 rules out
committing until a hit from three hits on, and the commit gap, the
two-category case and the two-failure case rest on enumeration (sizes up to
24, 24 and 40 in one-off exact runs; the receipt runs smaller grids). The
enumerations stop at six items for the lattice. The complexity of PATCH for
fixed \(H\ge3\) and for unbounded \(H\) is open. No model or loop evidence.
