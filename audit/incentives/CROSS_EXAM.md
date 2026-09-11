# Cross-examination of the inference auditor

2026-09-11. These are actual messages exchanged between the incentive and inference sub-agents in this task, summarized without invented speakers or simulated agreement. They concern exploratory audit code, not live Lightning behavior.

## Executed-attempt budgets versus inspected-candidate budgets

The incentive auditor read `audit/inference/run_audit.py`, `audit/inference/test_audit.py`, the resulting `results.json`, and the original `execute_payment` implementation. The challenger sent this objection:

> “retry3↔oracle3 and retry8↔oracle8 trajectory identity is sound by induction only because rejected attempts have no balance/time state effect. But 'matched budget' needs two axes: oracle3 restricts inspected candidates; retry8 relaxes costly attempt budget. Original online sees all8 candidates, may attempt3; oracle feasibility-filters all8 and attempts1. Thus the original design can legitimately measure value of information under a 3-attempt operational constraint, not simply an implementation error/confound.”

The inference auditor responded:

> “Accepted. Report will distinguish candidate-feasibility queries from executed attempts, and preserve oracle probe-cost advantage. The equal-8 retry comparison spends more operational attempts, so it does not refute value-of-information under fixed attempt budget.”

Adjudication: retain the exact structural equivalence as a result of the simulator's free rejected-attempt semantics. Do not describe it as proof that state knowledge is valueless. In the current diagnostic output, retry8 and oracle8 both deliver 85.7576%, while retry8 records 519 infeasible attempts and oracle8 records zero across the same 1,980 evaluation demands. Those figures are post-hoc bounded diagnostics, not independent replication of the original headline effect.

## Overlap is not automatically dependence

The measured original sample overlap is 182 of 378 sealed pairs sharing at least one node and 47 sharing an edge; mean node Jaccard is .007159 and mean edge Jaccard .001397. The incentive auditor sent this qualification:

> “Your conditional-independence caveat is important: fixed-snapshot randomized draws need not become statistically dependent merely by sharing nodes. Avoid '28 clusters invalid' leap; strongest limitation is unmeasured snapshot uncertainty and sampling design.”

The original inference code already included this qualification. Adjudication: report the measured overlap honestly; do not infer a covariance, a design-effect correction, or an effective sample size from overlap counts alone. The original intervals describe uncertainty under the configured fixed-snapshot simulation design, not an independently sampled population of historical Lightning states.

## Failed reproduction is not silently repaired evidence

The incentive auditor observed `original_four_policies_exactly_reproduced: false` and requested that the diagnostic runs not be treated as an exact decomposition of the previously published means. The inference auditor replied that it was testing hash-order dependence because the same sample ID, code, and configuration had changed metrics.

Adjudication at the time of this exchange: reproduction is unresolved. The current resource-budget trajectory identities are internally checked on their new executions, but old-versus-new arithmetic should not be attributed to the budget intervention alone. The inference auditor's separate reproducibility investigation supplies any later final disposition.

## No false novelty from deployment costs

The incentive auditor verifies that the old manuscript explicitly omits opening delay and on-chain costs at `paper/manuscript.md:466` and says a 120,000-unit connector can be uneconomic at `paper/manuscript.md:547`. Its supplement calls the coordination bonus an assumption at `paper/hive_lab.md:63` and cautions against treating the income difference as discovered at `paper/hive_lab.md:89`.

Adjudication: these are disclosed missing mechanisms, not concealed premises exposed for the first time. The audit contributes executable counterexamples, cost thresholds, and a historical testnet ordering scaffold. Null differences in shifted demand do not prove absence of all useful adaptive strategies; the relevant conclusion is about the particular static heuristic and tested support.
