# Empirical review for the public-comment draft

Reviewed baseline: `6a9df365f727cf2471ae52e00b36e8816d0081bc`, 2026-10-21.
This review reanalyzes retained files. It adds no live-network observations and
does not replace or rewrite the archived campaigns.

## The retained numbers reproduce

Run `python audit/peer_review/check_empirical.py` from the repository root.
The script uses only the Python standard library. It verifies the CSV checksums
against the original combined receipt, rejects duplicate conditions and
unmatched pairs, then recomputes topology-cluster means and their two-sided 95%
Student-t intervals using the archived rounded critical values.

There are 4,536 rows across three campaigns, including 3,348 sealed rows and 28
sealed topology clusters. The original campaign contributes four clusters, the
replication six, and the precision extension eighteen. All seven archived
success contrasts checked by the script reproduce to numerical tolerance
`1e-12`. `empirical_check.json` records the inputs and results.

| Comparison | Mean, percentage points | 95% interval |
|---|---:|---:|
| Retry minus one-shot public routing | 5.1389 | [3.0823, 7.1954] |
| Online feedback heuristic minus retry | 0.3481 | [0.1477, 0.5485] |
| Current-state greedy oracle minus online heuristic | 1.1099 | [0.6395, 1.5803] |
| Current-state greedy oracle minus retry | 1.4580 | [0.8446, 2.0715] |
| Failure-aware minus random capital, stationary demand | 6.1310 | [4.9090, 7.3530] |
| Failure-aware minus random capital, diffuse demand | 0.1443 | [-0.0222, 0.3108] |
| Failure-aware minus random capital, shifted demand | 0.4383 | [-0.2119, 1.0886] |

The oracle-minus-retry contrast is a new arithmetic reanalysis of archived
paired observations. The other comparisons reproduce retained results.

## Required manuscript corrections

1. **Name the oracle comparator correctly.** Baseline Table 1 labels the 1.11
   point effect as oracle over retries. The stored contrast is oracle over the
   online heuristic. Oracle over retries is 1.46 points. Use one comparator
   consistently in the abstract, introduction, table, and interpretation.

2. **Describe the information and attempt resources.** The ordinary retry and
   online arms attempt at most three routes. The oracle tests the hidden
   feasibility of all eight candidates before selecting a feasible route.
   This makes the comparison an information/resource package. Its failed
   attempt count is zero by construction. The words "fixed attempt budget"
   omit that distinction.

3. **Respect the earlier audit's adjudication.** `audit/inference/report.md`,
   section I2, demonstrates equivalence between exhaustive retries and an
   oracle inspecting the same ordered candidate prefix when failures have no
   consequential cost. Its 126 post-hoc episodes did not exactly regenerate
   the historical campaigns: only six of 72 original-policy checks matched
   both success and failed-attempt counts. That diagnostic cannot decompose
   the archived 1.11 point estimate into an "attempt budget, not information"
   effect. Operational timing, reservations, and HTLC slots are absent.

4. **Keep the routing claim at the tested scope.** A cut conservation identity
   constrains feasible executions. It does not bound the relative success of
   every routing policy by one percentage point. The stored oracle is greedy
   in current state; the prior audit gives a two-demand counterexample to its
   being a horizon-optimal controller. Describe these results as comparisons
   of the tested heuristics on the specified synthetic workloads.

5. **Report uncertainty after the demand shift.** The combined interval extends
   to +1.089 percentage points, outside the declared +/-1 point band. It
   includes zero, so it establishes neither a positive combined effect nor
   practical equivalence under that rule. The precision extension alone is
   tightly concentrated near zero. Those statements answer different
   questions. Baseline passages saying "the six vanish", "nothing after a
   shift", and a coalition gain "is zero" should use the combined estimate
   and its interval.

6. **Separate the capital theorem from the coalition hypothesis.** A bound on
   authenticated capital does not make the six-point placement estimate an
   upper bound on all gains from coordination. The experiments neither
   optimize across every possible placement nor monetize all benefits of
   coordination. The proposed coalition experiment needs a distinct payoff,
   admissible policy class, and actual bound or an explicitly empirical
   hypothesis.

7. **Correct the campaign count and scope of preregistration.** Baseline text
   says two campaigns; the combined estimate uses three. The precision
   configuration states that it responds to heterogeneity observed after the
   replication and declares tests on combined data. Present original,
   replication, and extension evidence separately, with the combined estimate
   identified as an adaptive extension. The initial configuration has no
   `preregistered_hypotheses` field. A claim of preregistration requires the
   timestamped pre-run protocol and the result chronology; the configuration
   label alone does not establish either.

8. **State the conditional population.** All sampled topologies come from one
   July 16, 2023 public-gossip snapshot, with synthetic capacities and
   directional balances. Twenty-eight sampled subgraphs do not measure
   snapshot-to-snapshot variability or contemporary operational conditions.
   The existing inference audit checked sample overlap and did not establish
   that overlap invalidates the conditional Monte Carlo intervals.

## Reproduction gap to disclose

The archived simulator constructs graph/state order in a way sensitive to
Python's process hash seed. The audit contains concrete same-seed/different-
hash-seed witnesses. This does not corrupt the archived CSV estimates, whose
integrity survives. Future confirmatory runs should canonicalize the graph,
candidate ordering, and state assignment, then record Python and dependency
versions plus initial-state and candidate-catalogue hashes.

The raw public snapshot is ignored by Git and must be obtained by the retained
fetcher and checked against its SHA-256. This review verified row-based
inference without regenerating the 2023 topology or rerunning the campaigns.
The original analysis API also permits duplicate overwrite, silent unpaired
intersection, and intervals with zero or one cluster. The new audit rejects
these inputs without changing the frozen historical analysis.

## What the retained testnet4 evidence supports

The offline script independently decoded and hashed all 512 archived headers,
checked their encoded PoW targets and 511 internal parent links, and matched
the retained log anchor at height 147984. The first header is at 147473.
Sixty-four consecutive header timestamp differences are nonpositive, with a
minimum of -6004 seconds.

The files are historical public-header evidence. Their synthetic funding
inclusion and depth gates are declared scenarios. They contain no actual
funding transaction, operational payment, observed arrival time, or current
node measurement. Further repetitions of the same ordinal scenarios would
add no independent evidence about liquidity pooling or deployed settlement.

## Primary references checked for the next experiment

- [Bitcoin Core 28.0 release notes](https://bitcoincore.org/en/releases/28.0/)
  document testnet4 support.
- [LND 0.19.0 release notes](https://github.com/lightningnetwork/lnd/blob/master/docs/release-notes/release-notes-0.19.0.md)
  record its addition of testnet4. Its [sample configuration](https://github.com/lightningnetwork/lnd/blob/master/sample-lnd.conf)
  includes `bitcoin.testnet4`.
- [Core Lightning configuration](https://docs.corelightning.org/reference/lightningd-config)
  lists `network=testnet4`.
- [Second's Lightning payment documentation](https://second.tech/docs/learn/payments-lightning)
  states that a successfully spent outgoing HTLC is held off chain and that
  the server sweeps the round at expiry. The document gives distinct clocks
  for incoming Lightning pool VTXOs.
- [Second's local server guide](https://second.tech/docs/ark-server/docker-compose)
  supplies a regtest stack with an optional Core Lightning service. Its
  [manual server guide](https://second.tech/docs/ark-server/manual-setup)
  uses signet.

These web pages were checked on 2026-10-21. The experiment must pin software
commits and record parameters at execution time.
