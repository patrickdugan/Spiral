# AHR-QPU-04 exploratory IBM pilot

IBM job `dc2b0g5s2omc738bn0d0` completed on 24 November 2026 Singapore time. It ran the approved byte-identical 76-circuit workload on `ibm_kingston`, physical qubits [1, 16, 2, 3]. All 155,648 shots were returned, and all 76 returned PUB identifiers matched the manifest order. IBM reported 45 free QPU seconds against a 112-second cap, leaving 416 free seconds. [Job](receipts/hardware/job.json) · [Execution](receipts/hardware/execution.json) · [Allocation](receipts/hardware/post_allocation.json)

This was the single separately authorized exploratory run after the simulated confidence gate missed. At submission, the calibration identity advanced from 04:37:03 to 05:03:37 Singapore time. The live physical model, QPY, qubit assignments, and readout maps matched the compiled study, and the refreshed estimate was 56.00 seconds. IBM reported the historical calibration timestamp 05:21:04 at both the job start and completion. [Submission preflight](receipts/hardware/preflight.json) · [Approved manifest](receipts/manifest.json)

The historical job-start target differed from preflight in eight of 38 compared entries. The changes were readout error or assignment probabilities on the selected four qubits. A post hoc Aer replay replaced only the frozen assignment matrices with the job-start values, giving **82.95%** predicted joint success. This substitution leaves an approximately 11.8 percentage-point gap to the hardware result. [Calibration comparison](receipts/hardware/calibration_comparison.json) · [Readout replay](receipts/hardware/execution_readout.json)

## Primary measurement

The hardware reproduced the predicted Y signs for the orthogonal fixture and reversed both signs when both loops were reversed. The mean joint correct-order-and-return probability was **71.14%**, with a simultaneous 95% interval of **67.86–74.32%** including the specified one-point systematic allowance. The result missed the 80% design threshold. Frozen calibrated Aer predicted **82.46%** joint success.

| Label | Joint success | Wilson 95% | Spatial return | Correct given return | Y given return |
|---|---:|---:|---:|---:|---:|
| AB | 67.09% | 65.02–69.09% | 79.35% | 84.55% | −0.6911 |
| BA | 75.20% | 73.28–77.02% | 79.00% | 95.18% | +0.9036 |

The primary denominator is all 2,048 shots per label. The spatial return and conditional values show how return failures and internal readout both contributed to the joint result. [Analysis](receipts/hardware/analysis.json) · [Raw histogram ledger](receipts/hardware/counts.json)

## Controls and dwell time

The commuting control's AB-minus-BA contrast in return with positive Y was −4.05 percentage points. Its interval with the registered allowance was [−8.12, +0.03] percentage points. The upper end was close to zero. The inverse-cancellation control had conditional Y −0.2642 and +0.0551 for AB and BA. The pure-gauge control had −0.1699 and −0.1707. These nonzero control residuals limit interpretation of the signal as a precision measurement. The lowest measured correct outcome across the 16 preparation/readout settings was 94.19%. [Control results](receipts/hardware/analysis.json)

| Dwell | Routed AB joint | Routed BA joint | Direct gates, mean joint | Order register, mean joint |
|---|---:|---:|---:|---:|
| 0 µs | 67.09% | 75.20% | 93.90% | 93.58% |
| 2 µs | 59.67% | 75.78% | 93.63% | 93.21% |
| 8 µs | 36.04% | 77.05% | 90.63% | 88.01% |
| 24 µs | 7.13% | 76.76% | 75.42% | 55.62% |

The delay follows the first loop. In the ideal protocol, A first prepares a superposition in the internal mode, while B first applies a phase to the initial basis state. The measured label asymmetry shows why one aggregate memory score is insufficient. The direct gate and known-label register references have distinct circuits and separate error exposure. The six held-out angle pairs and their matched direct settings are in the raw ledger.

## Offline replay

```sh
python hardware_analysis.py --manifest receipts/manifest.json --hardware receipts/hardware --output reproduced/hardware_analysis.json
python execution_readout.py --receipts receipts --output reproduced/execution_readout.json
```

The measurements are a benchmark of the specified four-qubit routes and readout settings. Further QPU execution remains on HOLD.
