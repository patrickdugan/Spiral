# Measuring the judge's shared error on a sealed sample

Draft 0.1 — 2026-10-13. Delivers the last bullet of [rl_training_signal_limits.md](rl_training_signal_limits.md)
§6: a measurement procedure for \(\varepsilon_1\), the judge's error rate on items the controller gets
wrong, with exact inference. Axiom A2 there is falsified by a measured \(\varepsilon_1>\varepsilon\); L4
says the ceiling \(1-\varepsilon\) is reached without memorization exactly when \(\varepsilon_1\ge\tfrac12\).
Files: `src/spiral_ln/evaluation_judge_measurement.py`, `tests/test_evaluation_judge_measurement.py`
(58 tests), `output/evaluation_judge_measurement/judge_v0_1.json` (19 checks, source hashes, exact
fractions, floats under `headline`). No model was called; nothing here is evidence about any judge or
controller. Every number is a `Fraction`; binomial and hypergeometric tails are finite sums, so every
p-value and power figure is exact. Evidence levels follow the calculus card (§11).

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_judge_measurement.py --output output/evaluation_judge_measurement/judge_v0_1.json
python -m pytest tests/test_evaluation_judge_measurement.py -q
```

## 1. Procedure

1. Draw \(m\) items with gold labels from a source independent of both controller and judge
   (ground truth, or a third grader); declare the sample a sealed readout set in the feedback
   ledger (`EvalSet(role="readout", access="sealed")`), readout budget one.
2. Run controller and judge on it; read it once (`LoopEvent("readout")`).
3. Tabulate (controller right/wrong against gold) \(\times\) (judge right/wrong against gold):
   counts \(R_0,R_1,W_0,W_1\) (`JudgeTable`); \(W=W_0+W_1\).
4. Estimate \(\hat a=(R_0+R_1)/m\), \(\hat\varepsilon=(R_1+W_1)/m\), \(\hat\varepsilon_0=R_1/(R_0+R_1)\),
   \(\hat\varepsilon_1=W_1/W\) (`table_estimates`); run the exact tests of §3 on \((W,W_1)\).
5. Publish the card item of §8. `audit_ledger` withholds the measurement (`not_evaluated`) if the
   sample was read twice or any score or item from it reached the loop.

## 2. Bookkeeping identity

With binary labels a judge wrong about a wrong answer marks it correct and agrees with the controller; the agreement rate is \((R_0+W_1)/m\).

**Proposition 1.** \((R_0+W_1)/m=\hat a-\hat\varepsilon+2(1-\hat a)\hat\varepsilon_1\) for every table.
*Proof.* \(\hat a-\hat\varepsilon=(R_0+R_1-R_1-W_1)/m=(R_0-W_1)/m\) and \(2(1-\hat a)\hat\varepsilon_1
=2(W/m)(W_1/W)=2W_1/m\); add. For \(W=0\) the last term is \(2W_1/m=0\). \(\square\) *Evidence status:
algebraic identity*, checked on all \(5^4-1\) tables with cells in \(0..4\). At expected counts it is
L4's \(a-\varepsilon+2(1-a)\varepsilon_1\) (`observed_accuracy_shared`), and
\(2(1-\hat a)(\hat\varepsilon_1-\hat\varepsilon)\) is the plug-in inflation (`judge_correlation_inflation`).

## 3. Exact inference on the conditional count

Given \(W\), \(W_1\sim\mathrm{Bin}(W,\varepsilon_1)\). Tails are exact rationals (`binomial_upper_tail`,
`binomial_lower_tail`; cross-checked against enumeration of all \(2^W\) outcomes for \(W\le6\)).

- **(a) Independence**, \(H_0:\varepsilon_1=\varepsilon\) against \(\varepsilon_1>\varepsilon\):
  \(p=\Pr[\mathrm{Bin}(W,\varepsilon)\ge W_1]\) (`independence_p_value`), with \(\varepsilon\) declared
  from a source other than this table. With \(\hat\varepsilon\) from the same table it is a plug-in;
  then use **Fisher's conditional test** (`fisher_p_value`): under \(\varepsilon_1=\varepsilon_0\) the
  \(W\) controller-wrong items are an exchangeable draw from the \(m\), of which \(E=R_1+W_1\) are
  judge-wrong, so \(W_1\) is hypergeometric and \(p=\Pr[X\ge W_1]\); exact, no declared \(\varepsilon\).
- **(b) Ceiling**, \(H_0:\varepsilon_1\ge\tfrac12\) against \(<\tfrac12\):
  \(p=\Pr[\mathrm{Bin}(W,\tfrac12)\le W_1]\) (`ceiling_p_value`). The lower tail is non-increasing in
  the success probability, so the supremum over the composite null is at \(\tfrac12\) (checked).
- **Interval.** A Clopper–Pearson endpoint solves \(\Pr[\mathrm{Bin}(W,L)\ge W_1]=\alpha/2\), a beta
  quantile, algebraic and in general irrational, so no exact rational interval exists. Exact instead:
  membership of any rational (`clopper_pearson_contains`, both tails \(\ge\alpha/2\)) and brackets of
  width \(2^{-16}\) around each endpoint by bisection on exact tails (`clopper_pearson_bracket`).

*Evidence status: algebraic identity* for the tests; the sawtooth facts of §4 are *finite verified examples*.

## 4. Planning

The level-\(\alpha\) test rejects at \(W_1\ge c(W)\), \(c\) the smallest cutoff with
\(\Pr[\mathrm{Bin}(W,\varepsilon)\ge c]\le\alpha\); power at \(\varepsilon_1=\tfrac12\) is the mass of
\(\mathrm{Bin}(W,\tfrac12)\) on \(\{W_1\ge c\}\). \(W^\*\) is the smallest \(W\) with power \(\ge1-\beta\); exact
power is a sawtooth in \(W\), so the table also gives the \(W\) from which it stays there (checked to
200). \(m\approx W/(1-a)\) is an expectation: the realised \(W\) is \(\mathrm{Bin}(m,1-a)\), and the
procedure's unconditional power \(\sum_w\Pr[W=w]\,\mathrm{power}(w)\) at that \(m\) falls short of \(1-\beta\)
in every cell; \(m_{\text{guar}}\) is the smallest \(m\) at which it does not (`smallest_sample_size`,
re-checked on the next 25 sizes). \(\alpha=\tfrac1{20}\) throughout.

| \(\varepsilon\) | \(\beta\) | \(W^\*\) | \(c\) | power | stable from | \(m\) (a=4/5, 9/10) | uncond. power | \(m_{\text{guar}}\) (4/5, 9/10) |
|---|---|---|---|---|---|---|---|---|
| 1/20 | 1/5 | 5 | 2 | 13/16 | 5 | 25, 50 | 0.731, 0.725 | 30, 61 |
| 1/20 | 1/10 | 7 | 2 | 15/16 | 9 | 35, 70 | 0.851, 0.846 | 43, 87 |
| 1/10 | 1/5 | 8 | 3 | 219/256 | 10 | 40, 80 | 0.741, 0.737 | 47, 94 |
| 1/10 | 1/10 | 12 | 4 | 0.9270 | 12 | 60, 120 | 0.889, 0.887 | 63, 126 |
| 1/5 | 1/5 | 17 | 7 | 0.8338 | 19 | 85, 170 | 0.778, 0.776 | 90, 181 |
| 1/5 | 1/10 | 21 | 8 | 0.9054 | 24 | 105, 210 | 0.858, 0.856 | 120, 242 |

Exact rationals for every entry are in the receipt. A judge at \(\varepsilon=\tfrac15\) against a controller
at \(a=\tfrac9{10}\) needs about 240 gold items to separate independence from the ceiling at power 0.9.

## 5. Gold noise

Let gold flip (\(F\)) independently at rate \(\eta<\tfrac12\), independent of the controller's correctness
\(C\) and the judge's \(J\); measured controller-right is \(C\oplus F\), measured judge-right \(J\oplus F\).

**Proposition 2.** \(a'=\eta+a(1-2\eta)\), \(\varepsilon'=\eta+\varepsilon(1-2\eta)\),
\(W_1'/m=(1-a)\varepsilon_1+\eta(a-\varepsilon)\), \(\varepsilon_1'=(W_1'/m)/(1-a')\); inverted by
\(a=(a'-\eta)/(1-2\eta)\), \(\varepsilon=(\varepsilon'-\eta)/(1-2\eta)\),
\(\varepsilon_1=\big(\varepsilon_1'(1-a')-\eta(a-\varepsilon)\big)/(1-a)\) for \(a<1\); the agreement rate
is invariant, since \(C\oplus F=J\oplus F\) iff \(C=J\). *Proof.* \(W_1'/m=\Pr[C=0,F=0,J=0]+\Pr[C=1,F=1,J=1]
=(1-\eta)(1-a)\varepsilon_1+\eta a(1-\varepsilon_0)\) and \(a\varepsilon_0=\varepsilon-(1-a)\varepsilon_1\). \(\square\)
*Evidence status: algebraic identity*, cross-checked against enumeration of the eight \((C,J,F)\) cells.

**Corollary.** An independent judge (\(\varepsilon_1=\varepsilon\)) measures
\((\varepsilon_1'-\varepsilon')(1-a')=\eta(1-\eta)(2a-1)(1-2\varepsilon)\), positive whenever \(a>\tfrac12\)
and \(\varepsilon<\tfrac12\) (`independent_judge_measured_excess`): a flipped gold label makes controller
and judge look wrong together, the enrichment of `failed_item_noise_share` now on the judge. Noisy
gold therefore mimics a violation of A2, and test (a) on measured counts over-rejects unless they
are first inverted at a known \(\eta\). Fixture, \(\eta=\tfrac1{20}\): \(a'=\tfrac{77}{100}\),
\(\varepsilon'=\tfrac7{50}\); the independent judge measures \(\varepsilon_1'=\tfrac{11}{46}\), so
\(\varepsilon_1'-\varepsilon'=\tfrac{57}{575}\approx0.099\) and the Corollary's quantity
\((\varepsilon_1'-\varepsilon')(1-a')=\tfrac{57}{2500}=\eta(1-\eta)(2a-1)(1-2\varepsilon)\); inversion returns \(\tfrac1{10}\), and \(\tfrac12\) for the shared judge,
exactly. Boundary: \(\eta\) must be known; [gold_calibration_second_grader.md](gold_calibration_second_grader.md)
estimates it from a second independent grader by the three-rater identity
\((1-2\eta_1)^2=\kappa_{12}\kappa_{1C}/\kappa_{2C}\), with \(d\varepsilon_1/d\eta=-4\) at this fixture.

## 6. Falsifiers of the design

- **Gold shares a source with the judge** (the judge wrote or graded the reference, as in the
  atlas's shadow evaluation): \(W_1\) is not a draw from \(\mathrm{Bin}(W,\varepsilon_1)\); the tests say nothing.
- **The sample was touched by the loop**: a second readout, score query or item fed back is a ledger breach; the measurement is withheld.
- **The judge was trained on the controller's outputs**: declare it. It does not invalidate the
  measurement; it is the case the measurement exists for.
- **Noisy gold without a declared \(\eta\)**: the excess of §5 is then confounded.

## 7. Fixture

\(m=200\), \(a=\tfrac45\), \(\varepsilon=\tfrac1{10}\). Expected counts are integers; rounding (half-up per cell) changes nothing.

| judge | \(\varepsilon_1\) | \((R_0,R_1,W_0,W_1)\) | agreement | (a) \(p\) | Fisher \(p\) | (b) \(p\) | 95% CP for \(\varepsilon_1\) |
|---|---|---|---|---|---|---|---|
| independent | 1/10 | (144, 16, 36, 4) | 148/200 = 37/50 | 0.5769 | 0.5978 | \(102091/2^{40}\approx9.3\times10^{-8}\) | [0.0279, 0.2366] |
| maximally shared | 1/2 | (160, 0, 20, 20) | 180/200 = 9/10 | \(1.9\times10^{-10}\) | \(8.5\times10^{-17}\) | \(309339539149/2^{39}\approx0.563\) | [0.338, 0.662] |

The agreement rates are L4's \(\tfrac{37}{50}\) and the ceiling \(\tfrac9{10}\); plug-in inflation \(0\)
and \(\tfrac4{25}\). Test (a) keeps the independent judge and rejects the shared one; test (b) does the
reverse; the interval contains \(\varepsilon\) and excludes \(\tfrac12\) for the first, the reverse for
the second. The (a) p-value for the independent judge has denominator \(10^{40}\); the receipt has it in full.

## 8. Card item

Text for §11 of the calculus (after the insertions' feedback-ledger item 10) and the atlas's \(J\) field; `render_card_item` renders it:

> 11. **Judge shared error:** sample size \(m\) and gold source, with its independence from judge
> and from controller stated; the ledger set holding the sample and its status; \(W\), \(W_1\);
> \(\varepsilon\) as declared and as measured; \(\hat\varepsilon_1\); the exact test of
> \(\varepsilon_1=\varepsilon\) against \(\varepsilon_1>\varepsilon\) with its p-value (binomial with
> declared \(\varepsilon\), or Fisher's conditional test); the ceiling test \(\varepsilon_1\ge\tfrac12\)
> with its p-value; whether the judge was trained on the controller's outputs.

The receipt's `card.rendered` holds both judges' renderings; `card.withheld_after_breach` the item after a breach (`measurement_valid: false`).

## 9. Not delivered

- No observed judge; the fixture tables are expectations, not data. Binary labels only. \(\eta\) is taken
  as known here; its estimation (and the dependent-grader falsifier) is in the gold-calibration note.
- The sawtooth and guaranteed-\(m\) figures are checked on the listed cells and horizons, not
  proved monotone beyond them. Items are treated as independent draws; clustered items shrink \(W\).
