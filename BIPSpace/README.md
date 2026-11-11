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
