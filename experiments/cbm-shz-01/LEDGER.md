# CBM-SHZ-01 / "Where the Rent Moves" continuation ledger

Branch `research/shz-clearing-rent-20261125` (Spiral PR #21). Paper section:
`paper/tex/rent.tex` (Section 8 of the rebuilt `paper/tex/main.pdf`).

## Completed gates

| Gate | Result | Evidence |
|---|---|---|
| R-THEORY-1 | Contestable execution (markup ≤ switching cost), resource taxonomy, competitive return vs rent, rent relocation via duals | `paper/tex/rent.tex` §8.1–8.3, §8.9 |
| R-LEAN-1 | 19 theorems (22 with R-LEAN-2a and R-PM-1), standard axioms only, no placeholders: fee feasibility (+ aggregate-not-individual counterexample, monotone ceiling), netting bound (+ zero-flow counterexample), payout cut necessity, deficit certificate, sufficiency for one vault and for unrestricted edges, conservation/backing/authentication under release, undercut and sustainable markup | `formal-rent/` (local WSL build against Mathlib d13f23b; CI job `lean`) |
| R-CAL-1 | Lighter BTC regimes from 67 days of public trades; sigma_1m 1.7–12.8 bp; aggregates only | `data/lighter_regimes.json` |
| R-SIM-1 | Five architectures + three portfolio-margin rows on one demand trace; distinct capital objects with owner, category and verification class | `cbm/sim.py`, `tests/test_cbm.py` (11 pass) |
| R-RUN-1 | 46 sweep cells + empirical replay; base over 3 seeds; rerun with the measured 130 vB exit (base C surplus 0.40 → 0.41 bp, D −0.20 → −0.19) | `results/sweeps.json`; `verify.py` reproduces the base cell |
| R-COM-1 | Duals, pooling, fragmentation, services | `results/commercial.json` |
| R-CI-1 | Workflow `CBM-SHZ-01` run 45517736704 on 6b3e5b2: `lean` (lake build, axiom audit, no placeholders) and `simulator` (9 tests; base cell reproduces on Linux: 606,933 contracts, 8 architectures) both green | public notice on the simulator job |
| R-VER-1r | Regtest-verified release path of C (Core 31.1): two-vault MuSig2 clearing (owner + operator wallets, one key each) conserves value, pays exactly the claim, 255 vB (= simulator formula); released outputs reused from owners' wallets; key path unfinalizable without operator; CSV exit rejected at 1 and 143 conf (non-BIP68-final), accepted at 144, 130 vB (replaced the assumed 200 vB) | `regtest/clearing_release_regtest.py`, `results/regtest_release.json`, CI job `regtest` |
| R-LEAN-2a | Dual price of payout capacity bounded by the substitute's cost: `capacity_value_le_substitute` | `formal-rent/SpiralRent/Duals.lean` |
| R-PM-1 | Risk statement for portfolio margin: `inverse_move_bound`, `gap_buffer_covers` (Lean); gapped liquidating rule C_pmg in the sim; tail measured on 67 days: 4σ√15 exceeded in 1.05% of 15-min windows (median σ), 8σ 0.14%, 8σ own-day σ 0.02%, max 14.3σ; covering the max costs 67 BTC-days vs C 1,558 (seed 1) | `formal-rent/SpiralRent/GapBuffer.lean`, `cbm/pm_tail.py`, `results/pm_tail.json`, cells `pm_gap_mult=*`, `pm_liq_lag_min=*` |
| R-CI-2 | Run 45531174422 on d3a7543: `simulator` (11 tests, base reproduces), `regtest` (Core 31.1 Linux tarball checked against SHA256SUMS; 8/8 checks; 255 vB clearing, 130 vB exit, CSV rejected at [1, 143], accepted at 144) and `lean` (22 theorems) all green | public notice on the regtest job |
| R-PAPER-1 | Section integrated; abstract, introduction, preregistration, limitations, conclusion, appendix updated; PDF rebuilt with Tectonic | `paper/tex/main.tex`, `paper/tex/main.pdf` |

## Findings (base cell unless stated)

- C locks 39% of A's BTC-time (38% on the empirical replay); the saving is idle per-edge provisioning, not netting. Netting cuts settlement flow 61% and pre-maturity capital 0%.
- C fee ceiling 0.70 bp vs provider cost 0.29 bp (surplus 0.41); infeasible below ~1% cost of capital and at 200 sat/vB.
- D (LP advance, 144-block challenge) locks 11% more than A; surplus −0.19 bp (−0.14 empirical). Feasible at 6 or 36 blocks, at 168 h maturity, or payouts-only.
- Duals: 0 where slack; equal to the substitute's cost when binding: 13,700 sat/BTC-day with LP entry, 349,000 without (25×).
- Natural-monopoly rent cap 0.02–0.14 bp (2–8 independent pools), 0.015–0.10 bp with interoperable netting; no pooling economy in bonds under common timing.
- Portfolio margin −85% capital but impairs claims (0.063 BTC base per-router, 0.169 volatile). The gapped liquidating rule (Lean-backed buffer) locks 29 BTC-days at 4σ and 67 at 14.3σ; its impairment is default rate × exceedance (≈1% per default at 4σ with fixed σ). It needs an attested close-out authority SHZ does not have.

## Negative findings and corrections

- Settlement credit over a one-day dispute window adds capital (counterexample).
- Imbalance correlation and router count leave per-contract capital unchanged (by construction of DLC margin); they move only flows and portfolio margin.
- Bond pooling: sum of per-pool peak advances equals the pooled peak.
- Smoke-run corrections before the registered sweeps: trade size from day mean rather than per-second median (10× too many contracts); offline as (party, day) events rather than per contract (chain fees inflated ~20×); C/D gross and net totals include offline obligations settled bilaterally.
- An ad hoc fragmentation estimate with assumed scaling constants was discarded and replaced by the simulated computation before any result was recorded.

## Simulated vs verified

Every capital release in the CBM-SHZ-01 sweeps is SIMULATED. The release PATH of C (MuSig2 clearing, reuse, CSV exit) is verified on regtest under consensus rules (R-VER-1r), with a supplied claim, not an oracle-attested DLC outcome. Verification classes recorded per object: `ln_channel_state`, `onchain_confirmed (clearing tx)`, `ln_settled (LP advance)`, `proof + challenge (LP reimbursement)`. The only verified recovery of spend authority in the program is the Testnet4 pilot01 change reuse (2 blocks; 1,730 s and 2,290 s), on `research/capital-bound-testnet4`.

## Outstanding

| ID | What | Blocker / next step |
|---|---|---|
| R-VER-1 | Observe an oracle-attested DLC margin release and one LP reimbursement on Testnet4 | SHZ reference router has no DLC closure/withdrawal; needs implementation, then a Testnet4 campaign with a new campaign ID (broadcast needs Patrick's yes) |
| R-LEAN-2b | General max-flow sufficiency; attainment of the dual bound (complementary slackness) | upper bound proved (R-LEAN-2a); attainment and general MFMC need LP duality / flow machinery; numeric checks in `tests/` |
| R-PM-2 | Attested close-out authority for portfolio margin in SHZ | design + implementation; until then only per-contract margin is offered |
| R-DATA-1 | Participant collateral, offline and topology data | none public; assumptions stated in SPEC.md |
| R-PROOF-1 | Prove one SHZ clearing statement with Nova → SP1 (BLAKE3 final layer) | costs used are the measured guest-A figures, not an SHZ statement |
