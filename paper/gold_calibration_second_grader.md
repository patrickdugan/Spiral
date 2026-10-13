# Estimating the gold grader's error with a second grader

Draft 0.1 — 2026-10-13. Closes the boundary of [judge_shared_error_measurement.md](judge_shared_error_measurement.md)
§5: Proposition 2 inverts gold noise at a *known* flip rate \(\eta\); here \(\eta\) is estimated from a second
independent grader, exactly. Files: `src/spiral_ln/evaluation_gold_calibration.py`, `tests/test_evaluation_gold_calibration.py`
(48 tests), `output/evaluation_gold_calibration/gold_v0_1.json` (23 checks, source hashes, exact fractions, floats under
`headline`). No model, judge or grader was called; every number is a `Fraction`; the judge module's tails and gold-noise maps are reused.

```powershell
$env:PYTHONPATH = "src"; python scripts/verify_evaluation_gold_calibration.py --output output/evaluation_gold_calibration/gold_v0_1.json
python -m pytest tests/test_evaluation_gold_calibration.py -q
```

## 1. Model

True label \(Y\in\{0,1\}\), \(\pi=\Pr[Y=1]\). Three raters report \(Y\) flipped independently given \(Y\), each
with one symmetric error rate: the gold grader \(G_1\) (\(\eta_1\)), a second grader \(G_2\) (\(\eta_2\)) and the
controller's own answer \(X_C\) (error \(1-a\)). The judge is excluded: its verdict implies a label that equals
\(Y\) iff \(J=1\), and that label is conditionally independent of \(X_C\) given \(Y\) iff \(\varepsilon_0=\varepsilon\),
i.e. iff \(\varepsilon_1=\varepsilon\) — axiom A2, the hypothesis under test. Write \(\tau=1-2\pi\),
\(d_i=1-2e_i\), and for \(S\subseteq\{1,2,3\}\) the Walsh coefficient \(\hat p_S=E\prod_{i\in S}(-1)^{X_i}\).

**Proposition 1.** \(\hat p_S=\tau^{[|S|\text{ odd}]}\prod_{i\in S}d_i\). *Proof.* \(E[(-1)^{X_i}\mid Y]=(-1)^Y d_i\);
conditional independence multiplies; \(E[(-1)^{kY}]\) is \(\tau\) for odd \(k\) and \(1\) for even. \(\square\)
So the marginal bias \(M_i=\Pr[X_i=0]-\Pr[X_i=1]=\tau d_i\), the pair polarity \(\kappa_{ij}=2A_{ij}-1=d_id_j\)
with \(A_{ij}=\Pr[X_i=X_j]=1-e_i-e_j+2e_ie_j\), and the parity bias \(P=\hat p_{123}=\tau d_1d_2d_3\).
(`walsh_coefficients`, `three_rater_model`; checked against enumeration of the \(2^4\) latent cells
\((Y,X_1,X_2,X_3)\) on a grid of 750 rational parameter points.)

## 2. Identities and identifiability

**Proposition 2.** If \(\kappa_{jk}\ne0\) then \((1-2e_i)^2=\kappa_{ij}\kappa_{ik}/\kappa_{jk}\). *Proof.*
\(d_id_j\,d_id_k/(d_jd_k)=d_i^2\). \(\square\) (`polarity_squares`.) From the agreement rates alone the three
\(\kappa\)'s determine the three squares and nothing more; the root's sign is fixed by the convention
\(e_i<\tfrac12\), which needs every \(\kappa>0\). That convention is a modelling assumption, not a finding:
\((\tau,d)\mapsto(-\tau,-d)\) — every rater worse than chance and the prior swapped — leaves every \(\hat p_S\)
unchanged (`three_rater_model(1-π, 1-e)` equals `three_rater_model(π, e)` on the whole grid). A rater at chance
(\(d_i=0\)) zeroes both of its polarities and leaves the other two with one equation for two unknowns
(`polarity_squares` raises). Exactly one or three negative \(\kappa\)'s fit no symmetric model of any sign.

The root is irrational in general, so three exact operations replace it (`error_rate_from_square`,
`error_rate_at_most`, `error_rate_bracket`): (a) exact recovery when the square is a perfect square, which at
expected counts with rational rates it always is — the fixture's \(\kappa=(\tfrac{12}{25},\tfrac{12}{25},
\tfrac9{25})\) give squares \(\tfrac{16}{25},\tfrac9{25},\tfrac9{25}\), hence \(\eta_1=\tfrac1{10}\),
\(\eta_2=\tfrac15\), \(a=\tfrac45\); (b) membership: \(\eta_1\le\eta_0\) iff \(d_1\ge1-2\eta_0\) iff (for
\(\eta_0<\tfrac12\)) \(\kappa_{12}\kappa_{13}/\kappa_{23}\ge(1-2\eta_0)^2\), a rational comparison; (c) a bracket
of width \(2^{-16}\) by bisection on (b). Gradient of the estimate (`eta_gradient`):
\(\partial\eta_1/\partial\kappa=(-d_1/4\kappa_{12},\,-d_1/4\kappa_{13},\,+d_1/4\kappa_{23})\), at the fixture
\((-\tfrac5{12},-\tfrac5{12},\tfrac59)\); per agreement rate twice that.

## 3. Testable constraints and falsifiers

The \(2^3\) cells have 7 degrees of freedom; the model has 4 parameters \((\tau,d_1,d_2,d_3)\), and its exact
Jacobian has rank 4 wherever every \(d_i\ne0\) (the three pair rows have determinant \(-2d_1d_2d_3\) on the
\(d\) columns; `model_jacobian_rank`). So there are exactly three constraints:

**Proposition 3.** \(M_1\kappa_{23}=M_2\kappa_{13}=M_3\kappa_{12}=P\). *Proof.* Each side is \(\tau d_1d_2d_3\).
\(\square\) Conversely, a table with all \(\kappa>0\), squares in \([0,1]\), \(M_i^2\le d_i^2\) and these three
equalities is the image of exactly one parameter point with every \(e_i<\tfrac12\) (set \(d_i\) from
Proposition 2, \(\tau=M_1/d_1\); the equalities make \(M_i/d_i\) agree; argued here, not separately checked in code).
In cell terms: for every \(x\), \(p(x)+p(\bar x)=\tfrac14\big(1+\sum_{i<j}\kappa_{ij}\chi_{ij}(x)\big)\) holds for
*any* distribution, so the complementary-pair sums carry no constraint; the content sits in the imbalances
\(p(x)-p(\bar x)=\tfrac14\big(\sum_iM_i\chi_i(x)+P\chi_{123}(x)\big)\), whose parity term must equal each
\(M_i\kappa_{jk}\). **At a balanced prior every odd coefficient vanishes and the equalities read \(0=0\):**
the check has no power against grader dependence when \(\pi=\tfrac12\) (`vacuous_at_balanced_prior`).

Falsifiers (`model_constraints`), all exact: a table with \(\kappa=(-\tfrac15,\tfrac15,\tfrac15)\) (one negative:
no sign assignment); a table with \(\kappa=(\tfrac{12}{25},\tfrac{12}{25},\tfrac1{25})\), whose implied
\((1-2\eta_1)^2=\tfrac{144}{25}>1\); and a dependent grader. If \(G_2\) copies \(G_1\) with probability \(\rho\)
and grades independently otherwise, then \(r_1=r_2=-\tau d_C\,\rho\,4\eta_1(1-\eta_1)\) and \(r_3=0\), where
\(r_i=M_i\kappa_{jk}-P\) (`copy_grader_residual`; checked for \(\rho\in\{0,\tfrac14,\tfrac12,\tfrac34,1\}\) at the
fixture prior and for four \(\rho\) at each of five priors): the failing constraints name the dependent pair, and any \(\rho>0\) is detected whenever
\(\tau\ne0\), \(a\ne\tfrac12\) and \(0<\eta_1<1\). With asymmetric errors (false-positive \(\ne\) false-negative)
the model has \(6+1=7\) parameters, the just-identified two-class Dawid–Skene case; this module does not fit it.

## 4. Pipeline (`calibrate`)

Input: the \(2^4\) record of \((x_C,v_J,g_1,g_2)\) on \(m\) sealed items. (1) Marginalise over the judge to the
label table \((g_1,g_2,x_C)\); run the constraint check. (2) \(\kappa\)'s, squares, \(\hat\eta_1,\hat\eta_2,\hat a\)
by Proposition 2, exact or bracketed. (3) Tabulate the judge note's \(2\times2\) against \(G_1\): \(a',\varepsilon',
w=W_1'/m\). (4) Invert Proposition 2 of the judge note at \(\eta=\hat\eta_1\) (`gold_noise_inverse`, reused) to
\((\hat a,\hat\varepsilon,\hat\varepsilon_1)\); the inverted \(\hat a\) equals the identity's \(\hat a\) on every
table with all \(\kappa>0\), since \(\hat d_1\hat d_C=\kappa_{1C}\) exactly. (5) `expected_table` at the recovered
rates, rounded half-up (`rounded_table`), then `independence_p_value` (declared \(\varepsilon\), or the plug-in
flagged), `fisher_p_value`, `ceiling_p_value`, `clopper_pearson_contains`. When \(\hat\eta_1\) is a bracket, every
inverted rate is monotone in \(\eta\) (\(da/d\eta=(2a'-1)/(1-2\eta)^2\), \(d\varepsilon/d\eta=(2\varepsilon'-1)/(1-2\eta)^2\),
and the next line), so the bracket ends map to ends and steps (4)–(5) run at both.

**Sensitivity.** Substituting \(a-\varepsilon=(a'-\varepsilon')/(1-2\eta)\) and \(1-a=(1-a'-\eta)/(1-2\eta)\)
into the note's inversion gives one rational function
\(\varepsilon_1(\eta)=\dfrac{w(1-2\eta)-\eta(a'-\varepsilon')}{1-a'-\eta}\) (`inverted_eps1`, equal to the judge
module's value on the grid). Numerator and denominator are affine, so with
\(K=w(2a'-1)-(a'-\varepsilon')(1-a')\), free of \(\eta\):
\(\dfrac{d\varepsilon_1}{d\eta}=\dfrac{K}{(1-a'-\eta)^2}\) and exactly
\(\varepsilon_1(\eta+\Delta)-\varepsilon_1(\eta)=\dfrac{\Delta K}{(1-a'-\eta)(1-a'-\eta-\Delta)}\)
(`eps1_sensitivity`, `eps1_displacement`; checked against direct re-inversion). At the fixture \(K=-\tfrac{64}{625}\),
\(1-a'-\eta=\tfrac4{25}\): **\(d\varepsilon_1/d\eta=-4\)** for the independent judge and \(-\tfrac52\) for the
shared one. Overestimating \(\eta\) by \(\Delta\) lowers \(\hat\varepsilon_1\) by about \(4\Delta\) (more of the
wrong-wrong cell is attributed to flips); \(\Delta=\tfrac1{100}\) moves it by exactly \(-\tfrac{16}{375}\).
Chained through the gradient of §2, \(d\varepsilon_1/dA_{G_1G_2}=\tfrac{10}{3}\): a 1-point error in the two
graders' agreement rate moves \(\hat\varepsilon_1\) by 3.3 points.

Falsifiers of the pipeline: \(G_1\) and \(G_2\) share a rubric or source (conditional independence fails; the
constraint check is the test, with no power at \(\pi=\tfrac12\)); any rater at or below chance (not identified,
or the sign convention falsified); the sample touched by the loop (`measurement_ledger` reused; `calibration_valid`
withholds). The tests in step (5) take the corrected counts as given: they are an estimate, not a sample, so
the sampling error of \(\hat\eta_1\) is not in their p-values; the sensitivity is its first-order account.

## 5. Fixture

\(m=10000\), \(\pi=\tfrac14\), \(a=\tfrac45\), \(\varepsilon=\tfrac1{10}\), \(\eta_1=\tfrac1{10}\), \(\eta_2=\tfrac15\),
judges \(\varepsilon_1=\tfrac1{10}\) and \(\tfrac12\). Not \(m=400\): that makes the \(2\times2\) integral but the
smallest raw cell has probability \(\tfrac14\cdot\tfrac15\cdot\tfrac1{10}\cdot\tfrac1{10}\cdot\tfrac15=10^{-4}\);
\(10^4\) is the least size at which all sixteen expected counts are integers. No adjustment to a
perfect-square case was needed (§2a). Expected \(2^4\) counts in lexicographic order of \((x_C,v_J,g_1,g_2)\):
independent judge 441, 144, 129, 336, 3889, 976, 441, 144, 976, 259, 144, 171, 144, 171, 336, 1299; shared judge
5, 20, 45, 180, 4325, 1100, 525, 300, 540, 135, 60, 15, 580, 295, 420, 1455. Both marginalise to the label table
\((g_1,g_2,x_C)\): 4330, 1120, 1120, 430, 570, 480, 480, 1470, with \(M=(\tfrac25,\tfrac3{10},\tfrac3{10})\),
\(\kappa=(\tfrac{12}{25},\tfrac{12}{25},\tfrac9{25})\), \(P=\tfrac{18}{125}=\tfrac25\cdot\tfrac9{25}\): residuals
\((0,0,0)\), rank 4, every check passes. Recovered exactly: \(\hat\eta_1=\tfrac1{10}\), \(\hat\eta_2=\tfrac15\),
\(\hat a=\tfrac45\). Measured against \(G_1\): \(a'=\tfrac{37}{50}\), \(\varepsilon'=\tfrac9{50}\) (the judge note's
values), tables \((6500,900,1700,900)\) and \((7300,100,900,1700)\), \(\varepsilon_1'=\tfrac9{26}\) and
\(\tfrac{17}{26}\). Inversion at \(\hat\eta_1\): \((\tfrac45,\tfrac1{10},\tfrac1{10})\) and \((\tfrac45,\tfrac1{10},\tfrac12)\).

| judge | corrected \((R_0,R_1,W_0,W_1)\) | (a) \(p\), \(\varepsilon=\tfrac1{10}\) declared | Fisher \(p\) | (b) \(p\) | 95% CP holds \(\varepsilon\) / \(\tfrac12\) | \(d\varepsilon_1/d\eta\) |
|---|---|---|---|---|---|---|
| independent | (7200, 800, 1800, 200) | 0.5109 | 0.5140 | \(<10^{-321}\) | yes / no | \(-4\) |
| maximally shared | (8000, 0, 1000, 1000) | \(<10^{-300}\) | \(<10^{-300}\) | 0.5089 | no / yes | \(-\tfrac52\) |

The corrected tables are the judge note's fixture scaled by 50, with no rounding; exact p-values are in the receipt.

**Dependent grader.** \(G_2\) a copy of \(G_1\) (\(\rho=1\)): residuals \((-\tfrac{27}{250},-\tfrac{27}{250},0)\),
check fails; the identity returns \(\hat\eta_1=0\) (the copy makes gold look perfect), inversion returns the
uncorrected \(\hat\varepsilon_1=\tfrac9{26}\approx0.346\) against \(\hat\varepsilon=\tfrac9{50}\), and test (a) on
\((2600,900)\) gives \(p\approx7.6\times10^{-252}\): the independent judge is declared shared. Half a copy
(\(\rho=\tfrac12\)): square \(\tfrac{148}{175}\), not perfect; \(\hat\eta_1\in(\tfrac{2633}{65536},\tfrac{1317}{32768})
\approx(0.04018,0.04019)\); \(\hat\varepsilon_1\in(0.27414,0.27417)\); residuals \((-\tfrac{27}{500},-\tfrac{27}{500},0)\).
The constraint check is what stands between a shared rubric and a false finding against A2.
*Evidence status.* Propositions 1–3, the inversion and its sensitivity: *algebraic identity*, cross-checked by
enumeration (latent cells; \(2^5\) for the record table) on rational grids. Fixture values, falsifier tables and
the dependent-grader residuals: *finite verified examples*. Nothing is evidence about any grader, judge or controller.

## 6. Not delivered

- No observed graders; the tables are expectations. Binary labels and symmetric errors only; no Dawid–Skene
  fit. On real counts the squares are not perfect squares; only membership and brackets are exact there.
- No sampling distribution for \(\hat\eta_1\), no joint interval for \((\hat\eta_1,\hat\varepsilon_1)\) and no
  planning rule for the grader step; the p-values at corrected counts condition on the point estimate.
- The constraint check has no power at \(\pi=\tfrac12\) and excludes only dependence that breaks Proposition 3.
