# Partial leakage as a lattice of feedback channels

Version 0.1 — 2026-10-12. Exact fixtures for the gap named in
[evaluation_feedback_insertions.md](evaluation_feedback_insertions.md) §H:
feedback that reveals failure *categories* and not items. Files:
`src/spiral_ln/evaluation_feedback_lattice.py`, `tests/test_evaluation_feedback_lattice.py`,
`output/evaluation_feedback_lattice/lattice_v0_1.json`. No model was called.
Evidence levels follow the calculus card (§11): *algebraic identity* (proved
for all inputs) or *finite verified example* (checked on the enumerated cases
only); no synthetic mechanism result is claimed.

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_feedback_lattice.py --output output/evaluation_feedback_lattice/lattice_v0_1.json
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

**Finite observation.** \(\Phi\) does not preserve joins: for rows
\(\{0,1\}|\{2,3\}\) and columns \(\{0,2\}|\{1,3\}\), \(\Phi(\gamma\vee\gamma')\)
is `item_level` but \(\Phi(\gamma)\vee\Phi(\gamma')\) confuses `1001` with
`0110` (equal row and column sums): two separate category leaks are strictly
coarser than one leak with the refined categories. On \([4]\), 219 of 225
ordered pairs preserve the join and 225 of 225 the meet. *Finite verified
example*: the join failure is a proof by witness; meet preservation is not proved.

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

**Finite observations on the stopping time.** \(\mathbb E[T]\) under the static
greedy schedule is *not* monotone along refinement: one block \((4,2)\), \(H=2\),
gives \(10/3\); \((2,1),(2,1)\) gives \(7/2\). On \([6]\): record `001101`,
\(H=3\), \(21/4\) against \(11/2\). An adaptive schedule that re-queries the
channel after each patch and patches the highest current rate (exact dynamic
programming on count multisets) was at most the static value in every
enumerated case and monotone on every refining pair of \([6]\) and along the
50-item chain; no proof is offered. Chain with block sizes 50, 25, 10, 5, 2, 1
and failures at items \(0,4,\dots,48\): \(m^*/n=8/13,7/12,8/15,1/2,8/25,4/25\);
\(\mathbb E[T]_{\text{static}}=204/7,201/7,51/2,23,31/2,8\);
\(\mathbb E[T]_{\text{adaptive}}\approx29.14,25.64,21.17,18,12,8\).
*Finite verified example.*

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
on that choice when two categories share a rate. No model or loop evidence.
