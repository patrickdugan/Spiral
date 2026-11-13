# BIPSpace

Bitcoin consensus and Script design research for Spiral. Each proposal is kept
under its own title-named directory so its BIP draft, executable experiments,
vectors, measured results and compatibility notes stay together.

## Proposals

### [Keyless-CHECKSIG](Keyless-CHECKSIG/)

**Keyless CHECKSIG: Transaction Commitments via Tapscript Unknown-Key Types**

Unsubmitted soft-fork proposal reusing OP_CHECKSIGVERIFY's BIP341 signature
message to compare a Script-computed transaction digest with the actual
transaction. The proof-authorized spend can select a recipient after funding.

The prototype includes a 177-byte executable Script model, two
post-funding recipient alternatives from one keyless reserve, 33 passing tests,
seven official BIP341 sighash vectors, and dedicated lightweight GitHub CI.

**Status:** research implementation. The proposed key type and key version are
unallocated. BIP347 CAT and BIP360 P2MR are separate pending activations.
The demonstrator uses SHA256 Merkle authorization, not a STARK or ZK proof.
Bitcoin Core consensus integration is not implemented.

See its [README](Keyless-CHECKSIG/README.md) and
[BIP research draft](Keyless-CHECKSIG/bip-keyless-checksig.md).


The [Keyless CHECKSIG verifier workbench](Keyless-CHECKSIG/verifiers/)
contains the current transparent Script arithmetic and Pallas/Nova
cryptographic prototypes. Its full-trace AIR model is distinguished
from a production STARK, and the separate Rust adapter calls the
existing real Nova 0.76 native compressed verifier.

## Research papers

### [The BIP Sieve](The-BIP-Sieve/)

[How Bitcoin Upgrades Earn Consent](The-BIP-Sieve/paper.md) studies historical
proposal outcomes, compares soft-fork and hard-fork routes, and applies an
evidence-based review framework to Spiral's recent designs. The first draft
includes a dated [cohort ledger](The-BIP-Sieve/cohorts.json) and pinned
[source index](The-BIP-Sieve/references.json).

