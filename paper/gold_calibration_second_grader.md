# Estimating the gold grader's error with a second grader

Draft 0.2 — 2026-10-13. Closes the boundary of [judge_shared_error_measurement.md](judge_shared_error_measurement.md) §5: Proposition 2 inverts
gold noise at a *known* flip rate \(\eta\); here \(\eta\) is estimated from a second independent grader, exactly. 0.2 adds the exact sampling law of
\(\hat\eta_1\) (§6) and the asymmetric Dawid–Skene model with its inversion (§7). Files: `src/spiral_ln/evaluation_gold_calibration.py`,
`tests/test_evaluation_gold_calibration.py` (84 tests), `output/evaluation_gold_calibration/gold_v0_2.json` (40 checks, source hashes, exact
fractions, floats under `headline`). No model, judge or grader was called; every number is a `Fraction`; the judge module's tails and maps are reused.

```powershell
$env:PYTHONPATH = "src"; python scripts/verify_evaluation_gold_calibration.py --sampling-size 400 --sampling-size 742 --output output/evaluation_gold_calibration/gold_v0_2.json
python -m pytest tests/test_evaluation_gold_calibration.py -q
```

## 1. Model

True label \(Y\in\{0,1\}\), \(\pi=\Pr[Y=1]\). Three raters report \(Y\) flipped independently given \(Y\), each with one symmetric error rate: the gold
grader \(G_1\) (\(\eta_1\)), a second grader \(G_2\) (\(\eta_2\)) and the controller's own answer \(X_C\) (error \(1-a\)). The judge is excluded: its verdict
implies a label that equals \(Y\) iff \(J=1\), and that label is conditionally independent of \(X_C\) given \(Y\) iff \(\varepsilon_0=\varepsilon\), i.e. iff
\(\varepsilon_1=\varepsilon\) — axiom A2, the hypothesis under test. Write \(\tau=1-2\pi\), \(d_i=1-2e_i\), and for \(S\subseteq\{1,2,3\}\) the Walsh
coefficient \(\hat p_S=E\prod_{i\in S}(-1)^{X_i}\).

**Proposition 1.** \(\hat p_S=\tau^{[|S|\text{ odd}]}\prod_{i\in S}d_i\). *Proof.* \(E[(-1)^{X_i}\mid Y]=(-1)^Y d_i\); conditional independence multiplies;
\(E[(-1)^{kY}]\) is \(\tau\) for odd \(k\) and \(1\) for even. \(\square\) So the marginal bias \(M_i=\Pr[X_i=0]-\Pr[X_i=1]=\tau d_i\), the pair polarity
\(\kappa_{ij}=2A_{ij}-1=d_id_j\) with \(A_{ij}=\Pr[X_i=X_j]=1-e_i-e_j+2e_ie_j\), and the parity bias \(P=\hat p_{123}=\tau d_1d_2d_3\). (`walsh_coefficients`,
`three_rater_model`; checked against enumeration of the \(2^4\) latent cells \((Y,X_1,X_2,X_3)\) on a grid of 750 rational parameter points.)

## 2. Identities and identifiability

**Proposition 2.** If \(\kappa_{jk}\ne0\) then \((1-2e_i)^2=\kappa_{ij}\kappa_{ik}/\kappa_{jk}\). *Proof.* \(d_id_j\,d_id_k/(d_jd_k)=d_i^2\). \(\square\) (`polarity_squares`.)
From the agreement rates alone the three \(\kappa\)'s determine the three squares and nothing more; the root's sign is fixed by the convention
\(e_i<\tfrac12\), which needs every \(\kappa>0\). That convention is a modelling assumption, not a finding: \((\tau,d)\mapsto(-\tau,-d)\) — every rater worse
than chance and the prior swapped — leaves every \(\hat p_S\) unchanged (`three_rater_model(1-π, 1-e)` equals `three_rater_model(π, e)` on the whole
grid). A rater at chance (\(d_i=0\)) zeroes both of its polarities and leaves the other two with one equation for two unknowns (`polarity_squares`
raises). Exactly one or three negative \(\kappa\)'s fit no symmetric model of any sign.

The root is irrational in general, so three exact operations replace it (`error_rate_from_square`, `error_rate_at_most`, `error_rate_bracket`):
(a) exact recovery when the square is a perfect square, which at expected counts with rational rates it always is — the fixture's
\(\kappa=(\tfrac{12}{25},\tfrac{12}{25},\tfrac9{25})\) give squares \(\tfrac{16}{25},\tfrac9{25},\tfrac9{25}\), hence \(\eta_1=\tfrac1{10}\), \(\eta_2=\tfrac15\), \(a=\tfrac45\); (b) membership:
\(\eta_1\le\eta_0\) iff \(d_1\ge1-2\eta_0\) iff (for \(\eta_0<\tfrac12\)) \(\kappa_{12}\kappa_{13}/\kappa_{23}\ge(1-2\eta_0)^2\), a rational comparison; (c) a bracket of width
\(2^{-16}\) by bisection on (b), or from \(r=\lfloor2^{16}\sqrt S\rfloor=\mathrm{isqrt}\lfloor4^{16}S\rfloor\) (`root_bracket`, exact integer arithmetic). Gradient of
the estimate (`eta_gradient`): \(\partial\eta_1/\partial\kappa=(-d_1/4\kappa_{12},\,-d_1/4\kappa_{13},\,+d_1/4\kappa_{23})\), at the fixture \((-\tfrac5{12},-\tfrac5{12},\tfrac59)\);
per agreement rate twice that.

## 3. Testable constraints and falsifiers

The \(2^3\) cells have 7 degrees of freedom; the model has 4 parameters \((\tau,d_1,d_2,d_3)\), and its exact Jacobian has rank 4 wherever every
\(d_i\ne0\) (the three pair rows have determinant \(-2d_1d_2d_3\) on the \(d\) columns; `model_jacobian_rank`). So there are exactly three constraints:

**Proposition 3.** \(M_1\kappa_{23}=M_2\kappa_{13}=M_3\kappa_{12}=P\). *Proof.* Each side is \(\tau d_1d_2d_3\). \(\square\) Conversely, a table with all \(\kappa>0\),
squares in \([0,1]\), \(M_i^2\le d_i^2\) and these three equalities is the image of exactly one parameter point with every \(e_i<\tfrac12\) (set \(d_i\) from
Proposition 2, \(\tau=M_1/d_1\); the equalities make \(M_i/d_i\) agree; argued here, not separately checked in code). In cell terms: for every \(x\),
\(p(x)+p(\bar x)=\tfrac14\big(1+\sum_{i<j}\kappa_{ij}\chi_{ij}(x)\big)\) holds for *any* distribution, so the complementary-pair sums carry no constraint; the
content sits in the imbalances \(p(x)-p(\bar x)=\tfrac14\big(\sum_iM_i\chi_i(x)+P\chi_{123}(x)\big)\), whose parity term must equal each \(M_i\kappa_{jk}\). **At a
balanced prior every odd coefficient vanishes and the equalities read \(0=0\):** the check has no power against grader dependence when
\(\pi=\tfrac12\) (`vacuous_at_balanced_prior`).

Falsifiers (`model_constraints`), all exact: a table with \(\kappa=(-\tfrac15,\tfrac15,\tfrac15)\) (one negative: no sign assignment); a table with
\(\kappa=(\tfrac{12}{25},\tfrac{12}{25},\tfrac1{25})\), whose implied \((1-2\eta_1)^2=\tfrac{144}{25}>1\); and a dependent grader. If \(G_2\) copies \(G_1\) with probability
\(\rho\) and grades independently otherwise, then \(r_1=r_2=-\tau d_C\,\rho\,4\eta_1(1-\eta_1)\) and \(r_3=0\), where \(r_i=M_i\kappa_{jk}-P\) (`copy_grader_residual`;
checked for \(\rho\in\{0,\tfrac14,\tfrac12,\tfrac34,1\}\) at the fixture prior and for four \(\rho\) at each of five priors): the failing constraints name the
dependent pair, and any \(\rho>0\) is detected whenever \(\tau\ne0\), \(a\ne\tfrac12\) and \(0<\eta_1<1\). With asymmetric errors the model has 7 parameters,
the just-identified Dawid–Skene case of §7, which has no such constraint.

## 4. Pipeline (`calibrate`)

Input: the \(2^4\) record of \((x_C,v_J,g_1,g_2)\) on \(m\) sealed items. (1) Marginalise over the judge to the label table \((g_1,g_2,x_C)\); run the
constraint check. (2) \(\kappa\)'s, squares, \(\hat\eta_1,\hat\eta_2,\hat a\) by Proposition 2, exact or bracketed. (3) Tabulate the judge note's \(2\times2\)
against \(G_1\): \(a',\varepsilon',w=W_1'/m\). (4) Invert Proposition 2 of the judge note at \(\eta=\hat\eta_1\) (`gold_noise_inverse`, reused) to
\((\hat a,\hat\varepsilon,\hat\varepsilon_1)\); the inverted \(\hat a\) equals the identity's \(\hat a\) on every table with all \(\kappa>0\), since \(\hat d_1\hat d_C=\kappa_{1C}\) exactly.
(5) `expected_table` at the recovered rates, rounded half-up (`rounded_table`), then `independence_p_value` (declared \(\varepsilon\), or the plug-in
flagged), `fisher_p_value`, `ceiling_p_value`, `clopper_pearson_contains`. When \(\hat\eta_1\) is a bracket, every inverted rate is monotone in \(\eta\)
(\(da/d\eta=(2a'-1)/(1-2\eta)^2\), \(d\varepsilon/d\eta=(2\varepsilon'-1)/(1-2\eta)^2\), and the next line), so the bracket ends map to ends and (4)–(5) run at both.

**Sensitivity.** Substituting \(a-\varepsilon=(a'-\varepsilon')/(1-2\eta)\) and \(1-a=(1-a'-\eta)/(1-2\eta)\) into the note's inversion gives one rational function
\(\varepsilon_1(\eta)=\dfrac{w(1-2\eta)-\eta(a'-\varepsilon')}{1-a'-\eta}\) (`inverted_eps1`, equal to the judge module's value on the grid). Numerator and denominator
are affine, so with \(K=w(2a'-1)-(a'-\varepsilon')(1-a')\), free of \(\eta\): \(\dfrac{d\varepsilon_1}{d\eta}=\dfrac{K}{(1-a'-\eta)^2}\) and exactly
\(\varepsilon_1(\eta+\Delta)-\varepsilon_1(\eta)=\dfrac{\Delta K}{(1-a'-\eta)(1-a'-\eta-\Delta)}\) (`eps1_sensitivity`, `eps1_displacement`; checked against direct re-inversion).
At the fixture \(K=-\tfrac{64}{625}\), \(1-a'-\eta=\tfrac4{25}\): **\(d\varepsilon_1/d\eta=-4\)** for the independent judge and \(-\tfrac52\) for the shared one. Overestimating
\(\eta\) by \(\Delta\) lowers \(\hat\varepsilon_1\) by about \(4\Delta\) (more of the wrong-wrong cell is attributed to flips); \(\Delta=\tfrac1{100}\) moves it by exactly
\(-\tfrac{16}{375}\). Chained through the gradient of §2, \(d\varepsilon_1/dA_{G_1G_2}=\tfrac{10}{3}\): a 1-point error in the graders' agreement rate moves \(\hat\varepsilon_1\) by 3.3 points.

Falsifiers of the pipeline: \(G_1\) and \(G_2\) share a rubric or source (conditional independence fails; the constraint check is the test, with no
power at \(\pi=\tfrac12\)); any rater at or below chance (not identified, or the sign convention falsified); the sample touched by the loop
(`measurement_ledger` reused; `calibration_valid` withholds). The tests in step (5) take the corrected counts as given: they are an estimate, not
a sample, so the sampling error of \(\hat\eta_1\) is not in their p-values; §6 gives that error exactly.

## 5. Fixture

\(m=10000\), \(\pi=\tfrac14\), \(a=\tfrac45\), \(\varepsilon=\tfrac1{10}\), \(\eta_1=\tfrac1{10}\), \(\eta_2=\tfrac15\), judges \(\varepsilon_1=\tfrac1{10}\) and \(\tfrac12\). Not \(m=400\): that makes the
\(2\times2\) integral but the smallest raw cell has probability \(\tfrac14\cdot\tfrac15\cdot\tfrac1{10}\cdot\tfrac1{10}\cdot\tfrac15=10^{-4}\); \(10^4\) is the least size at which all sixteen
expected counts are integers. No adjustment to a perfect-square case was needed (§2a). Expected \(2^4\) counts in lexicographic order of
\((x_C,v_J,g_1,g_2)\): independent judge 441, 144, 129, 336, 3889, 976, 441, 144, 976, 259, 144, 171, 144, 171, 336, 1299; shared judge 5, 20, 45, 180,
4325, 1100, 525, 300, 540, 135, 60, 15, 580, 295, 420, 1455. Both marginalise to the label table \((g_1,g_2,x_C)\): 4330, 1120, 1120, 430, 570, 480, 480,
1470, with \(M=(\tfrac25,\tfrac3{10},\tfrac3{10})\), \(\kappa=(\tfrac{12}{25},\tfrac{12}{25},\tfrac9{25})\), \(P=\tfrac{18}{125}=\tfrac25\cdot\tfrac9{25}\): residuals \((0,0,0)\), rank 4, every check passes.
Recovered exactly: \(\hat\eta_1=\tfrac1{10}\), \(\hat\eta_2=\tfrac15\), \(\hat a=\tfrac45\). Measured against \(G_1\): \(a'=\tfrac{37}{50}\), \(\varepsilon'=\tfrac9{50}\) (the judge note's values),
tables \((6500,900,1700,900)\) and \((7300,100,900,1700)\), \(\varepsilon_1'=\tfrac9{26}\) and \(\tfrac{17}{26}\). Inversion at \(\hat\eta_1\): \((\tfrac45,\tfrac1{10},\tfrac1{10})\) and \((\tfrac45,\tfrac1{10},\tfrac12)\).

| judge | corrected \((R_0,R_1,W_0,W_1)\) | (a) \(p\), \(\varepsilon=\tfrac1{10}\) declared | Fisher \(p\) | (b) \(p\) | 95% CP holds \(\varepsilon\) / \(\tfrac12\) | \(d\varepsilon_1/d\eta\) |
|---|---|---|---|---|---|---|
| independent | (7200, 800, 1800, 200) | 0.5109 | 0.5140 | \(<10^{-321}\) | yes / no | \(-4\) |
| maximally shared | (8000, 0, 1000, 1000) | \(<10^{-300}\) | \(<10^{-300}\) | 0.5089 | no / yes | \(-\tfrac52\) |

The corrected tables are the judge note's fixture scaled by 50, with no rounding; exact p-values are in the receipt.

**Dependent grader.** \(G_2\) a copy of \(G_1\) (\(\rho=1\)): residuals \((-\tfrac{27}{250},-\tfrac{27}{250},0)\), check fails; the identity returns \(\hat\eta_1=0\) (the copy
makes gold look perfect), inversion returns the uncorrected \(\hat\varepsilon_1=\tfrac9{26}\approx0.346\) against \(\hat\varepsilon=\tfrac9{50}\), and test (a) on \((2600,900)\) gives
\(p\approx7.6\times10^{-252}\): the independent judge is declared shared. Half a copy (\(\rho=\tfrac12\)): square \(\tfrac{148}{175}\), not perfect;
\(\hat\eta_1\in(\tfrac{2633}{65536},\tfrac{1317}{32768})\approx(0.04018,0.04019)\); \(\hat\varepsilon_1\in(0.27414,0.27417)\); residuals \((-\tfrac{27}{500},-\tfrac{27}{500},0)\). The constraint check is what
stands between a shared rubric and a false finding against A2. *Evidence status.* Propositions 1–3, the inversion and its sensitivity: *algebraic
identity*, cross-checked by enumeration (latent cells; \(2^5\) for the record table) on rational grids. Fixture values, falsifier tables and the
dependent-grader residuals: *finite verified examples*. Nothing is evidence about any grader, judge or controller.

## 6. The sampling law of \(\hat\eta_1\)

On \(m\) items the label table is \(\mathrm{Multinomial}(m;p)\); \(\hat\kappa_{ij}=(2N_{ij}-m)/m\) from the agreement counts, \(\hat S=\hat\kappa_{12}\hat\kappa_{13}/\hat\kappa_{23}\),
\(\hat\eta_1=(1-\sqrt{\hat S})/2\), *defined* iff every \(\hat\kappa>0\) and \(\hat S\le1\). Per item \((I_{12},I_{13},I_{23})\) takes four values only — all agree, or exactly
one pair — with probabilities \(q_{\text{all}}=p(000)+p(111)=\tfrac14(1+\sum\kappa)\) and \(q_{ij}=A_{ij}-q_{\text{all}}\), functions of the \(\kappa\)'s alone: **the law of
\(\hat\eta_1\) is free of the prior** and is the image of a four-category multinomial, enumerated in \(\binom{m+3}{3}\) integer terms (`sampling_law`: weights
over a common denominator \(D^m\), the square's class by integer comparison, its moments grouped by \(\hat\kappa_{23}\), the moments of \(\hat\eta_1\) bracketed
through \(\lfloor2^{16}\sqrt{\hat S}\rfloor\) per outcome). Enumerating all \(\binom{m+7}{7}\) label tables instead (`sampling_law_by_tables`; 245,157 at \(m=16\), 0.7 s)
gives every class probability and moment identically; the reduction reaches \(m=742\) in the receipt (68,638,340 terms; the whole receipt run, with
\(m=400\) too, takes about 7 minutes, almost all of it there). Moments are conditional on the defined event; "within" is
\(\Pr[\text{defined},\ |\hat\eta_1-\eta_1|\le\tfrac1{50}]\). Truth: \(S=\tfrac{16}{25}\), \(\eta_1=\tfrac1{10}\), \(d=(\tfrac45,\tfrac35,\tfrac35)\).

| \(m\) | undefined (sign + range) | \(\hat S\) perfect | within \(\pm0.02\) | \(E\hat S\) | \(m\,\mathrm{Var}\hat S\) | \(E\hat\eta_1\) | \(m\,\mathrm{Var}\hat\eta_1\) |
|---|---|---|---|---|---|---|---|
| 16 | 0.3233 (0.1460 + 0.1774) | 0.1146 | 0.0201 | 0.5517 | 1.017 | 0.1404 | 0.1377 |
| 100 | 0.05615 (0.00014 + 0.05601) | 0.02894 | 0.2769 | 0.6393 | 2.487 | 0.1034 | 0.2535–0.2541 |
| 200 | 0.012236 (\(10^{-7}\) + 0.012236) | 0.01027 | 0.3936 | 0.6479 | 2.994 | 0.09935–0.09936 | 0.2905–0.2917 |
| 400 | 0.000711 (\(10^{-13}\) + 0.000711) | 0.00551 | 0.5350 | 0.6460 | 3.171 | 0.09908–0.09909 | 0.3044–0.3069 |
| 742 | \(6.8\times10^{-6}\) (\(10^{-24}\) + \(6.8\times10^{-6}\)) | \(9.9\times10^{-5}\) | 0.6808 | 0.6433 | 3.125 | 0.09948 | 0.3005–0.3050 |

Exact at \(m=16\): \(\Pr[\text{undefined}]=\tfrac{493351425713175714530369379}{1525878906250000000000000000}\); \(\hat S\) has 43 support points, listed with probabilities in the
receipt. At small \(m\) truncating \(\hat S>1\) biases the square down and the estimate up; the range failure dominates the sign failure from \(m\approx100\).

**Delta method** (`delta_variance`). The indicators' covariance is not diagonal: for any distribution \(\mathrm{Var}\,I_{ij}=(1-\kappa_{ij}^2)/4\) and
\(\mathrm{Cov}(I_{ij},I_{ik})=q_{\text{all}}-A_{ij}A_{ik}=(\kappa_{jk}-\kappa_{ij}\kappa_{ik})/4\), under the model \(d_jd_k(1-d_i^2)/4\) (`agreement_covariance`, checked against the exact
count covariances at \(m=2,3\) over all \(8^m\) sequences). With the gradient per agreement rate \(g=(-1/2d_2,\,-1/2d_3,\,d_1/2d_2d_3)\),
\[m\,\mathrm{Var}\,\hat\eta_1\to V=g^\top\Sigma g=\frac{d_1^2+d_2^2+d_3^2-2d_1^2d_2^2-2d_1^2d_3^2+2d_2^2d_3^2-d_1^2d_2^2d_3^2}{16\,d_2^2d_3^2},\qquad m\,\mathrm{Var}\,\hat S\to16d_1^2V.\]
At the fixture **\(V=\tfrac{2401}{8100}=(\tfrac{49}{90})^2\approx0.2964\)**, \(16d_1^2V=\tfrac{153664}{50625}\approx3.035\). The table's last two columns (\(\hat S\) exact, \(\hat\eta_1\)
through its bracket) rise through these values — truncation depresses the variance at small \(m\) — and sit 1–5% above them at \(m=400\) and
742, the delta variance being first order in \(1/m\) (the receipt check allows 5% at the largest size). **Planning:** the delta s.e. \(\tfrac{49}{90}/\sqrt m<0.02\) from \(m=742\) (`planning_size`); the exact
law there puts 0.6808 of the mass within \(\pm0.02\) (normal: 0.6827). Other points at \(m=200\): \((\tfrac1{20},\tfrac1{10},\tfrac1{10})\): \(V=\tfrac{31489}{409600}\approx0.0769\), \(m^*=193\),
undefined 0.0027, within 0.703; \((\tfrac15,\tfrac14,\tfrac3{10})\): \(V=\tfrac{1351}{1600}\approx0.844\), \(m^*=2111\), undefined 0.0271, within 0.238. The denominator
\(d_2^2d_3^2\): a weak controller makes the gold grader hard to calibrate.

**Exact, conservative** (`disagreement_bound`). Inverting a test of \(\eta_1=\eta_0\) is awkward with \((\pi,\eta_2,a)\) as nuisances; but \(N_{12}\sim\mathrm{Bin}(m,A_{12})\),
\(A_{12}=(1+d_1d_2)/2\), whenever the graders are conditionally independent — no controller, no prior. With the one-sided lower Clopper–Pearson
endpoint \(A_L\) (bisection on an exact integer tail), \(d_1d_2\ge2A_L-1\) at confidence \(1-\alpha\) and, as \(d_2\le1\), \(\eta_1\le1-A_L\), likewise \(\eta_2\). It bounds
each grader from above by the pair's disagreement only, separates nothing, and is tight only for a perfect partner. Fixture (\(1-A_{12}=\tfrac{13}{50}\)):
\(\eta_1\le0.288\) at \(m=742\), \(\le0.267\) at \(m=10000\), against \(\tfrac1{10}\).

## 7. The asymmetric model (two-class Dawid–Skene)

Rater \(i\): false-negative \(\alpha_i=\Pr[X_i=0\mid Y=1]\), false-positive \(\beta_i=\Pr[X_i=1\mid Y=0]\); with \(\pi\), seven parameters on seven degrees of freedom
(`dawid_skene_model`). Write \(s_i=1-\alpha_i\), \(t_i=\beta_i\), \(\delta_i=1-\alpha_i-\beta_i\), \(u=\pi(1-\pi)\); from the table \(p_i=\Pr[X_i=1]\), \(c_{ij}=p_{ij}-p_ip_j\),
\(k_3=E\prod(X_i-p_i)=p_{123}-\sum_ip_ip_{jk}+2p_1p_2p_3\).

**Proposition 4.** \(c_{ij}=u\delta_i\delta_j\), \(k_3=u(1-2\pi)\delta_1\delta_2\delta_3\), so \(R^2:=k_3^2+4c_{12}c_{13}c_{23}=u^2\delta_1^2\delta_2^2\delta_3^2\) and, under \(\delta_1\delta_2\delta_3>0\), with \(\{i,j,k\}=\{1,2,3\}\):
\[\pi=\frac{R-k_3}{2R},\qquad s_i=p_i+\frac{R+k_3}{2c_{jk}},\qquad t_i=p_i-\frac{R-k_3}{2c_{jk}}.\]
*Proof.* \(s_i-p_i=(1-\pi)\delta_i\) and \(t_i-p_i=-\pi\delta_i\) have product \(-u\delta_i^2=-c_{ij}c_{ik}/c_{jk}\) and sum \((1-2\pi)\delta_i=k_3/c_{jk}\): the roots of
\(z^2-(k_3/c_{jk})z-c_{ij}c_{ik}/c_{jk}\), discriminant \(R^2/c_{jk}^2\); and \(u=c_{12}c_{13}c_{23}/R^2\) gives \(1-2\pi=k_3/R\). \(\square\) One root for everything: \(\pi\) is monotone
and each rate affine in \(R\), so a \(2^{-16}\) bracket on \(R\) brackets all seven (`dawid_skene_three_raters`; exact when \(R^2\) is a rational square, always at
expected counts since \(R=u|\delta_1\delta_2\delta_3|\)). Identifiable iff every \(c_{ij}\ne0\) (\(0<\pi<1\), every \(\delta_i\ne0\)) and \(R^2>0\). **Label switching:** \((\pi,\alpha,\beta)\)
and \((1-\pi,1-\beta,1-\alpha)\) give the same table (\(\delta\mapsto-\delta\)); `all_informative` (\(\delta_i>0\): hit rate above false-alarm rate for every rater) needs every
\(c_{ij}>0\) and refuses otherwise; `rater_1_informative` fixes \(\delta_1>0\), puts \(\sigma=\mathrm{sign}\,c_{23}\) in the formulas and recovers an anti-informative \(G_2\)
exactly (\((\alpha_2,\beta_2)=(\tfrac35,\tfrac35)\), \(\delta_2=-\tfrac15\)). Both solutions are returned.

**Fixture.** \(\pi=\tfrac14\), \(\alpha=(\tfrac1{10},\tfrac15,\tfrac1{10})\), \(\beta=(\tfrac15,\tfrac1{10},\tfrac3{10})\) (gold misses 10% of positives, false-alarms on 20% of negatives; the
controller is right on 90% / 70%): \(\delta=(\tfrac7{10},\tfrac7{10},\tfrac35)\), \(c=(\tfrac{147}{1600},\tfrac{63}{800},\tfrac{63}{800})\), \(k_3=\tfrac{441}{16000}\), \(R=\tfrac{441}{8000}\), every parameter exact; so on a
grid of 256 points, and on the symmetric grid the fit returns \(\alpha_i=\beta_i=e_i\), the \(\eta\)'s of §2. The exact Jacobian of \((\pi,\alpha,\beta)\mapsto\) cells (affine in
each parameter, so differences are exact) has rank 7 there and on the symmetric grid (5 with a chance rater): **no degree of freedom is left, no
equality constraint, hence no test of conditional independence** — against the symmetric model's three. Only inequalities remain:
\(p(100)=p(010)=p(001)=\tfrac7{30}\), \(p(011)=p(101)=p(110)=\tfrac1{10}\) has \(R^2=-\tfrac{49}{30000}\), no real point (`outside_model`); and rates must lie in \([0,1]\). The copy
grader of §5 passes both: at \(\rho=1\) the fit is exact and in range — \(\pi=\tfrac3{10}\), \(\alpha_1=\beta_1=\alpha_2=\beta_2=0\), controller \((\tfrac7{20},\tfrac{31}{140})\): two *perfect*
graders and an asymmetric controller — while the symmetric constraints fail; \(\rho=\tfrac12\) likewise (bracketed). The dependence §3 detects is
absorbed as asymmetry. A fixture table with \(\tfrac1{100}\) moved between two cells is bracketed and in range.

**Asymmetric inversion** (`asymmetric_gold_noise_inverse`, `calibrate_asymmetric`). With \(a_y\) the controller's accuracy on class \(y\) (\(1-\alpha_3\), \(1-\beta_3\)),
\(f_y\) the gold flip rate (\(\alpha_1\), \(\beta_1\)), the judge depending on correctness only, measured against \(G_1\): \(a'=\sum_y\pi_y(a_y(1-f_y)+(1-a_y)f_y)\),
\(\varepsilon'=\sum_y\pi_y(f_y+(1-2f_y)(a_y\varepsilon_0+(1-a_y)\varepsilon_1))\), \(w=\sum_y\pi_y((1-a_y)(1-f_y)\varepsilon_1+a_yf_y(1-\varepsilon_0))\). The agreement rate \(\Pr[C=J]\) **is still invariant**:
\(C\oplus F=J\oplus F\) iff \(C=J\), whatever the law of \(F\). Given the fit, \(\varepsilon'\) and \(w\) are affine in \((\varepsilon_0,\varepsilon_1)\): with \(F=\sum\pi_yf_y\), \(E_a=\sum\pi_y(1-2f_y)a_y\),
\(E_b=\sum\pi_y(1-2f_y)(1-a_y)\), \(G_a=\sum\pi_ya_yf_y\), \(G_b=\sum\pi_y(1-a_y)(1-f_y)\), \(\Delta=E_aG_b+E_bG_a\):
\[\varepsilon_1=\frac{E_a(w-G_a)+G_a(\varepsilon'-F)}{\Delta},\qquad\varepsilon_0=\frac{G_b(\varepsilon'-F)-E_b(w-G_a)}{\Delta},\]
\(a=\pi a_1+(1-\pi)a_0\), \(\varepsilon=a\varepsilon_0+(1-a)\varepsilon_1\); \(a'\) is reproduced identically. Symmetric case: \(\Delta=a(1-a)(1-2\eta)\) and the judge note's inversion (checked
on a grid). Record fixture, \(m=4000\) (label table integral; \(a=\tfrac34\), \(\varepsilon=\tfrac1{10}\), judges \(\varepsilon_1=\tfrac1{10}\) and the ceiling \(\tfrac25\)): measured \(a'=\tfrac{67}{100}\),
\(\varepsilon'=\tfrac6{25}\), \(w=\tfrac{27}{200}\) and \(\varepsilon'=\tfrac{237}{1000}\), \(w=\tfrac{417}{2000}\); both judges recovered exactly, corrected \((2700,300,900,100)\) (\(p=0.515\), Fisher 0.521) and
\((3000,0,600,400)\) (\(p<10^{-136}\)). The **symmetric pipeline on the same records** fails its constraints (residuals \((\tfrac{21}{500},\tfrac{21}{200},0)\)), brackets
\(\hat\eta_1\approx0.1634\) (the marginal flip rate is \(\tfrac7{40}\)), inverts to \(\hat\varepsilon_1\approx0.124\) and \(0.418\); the symmetric inversion at the marginal flip rate gives
\(\tfrac5{62}\approx0.081\) and \(\tfrac{239}{620}\approx0.385\): asymmetric gold is misread in both directions, and the constraint check flags it. *Evidence status.*
Proposition 4, the covariance, delta and inversion formulas: *algebraic identity*, enumeration-checked; the laws, fixtures and falsifiers: *finite verified examples*.

## 8. Not delivered

- No observed graders; binary labels only. On real counts the squares and \(R^2\) are not perfect squares: brackets.
- The sampling law is conditional on the defined event; the moments of \(\hat\eta_1\) are brackets, not rationals; no joint interval for
  \((\hat\eta_1,\hat\varepsilon_1)\); the only exact confidence statement is the one-sided disagreement bound, which ignores the controller. No sampling law
  for the Dawid–Skene fit.
- A bracketed Dawid–Skene fit is inverted at both ends of the bracket on \(R\); that brackets \(\hat\varepsilon_1\) only if the inversion is monotone in \(R\), not
  checked. The asymmetric model cannot test conditional independence (a fourth rater or the symmetric restriction is needed), and the symmetric
  check has no power at \(\pi=\tfrac12\).
