# Eval exhaustion toy: predictions frozen before first run

Written 2026-10-11, before `sim.js` was executed. Hash of this file and of
`sim.js` is recorded in `SEAL.txt` before the run.

## Question

When a self-improvement loop selects candidates on a reused held-out set
(score-only feedback), how far does the reported score separate from
population accuracy, and how does that distort a takeoff readout?

## Model (all parameters fixed here)

- Items: difficulty b ~ N(0, 1.5^2). Model-item quirk u ~ N(0, 1).
- A model solves item i iff a - b_i + u_i > 0 (deterministic evaluation).
- Population accuracy is closed form: Phi(a / sqrt(1.5^2 + 1)).
- Start: a0 chosen so population accuracy = 0.26.
- Each generation g = 1..100, K = 16 candidates. Candidate = incumbent plus
  - general change da = s_g * z, s_g = 0.06 * 0.95^(g-1)  (true gain ratio 0.95)
  - quirk re-roll u' = cos(phi) u + sin(phi) z, sin(phi) = 0.2
- Arms
  - FRESH: candidates and incumbent scored on a new block of n items each
    generation; accept best candidate if it beats the incumbent on that block.
  - REUSE-NAIVE: one fixed set of n items; accept best candidate if its score
    exceeds the incumbent's.
  - REUSE-GATED: same, but accept only if the gain exceeds
    3 * sqrt(p(1-p)/n), p = incumbent score.
- n in {500, 1000, 4000, 16000}. 20 seeds per cell.
- gap = reported score on the reused set minus population accuracy.

## Predictions

- P1. REUSE-NAIVE gap at generation 100, n = 4000, lies in [0.08, 0.25].
- P2. REUSE-NAIVE gap at generation 100 scales as n^(-1/2): log-log slope
  across the four n values lies in [-0.6, -0.4].
- P3. Phantom share of reported gain over generations 51-100,
  1 - (true gain)/(reported gain), exceeds 0.5 in REUSE-NAIVE for
  n in {500, 1000, 4000}.
- P4a. At n = 4000, REUSE-GATED gap at generation 100 is at most half the
  REUSE-NAIVE gap.
- P4b. At n = 4000, final population accuracy orders
  FRESH > REUSE-NAIVE > REUSE-GATED.
- P5. At n = 4000 in REUSE-NAIVE, the late/early gain ratio
  (gain over 51-100)/(gain over 1-50) computed from reported scores is at
  least twice the same ratio computed from population accuracy.

## Not modeled

- Item-level feedback (the loop seeing which items failed). Score-only here.
- Stochastic evaluation noise. Evaluation is deterministic.
- Any real model. This is a property of the toy and its parameters.
