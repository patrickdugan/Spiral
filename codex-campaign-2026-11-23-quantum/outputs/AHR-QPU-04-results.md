# AHR-QPU-04 simulation results

**Hardware HOLD.** The calibrated routed circuit reached **82.46%** mean joint success. Its nominal simultaneous 95% lower bound was **78.42%** after the one-point systematic allowance. Every noise scenario missed the 80% lower-bound gate. IBM verified **461 free Open Plan seconds** at 05:06 Singapore time on 24 November 2026. The candidate estimate was 56.00 seconds with a provisional 112-second cap. No IBM job was submitted. [Manifest](receipts/manifest.json) · [Calibration](receipts/calibration.json)

## Exact and native checks

At the reference angles, AB and BA both returned to vertex 0 and produced internal Y expectations −1 and +1. The two amplitudes in the internal computational basis after AB are $e^{i\beta}\cos\alpha$ and $i e^{-i\beta}\sin\alpha$. After BA, they are $e^{i\beta}\cos\alpha$ and $i e^{i\beta}\sin\alpha$. The absolute determinant of these two state vectors is $|\sin(2\alpha)\sin\beta|$. Twenty seeded angle pairs matched that expression within 4×10⁻¹⁶. Reversing each route applied its adjoint. All three implementations matched the full 16-dimensional edge operator within 6×10⁻¹⁵ and followed the expected vertex after each of eight steps.

The native comparison used IBM Kingston calibration timestamped 04:37:03 Singapore time. It examined two connected subsets and three initial placements per method. The selected initial mapping from q0 through q3 was [1, 16, 2, 3]. The table uses the best placement for each method and reports the worse label’s joint probability under nominal Aer.

| Routed synthesis | Weaker label | Maximum native depth | Maximum CZ count | Native critical path |
|---|---:|---:|---:|---:|
| Exact controlled edge block | 68.78% | 647 | 177 | 21.81 µs |
| Conditional rotation and swap | 74.61% | 541 | 158 | 18.83 µs |
| Multiplexed rotation and swap | 82.44% | 318 | 104 | 12.62 µs |

The explicitly inserted identity probe contained eight internal identity operators before transpilation. The compiler removed all eight and preserved all eight route barriers. The identity route retained 64 CZ gates, compared with 104 for the selected signal. Padding matched duration for shorter controls where possible. The data include actual gate count, critical path, and the unpadded predictions, so duration matching can be assessed separately from channel exposure. [Compilation comparison](receipts/compilation.json) · [Simulation receipt](receipts/simulation.json)

## Primary endpoint and controls

| Nominal label | Correct and returned | Spatial return | Correct, conditional on return | Conditional Y |
|---|---:|---:|---:|---:|
| AB | 82.49% | 85.03% | 97.01% | −0.9403 |
| BA | 82.44% | 85.05% | 96.94% | +0.9388 |

The high conditional accuracy excludes shots that leave the base vertex. The registered joint endpoint includes those failures. The commuting control remained consistent with zero order contrast in all four scenarios. Reversing both loops flipped the modeled Y signs. The inverse-cancellation and pure-gauge controls had conditional `|Y|` below 0.004 in both labels under nominal Aer. The lowest modeled correct outcome among the 16 preparation/readout settings was 96.46%.

| Scenario | Mean joint success | Simultaneous 95% interval with allowance |
|---|---:|---:|
| Nominal | 82.46% | 78.42–84.27% |
| Extra two-qubit gate error | 80.57% | 78.27–84.13% |
| Shorter idle coherence and higher readout error | 81.33% | 78.01–83.89% |
| Coherent coupler shift | 82.29% | 79.31–85.09% |

The confidence intervals are from reproducible synthetic counts with 2,048 shots per circuit. They demonstrate the gate calculation under the declared model and allowance. They are not IBM observations.

## Memory sweep and references

These are mean modeled joint scores across the two labels with the declared timing padding. The requested delay sits between the first and second loop or direct gate. For the order-register comparator it follows label preparation.

| Delay | Routed | Direct internal gates | Prepared order register |
|---|---:|---:|---:|
| 0 µs | 82.46% | 93.98% | 94.03% |
| 2 µs | 82.37% | 93.83% | 93.68% |
| 8 µs | 82.09% | 93.39% | 92.81% |
| 24 µs | 81.39% | 92.27% | 90.56% |

The direct sequence and prepared register are comparators with no spatial route. The six held-out angle pairs were evaluated after choosing the compiled circuit and have paired direct-gate predictions in the receipt. The routed fixed-Y label scores ranged from 27.36% to 81.71% across those cases. The Y readout was selected at the orthogonal fixture and its classification performance depends on angle.

## Resource and reproducibility

The ordered candidate has 76 circuits and 155,648 shots, including every control, dwell, held-out, and calibration setting. The estimate sums calibrated critical paths and the backend’s 250 µs repetition delay over the shot ledger. A 15-second fixed assumption and a factor-of-two margin produce the 112-second provisional cap. The allocation can accommodate that figure on paper. The precision gate failed, so the candidate remains simulation-only. [Exact QPY](receipts/q4_candidate_isa.qpy) · [Per-case manifest](receipts/manifest.json) · [Pinned design](../ibm_qpu_03b/AHR_QPU_04_SPEC.md)
