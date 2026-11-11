# OP_CHECKSIBLINGVERIFY: preliminary soft-fork design

**Status:** unsubmitted proposal, experimental semantics.

## Abstract

Introduce a restricted tapscript opcode that requires two input outpoints in the spending transaction to refer to different outputs of exactly the same funding transaction. This enables one-shot BitVM withdrawal graphs to bind a reserved principal to the precise dispute connector created with it. Template commitments separately constrain settlement and challenge recovery.

## Motivation

Template-based covenants fix outputs, sequences, locktime and other transaction fields while leaving the selected funding outpoints unspecified. This permits rebinding. The proposed sibling rule addresses that narrow gap and may reduce pre-signature and key-erasure ceremonies where a finite graph can be prescribed entirely by consensus constraints. The same-parent construction was discussed by Anthony Towns in 2025. The design's novelty and deployment value require further review.

## Opcode

Witness script pushes a **constant** twelve-byte descriptor `d` before the proposed opcode:

| Offset | Bytes | Meaning |
| --- | --- | --- |
| 0 | 4 | own outpoint's output index, unsigned LE |
| 4 | 4 | peer input index in spending transaction, unsigned LE |
| 8 | 4 | peer outpoint's output index, unsigned LE |

Let the script currently execute on input `i`, and let `j` equal the peer index. It fails if the descriptor length differs from 12, `j` is out of range, `j == i`, or the declared output indices are equal. Otherwise it succeeds precisely when:

```
T.vin[i].prevout.n == own_vout
T.vin[j].prevout.n == peer_vout
T.vin[i].prevout.hash == T.vin[j].prevout.hash
```

All comparisons use the consensus transaction's actual previous-output identifiers. No parent txid is embedded in script. No transaction input introspection beyond the two outpoints is authorized by this predicate.

### Candidate transaction layout

```
Assert:
  vout0: principal P, protected script V
  vout1: connector/bond B, protected script C
  vout2: optional anchor

Settle:
  vin0 = Assert:0   // V enforces (0, 1, 1)
  vin1 = Assert:1   // C enforces (1, 0, 0)
  vout*: fixed settlement amount(s) and beneficiary

Disprove:
  vin0 = Assert:0
  vin1 = Assert:1
  witness: authenticated disproof
  vout*: fixed recovery and bond-policy output(s)
```

The settlement branch checks a relative delay beginning when Assert confirms. The recovery branch checks a correct claim-bound fraud witness. Both coin scripts must enforce compatible fixed destination templates, and branches must not permit mixed settlement/recovery templates. For each path, their input-index-specific template hashes must agree on the complete transaction. Separate anchor fee sponsorship prevents fees from consuming protected amounts.

## Required application invariants

1. Funding creates V and C simultaneously with the correct scripts, denominations, and claim commitment.
2. The Reserve-to-Assert path authenticates the statement and evaluable proof transcript before starting the dispute clock.
3. The effective Taproot program has no unconstrained key-path or alternate-leaf bypass.
4. A disproof consumes both V and C, returns principal to an authorized destination, and closes the graph.
5. The claim admission layer prevents distinct instances from paying the same economic liability.
6. Challenger data and compute are available with enough time for confirmation before the delayed spend becomes valid.
7. Recovery preserves any outstanding liability of the desk or bridge.

## Invariants and their boundaries

If V's required peer is C from the same Assert transaction, a connector copied into a different parent transaction cannot satisfy the equality, even if its script matches byte-for-byte.

Settle and Disprove spend the same UTXOs, hence no valid chain can contain both confirmed transactions. At maturity the miner may choose the first confirmed conflicting transaction; this construction does not guarantee challenger inclusion.

If multiple root transactions independently authorize claims for the same payment, the sibling predicate accepts the individual graph pairings. Global uniqueness needs a separate shared-state mechanism or a proven admission process.

## Baseline comparison

A template covenant may put principal directly in a contested output, with recovery and delayed settlement branches spending that one coin. This may achieve the same single-claim safety without a new opcode. Deployment requires showing measurable benefit of the two-output graph, such as lower witness size, simpler funding authorization, or separation of bond accounting.

## Activation and verification work

Specify an available OP_SUCCESSx slot under BIP 342 and develop a Bitcoin Core consensus implementation with updated tapscript cost and validation tests. Run differential transaction-vector testing, full script-tree enumeration, transaction package/RBF/pinning adversaries, witness-size checks, and reorganization simulations. Extend the model to real garbling/proof verification and end-to-end fund conservation. Nothing in this design document constitutes activated Bitcoin consensus.