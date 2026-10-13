# Partial leakage as a lattice of feedback channels

Version 0.5 — 2026-10-13. Exact fixtures for the gap named in
[evaluation_feedback_insertions.md](evaluation_feedback_insertions.md) §H:
feedback that reveals failure *categories* and not items. Files:
`src/spiral_ln/evaluation_feedback_lattice.py`, `tests/test_evaluation_feedback_lattice.py`,
`output/evaluation_feedback_lattice/lattice_v0_5.json`. No model was called.
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
python scripts/verify_evaluation_feedback_lattice.py --output output/evaluation_feedback_lattice/lattice_v0_5.json
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
needed the optimal expected patch count is \(\min_c(n_c+1)/(F_c+1)\), attained
by patching a category of minimal \((n_c+1)/(F_c+1)\) until it hits and never
switching. *Proof.* Induct on the total number of items. Sticking with
\(c\) costs \(1+(1-F_c/n_c)\,n_c/(F_c+1)=(n_c+1)/(F_c+1)\). A miss in \(c\)
lowers its value to \(n_c/(F_c+1)\) and changes nothing else, so if \(c\)
was a best finisher it still is, and by induction continuing with it is
optimal from the new state. Starting in any other \(c'\) costs at least
\(1+(1-F_{c'}/n_{c'})\min(n_{c'}/(F_{c'}+1),\,v)\) with \(v\) the best
finisher's value; the first branch gives \((n_{c'}+1)/(F_{c'}+1)\ge v\), and
the second gives \(1+(1-F_{c'}/n_{c'})v\ge v\) because
\(v\le(n_{c'}+1)/(F_{c'}+1)\le n_{c'}/F_{c'}\). \(\square\) *Algebraic
identity*; `one_hit_fixture` checks the closed form against the dynamic
programme on every state with at most four categories of size at most
eight. The highest current rate is therefore *not* the right rule at one hit:
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
categories), and patches a maximizer; it therefore ranks two categories the
same way in any two states that agree on those inputs. No such rule is
optimal. With \(H=2\), patching \((2,1)\) before \((4,2)\) is strictly better
in the state \(\{(1,1),(2,1),(4,2)\}\) (\(5/2\) against \(8/3\)) and strictly
worse in \(\{(2,1),(4,2)\}\) (\(19/6\) against \(37/12\)). With the totals and
the category count added to the index, \((2,1)\) before \((4,2)\) at
\(H=3\), ten items, five failures, four categories is strictly better in
\(\{(2,1),(2,1),(2,1),(4,2)\}\) and strictly worse in
\(\{(1,1),(2,1),(3,1),(4,2)\}\). *Proof.* By witness; the values are exact
dynamic-programme continuations (`first_patch_values`). \(\square\)
`preference_reversals` finds 30 such pairs for own-count indices over all
33,915 states with at most four categories of size at most five, and 125
and 120 with the two richer contexts. *Evidence status: algebraic identity*
(a counterexample proves the universal negative); the counts are a finite
verified example.

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
the optimal policy; the dynamic programme is exact and cheap, so the gap is
one of understanding, not computation.

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
exchange argument settles \(H=1\) and nothing beyond it.

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
is computed, not characterized: Proposition 7 rules out index rules, Lemma 9
and the survey rule out the obvious extremal rules, and the enumerations
stop at six items for the lattice and at four categories of size five for
the policy search. No model or loop evidence.
