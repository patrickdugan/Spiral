# Formal proof leaves for *Where the Capital Bound Moves*

An initial Lean 4 / Mathlib formalization of the accounting core of the
[October 2026 paper](../paper/tex/main.tex). The manuscript and the TypeScript
and Python reference models remain the source of protocol intent. This package
is an independent attempt to state and check their mathematical contracts.

## Scope and source correspondence

| Checked declaration | Paper | Implementation | Assumptions and limits |
| --- | --- | --- | --- |
| cutInvariant_initial | Section 3, prefix cut bound | model/ledger.ts; src/spiral_ln/algebra.py | Aggregate cut starts with nonnegative directional balances |
| cutStep_preserves | Section 3, prefix cut bound | src/spiral_ln/algebra.py:Channel.transfer | Each crossing settles only when stock is available; the aggregate abstraction suppresses per-edge detail |
| sendLeft_refines_cut / sendRight_refines_cut | Section 3, a concrete directional hop | src/spiral_ln/algebra.py:Channel.transfer | Local guarded transfer with reserve and locks, arbitrary unchanged cut framing; not a full Python refinement theorem |
| sendLeft_preserves_capacity / sendRight_preserves_capacity | Section 3, conservation per channel | src/spiral_ln/algebra.py:Channel.transfer | Two-sided balances and direction-dependent reserve/lock guards |
| prefix_cut_bound | Section 3, Lemma 1 | src/spiral_ln/algebra.py:NetworkState | A finite abstract cut trace, rather than a proof that route execution refines it |
| policy_invariance | Section 3, policy-invariance proposition | src/spiral_ln/simulator.py | Every admissible trace; does not promise that two policies realize equal volumes |
| peak_of_pool_le_sum_of_peaks | Sections 3 and 5, provisioning advantage | model/server.ts:hyperedgeLiquidityDuration | Finite agent and time sets; deterministically bounds pooled envelope by sum of separate envelopes, with no stochastic gain ratio |
| singleton_pool_has_same_peak | Section 5, k=1 identity | model/server.test.ts | A single member's pooled peak equals its separate peak exactly |
| cross_class_conservation / held_plus_available_eq_source | Section 4, conservation across settlement objects | model/ledger.ts | A guarded two-account projection including holds, fee collection and slashes; clock/journal correspondence outstanding |
| server_capital_bound | Section 4, server bound, outstanding-capital reading | model/server.ts:ArkServer.forfeit, spendLightning, advance | The server atomically fronts the full gross VTXO input; recovered amounts decrease outstanding capital |
| fronting_fits_headroom | Section 4, server admission | model/server.ts:ArkServer.spendLightning | The server begins within its budget |
| cumulative_allocation_not_headroom | Counterexample to literal cumulative-allocation inequality | model/server.ts:ArkServer.allocated, aggregateBoundHolds | Three 300,000-sat spends from gross 400,000-sat inputs |

The server's code checks current outstanding commitments within B. Its allocated
map is cumulative, and its aggregateBoundHolds() tests only committed <= capital.
The paper's expression sum_A K_A^S(n) <= B_S - W_S(n) is false if K is a
cumulative sum of allocations over time. The example with B=1,300,000,
W=1,200,000 and K=900,000 shows this directly. The theorem proved here is the
sound instantaneous constraint W <= B, plus its atomic admission guard.

The boundary remains important: individual channel transitions have a local
cut refinement theorem, but full graph and hypergraph states still need
an implementation-level projection into CutTrace. Additional modeling should cover
failure/rejection identity, HTLC holds, capacity-event confirmation clocks,
fees, Script and on-chain commitments, time-indexed server releases,
and the cryptographic/epoch-snapshot semantics of the reward registry.

The reflected-random-walk pooling estimate near pi/2 and the liquidity-duration
grid are stochastic and empirical claims, outside these deterministic leaves.
None of the proof results validates the whole paper or Bitcoin consensus.

The [review packet](REVIEW.md) records three independently replayable
reference-model bugs, their fixes, and assumptions that a proof cannot erase.

## Build

This package is isolated in formal/ to avoid changing the paper's simulation
requirements. It pins Lean 4 and Mathlib to matching v4.35.0 releases.

    cd formal
    lake update
    lake exe cache get
    lake build
    lake build SpiralFormal.Audit

Review the printed trusted-assumption lists for the headline theorems. Use the
CI workflow for repeatable Linux build results. Do not regard a proof as checked
until it has successfully elaborated in the pinned toolchain.

## Next proof leaves

1. Extend the local Channel.transfer cut-refinement theorem to the whole
   Python NetworkState.apply_route transaction, then prove the hyperedge
   projection for the BIP 448 model. The finite route-to-cut campaign tests
   128 seeds and repeated channels as a provisional correspondence witness.
2. A time-indexed server budget with reservations, sweep clocks, and
   source/recipient value accounting, followed by the corrected paper statement.
3. Finite-set claim-once and epoch-lineage invariants before implementing a
   commitment or knowledge-soundness model; separate the formal statement
   from the simulated registry verifier.
