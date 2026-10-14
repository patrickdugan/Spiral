# Estimating the gold grader's error with a second grader

Draft 0.4 — 2026-10-14. Closes the boundary of [judge_shared_error_measurement.md](judge_shared_error_measurement.md) §5: Proposition 2 inverts
gold noise at a *known* flip rate \(\eta\); here \(\eta\) is estimated from a second independent grader, exactly. 0.2 added the sampling law of \(\hat\eta_1\) (§6) and the asymmetric
Dawid–Skene model (§7); 0.3 a fourth rater, which makes that model testable (§8), and a joint statement for \((\eta_1,\varepsilon_1)\) (§9). 0.4 takes three items off 0.3's list of what
was not delivered: level-\(\alpha\) tests of the four-rater tetrad on \(m\) items (§10), a confidence interval for \(\varepsilon_1\) with no plug-in (§11), and the monotonicity question for
bracketed Dawid–Skene fits, refuted with an exact witness and replaced by a certified enclosure (§12). Files: `src/spiral_ln/evaluation_gold_calibration.py`,
`tests/test_evaluation_gold_calibration.py` (174 tests), `output/evaluation_gold_calibration/gold_v0_4.json` (75 checks, source hashes, exact fractions, floats under `headline`).
No model, judge or grader was called; every number is a `Fraction` (or an integer bound, §9–§10); the judge module's tails and maps are reused.

```powershell
$env:PYTHONPATH = "src"; python scripts/verify_evaluation_gold_calibration.py --sampling-size 400 --sampling-size 742 --joint-size 4000 --coverage-size 16 --workers 4 --output output/evaluation_gold_calibration/gold_v0_4.json
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
\(m=400\), §9 at 4000 and §10–§12, takes about 10 minutes, most of it there). Moments are conditional on the defined event; "within" is
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

**Proposition 4.** \(c_{ij}=u\delta_i\delta_j\), \(k_3=u(1-2\pi)\delta_1\delta_2\delta_3\), so \(R^2:=k_3^2+4c_{12}c_{13}c_{23}=u^2\delta_1^2\delta_2^2\delta_3^2\) and, under \(0<\pi<1\) and \(\delta_1\delta_2\delta_3>0\) (the first is
implied by the identifiability condition below but is a hypothesis here: it makes \(u>0\) and \(R>0\)), with \(\{i,j,k\}=\{1,2,3\}\):
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
equality constraint, hence no test of conditional independence** — against the symmetric model's three (a fourth rater restores six: §8). Only inequalities remain:
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

## 8. Four raters: the asymmetric model becomes testable

Add a third grader \(G_3\), keep the controller \(C\) as rater 4; the cost is one more independent grading of the same sealed sample. Nine parameters \((\pi,\alpha_i,\beta_i)\) on
15 degrees of freedom (`four_rater_model`); write \(k_S=E\prod_{i\in S}(X_i-p_i)\), \(c_{ij}=k_{ij}\).
**Proposition 5.** \(k_S=\mu_{|S|}\prod_{i\in S}\delta_i\), \(\mu_2=u\), \(\mu_3=u(1-2\pi)\), \(\mu_4=u(1-3u)\). *Proof.* \(E[X_i-p_i\mid Y]=\delta_i(Y-\pi)\); conditional independence multiplies. \(\square\)
Hence six equalities (`four_rater_residuals`): tetrads \(c_{12}c_{34}=c_{13}c_{24}=c_{14}c_{23}\) (each \(u^2\prod\delta\)); ratios \(k_{123}c_{14}=k_{124}c_{13}\), \(k_{123}c_{14}=k_{134}c_{12}\), \(k_{123}c_{24}=k_{234}c_{12}\)
(both sides \(u^2(1-2\pi)\delta_p^2\prod_{q\ne p}\delta_q\), \(p\) the pivot); and \((k_{1234}-c_{12}c_{34})c_{12}=k_{123}k_{124}\), as \(\mu_4-u^2=u(1-2\pi)^2\). The other nine ratio relations follow (`ratio_relations`).
**Proposition 6 (exactly six).** (a) The \(16\times9\) parameter Jacobian has rank 9 wherever \(0<\pi<1\) and three \(\delta_i\ne0\): Proposition 4 on that triple with \(\delta_4=c_{14}/(u\delta_1)\),
\(1-\alpha_4=p_4+(1-\pi)\delta_4\), \(\beta_4=p_4-\pi\delta_4\) is a smooth left inverse. (b) The residuals' \(6\times15\) Jacobian in the centred moments (coordinates on the simplex) has rank 6
wherever \(c_{12}c_{13}\ne0\), model or not: with each equality written as left minus right and the rows in the order (\(c_{13}c_{24}-c_{14}c_{23}\), \(c_{12}c_{34}-c_{13}c_{24}\),
the three ratios as listed, the fourth-moment relation), the minor on \((c_{24},c_{34},k_{124},k_{134},k_{234},k_{1234})\) is lower triangular with diagonal \((c_{13},c_{12},-c_{13},-c_{12},-c_{12},c_{12})\) and
determinant \(-c_{12}^4c_{13}^2\) (with the two tetrads swapped it is \(+c_{12}^4c_{13}^2\); the rank is the same). So near an identified model
point the nine-dimensional image is the zero set of six independent functions. \(\square\) Both ranks are also computed exactly on 243 grid points; moments match the \(2^5\) latent
enumeration on 1024. **Test** (`four_rater_constraints`): with every \(c_{ij}\ne0\), a table is in the model iff the residuals vanish and the triple fits exist with all nine rates in
\([0,1]\) (triple \((1,2,3)\) fixes \(\pi\) and three raters, \(c_{14},p_4\) rater 4, the equalities the remaining six moments; the four fits must agree; exact fits are rebuilt cell by cell).
A chance rater keeps rank 9 but zeroes three covariances: the residuals degenerate (rank 4 with \(G_2\) at chance, 6 with \(C\)) and the test refuses; two chance raters lower the rank.
**Fixture.** \(\pi=\tfrac14\); \((\alpha,\beta)\): \(G_1\) \((\tfrac1{10},\tfrac15)\), \(G_2\) \((\tfrac15,\tfrac1{10})\), \(G_3\) \((\tfrac15,\tfrac25)\), \(C\) \((\tfrac1{10},\tfrac3{10})\); \(\delta=(\tfrac7{10},\tfrac7{10},\tfrac25,\tfrac35)\). Counts at \(m=10000\) (lexicographic
in \(x_1..x_4\)): 2269, 981, 1516, 684, 256, 144, 184, 216, 576, 324, 414, 486, 99, 351, 186, 1314. \(c_{12}c_{34}=\tfrac{1323}{320000}\), \(k_{123}=\tfrac{147}{8000}\), \(k_{1234}=\tfrac{3087}{320000}\);
residuals zero, ranks 6 and 9, all nine parameters recovered exactly on every triple (\(R=u|\delta_i\delta_j\delta_k|\) is rational). An anti-informative \(G_2\) needs `rater_1_informative`.
**Copying grader.** If \(G_2\) copies \(G_1\) with probability \(\rho\), \(\mathrm{Cov}(X_1,X_2\mid Y)=\rho\,\mathrm{Var}(X_1\mid Y)\): \(c_{12}=u\delta_1\tilde\delta_2+\rho V_1\), \(V_1=\pi\alpha_1(1-\alpha_1)+(1-\pi)\beta_1(1-\beta_1)\),
\(\tilde\delta_2=\rho\delta_1+(1-\rho)\delta_2\), the other covariances keep product form, so **\(c_{12}c_{34}-c_{13}c_{24}=\rho V_1c_{34}\)** and \(c_{13}c_{24}=c_{14}c_{23}\) (`copy_grader_tetrad_residual`; exact on
24 cells). Fixture: \(V_1=\tfrac{57}{400}\), \(c_{34}=\tfrac9{200}\), residual \(\tfrac{513}{80000}\rho\). Witness at \(\rho=1\), \(m=10000\): 2525, 1125, 1700, 900, eight zeros, 675, 675, 600, 1800; its triple
\((G_1,G_2,G_3)\) fits exactly and in range (\(\pi=\tfrac38\), two perfect graders: §7's absorption), four raters reject it (residual \(\tfrac{513}{80000}\), triple fits inconsistent). Any \(\rho>0\) is
detected when \(V_1>0\), \(0<\pi<1\), \(\delta_3\delta_4\ne0\), **at \(\pi=\tfrac12\) too**, where §3's check is vacuous. The odd product names the split \(\{1,2\mid3,4\}\), not the dependent side.
*Evidence status.* Propositions 5–6, the converse, the residual: *algebraic identities*, enumeration-checked; fixtures: *finite verified examples*. All are population identities:
on observed counts the residuals never vanish exactly; §10 tests the first tetrad at level \(\alpha\) on \(m\) items.

## 9. A joint statement for \((\eta_1,\varepsilon_1)\)

`joint_statement(record, alpha, grid)`, symmetric model, withheld when §3's check fails. (1) \(H\) = grid points \(\eta_0\) kept by (a) the disagreement bound at level \(\alpha/2\) (exact)
and (b) the two-sided test of the observed square at \(\alpha/2\): \(p(\eta_0)=\min(1,2\min(\Pr[\tilde S\le\hat s],\Pr[\tilde S\ge\hat s]))\) under §6's law at \((\eta_0,\hat\eta_2,1-\hat a)\), \(\tilde S\) putting
sign failures below every square and range failures above. (2) At each \(\eta_0\in H\): §4's inversion (clamped into the feasible range, flagged), the exact ceiling and independence
tests and the two-sided level-\(\alpha\) Clopper–Pearson bracket on the corrected counts. (3) **If \(\eta_1\) is a grid point, with probability \(\ge1-2\alpha\) (Bonferroni) \(\eta_1\in H\) and
\(\varepsilon_1\in\bigcup_H\mathrm{CP}(\eta_0)\)**: exactly for (1a), else under two plug-ins: (1b) fixes \(\eta_2,a\) at their estimates (their error is not propagated), (2) treats the corrected
counts as a binomial sample, as §4 does. The sampling law of \(\hat\varepsilon_1\) is not derived.
*Tails.* Given \(\mathrm{rest}=k_{12}+k_{13}\), \(d=m-2\,\mathrm{rest}\) is fixed and \(ab\le\hat s\,md\) is two tails in \(k_{12}\): `square_tail_law` sums prefix sums, \(O(m^2)\) big-integer products (about 270 s a
point at \(m=4000\)), equal to the label-table enumeration at \(m=16\). `square_tail_bracket` bounds the same tails in integers: the law factors into \(\mathrm{Bin}(m,q_{12}+q_{13})\), \(\mathrm{Bin}(m-\mathrm{rest},\cdot)\),
\(\mathrm{Bin}(\mathrm{rest},\cdot)\); each pmf is floored and ceiled at \(2^{-160}\) outward from its exact mode (ratios \(\le1\)), terms below \(2^{-128}\) are bounded in bulk. The bracket holds the exact law
on nine cases up to \(m=742\), is narrower than \(10^{-34}\), takes 3 s a point at \(m=4000\); one straddling the level would fall back to the exact law (never needed). *Counts.* Rounding the
\(N_{ij}\) separately can break the parity \(\sum N_{ij}\equiv m\) (at 742: 549, 549, 505, which no table has); `agreement_counts` rounds the four pattern counts by largest remainder: (549, 549, 504),
\(\hat s=\tfrac{31684}{49343}\approx0.6421\); at 4000 (2960, 2960, 2720), \(\hat s=\tfrac{16}{25}\). Grid \(k/100\), \(\alpha=\tfrac1{20}\), \(\varepsilon=\tfrac1{10}\) declared:

| \(m\) | \(H\) | independent judge: \(\varepsilon_1\in\) | shared judge: \(\varepsilon_1\in\) | ranges | tests, jointly |
|---|---|---|---|---|---|
| 742 | 0.06–0.14 (9 points) | [0, 0.2970] | [0.2509, 0.6553] | overlap on [0.251, 0.297] | separate |
| 4000 | 0.09–0.12 (4 points) | [0.0030, 0.1629] | [0.3927, 0.5580] | disjoint | separate |

"Separate": at every \(\eta_0\in H\) the ceiling test rejects for the independent judge (\(p\le2.8\times10^{-13}\) at 742) and the independence test for the shared one (\(p\le1.7\times10^{-12}\)),
while neither is rejected under its own hypothesis everywhere (at 742: independence at 0.06–0.08, ceiling at 0.13–0.14). **At the planning size the judges separate jointly by the
tests but not by the \(\varepsilon_1\) ranges**; at 4000 by both. The overlap comes from the ends of \(H\) (\(\hat\varepsilon_1=\tfrac13\) for the shared judge at 0.14, 0.228 for the independent one
at 0.06). With the disagreement bound alone (\(\eta_0\le0.288\) at level \(\alpha\)) the set passes \(1-a'=0.26\), where the inversion implies a perfect controller: \(\varepsilon_1\) undetermined. §7's
asymmetric record is withheld. *Evidence status:* coverage is a theorem given the plug-ins; the sets, ranges and p-values are *finite verified examples*. §11 shows the second
plug-in is far from harmless (the binomial on corrected counts understates the first-order variance of \(\hat\varepsilon_1\) 7.7-fold for the independent judge) and gives an interval
that needs neither.

## 10. Level-\(\alpha\) tests of the tetrad on \(m\) items

The first tetrad of §8, \(\tau=c_{12}c_{34}-c_{13}c_{24}\), is the one copying breaks. On four items \(i,j,k,l\) write \(D_a(ij)=x_{ai}-x_{aj}\) and, for the split \(\{ij\mid kl\}\),
\(\Delta_{ab}=D_a(ij)D_b(kl)-D_a(kl)D_b(ij)\). The integer kernel \(K=\sum_{\text{3 splits}}\Delta_{14}\Delta_{23}\) (`tetrad_kernel`, all \(16^4\) quadruples) is the symmetrised
\(g_{12}g_{34}-g_{13}g_{24}\), \(g_{ab}(x,y)=(x_a-y_a)(x_b-y_b)/2\), times 24: expanding the two determinants gives the eight orderings of a split, so \(E K=24\tau\) for *every* law.
By exhaustion \(\max|K|=4\). Under the model, given the four latent classes, \(E[D_a(ij)\mid Y]=\delta_a(Y_i-Y_j)\), so each determinant has conditional mean
\(\delta_a\delta_b\big((Y_i-Y_j)(Y_k-Y_l)-(Y_k-Y_l)(Y_i-Y_j)\big)=0\), and the two involve disjoint raters: every split term is a product of two conditionally independent
mean-zero factors. The unbiased U-statistic \(U_m\) is computed from the sixteen counts in \(O(16^2)\) (`tetrad_u_statistic`; equal to the average over ordered 4-tuples on random
item lists); \(\mathrm{Var}\,U_m=\sum_c\binom4c\binom{m-4}{4-c}\binom m4^{-1}\zeta_c\) (Hoeffding 1948, *cited*), with the \(\zeta_c\) exact by marginalising \(K\) item by item
(`tetrad_moments`; enumeration of all \(\binom{m+15}{15}\) tables reproduces \(E U_m\) and \(\mathrm{Var}\,U_m\) exactly at \(m=4,5\) for a non-model table and at \(m=6\), 54,264 tables,
for the fixture and its \(\rho=1\) copy).

**Proposition 7 (the influence function factorises).** Under the four-rater model, with \(Y_a=x_a-p_a\),
\(c_{34}\varphi_{12}+c_{12}\varphi_{34}-c_{24}\varphi_{13}-c_{13}\varphi_{24}=u(\delta_4Y_1-\delta_1Y_4)(\delta_3Y_2-\delta_2Y_3)\), \(\varphi_{ab}=Y_aY_b-c_{ab}\), and
\(\delta_4Y_1-\delta_1Y_4=\delta_4\varepsilon_1-\delta_1\varepsilon_4\) with \(\varepsilon_a=x_a-E[x_a\mid Y]\). Hence
\(16\zeta_1=\mathrm{Var\,IF}=u^2E\big[(\delta_4^2v_1+\delta_1^2v_4)(\delta_3^2v_2+\delta_2^2v_3)\big]\), \(v_a=\mathrm{Var}(x_a\mid Y)\). *Proof.* Group the four products as
\(Y_1(\cdot)+Y_4(\cdot)\); the constants cancel because \(\tau=0\); the latent part \(\delta_a(Y-\pi)\) cancels in each factor; the factors are conditionally independent with mean
zero. \(\square\) (`tetrad_influence_variance`; cell by cell at two points, and \(16\zeta_1\) equal to it on 52 grid points including a chance, an anti-informative, a near-perfect and
a balanced-prior point.) Fixture: \(16\zeta_1=\tfrac{321813}{512000000}\approx6.285\times10^{-4}\); \(m\,\mathrm{Var}\,U_m=6.356\times10^{-4}\) at 742 (1.1% above first order),
\(6.299\times10^{-4}\) at 4000.

**Proposition 8 (a variance bound for every null point of a region).** Let \(g(\delta)=\tfrac14\) for \(|\delta|\le\tfrac12\), else \(|\delta|(1-|\delta|)\); then \(v_a(y)\le g(\delta_a)\).
With \(h_{14}=\delta_4^2g(\delta_1)+\delta_1^2g(\delta_4)\le\min(A/4,\tfrac14)\), \(A=\delta_1^2+\delta_4^2\), likewise \(h_{23}\) with \(B=\delta_2^2+\delta_3^2\), and \(w_c\) Hoeffding's weights,
\[\mathrm{Var}\,U_m\le w_1\frac{u^2h_{14}h_{23}}{16}+\Big(\frac{w_2}2+\frac{3w_3}4+w_4\Big)\frac{\tfrac14+4u(h_{14}+h_{23})+16h_{14}h_{23}(u+2u^2)}{64}.\]
*Proof.* The first term is Proposition 7 with \(v\le g\). \(\zeta_c/c\) is non-decreasing (Hoeffding 1948; Serfling 1980, Lemma 5.2.1A: *cited*), so \(\zeta_2,\zeta_3\le\tfrac24\zeta_4,\tfrac34\zeta_4\).
\(\zeta_4=E h^2\le E H^2\) for one split term \(H=\Delta_{14}\Delta_{23}/8\) (Cauchy–Schwarz over the three); given the classes the determinants are independent and
\(E[\Delta_{14}^2\mid Y]=V_1(ij)V_4(kl)+V_1(kl)V_4(ij)+\delta_4^2(V_1(ij)e_{kl}+V_1(kl)e_{ij})+\delta_1^2(V_4(kl)e_{ij}+V_4(ij)e_{kl})\le\tfrac12+2h_{14}e\), with \(V_a(ij)=v_a(Y_i)+v_a(Y_j)\),
\(e_{ij}=[Y_i\ne Y_j]\), \(e=e_{ij}+e_{kl}\), \(Ee=4u\), \(Ee^2=4u+8u^2\). \(\sup_{[0,1]^2}y^2g(x)+x^2g(y)=\tfrac14\) (three cases; the last is \(p(s-2p)\le p(1-p)\) with \(p=xy\), \(s\le1+p\)).
The bound increases in \(u,h_{14},h_{23}\). \(\square\) (`tetrad_variance_bound`; exact \(\mathrm{Var}\,U_m\) below the point bound below the region bounds on all 52 grid points at
\(m=6,742,4000\).) **Every four-rater model** is the region \((u,A,B)\le(\tfrac14,2,2)\): \(\zeta_1\le\tfrac1{4096}\), \(\zeta_4\le\tfrac9{512}\). The fixture region
\((u,A,B)\le(\tfrac3{16},\tfrac{17}{20},\tfrac{13}{20})\) — prior at least \(\tfrac14\) from \(\tfrac12\), the two sums of squared discriminations no larger than the fixture's — gives \(\tfrac{1989}{26214400}\) and \(\tfrac{34493}{3276800}\).
\(m\) times the bounds: universal 0.00471 / 0.00406 / 0.00397 at 742 / 4000 / 10000; fixture region 0.00171 / 0.00131 / 0.00125; exact 0.00064 / 0.00063 / 0.00063.

**Test A** (`tetrad_cantelli_test`). Reject when \(U_m\ge t\), \(t\ge\sqrt{\bar V(1-\alpha)/\alpha}\) (Cantelli; the copying direction when \(c_{34}>0\)), or \(|U_m|\ge t\), \(t\ge\sqrt{\bar V/\alpha}\)
(Chebyshev); \(\bar V\) the region's bound, \(t\) rounded up to \(2^{-32}\). **Size \(\le\alpha\) at every null point of the region — a theorem; with the universal region, at every
parameter of the four-rater model**, informative or not, any prior. One-sided \(t\) at \(\alpha=\tfrac1{20}\): universal 0.01098 / 0.00439 / 0.00275, fixture region 0.00662 / 0.00249 / 0.00154.
Exactly at \(m=6\) the rejection probability of all four variants is 0 (the bound is far from tight). On the integral \(m=10^4\) tables: \(U=0\) for the fixture (accepted),
\(U=\tfrac{35625}{5553889}\approx0.00641\) for the \(\rho=1\) witness of §8 (rejected by all four). Power is bounded below by Cantelli at the alternative with the exact
\(\mathrm{Var}\,U_m\) there (`tetrad_cantelli_power_bound`), zero when \(\tau\le t\).

**Test B** (`tetrad_sign_test`), exact and nuisance-free. Blocks of four consecutive items; \(Z=\mathrm{sign}(K)\) when an independent uniform \(U\in\{0,1,2,3\}\) is below \(|K|\), else 0.
Then \(EZ=EK/4=6\tau\): whenever the tetrad vanishes, \(P(Z=1)=P(Z=-1)\) (`tetrad_sign_block_law`, exact over the \(16^4\) quadruples; symmetric on all 52 grid points), so given
\(N\) nonzero blocks \(N_+\sim\mathrm{Bin}(N,\tfrac12)\) and rejecting at \(N_+\ge c(N)\), \(c(N)\) the smallest cut with \(P(\mathrm{Bin}(N,\tfrac12)\ge c)\le\alpha\) (`sign_test_critical_value`, exact),
has **size \(\le\alpha\) for every law with \(\tau=0\): every four-rater parameter, no region, no plug-in — a theorem**, randomized only through the external uniforms. Exact attained
size at the fixture (`sign_test_rejection_probability`: a finite sum to 300 blocks, a fixed-point bracket narrower than \(10^{-35}\) above): 0.0312 / 0.0398 / 0.0437 (one-sided).

Power against the copying grader at the §8 fixture, \(\alpha=\tfrac1{20}\), one-sided (sign test exact; Cantelli rigorous lower bounds; last column \(m\tau^2/16\zeta_1\), the squared
noncentrality of the efficient but only asymptotically valid studentised test):

| \(m\) | \(\rho\) | \(\tau\) | sign test | Test A universal \(\ge\) | Test A fixture region \(\ge\) | \(m\tau^2/16\zeta_1\) |
|---|---|---|---|---|---|---|
| 742 | 1/4, 1/2, 3/4, 1 | \(\tfrac{513}{80000}\rho\) | 0.074, 0.140, 0.227, 0.326 | 0, 0, 0, 0 | 0, 0, 0, 0 | 3.0, 12.1, 27.3, 48.5 |
| 4000 | same | | 0.212, 0.519, 0.788, 0.930 | 0, 0, 0.242, 0.844 | 0, 0.570, 0.907, 0.953 | 16.4, 65.4, 147, 262 |
| 10000 | same | | 0.417, 0.869, 0.990, 0.9996 | 0, 0.579, 0.951, 0.978 | 0.036, 0.947, 0.980, 0.987 | 40.9, 164, 368, 654 |

Two-sided sign test at 4000: 0.134, 0.394, 0.687, 0.877. Per item the sign test's noncentrality is \(9\tau^2/P_0(Z\ne0)\) against the U-statistic's \(\tau^2/16\zeta_1\):
the ratio \(144\zeta_1/P_0(Z\ne0)=\tfrac{558703125}{9045033248}\approx\tfrac1{16.2}\) — **the exact test needs about sixteen times the items of the asymptotic one**; Test A
pays instead through the slack of \(\bar V\) and of Cantelli's inequality. Of the two tests valid at every parameter the sign test is the stronger in every cell; the
region-restricted Test A's lower bound beats it at 4000 for \(\rho\ge\tfrac12\) and at 10000 for \(\rho=\tfrac12\). At the planning
size 742 no test here has useful power against copying; at 4000 the exact sign test has 0.93 at \(\rho=1\) and 0.52 at \(\rho=\tfrac12\). Not attempted: a likelihood-ratio test
calibrated by enumeration — its size is a supremum over a nine-dimensional nuisance, and enumeration gives it only at points. *Evidence status.* Propositions 7–8, the kernel's
unbiasedness and the sign-test symmetry: *algebraic identities* (with the cited U-statistic facts); \(\max|K|=4\): exhaustive; sizes and powers: *finite verified examples*;
size control: proven for every parameter (Test B; Test A universal) or every point of the stated region (Test A), not checked on a grid.

## 11. \(\varepsilon_1\) with no plug-in

§9's statement fixes \(\eta_2\) and \(a\) at estimates in (1b) and treats the corrected counts as a binomial sample in (2). **The second is badly anti-conservative.** With
\(\hat\varepsilon_1=f(\hat\eta_1,\hat a',\hat\varepsilon',\hat w)\) and \(\hat\eta_1\) from the same record (\(a'=A_{13}\) enters twice), the first-order variance over the sixteen record
cells (`eps1_delta_variance`, exact since \(d_1\) is rational) is, per item, at the §5 fixture:

| judge | \(m\,\mathrm{Var}\,\hat\varepsilon_1\) | \(\eta\) known | \(\eta\)-only \(=(d\varepsilon_1/d\eta)^2V\) | \(2\,\)cov | binomial on corrected counts, \(\varepsilon_1(1-\varepsilon_1)/(1-a)\) |
|---|---|---|---|---|---|
| independent | \(\tfrac{1798393}{518400}\approx3.47\) | \(\tfrac{657}{256}\approx2.57\) | \(16\cdot\tfrac{2401}{8100}\approx4.74\) | \(-3.84\) | \(\tfrac9{20}=0.45\) |
| maximally shared | \(\tfrac{51457}{20736}\approx2.48\) | \(\tfrac{545}{256}\approx2.13\) | \(\tfrac{2401}{1296}\approx1.85\) | \(-1.5\) | \(\tfrac54\) |

The binomial understates by 7.7× and 2.0×; even with \(\eta\) known the measured counts' noise, amplified by the inversion (\(\partial\varepsilon_1/\partial w=(1-2\eta)/(1-a'-\eta)=5\)), is 5.7× and 1.7×.

**Proposition 9 (an interval with proven coverage).** Six counts are binomial given others: \(\mathrm{rest}=m-N_{23}\sim\mathrm{Bin}(m,\theta_1)\), \(\theta_1=(1-\kappa_{23})/2\);
\(k_{12}\mid\mathrm{rest}\sim\mathrm{Bin}(\mathrm{rest},\theta_2)\), \(2\theta_2-1=(\kappa_{12}-\kappa_{13})/(1-\kappa_{23})\); \(k_{\rm all}\mid\mathrm{rest}\sim\mathrm{Bin}(m-\mathrm{rest},\theta_3)\),
\(2\theta_3-1=(\kappa_{12}+\kappa_{13})/(1+\kappa_{23})\) (§6's four-pattern multinomial, factorised); \(N_{13}\sim\mathrm{Bin}(m,a')\); and the judge's errors on the measured-right and
measured-wrong items, binomial given \(N_{13}\) at \(\varepsilon_0',\varepsilon_1'\). Clopper–Pearson intervals at levels summing to \(\alpha\) (Clopper–Pearson 1934, *cited*; brackets rounded
outward) cover all six with probability \(\ge1-\alpha\). On that event, with \(A=(2\theta_3-1)^2\), \(B=(2\theta_2-1)^2\), \(\kappa=\kappa_{23}\in(0,1)\):
\(S=d_1^2=\tfrac14(A-B)(\kappa+\kappa^{-1})+\tfrac12(A+B)\) is monotone in each of \(A,B,\kappa\) (\(\partial_\kappa S=\tfrac14(A-B)(1-\kappa^{-2})\)), so it lies between its eight corner values
and \(\eta_1=(1-\sqrt S)/2\) in the root-bracketed range; and
\(\varepsilon_1=\dfrac{(1-a')\varepsilon_1'(1-\eta)-\eta a'(1-\varepsilon_0')}{1-a'-\eta}\) is Möbius in \(\eta\) and in \(a'\) and affine with nonnegative coefficients in \(\varepsilon_0',\varepsilon_1'\), hence
monotone in each coordinate where \(1-a'-\eta>0\): it lies between its sixteen corner values. **Coverage \(\ge1-\alpha\) at every parameter of the symmetric model** (raters
conditionally independent and better than chance, gold flips independent of controller and judge) — a theorem; no plug-in, no grid, and \(1-\alpha\) rather than §9's \(1-2\alpha\).
(`eps1_confidence_interval`; random points of the box stay inside the corner ranges. When \(\kappa_{23}\) or \(2\theta_3-1\) can reach 0, or the box reaches \(1-a'-\eta\le0\), it
returns \([0,1]\).) Exact coverage by enumerating the \(\binom{m+7}{7}\) tables of (agreement pattern, judge wrong) that determine it (`eps1_interval_coverage`): at \(m=8,12,16\)
the interval covers with probability 1 (it is \([0,1]\) or nearly) and all six intervals jointly with 0.9952 / 0.9908 / 0.9889 (independent judge) and 0.9943 / 0.9920 / 0.9906 (shared).

Fixture, \(\alpha=\tfrac1{20}\) split equally, records rounded to counts by largest remainder (`rounded_record`):

| \(m\) | \(\eta_1\in\) | independent judge \(\varepsilon_1\in\) | shared judge \(\varepsilon_1\in\) | §9 (coverage 0.9, plug-ins) |
|---|---|---|---|---|
| 742 | [0.018, 0.170] | [0, 0.432] | [0, 0.734] | [0, 0.297] / [0.251, 0.655] |
| 4000 | [0.068, 0.130] | [0, 0.2756] | [0.2794, 0.6256] | [0.003, 0.163] / [0.393, 0.558] |
| 10000 | [0.080, 0.119] | [0, 0.220] | [0.379, 0.586] | — |

**The judges separate by the plug-in-free intervals from 4000 items** (by a margin of 0.004), not at 742. The interval is wider than §9's because §9's second plug-in was
too narrow, not only because of the union bound. *Evidence status.* Proposition 9 and the delta variance: *algebraic identity* plus the cited exactness of Clopper–Pearson; the
intervals, coverages and variances: *finite verified examples*. The sampling law of \(\hat\varepsilon_1\) itself is still not derived; the interval does not need it.

## 12. Monotonicity of the asymmetric inversion in the Dawid–Skene root

Every fitted rate is affine in \(R\) and \(\pi=(R-\sigma k_3)/2R\), so with \(P_1=2R\pi\), \(P_0=2R(1-\pi)\) the class-weighted sums of §7 are cubics over \(2R\) and
\(\varepsilon_1(R)=\dfrac{e_a(2Rw-g_a)+g_a(2R\varepsilon'-f)}{e_ag_b+e_bg_a}\), a ratio of polynomials of degree at most six; at the §7 records the degrees are (6, 5), the derivative's
numerator \(D=N'Q-NQ'\) degree 10 (`asymmetric_eps1_rational`; equal to `asymmetric_gold_noise_inverse` at \(0.9R^*,R^*,1.1R^*\)). Sturm sequences in exact rationals count \(D\)'s
roots on any interval (`sturm_root_count`), and the sign of a polynomial at \(\sqrt r\) is decided exactly by reducing to \(A+B\sqrt r\) (`sign_at_square_root`).

- **Where it holds.** At both §7 records \(D\) has no root on the whole in-range interval \(R\in[\tfrac{441}{16000},\tfrac{567}{8000}]\) (\(R^*=\tfrac{441}{8000}\)): monotone there. The same
  records rounded at \(m=742\) give bracketed fits, certified monotone on their brackets.
- **Refuted in general** (`witness_record`). Dawid–Skene table \(\pi=\tfrac{19}{50}\), \(\alpha=(\tfrac3{10},\tfrac3{25},\tfrac1{50})\), \(\beta=(\tfrac{29}{100},\tfrac1{10},\tfrac2{25})\), with \(\tfrac1{200}\)
  moved from cell \((0,0,0)\) to \((0,0,1)\): \(R^{*2}=\tfrac{278331210135729}{62500000000000000}\), irrational root, fit in range, bracket \([\tfrac{4373}{65536},\tfrac{2187}{32768}]\). A judge whose
  verdict depends on measured correctness only, \(\varepsilon'=\tfrac{47}{100}\), \(w=\tfrac{28287}{187598}\) (the exact zero of \(D\) at the bracket's midpoint, linear in \(w\), rounded to
  denominator \(\le10^6\)). \(D\) has one root inside the bracket (two on the in-range interval); the inversions at the bracket ends, 0.0202800657139 and 0.0202800657332, are
  **both above** \(\hat\varepsilon_1=\varepsilon_1(R^*)\) (exact signs). The judge is informative: \((\varepsilon_0,\varepsilon_1)\approx(0.456,0.020)\) at both ends. The miss is about \(10^{-8}\), second order in the
  bracket width — immaterial numerically, but the claimed bracket is false.
- **The fix** (`asymmetric_eps1_enclosure`, now in `calibrate_asymmetric` as `eps1_enclosure`). No root of \(D\) in the bracket: the end values bracket \(\hat\varepsilon_1\) (status
  `monotone`). Otherwise bisect on Sturm counts: root-free pieces contribute their end values; a piece still holding a root after 60 halvings contributes its end values widened by
  \(Lw\), \(L\ge\max|D|/\min Q^2\) from absolute coefficients. The witness's certified enclosure \([0.02028005419,0.02028006573]\) contains \(\hat\varepsilon_1\) (exact signs).

*Evidence status.* The rational form and the enclosure's validity: *algebraic identity* (Sturm's theorem *cited*); monotonicity at the §7 records and its failure at the witness:
*finite verified examples*. Whether a critical point inside a bracket needs an implausible judge is open; the witness's judge rejects 46% of right answers.

## 13. Not delivered

- No observed graders; binary labels only.
- §10's tests are valid but weak at the planning size: none has useful power against copying at 742 items. Test A's size bound is far from tight (exact size 0 at \(m=6\)); the
  efficient studentised tetrad test is only asymptotically valid and its exact size at planning sizes is not computed. Only the first tetrad is tested; the other five equalities
  of §8 and a joint test of all six are not.
- The sampling law of \(\hat\varepsilon_1\) and of the three- or four-rater fits is not derived (§11 gives a first-order variance and an interval that does not need the law). §6's
  law is conditional on the defined event. §11 is for the symmetric model; the asymmetric analogue would propagate a confidence set for \(R\) through a non-monotone map (§12).
- The four-rater test refuses a chance rater though the model stays locally identified; three raters cannot test conditional independence; §3's check has no power at \(\pi=\tfrac12\).
