# Leak topology: what the cycles of the intersection complex cost

Draft 0.1 — 2026-10-14. Settles item 4 of §8 of [the crosswalk](feedback_channel_rsitopology_crosswalk.md)
(\(\beta_1\) made precise), prices the cycles, and answers for three or more category maps the question of
[the findings](feedback_channel_findings.md) §8 item 5: is "topology" in this programme more than the word?
Module `src/spiral_ln/evaluation_leak_topology.py` (imports `evaluation_feedback_lattice`, does not edit it);
45 tests in `tests/test_evaluation_leak_topology.py`; receipt `output/evaluation_leak_topology/leak_topology_v0_1.json`
(26 checks, SHA-256 of the five source files). No model, judge, grader or loop was run. Evidence levels follow the
calculus card (§11): *algebraic identity* (proved for every parameter), *finite verified example* (checked on the
enumerated cases only), *cited* (taken from the literature, not reproved). Every check is exact: integers and
`Fraction`s, ranks by fraction-free Gaussian elimination over \(\mathbb Q\) (cross-checked against ordinary
fraction elimination on 400 random matrices); \(\pi\) enters only through the rational bounds
\(3.14159265358979<\pi<3.14159265358980\); decimals in the receipt are exact truncations, for display.

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_leak_topology.py --output output/evaluation_leak_topology/leak_topology_v0_1.json
python -m pytest tests/test_evaluation_leak_topology.py -q
```

## 0. Setting

A record \(r\in\{0,1\}^n\) says which items passed. Category maps \(\gamma_0,\dots,\gamma_{k-1}\) are partitions of
\([n]\); a *cell* is a nonempty intersection \(c=A^0_{c_0}\cap\dots\cap A^{k-1}_{c_{k-1}}\), of size \(s_c\ge1\), and
\(x_c(r)\in[0,s_c]\) counts the passes in it. \(P\) is the set of cells (the *support*). Observing a set \(S\) of maps
jointly leaks the \(S\)-margins \(x_S(u)=\sum_{c_S=u}x_c\); an *observation pattern* \(\Delta\) is a family of jointly
observed sets closed under subsets (its maximal sets are its facets). The *fibre* is \(\ker M_\Delta\subseteq\mathbb Q^P\),
\(M_\Delta\) the margin map; its dimension is the number of free parameters the observation leaves open. The *nerve*
\(K_P\) is the simplicial complex on all blocks whose faces are the sets of blocks with nonempty common intersection;
blocks of one map are disjoint, so a face has at most one block per map, \(K_P\) is *balanced* (coloured by map), its
facets are the cells, and for a set \(T\) of maps the rank-selected subcomplex \(K_{P_T}\) is the nerve of those maps alone.

Two maps \(\gamma,\gamma'\): \(K_P\) is the intersection graph \(I=I(\gamma,\gamma')\) of lattice Prop 2c (vertices the
blocks, edges the cells), and \(M\) is its unsigned incidence matrix. By the proof of Prop 2c, the joint channel
\(\Phi(\gamma\vee\gamma')\) is the cell vector \(x(r)\) and the separate channel \(\Phi(\gamma)\vee\Phi(\gamma')\) is
\(Mx(r)\); the receipt re-derives both record partitions and compares them with the lattice module's channels on all
2,954 ordered pairs of maps on 3–5 items.

## 1. \(\beta_1\) made precise

**Theorem 1.** \(\ker_{\mathbb Q}M\) has dimension \(\beta_1(I)=|E|-|V|+c\); its integer points
\(\ker_{\mathbb Z}M=Z_1(I;\mathbb Z)=H_1(I;\mathbb Z)\cong\mathbb Z^{\beta_1}\) have as a basis the fundamental cycles of
any maximal spanning forest, each an alternating \(\pm1\) vector.

*Proof.* Orient each cell from its row block to its column block; the signed incidence \(D\) has \(M=\Sigma D\) with
\(\Sigma\) the diagonal sign \(+1\) on rows and \(-1\) on columns, so \(\ker M=\ker D\) over any ring, and \(\ker D\) is the
cycle space. \(y^TD=0\) iff \(y\) is constant on components, so \(\operatorname{rank}D=|V|-c\) and
\(\dim\ker D=|E|-|V|+c\). For a maximal spanning forest \(F\) and an edge \(f\notin F\), the fundamental cycle
\(z_f\) is \(+1\) on \(f\), alternates \(-1,+1,\dots\) along the forest path from \(f\)'s column back to its row (odd
length, so it closes), and vanishes on every other off-forest edge. For \(z\in\ker_{\mathbb Z}M\),
\(z-\sum_{f\notin F}z(f)z_f\) is an integer kernel vector supported on a forest, hence zero (a leaf's single edge must
carry zero). \(\square\) *Evidence: algebraic identity*; checked on all 25, 225, 2,704 and 41,209 ordered pairs of
category maps on 3, 4, 5 and 6 items (\(\beta_1\in\{0,1,2\}\); 120 pairs on six items have \(\beta_1=2\)).

This fixes the shared invariant of crosswalk §6: Prop 2c's failure set is the cycle space of \(I\); the differences
of cell tables with equal margins lie in \(H_1(I;\mathbb Z)\) and generate it (each \(z_f=z_f^+-z_f^-\) is one). That the same number
counts a transport graph's independent loops is the definition of \(\beta_1\), not a shared theorem.

**Theorem 2 (integer fibres).** For realized margins \(m\) let \(F(m)=\{x\in\mathbb Z^E:Mx=m,\ 0\le x\le s\}\).
(a) The differences \(x-y\) of points in a common fibre span \(\ker M\). (b) Every \(F(m)\) has affine dimension at
most \(\beta_1\), and some realized \(m\) attains \(\beta_1\). (c) Every \(F(m)\) is connected under single swaps
\(x\mapsto x\pm z_C\) along simple alternating cycles \(C\) that stay in the box.

*Proof.* (a) \(z_C=z_C^+-z_C^-\) with \(z_C^\pm\in\{0,1\}^E\) inside the box (\(s_e\ge1\)) and equal margins; the
\(z_C\) span the cycle space. (b) The upper bound is Theorem 1. Each edge on a cycle has a nonzero coordinate
functional on \(\ker M\), so a small generic \(w\in\ker M\) has \(w_e\notin\mathbb Z\) on every non-bridge and
\(w_e=0\) on bridges; \(y=w-\lfloor w\rfloor\) has \(My=-M\lfloor w\rfloor\) integral, \(0<y_e<1\le s_e\) on non-bridges
and \(y_e=0\) on bridges, which every kernel vector also vanishes on. So the polytope
\(\{x:Mx=My,\,0\le x\le s\}\) contains a \(\beta_1\)-ball of \(y+\ker M\); \([M;I;-I]\) is totally unimodular
(bipartite incidence; *cited*: Hoffman–Kruskal), so the polytope's vertices are integer points of \(F(My)\) and span
its affine hull. (c) \(d=x-y\) is an integer circulation on the oriented graph; it decomposes into simple directed
cycles conformal to \(d\), and a directed cycle alternates row-to-column on edges with \(d>0\) and back on edges
with \(d<0\), i.e. it is a \(\pm z_C\). Subtracting one such conformal \(z_C\) from \(x\) stays in the box (where
\(z_C=+1\), \(x_e\ge y_e+1\ge1\); where \(-1\), \(x_e\le s_e-1\)) and shortens \(\|d\|_1\). \(\square\)
*Evidence: algebraic identity*; (a)–(c) checked on every fibre of every ordered pair on 3–5 items.

## 2. What the cycles cost

**Proposition 3 (completion).** The separate observation plus the counts on a set \(S\) of cells determines every
cell count iff the cells outside \(S\) form a forest. So the joint leak is the separate leak plus exactly \(\beta_1\)
cell counts (those off a maximal spanning forest), no fewer suffice, and the number of minimum completions is the
number \(\kappa(I)\) of maximal spanning forests. *Proof.* A cycle \(C\) avoiding \(S\) gives
\(z_C^+\ne z_C^-\) agreeing on margins and on \(S\). If \(E\setminus S\) is a forest, subtract the known counts from
the margins and peel leaves (Prop 2c). A forest has at most \(|V|-c\) edges. \(\square\) *Evidence: algebraic
identity*; checked against brute force over every subset \(S\) on all 2,954 pairs, with \(\kappa\) cross-checked by
Kirchhoff's matrix-tree theorem (*cited*).

**Theorem 4 (confusion is a sum over \(H_1\)).** Let items pass independently (per-item probabilities arbitrary) and
\(R,R'\) be independent records, \(X_e,X'_e\) their cell counts, \(q_e(k)=\Pr[X_e-X'_e=k]\). Then
\[
\Pr[Mx(R)=Mx(R')]=\sum_{z\in H_1(I;\mathbb Z)}\ \prod_{e}q_e(z_e),\qquad \Pr[x(R)=x(R')]=\prod_e q_e(0),
\]
and under the uniform prior \(4^{n}\) times the left side is \(\sum_{z}\prod_e\binom{2s_e}{s_e+z_e}\) ordered record
pairs (Vandermonde). *Proof.* Margins agree iff \(x(R)-x(R')\in\ker_{\mathbb Z}M\) (Theorem 1); cells are independent.
\(\square\) The joint observation keeps the \(z=0\) term only, so the excess is the sum over nonzero cycles: positive
iff \(\beta_1>0\). With unit cells and \(p=\tfrac12\) the *collision ratio* \(\mathrm{CP}(\text{margins})/\mathrm{CP}(\text{cells})\)
is \(\sum_z2^{-|\operatorname{supp}z|}\) over \(z\in H_1\cap\{0,\pm1\}^E\). *Evidence: algebraic identity*; checked
against direct fibre sums on all 2,954 pairs at \(p=\tfrac12\) and \(p=\tfrac13\).

**Proposition 4b (blocks).** The collision ratio is the product of the ratios of the biconnected blocks of \(I\);
bridges contribute 1; for one cycle with cell sizes \(s_1,\dots,s_L\) it is
\(\sum_{t}\prod_i\binom{2s_i}{s_i+t}/\binom{2s_i}{s_i}\), a function of the multiset of sizes, and
\(1+2^{1-L}\) for unit cells. *Proof.* A cut argument (a circulation has zero net flow across the edges joining a
cut vertex to one component of its complement) shows \(z|_B\in Z_1(B)\) for each block \(B\), so
\(H_1(I;\mathbb Z)=\bigoplus_BH_1(B;\mathbb Z)\) and the summand of Theorem 4 factorizes; on one cycle
\(z=\pm t\) on every edge. \(\square\) *Algebraic identity*; checked on unit cycles of length 4–10, on rotated size
patterns of \(C_4\), and on the pendant, vertex-joined and disjoint witnesses below.

**Theorem 5 (dilation).** With \(p=\tfrac12\) and cell sizes \(s_e=N\sigma_e\),
\[
\frac{\mathrm{CP}(\text{margins})}{\mathrm{CP}(\text{cells})}=(\pi N)^{\beta_1/2}\Big(\frac{\prod_e\sigma_e}{\tau_\sigma(I)}\Big)^{1/2}(1+o(1)),
\qquad \tau_\sigma(I)=\sum_{\text{maximal spanning forests }T}\ \prod_{e\in T}\sigma_e .
\]
*Proof.* In fundamental coordinates \(z=Zt\), \(t\in\mathbb Z^{\beta_1}\), the ratio is
\(\sum_t\prod_e\rho_{N\sigma_e}((Zt)_e)\) with \(\rho_s(k)=\binom{2s}{s+k}/\binom{2s}{s}\). For \(0\le k\le s\),
\(\log\rho_s(k)=\sum_{j\le k}\log\bigl(1-\tfrac{2j-1}{s+j}\bigr)\le-k^2/(2s)\), a Gaussian majorant;
\(\rho_{N\sigma}(k)\to e^{-y^2/\sigma}\) when \(k/\sqrt N\to y\) (local de Moivre–Laplace; *cited*); dominated
convergence for the Riemann sum gives \(N^{-\beta_1/2}\sum_t\to\int e^{-u^TAu}du=\pi^{\beta_1/2}(\det A)^{-1/2}\),
\(A=Z^T\operatorname{diag}(1/\sigma)Z\). By Cauchy–Binet \(\det A=\sum_{|S|=\beta_1}\det(Z_S)^2\prod_{e\in S}\sigma_e^{-1}\);
\(Z_S\) is singular unless \(S\) is the complement of a maximal spanning forest \(F'\) (otherwise a cycle avoids \(S\)),
and then \(Z_S=U\) where \(Z=Z'U\) with \(Z'\) the fundamental basis for \(F'\) (\(Z'_S=I\)), \(U\in GL(\mathbb Z)\), so
\(\det Z_S=\pm1\) and \(\det A=\tau_\sigma/\prod\sigma\). \(\square\) *Evidence:* the determinant identity is an
*algebraic identity* (checked on all 2,954 pairs with weights \(s_e\) and \(1/s_e\), and on \(K_{3,3}\) with
weights \(1/3,\dots,3\)); the limit is proved modulo the cited local limit theorem; the trend is a *finite verified
example*. \(A_N=\text{ratio}^2\,\tau_\sigma/(N^{\beta_1}\prod\sigma)\) should tend to \(\pi^{\beta_1}\):

| graph, \(\sigma\) | \(\beta_1\) | \(\tau_\sigma\) | \(A_N\) at the scales computed | limit | \(N(A_N-\pi^{\beta_1})\) |
|---|---:|---:|---|---:|---|
| \(C_4\), unit | 1 | 4 | 3.4997, 3.3172, 3.2285, 3.1848, 3.1631 (\(N=4\dots64\)) | 3.1416 | 1.432 → 1.378 |
| \(C_4\), \((1,2,1,2)\) | 1 | 12 | 3.7341, 3.4291, 3.2831, 3.2118, 3.1765 (\(N=2\dots32\)) | 3.1416 | 1.185 → 1.118 |
| \(K_{2,3}\), unit | 2 | 12 | 14.822, 12.130, 10.948, 10.396 (\(N=2\dots16\)) | 9.8696 | 9.90 → 8.43 |

Each sequence decreases and stays above \(\pi^{\beta_1}\) (rational upper bound), and the scaled excess settles,
consistent with an \(O(1/N)\) error; the rate is not proved. The same argument with \(\operatorname{Var}(X-X')=2p(1-p)N\sigma\) gives
\((4\pi p(1-p)N)^{\beta_1/2}\) for general \(p\); that case is not checked. The Shannon gap \(H(x\mid Mx)\) is expected
to have the same leading term \(\tfrac{\beta_1}2\log_2N\) by an entropy local limit theorem; it is not proved or
checked here.

**Ehrhart degree.** Over margins \(N\,M(\mathbf 1)\) with sizes \(2N\) the fibre is \(N\mathbf1+Zt\) with
\(\|Zt\|_\infty\le N\); \(\{u:\|Zu\|_\infty\le1\}\) is a lattice polytope (its vertices solve \(Z_Su=\pm\mathbf1\) with
\(Z_S\) unimodular) of dimension \(\beta_1\), so the count is a polynomial of degree \(\beta_1\) (Ehrhart; *cited*).
Counts: \(C_4\) and \(C_6\): \(2N+1\); \(K_{2,3}\): \(3N^2+3N+1\); two \(C_4\) at a vertex: \((2N+1)^2\);
\(K_{3,3}\): \(1,31,217,811,2191,4861,9451\) (degree 4). *Finite verified example* for the counts.

**What depends only on \(\beta_1\), and what does not.** Determined by \(\beta_1\) alone (proved): the fibre dimension;
the rank of the integer move lattice; the affine dimension of the largest integer fibre; the number of extra cell
counts that complete the separate leak; the Ehrhart degree; the exponent \(\beta_1/2\) in Theorem 5. Not determined by
\(\beta_1\) (witnesses; each value exact, uniform prior):

| cell graph (all \(\beta_1=1\), six items unless noted) | separate classes | collision ratio | cell-guess error | record-guess gap | min. completions |
|---|---:|---:|---:|---:|---:|
| \(C_4\), unit (four items) | 15 | 9/8 | 1/16 | 1/16 | 4 |
| \(C_6\), unit | 63 | 33/32 | 1/64 | 1/64 | 6 |
| \(C_4\), sizes \(3,1,1,1\) | 29 | 19/16 | 5/64 | 3/64 | 4 |
| \(C_4\), sizes \(2,2,1,1\) (or \(2,1,1,2\)) | 32 | 11/9 | 3/32 | 1/16 | 4 |
| \(C_4\), unit, plus a pendant path | 60 | 9/8 | 1/16 | 1/16 | 4 |
| \(K_{2,3}\), unit (\(\beta_1=2\)) | 54 | 11/8 | 5/32 | 5/32 | 12 |
| two \(C_4\), at a vertex or disjoint (\(\beta_1=2\), eight items) | 225 | 81/64 | 31/256 | 31/256 | 16 |

The collision ratio depends on the cycles' lengths and cell sizes and on how cycles share edges (\(K_{2,3}\) against two
\(C_4\)), not on bridges; Bayes errors and class counts also depend on the forest part; the number of minimum
completions is \(\kappa(I)\). On all pairs up to five items, the confusion excess and the collision ratio already take
two values at \(\beta_1=1\). *Evidence: algebraic identity* for the dependence claims (a pair of witnesses proves the
negative); the table is exact.

## 3. Three or more maps

**Proposition 6 (full support).** If every \(k\)-fold intersection is nonempty (\(m_j\) blocks in map \(j\)),
\(\dim\ker M_\Delta=\sum_{T\notin\Delta}\prod_{j\in T}(m_j-1)\), and \(\prod_{j\in T}(m_j-1)=\tilde\beta_{|T|-1}(K_{P_T})\)
because \(K_{P_T}\) is a join of discrete sets. *Proof.* \(\mathbb Q^P=\bigotimes_j(\mathbb Q\mathbf1\oplus\mathbf1^\perp)
=\bigoplus_TW_T\); the \(S\)-margin kills \(W_T\) iff \(T\not\subseteq S\) and is injective on
\(\bigoplus_{T\subseteq S}W_T\). \(\square\) *Algebraic identity*; checked for all 19 patterns on the
\(2{\times}2{\times}2\), \(2{\times}3{\times}4\), \(3{\times}3{\times}3\) grids and all 167 on two four-map grids.
On full supports every pattern is homological; the question is general supports.

**Theorem 7 (one minimal non-face: links).** Let \(\Delta=\{S:W\not\subseteq S\}\) for a nonempty set \(W\) of maps,
\(R\) the rest. Then
\[
\ker M_\Delta\cong\bigoplus_{r\in P_R}\tilde H_{|W|-1}\bigl(\operatorname{lk}_{K_P}r;\mathbb Q\bigr),\qquad
\dim\ker M_\Delta=\sum_{r\in P_R}\tilde\beta_{|W|-1}(\operatorname{lk}r),
\]
and likewise over \(\mathbb Z\) with integral cycles. Cases: \(W=[k]\) gives \(\tilde\beta_{k-1}(K_P)\) (every map but
one observed jointly); \(k=2\), \(W=\{0,1\}\) is Theorem 1; \(|W|=1\) gives \(\sum_r(|\text{slice}_r|-1)\).
*Proof.* Every margin of \(\Delta\) fixes the \(R\)-coordinates, so \(M_\Delta\) is block diagonal over
\(r\in P_R\); on the slice over \(r\), whose nerve is \(\operatorname{lk}r\), the margins are the
\((W\setminus w)\)-margins for each \(w\in W\), the unsigned top boundary of a balanced complex. Multiplying the rows of
face type \(W\setminus w\) by \((-1)^{\text{position of }w}\) turns it into the simplicial boundary (the augmentation
when \(|W|=1\)); the slice complex has no faces above the top, so the kernel is \(\tilde H_{|W|-1}\). \(\square\)
Two reductions extend it: a map in no observed set can be projected away, adding \(|P|-|P_O|\) (the \(|W|=1\) case);
maps that every observed set contains together or omits together act as one map (their join). Of the 19 patterns on
three maps, 8 reduce to "everything observed jointly", 10 to a single minimal non-face, and one is left: all three
observed separately. On four maps the theorem and reductions cover 86 of 167 patterns. *Evidence: algebraic
identity*; checked against the rank on every pattern and every support of the \(2{\times}2{\times}2\) (193 supports)
and \(2{\times}2{\times}3\) (3,271) grids, and on seeded samples of \(3{\times}3{\times}3\) (120), \(2^4\) (120) and
\(2{\times}3{\times}2{\times}3\) (60): 79,992 pattern comparisons and 27,788 direct link-formula comparisons, no mismatch.

**Theorem 8 (separate observation: the projection sequence).** Observe \(k\ge2\) maps separately. Let
\(P'=P_{[k-1]}\) and let \(G\) be the intersection graph of the merged map \(\gamma_0\vee\dots\vee\gamma_{k-2}\) with
\(\gamma_{k-1}\) (vertices \(P'\sqcup V_{k-1}\), one edge per cell). The sequence
\[
0\to Z_1(G)\to\ker M_{\rm sep}(P)\xrightarrow{\ \pi\ }\ker M_{\rm sep}(P')\xrightarrow{\ \Psi\ }\tilde H_0(G)
\]
is exact, \(\pi\) summing out the last map and \(\Psi(y)_C=\sum_{u\in C\cap P'}y_u\) over components \(C\) of \(G\). So
\[
f(P)=\beta_1(G)+f(P')-\operatorname{rank}\Psi,\qquad 0\le\operatorname{rank}\Psi\le\min\bigl(f(P'),\,c(G)-1\bigr),
\]
and \(f(P)=\beta_1(G)+f(P')\) whenever \(G\) is connected. *Proof.* A kernel vector with zero projection has zero
\(P'\)-margins and zero last-map margins: the margin conditions of \(G\), whose kernel is \(Z_1(G)\) (Theorem 1). A
\(y\in\ker M_{\rm sep}(P')\) lifts iff the transportation problem on \(G\) with row sums \(y\) and column sums 0 is
solvable, iff each component's row sums total zero (the image of a bipartite incidence matrix is cut out by one
balance condition per component, by the rank count of Theorem 1). \(\Psi\) lands in the sum-zero vectors because
\(\sum_uy_u\) is a margin total. \(\square\) *Algebraic identity*; checked for every choice of the projected map on
every support of the two exhaustive grids and on seeded \(3^3\), \(2^4\), \(3{\times}2{\times}2{\times}3\) samples
(12,112 cases; \(\operatorname{rank}\Psi>0\) in 763 of them).

Note also that for separate observation the margin map *is* the vertex–facet incidence matrix of \(K_P\) (a block is
a vertex, a cell a facet), so \(f(P)\) is a combinatorial invariant of the nerve with its colours erased
(checked on all 3,271 supports of the \(2{\times}2{\times}3\) grid with anonymized vertices).

**Counterexample 9 (the separate fibre is not a homotopy invariant).** On six items, with one item per cell:

| | \(\gamma_0\) | \(\gamma_1\) | \(\gamma_2\) | \(f\) |
|---|---|---|---|---:|
| \(P_0\) | \(\{0,1,2,3\}\mid\{4,5\}\) | \(\{0,1,4\}\mid\{2,5\}\mid\{3\}\) | \(\{0,2\}\mid\{1,5\}\mid\{3,4\}\) | 0 |
| \(P_1\) | \(\{0,1,2,3\}\mid\{4,5\}\) | \(\{0,1\}\mid\{2,4\}\mid\{3,5\}\) | \(\{0,4\}\mid\{1,5\}\mid\{2,3\}\) | 1 |

Both nerves collapse to graphs with \(\beta_1=3\) (each is homotopy equivalent to a wedge of three circles); the three
rank-selected two-map graphs are connected with \(\beta_1=1\) in both; the vertex links agree as multisets of forests,
the edge links as multisets of point sets, the three merged-colour graphs are two trees each, and the coloured face
numbers agree \((2,3,3;5,5,6;6)\). Yet the three category leaks observed separately reveal every item under \(P_0\)
and confuse `101001` with `010110` under \(P_1\) (both checked against the lattice module's channels). Theorem 8
locates the difference: in both, \(G\) has two components and \(\beta_1(G)=0\), \(f(P')=1\), and the one cycle of \(K_{P'}\) either has nonzero sums over the components
(\(\operatorname{rank}\Psi=1\), \(P_0\)) or zero sums (\(P_1\)). So the separate fibre for \(k\ge3\) is not a function of
the homotopy types of the nerve, its rank-selected subcomplexes, its links and its merged-colour graphs, together
with the face numbers. A map with a single block changes no fibre and turns each natural complex into itself or a
cone over it, so the same pair works for every \(k\ge3\). *Evidence: algebraic identity* (a
counterexample proves the negative; the homotopy claims are certified by explicit collapses and graph Betti numbers).

**Non-local fibre vectors.** For the five cells \((000),(001),(011),(101),(110)\) of the \(2{\times}2{\times}2\) grid the
separate fibre has dimension 1 while every homological sub-fibre inside it (top cycles of the nerve, cycles of the
links, cycles of the merged-colour graphs) is zero: the fibre vector \((1,-2,1,1,-1)\) is not a sum of homological
pieces. In the \(2{\times}2{\times}2\) grid 8 of 193 supports have such a gap (none smaller than five cells), in the
\(2{\times}2{\times}3\) grid 240 of 3,271. *Finite verified example* for the counts; the witness is exact.

**Proposition 10 (for three maps the support no longer decides strictness).** For two maps, a separate leak is
strictly coarser than the joint one iff \(\beta_1>0\), whatever the cell sizes (Prop 2c; Theorem 1 gives \(\pm1\)
cycles). For three maps observed separately this fails. With the five cells above and one item per cell
(\(\gamma_0=\{0,1,2\}|\{3,4\}\), \(\gamma_1=\{0,1,3\}|\{2,4\}\), \(\gamma_2=\{0,4\}|\{1,2,3\}\)) the fibre has dimension 1, yet
the separate observation is item-level: \(\ker_{\mathbb Z}\) is spanned by the primitive \((1,-2,1,1,-1)\), and a
difference of two 0/1 tables cannot be a nonzero multiple of it. Give the cell \((001)\) two items and the separate
observation confuses `100110` with `011001`. In the \(2{\times}2{\times}2\) grid, 8 of the 99 supports with a positive
fibre are not strict with unit cells. *Algebraic identity* for the witness, checked at the record level against the
lattice module's channels.

**Proposition 11 (integrality inside the homological class).** Take the six-vertex \(\mathbb{RP}^2\), glue a disk (a cone
on three triangles) along the projective line \(1\!-\!2\!-\!5\), and let three category maps be the vertices, edges and
triangles of that complex, the items being its 78 flags (vertex \(\subset\) edge \(\subset\) triangle). The nerve is
the barycentric subdivision, \(\tilde\beta=(0,0,1)\), and observing every pair of maps jointly leaves a fibre of
dimension \(\tilde\beta_2=1\) (Theorem 7 with \(W=[3]\)). Its integral generator is \(\pm1\) on the 60 flags of
\(\mathbb{RP}^2\) and \(\pm2\) on the 18 flags of the disk (the \(\mathbb{RP}^2\) chain has boundary twice the line,
so the disk must carry coefficient 2). With one item per flag the pairwise-joint observation is item-level; with two items on each disk flag (96 items) the receipt
exhibits two records with equal pairwise margins and different cells. So the rational dimension is homological, but
whether a small-cell leak is strict depends on integral cycles, which the rational Betti number does not see.
*Finite verified example*, with the item-level claim proved by the same primitive-generator argument.

## 4. Is "topology" more than the word?

Partly, and the boundary is sharp. For every observation pattern with a single unobserved interaction (one minimal
non-face, after dropping unobserved maps and merging maps that are always observed together), the leak's free
parameters are exactly reduced homology: the top homology of the links of the nerve of the block cover, over
\(\mathbb Q\) for the dimension and over \(\mathbb Z\) for the fibre lattice. That includes two maps observed separately
(\(H_1\) of the intersection graph) and every three-map pattern but one. There the word is earned: the dimension is a
homotopy invariant of natural complexes, and for two maps the cost in Theorem 5 grows with exponent \(\beta_1/2\).

For three or more maps observed separately it is not. The fibre dimension is the corank of the nerve's vertex–facet
incidence, a combinatorial invariant, and it is not determined by the homotopy types of the nerve, its rank-selected
subcomplexes, its links or its merged-colour graphs, nor by the face numbers (Counterexample 9). The exact formula
(Theorem 8) is a sum of graph Betti numbers minus the rank of a connecting map, and that rank, where cycles of one
graph sit relative to the components of another, is the non-homological datum. Some fibre vectors lie outside every
homological sub-fibre. Any kernel is the second homology of some tautological 2-complex (one loop per block, one 2-cell
per cell), so "no natural complex" cannot be proved absolutely; what is shown is that none of the natural candidates
works. Even in the homological class, strictness at small cell sizes needs integral information (Proposition 11).

## 5. What this changes upstream

- Crosswalk §8 item 4: settled (Theorem 1), with the integer and fibre statements (Theorem 2). The status of
  \(\beta_1\) in crosswalk §6–§7 stays *same object, different regime*: graph homology on both sides, no shared theorem.
- Findings §8 item 5: answered as in §4. "Topology" is literal for observation patterns with one minimal non-face,
  and only nominal for separate observation of three or more category leaks. There a ledger must record the category
  maps themselves, not only which blocks intersect: the intersection pattern alone no longer decides whether separate
  observation hides anything (Proposition 10).
- Lattice Prop 2c generalizes as follows: a pattern hides nothing at every cell-size vector iff its fibre is zero
  (a nonzero integer fibre vector \(z\) is a witness once \(s_c\ge|z_c|\)); for two maps, and whenever the integer
  fibre contains a nonzero vector with entries in \(\{0,\pm1\}\), a positive fibre hides something at every size.

## Boundaries

Deterministic category channels and independent items only; nothing here involves a learner, a patch policy or a
model. Theorem 2(b) cites total unimodularity (Hoffman–Kruskal); the matrix-tree count, Ehrhart's theorem and the local
de Moivre–Laplace theorem are cited, the first cross-checked by brute force; Theorem 5 is checked as a trend on three
graphs at \(p=\tfrac12\) only, and the Shannon-gap asymptotic is not treated. Enumerations: two maps on up to six items
(fibres and record partitions up to five); supports of the \(2{\times}2{\times}2\) and \(2{\times}2{\times}3\) grids
exhaustively; larger grids and four maps by seeded samples (seeds in the receipt). Patterns on four or more maps
outside Theorem 7 (81 of 167 on four maps) are not classified; the negative result is shown for separate observation
(and anything that reduces to it) only. "Not homological" is relative to the named family of complexes. Whether a
balanced complex can have a top homology class with no \(\{0,\pm1\}\) representative in fewer flags than
Proposition 11 uses, or whether integrality ever matters for two maps observed jointly with a third, is not examined.
