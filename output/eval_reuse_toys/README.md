# Eval-reuse toy runs (2026-10-11)

Seeded simulations behind the "synthetic mechanism result" rows of
`paper/evaluation_feedback_insertions.md`. They are JavaScript, not exact, and
involve no language model. Files are stored as run; `output/**` is not
line-normalized, so the recorded hashes remain checkable.

| File | Role |
|---|---|
| `PREREG.md`, `sim.js`, `SEAL.txt`, `results.json` | Run 1: parametric model, score-only reuse. Predictions and script hashed before execution. |
| `PREREG_2.md`, `sim2.js`, `SEAL_2.txt`, `results2.json` | Run 2: 3-nearest-neighbour learner, item-level feedback. Predictions and script hashed before execution. |
| `sim2b.js`, `results2b.json` | Post hoc arm added after run 2's results were seen. Exploratory. Hashes appended to `SEAL_2.txt` afterwards. |

`results.json` from run 1 was not hashed at the time. Its hash, recorded when
these files were copied here, is `9149c1083716e4f901d0d728ede77a90abf8b9385a9ecf207e5bb47bc8f8a8bd`. That is a receipt for the copy, not a
seal on the run.

Reproduce with plain Node, from a scratch copy so existing results are kept:

```powershell
node sim.js
node sim2.js
node sim2b.js
```

Each script overwrites its results file in its own directory.

Prediction record: 5 of 6 passed in run 1, 3 of 6 in run 2. Both runs
overpredicted the size of the gap between reported and true accuracy.

A re-run from a scratch copy on the same day, in the environment that produced
them, reproduced all three results files byte for byte.

A second re-run on Node 24.19.0 under Windows reproduced `results2.json` and
`results2b.json` byte for byte. `results.json` differed in the last digit of 24
floating-point values, the largest relative difference about 1.2e-15. Its
`summary` and `checks` were identical. Run 1 is reproducible to its reported
precision, not to the byte, across platforms.
