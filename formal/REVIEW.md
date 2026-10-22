# Proof-leaf review packet

**Date:** 2026-10-22
**Manuscript:** [Where the Capital Bound Moves](../paper/tex/main.tex), revised October 16
**Baseline:** main commit 6a9df365f727cf2471ae52e00b36e8816d0081bc
**Work:** [draft PR #4](https://github.com/patrickdugan/Spiral/pull/4)

This packet follows the review lenses in Keagan McClelland's
[btc-verified #54](https://github.com/ProofOfKeags/btc-verified/issues/54):
statement adequacy, model fidelity, replayable negative cases, and explicit
trusted boundaries. A theorem checked by Lean, a tested program, and
correspondence between them count as separate evidence classes.

## Claim-to-evidence matrix

| Claim | Evidence | Residual assumptions |
| --- | --- | --- |
| Prefix cut bound, every admissible policy | Lean: Cut.prefix_cut_bound and Cut.policy_invariance | A full Python NetworkState refinement is outstanding |
| Bilateral directional transfers | Lean: Channel.sendLeft/Right_preserves_capacity and sendLeft/Right_refines_cut | One-channel proof with arbitrary unchanged cut framing; 128 sampled end-to-end traces |
| Deterministic pooling inequality | Lean: Pooling.peak_of_pool_le_sum_of_peaks | The stochastic sqrt(k) and pi/2 ratios are separate |
| Cross-class value, fees, holds and slashes | Lean: Ledger.cross_class_conservation | Two-account projection; journal IDs, timing and real Map mutations are outside the proof |
| Instantaneous Ark budget | Lean: Server.server_capital_bound and fronting_fits_headroom | Gross input fronting; issuance liabilities and live recovery economics require additional semantics |
| Claim-once registry | TypeScript mock tests and adversarial regressions | Real ZK, authority semantics and privacy are not proven |

Run the proof audit with:

    cd formal
    lake build
    lake build SpiralFormal.Audit

The model correspondence workflow checks Python reference transitions and
all TypeScript reference-model tests. Record the exact Git revision and CI
job for each review; retain failures as fixed regression tests.

## Refutations and repairs

### F1: a rejected repeated-channel route could mutate the network

The earlier route_feasible implementation checked each hop against the same
original directional balance. On route a,b,c,a,b, the second a-to-b transfer
could fail after prior hops had already changed balances. This violated the
manuscript's failed-attempt identity premise.

**Witness:** tests/test_algebra.py, repeated-channel atomicity regression.
The test failed against the previous implementation in
[CI 39754287201](https://github.com/patrickdugan/Spiral/actions/runs/39754287201).

**Fix:** stage only the touched channels, replay hops in order, commit their
new balances together after success; reject nonpositive amounts. An
additional 128-seed campaign in tests/test_route_cut_projection.py exercises
repeated channels, directional locks and reserves, five cuts per history and
failed-attempt identity. Finite sample results cannot replace a program
refinement theorem.

### F2: capital-time integrated past a sweep

The previous ArkServer.advance implementation charged outstanding capital
for a whole interval before executing sweeps inside it. One hundred satoshis
committed for five blocks were charged 1,000 sat-blocks over a ten-block
advance rather than 500. The round-recovery variant had the same problem.

**Witness:** model/server.test.ts, capital-time sweep regression, failed
in [CI 39754287201](https://github.com/patrickdugan/Spiral/actions/runs/39754287201).

**Fix:** integrate the outstanding-capital step function between exact
release heights. The existing grid is six-block round-aligned, so this
issue may have little impact on its reported cells; the correction matters
for general clock-step sizes.

### F3: mock commitment root ambiguous and object IDs overwriteable

The older SettledSet.root encoded fields by pipe separation. The distinct
objects (id="a|1", value=2, authorityKey="x") and
(id="a", value=1, authorityKey="2|x") gave the same input to SHA-256.
The add, refresh and transfer methods also permitted silently overwriting a
live object identifier.

**Witness:** two cases in model/registry.test.ts, both failed in
[CI 39755714180](https://github.com/patrickdugan/Spiral/actions/runs/39755714180).

**Fix:** hash canonical JSON arrays of sorted, typed records, check values,
reject duplicate identifiers before state changes, and keep consumed ID
tombstones across snapshots. This remains a simulated digest, without
Merkle inclusion proofs or a zero-knowledge verifier.

## Paper statement requiring a revision

Section 4 currently states the bound-relocation inequality:

    O_A(n) - I_A(n) <= V_A(0) + K_A^S(n)
    sum_A K_A^S(n) <= B_S - W_S(n)

The code's allocated map is cumulative, whereas its fronting guard applies
to *fresh requested* gross commitments and the uncommitted stock before an
event. Separate cumulative spending allocations from the per-event value
that is newly encumbered.

    sum_A F_A(t) <= B_S - W_S(t-before)
    W_S(t-after) <= B_S

Sweeps reduce W_S, and cumulative commitments can therefore exceed B_S
over a long horizon. The reference test with B=1,300,000 has three outward
payments of 300,000 sat consuming gross 400,000-sat inputs each. Afterwards
W=1,200,000 and current headroom is 100,000, while cumulative outward
payments are 900,000. The manuscript's second inequality fails under its
cumulative interpretation. The paper's first inequality also needs K and
V_A(0) defined precisely against the server's gross fronting.

The manuscript remains unchanged in this draft PR while the formal
accounting variables have separate meanings.

## Residual questions

**Routing oracle:** The conservation ceiling is policy-invariant, although
route choices can affect later balances. Quantify the paper's stronger
wording about oracle gains with a specified sequential demand model.

**Claim privacy:** Registry.submit(statement, witness) currently receives
an object identifier, and epoch-close logic retains it. This is an
acknowledged limitation of the simulated verifier. A production privacy
claim needs a public-proof-only verifier interface, a canonical nullifier
for each authorized object, and private successor/lineage checks.

**Ark recovery:** The expiry-only versus next-round reuse assumption
remains implementation-dependent and drives the liquidity-duration result.

**BIP 448 and LayerTree:** Proposed consensus changes, transaction weights,
policy limits, cryptographic assumptions, and actual network deployment
are distinct obligations. None is discharged by these abstract proofs.

## Method

The reusable lesson from btc-verified is to freeze the proposition and its
definitions before AI-assisted proof work, attempt independent counterexamples,
then pin each executable validation to the precise source and assumption
set it exercised. The three negative witnesses above are retained so a
later proof review can distinguish source behavior from the theorem text.
