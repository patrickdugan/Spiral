# OP_CHECKSIBLINGVERIFY: BitVM sibling covenant research

Unsubmitted Bitcoin consensus soft-fork proposal, prepared November 11, 2026.
This is an experimental design for `in-and-out-burger/`, not an activated BIP
or a production-safe BitVM bridge.

The proposed tapscript opcode requires the current input and a chosen peer
input to spend specified outputs created by the **same transaction**. The
one-shot BitVM profile binds a principal vault UTXO to its dispute connector.
A fixed output template governs settlement and fraud recovery. Both terminal
transactions consume both coins.

## Files

- [BIP draft](bip-XXXX-checksiblingverify.mediawiki): consensus semantics,
  motivation, security argument, transaction graph, deployment limits, and
  alternative designs.
- [Reference model](sibling_model.py): symbolic UTXOs, non-witness txids,
  BIP 446 template hashing, and abstract terminal transitions.
- [Adversarial tests](test_sibling_model.py): identity substitution,
  unauthorized payout, recovery, and timing properties.
- [Model report](model_report.json): recorded evidence and assumptions.
- [Original bundle notes](README.txt): provenance and reproduction.

## Run

From this directory with Python 3.11+:

```bash
python3 -m unittest -v test_sibling_model
```

The original model passed 43 tests, including an exhaustive 24-by-24
principal/connector substitution check: 24 intended pairs accepted and
552 cross-graph pairs rejected.

## Security boundary

The reference uses ideal cryptographic/setup predicates. Bitcoin Core
script execution, real garbling, proof verification, fee relay, censorship
and data-availability scenarios have not been tested. Separate graphs can
still reimburse the same economic claim if admission permits it. At
settlement maturity, the valid transaction mined first wins.

The BIP number, opcode byte and activation mechanism remain unassigned.
A template-only merged-coin construction should be benchmarked before
any new consensus opcode is pursued.
