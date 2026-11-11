# ProvenSpend: origin-certified proof programs

Research draft for `P2PROOF` and the semantic operation `OP_PROVENSPEND`.

A vault's creating transaction proves initialization under a committed program.
Later spends carry proofs authorizing the actual recipients, amounts and successor
state. This is a direct validity-proof design for the computations used by BitVM.

**Status:** unsubmitted proposal, no assigned BIP/opcode/witness version, no Core
patch, no real proof backend. Never fund these illustrative scripts. The model's
witness version 2 and profile 0 have no allocation or production meaning.

## Files

- [bip-provenspend.md](bip-provenspend.md): transaction rules, origination,
  dynamic targets, replay resistance, verifier boundary and deployment blockers.
- [model.py](model.py): executable semantic model with fail-closed backend.
- [test_model.py](test_model.py): ideal-receipt tests, including secp256k1 public
  key tweaking for dynamic P2WPKH payouts.
- [results.json](results.json): measured test result and source digests.

Run from this directory:

```sh
python3 test_model.py
```

55 tests pass. They check the modeled authorization boundary. Cryptographic
soundness, the Bitcoin wire parser, active-chain lookup and Core execution are
outside this test suite. `AuthenticatedPayment` is assumed authenticated in these
tests. Implementing its SPV and witness-commitment checks inside the guest remains
required. The test oracle has an in-memory allowlist and no cryptographic value.

The test state is a sorted-set commitment; the production proposal requires a
specified authenticated accumulator and reconstructible public updates. All test
resource limits are illustrative.

## Spiral integration

The current IOB desk checks an M16 proof in `kan-payment-gate` and signs the payout
itself. This draft proposes a new guest which authenticates the input payment,
derives its payout key, applies the menu, advances the claim history and commits
to the spending transaction. A single proof-locked reserve can then pay the
customer directly. The M16 program alone does not implement that relation.

This directory adds research material only. It changes no desk behavior, existing
BIP draft or deployed spending path.
