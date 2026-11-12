# Keyless CHECKSIG

**Proposed BIP title:** Keyless CHECKSIG: Transaction Commitments via
Tapscript Unknown-Key Types

An experimental interpretation of an otherwise unknown Tapscript key type
allows OP_CHECKSIGVERIFY to compare a Script-computed digest to the actual
BIP341 signature hash. This composes with a Script-level proof verifier to
authorize dynamic transaction outputs without a vault signing key.

## Code and documentation

- [bip-keyless-checksig.md](bip-keyless-checksig.md): precise proposed rule,
  forward-compatibility analysis, resource bounds and deployment caveats
- [reference.py](reference.py): BIP341 hashing, draft P2MR tree validation,
  subset Tapscript interpreter, and compiled 177-byte keyless demo
- [test_reference.py](test_reference.py): 33 automated checks
- [bip341-vectors.json](bip341-vectors.json): narrowly extracted canonical
  BIP341 wallet signature-hash vectors, with original source attribution
- [Research CI](../../.github/workflows/keyless-checksig-research.yml)

## What the prototype proves

One reserve output has two valid terminal payout alternatives selected
after the reserve's funding outpoint exists. Each selection has a different
TapSighash that the Script reconstructs using OP_CAT and OP_SHA256.

The upgraded-rule model rejects output substitution, funding-input changes,
malformed Merkle membership, invalid control branches and mismatched digest
data. Its existing-BIP342-mode comparison demonstrates why the new checking
rules must activate before any funding.

GitHub Actions run dated **2026-11-11**:
[33 tests passed](https://github.com/patrickdugan/Spiral/actions/runs/43046481061).
This includes checks against **7 official BIP341 hash vectors**. The example
Script is **177 bytes**. Witness and fee costs require a real transaction
integration before quantitative deployment claims.

Run:

~~~bash
python -m unittest discover -s BIPSpace/Keyless-CHECKSIG -p 'test_reference.py' -v
python BIPSpace/Keyless-CHECKSIG/reference.py
~~~

## Boundaries

- No Bitcoin Core consensus changes or regtest funds have been executed.
- The prototype uses a SHA256 two-leaf Merkle membership proof, which
  authenticates a recipient selected from an allowlist. It is **not** a
  transparent STARK or zero-knowledge proof.
- A general L1 BitVM application needs a transparent proof verifier in
  Script and a proof of the intended transaction's destination, amount,
  claim-history transition and provenance.
- BIP347 OP_CAT and BIP360 P2MR remain separate Bitcoin consensus proposals.
  The TXCOMMIT key selector and key_version are research placeholders.
- The reserve has no private-key spending path in the proposed P2MR
  construction; recipients can still have ordinary spending keys.
- The economic and denial-of-service costs of a real Script-based STARK
  verifier are an open feasibility question.

The original BIP341 test-vector source is
https://github.com/bitcoin/bips/blob/master/bip-0341/wallet-test-vectors.json .


## Nova and transparent proof workbench (2026-11-12)

See [verifiers/](verifiers/README.md). It now contains a 296-byte
Script-compiled full-trace AIR verifier with dynamic output targeting,
a real standalone Pallas IPA argument, public Nova folding-equation
checks, and a Rust adapter to the pinned real Nova 0.76 compressed
Spartan+IPA verifier.

The added research suite passed **69 tests** on GitHub Actions:
[CI run](https://github.com/patrickdugan/Spiral/actions/runs/43123997055).

The AIR is a fully opened four-step trace, **not a scalable STARK**;
the IPA and fold equation are **components**, not a complete native
Nova-on-Bitcoin verifier. The full real Nova verifier is callable by
the opt-in Rust runner but has not been exercised in this session.
No new consensus rules have been activated or run in Bitcoin Core.
