# CBM-SHZ-01 / "Where the Rent Moves" continuation ledger

Branch `research/shz-clearing-rent-20261125` (Spiral PR #21). Paper section:
`paper/tex/rent.tex` (Section 8 of the rebuilt `paper/tex/main.pdf`).

## Completed gates

| Gate | Result | Evidence |
|---|---|---|
| R-THEORY-1 | Contestable execution (markup ≤ switching cost), resource taxonomy, competitive return vs rent, rent relocation via duals | `paper/tex/rent.tex` §8.1–8.3, §8.9 |
| R-LEAN-1 | 19 theorems, standard axioms only, no placeholders: fee feasibility (+ aggregate-not-individual counterexample, monotone ceiling), netting bound (+ zero-flow counterexample), payout cut necessity, deficit certificate, sufficiency for one vault and for unrestricted edges, conservation/backing/authentication under release, undercut and sustainable markup | `formal-rent/` (local WSL build against Mathlib d13f23b; CI job `lean`) |
| R-CAL-1 | Lighter BTC regimes from 67 days of public trades; sigma_1m 1.7–12.8 bp; aggregates only | `data/lighter_regimes.json` |
| R-SIM-1 | Five architectures + three portfolio-margin rows on one demand trace; distinct capital objects with owner, category and verification class | `cbm/sim.py`, `tests/test_cbm.py` (9 pass) |
| R-RUN-1 | 39 sweep cells + empirical replay; base over 3 seeds | `results/sweeps.json`; `verify.py` reproduces the base cell |
| R-COM-1 | Duals, pooling, fragmentation, services | `results/commercial.json` |
| R-CI-1 | Workflow `CBM-SHZ-01` run 45517736704 on 6b3e5b2: `lean` (lake build, axiom audit, no placeholders) and `simulator` (9 tests; base cell reproduces on Linux: 606,933 contracts, 8 architectures) both green | public notice on the simulator job |
| R-PAPER-1 | Section integrated; abstract, introduction, preregistration, limitations, conclusion, appendix updated; PDF rebuilt with Tectonic | `paper/tex/main.tex`, `paper/tex/main.pdf` |

## Findings (base cell unless stated)

- C locks 39% of A's BTC-time (38% on the empirical replay); the saving is idle per-edge provisioning, not netting. Netting cuts settlement flow 61% and pre-maturity capital 0%.
- C fee ceiling 0.70 bp vs provider cost 0.29 bp (surplus 0.40); infeasible below ~1% cost of capital and at 200 sat/vB.
- D (LP advance, 144-block challenge) locks 11% more than A; surplus −0.20 bp (−0.14 empirical). Feasible at 6 or 36 blocks, at 168 h maturity, or payouts-only.
- Duals: 0 where slack; equal to the substitute's cost when binding: 13,700 sat/BTC-day with LP entry, 349,000 without (25×).
- Natural-monopoly rent cap 0.02–0.14 bp (2–8 independent pools), 0.015–0.10 bp with interoperable netting; no pooling economy in bonds under common timing.
- Portfolio margin −85% capital but impairs claims (0.063 BTC base per-router, 0.169 volatile).

## Negative findings and corrections

- Settlement credit over a one-day dispute window adds capital (counterexample).
- Imbalance correlation and router count leave per-contract capital unchanged (by construction of DLC margin); they move only flows and portfolio margin.
- Bond pooling: sum of per-pool peak advances equals the pooled peak.
- Smoke-run corrections before the registered sweeps: trade size from day mean rather than per-second median (10× too many contracts); offline as (party, day) events rather than per contract (chain fees inflated ~20×); C/D gross and net totals include offline obligations settled bilaterally.
- An ad hoc fragmentation estimate with assumed scaling constants was discarded and replaced by the simulated computation before any result was recorded.

## Simulated vs verified

Every capital release in CBM-SHZ-01 is SIMULATED. Verification classes recorded per object: `ln_channel_state`, `onchain_confirmed (clearing tx)`, `ln_settled (LP advance)`, `proof + challenge (LP reimbursement)`. The only verified recovery of spend authority in the program is the Testnet4 pilot01 change reuse (2 blocks; 1,730 s and 2,290 s), on `research/capital-bound-testnet4`.

## Outstanding

| ID | What | Blocker / next step |
|---|---|---|
| R-VER-1 | Observe one DLC margin release and one LP reimbursement on Testnet4 | SHZ reference router has no DLC closure/withdrawal; needs implementation, then a Testnet4 campaign with a new campaign ID |
| R-LEAN-2 | General max-flow sufficiency and complementary slackness for the duals | not formalized here; Hall-type or max-flow/min-cut machinery would be needed; numeric checks in `tests/` meanwhile |
| R-PM-1 | Risk statement for portfolio margin under gap moves | needs a margin model with a proven coverage bound |
| R-DATA-1 | Participant collateral, offline and topology data | none public; assumptions stated in SPEC.md |
| R-PROOF-1 | Prove one SHZ clearing statement with Nova → SP1 (BLAKE3 final layer) | costs used are the measured guest-A figures, not an SHZ statement |
