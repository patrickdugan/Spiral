# Eval exhaustion, run 2: item-level feedback with a real learner

Written 2026-10-11, before `sim2.js` was executed. Hashes in `SEAL_2.txt`.

## Why a second design

Run 1 used a parametric toy with score-only feedback. Adding item-level
feedback to that toy would make the result an input (how much of a patch
generalizes would be a parameter). Here the learner is real, so that share is
measured.

## Model (fixed)

- Task: x ~ N(0, I_6). Clean label sign(x0 + 0.7 x1 x2 - 0.3). Observed label
  flipped with probability 0.10, so no non-memorizing predictor can exceed
  0.90 on observed labels (the noise ceiling).
- Learner: 3-nearest-neighbour majority vote. Starts with 100 training points.
- Loop: 100 generations, each adds a batch of m = 10 training points.
- Arms (all add exactly 10 points per generation)
  - CLEAN: 10 fresh population draws. The reused set is never consulted.
  - SCORE: 16 candidate batches of 10 fresh draws; keep the batch with the
    best score on the reused set. Score-only feedback (replicates run 1's
    mechanism with a real learner).
  - LEAK: the 10 points are items the incumbent currently fails on the reused
    set, with their observed labels (duplicates allowed across generations;
    topped up with fresh draws when fewer than 10 fail).
  - MIXED: 5 failed reused-set items plus 5 fresh draws.
- Reused set size n in {250, 1000, 4000, 16000}. Sealed test set of 5000.
  10 seeds per cell, paired across arms.
- reported = accuracy on the reused set. true = accuracy on the sealed test.
  gap = reported - true.

## Predictions

- P1. LEAK gap at generation 100: n = 16000 in [0.025, 0.065];
  n = 4000 in [0.10, 0.24]; for n = 1000 and n = 250 reported >= 0.97
  (above the 0.90 noise ceiling).
- P2. LEAK gap dilutes linearly in n while unexhausted: slope
  ln(gap_16000 / gap_4000) / ln 4 in [-1.15, -0.75].
- P3. SCORE replicates run 1: gap at n = 4000 in [0.03, 0.15]; log-log slope
  over the four n in [-0.65, -0.35].
- P4. Patches generalize worse than fresh data. At n = 16000, true accuracy
  at generation 100 orders CLEAN > MIXED > LEAK, and LEAK's true gain is less
  than half of CLEAN's. (Reason expected: failed items are enriched for
  flipped labels.)
- P5. LEAK, n = 16000: phantom share of reported gain over generations
  51-100 exceeds 0.7.
- P6. LEAK, n = 16000: reported gain over generations 51-100 exceeds 0.02
  while true gain over the same span is below 0.01.

## Not modeled

- Any language model. The learner is k-NN on a synthetic task.
- Partial leakage (seeing failure categories rather than items).
- Deduplicated or perturbed reuse of failed items.
