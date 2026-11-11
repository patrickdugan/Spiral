# BIP TBD: ProvenSpend, origin-certified proof programs with dynamic outputs

| Field | Value |
| --- | --- |
| Status | Unsubmitted research draft, 2026-11-11 |
| Layer | Consensus; candidate soft-fork construction |
| Name | P2PROOF / OP_PROVENSPEND |
| Allocation | BIP number, opcode and witness version unassigned |
| License | BSD-3-Clause |
| Readiness | Semantic model only; cryptographic profile and wire implementation outstanding |

## Abstract

A proof-locked output commits to an application program, its immutable policy,
a unique origin and current state. Consensus checks a proof when the output is
first funded. Every spend proves a valid transition under that same program,
bound to the actual spending transaction. Recipients and amounts can be computed
from authenticated evidence after funding.

The logical primitive is:

```
OP_PROVENSPEND(program_id, phase, actual_context_digest, receipt)
```

Nodes perform bounded proof verification. Provers execute application programs
off chain. This draft uses a dedicated witness-output type plus an output-creation
validation hook. A spend-time opcode alone cannot enforce creation-time proofs.

The cryptographic profile is not selected or implemented. Consequently this is
not an activation-ready BIP or a claim of a working native ZK Bitcoin verifier.

## 1. Commitment established at origination

An output contains a 32-byte commitment to:

```
D = (format_version, verifier_profile, program_id, policy_hash, origin_id, state_root)
scriptPubKey = OP_<unallocated witness version> PUSH32 H_tag(D)
```

The current model uses witness version 2 as a byte-layout placeholder. That
number is not an allocation. Such scripts are unsafe to fund on existing Bitcoin.
The output type has no key-path escape hatch. An application can implement a
recovery rule in its committed program, subject to the same proof requirement.

One activated transparent verifier profile fixes its algorithm, verification
material and all proof-format/security parameters. The application supplies a
program commitment, not executable verifier code for a node to run. The profile
must authenticate that program commitment and its public result. Any variable
verification material must be strictly capped and authenticated under the profile.
Network retrieval of verification keys is excluded.

The first creating transaction must contain an `INIT` receipt proving that the
committed program's initialization entry point accepts this exact output,
including its value, policy and initial state. An initialization proof establishes
that relation; assurance about the program's intended behavior still requires
review of the program and proof system.

Define an origin independently of the creating transaction's future txid:

```
origin_id = H_tag(chain_domain || first_funding_outpoint || new_output_index ||
                  program_id || policy_hash || nonce)
```

Those fields exist before proving or signing. Consensus recomputes this value.
The funding outpoint can be consumed once on a valid chain. The v0 layout permits
one proof origin per initialization transaction.

## 2. Explicit origination and spending rules

The proposed v0 transaction-level rules are deliberately restrictive:

- `INIT` has no P2PROOF input and exactly one P2PROOF output. Input 0 is native
  Taproot and carries the initialization envelope in its BIP341 annex. Normal
  Taproot authorization remains required. Every P2PROOF output creation must
  be accounted for by INIT or STEP validation; merely funding a commitment fails.
- `STEP` has exactly one P2PROOF input, at input 0, and at most one P2PROOF output.
  Input 0 carries the proof envelope as its new witness type. Any successor has
  the same profile, program, policy and origin. Its state and value can change
  as authorized by the program. Zero successors represents a terminal transition.

Other inputs are restricted to native SegWit v0 or Taproot in this first design.
Their normal authorization is checked independently. Input scriptSigs are empty.
The proof program must authorize the entire allocation of value, including any
sponsor contribution, fee and change. The IOB model exercises the simpler
single-input, two-output case.

Coinbase creation of these outputs is excluded in v0. Deployment must define the
activation height and handling of preactivation unknown-version outputs. For the
strict origination property, proof spends require a creation height at or after
activation, which the UTXO view already records. No new global program registry
is proposed. Compatibility analysis of this rule remains required.

### Envelope placement

Use a domain-tagged canonical envelope. For INIT it is carried in input 0's
Taproot annex, beginning with `0x50` as required by BIP341. For STEP the dedicated
witness program defines its own single envelope item and strict size limit.
The envelope opens the relevant descriptors and includes the phase, successor
index, chain anchor, initialization nonce, public update journal and proof.

A native witness type allows proof data to have an explicitly specified bound
without pretending it fits inside the ordinary 520-byte Script stack-element
limit. Exact wire encoding and allocation remain outstanding. The Python model
uses length-prefixed typed objects and does not parse Bitcoin witness bytes.

Every P2PROOF transaction carries one receipt under the fixed profile. STEP's
receipt certifies the successor's valid initialization from the prior state;
there is no second constructor proof per transition. Envelope ambiguity, trailing
bytes, duplicate fields and noncanonical encodings must fail before verification.

## 3. Transaction-bound public statement

Consensus constructs the public statement from its transaction and UTXO views.
The spender cannot supply an unauthenticated replacement for those views.

```
C = H_tag(
    chain_domain,
    phase,
    transaction_version, locktime,
    all input outpoints, input amounts, spent scripts, sequences,
    all output amounts and scripts in order,
    old descriptor, new descriptor or terminal marker,
    successor index,
    anchor height and hash,
    origin nonce, public update journal
)
```

All encodings are length-delimited. Input amounts and scripts come from the
validated UTXO view. The receipt must authenticate the pinned program ID, correct
entry point, successful exit and exact digest C. A proof that merely authenticates
an application-supplied output hash is insufficient.

Proof bytes and all authorization witnesses are excluded from C. Otherwise the
receipt would need to commit to itself. INIT's Taproot signature is produced
after the receipt and commits to its annex under existing Taproot rules. A proof
may be publicly rebroadcast with unchanged authorized effects. Changing a payout,
fee allocation or input requires a proof for the changed context.

Full transaction binding makes adding inputs or changing fees require new proving.
A program can preauthorize a usable fee/CPFP output. Broader selective binding is
excluded from this version to keep the authorization boundary auditable.

## 4. Chain evidence and actual consensus history

Payment inclusion is evaluated against an explicitly selected ancestor of the
block being validated. Consensus checks `(anchor_height, anchor_hash)` against
that block parent's active ancestry and supplies it to the receipt statement.
A mempool uses the current candidate parent's ancestry and revalidates after reorg.
The anchor must be a prior block; same-block external payment claims are excluded.

The application proof authenticates payment inclusion and confirmation depth
relative to that anchor. A separately proved chain with sufficient work is not
an authoritative canonical-chain oracle. The current M16 integration needs this
binding when used inside the new guest.

This rule introduces an active-ancestry lookup during validation. Its implementation
must remain deterministic during historical replay, including assumeutxo and
reorg paths. A moving wall-clock height or external API is unsuitable.

## 5. Dynamic output targeting for In-and-Out-Burger

The new application program authenticates the inbound payment and its sender
under the existing IOB rules. A witness-derived sender key requires authenticated
witness-commitment evidence. The program computes the tagged tweak:

```
t = int(tagged_hash("IOB/payout-key", payment_txid_internal || vout_le32 || P))
P_prime = P + t*G
```

The current Spiral implementation rejects exceptional `t == 0` or `t >= n` and
an infinite result. The guest must match that behavior exactly. For a compressed
P2WPKH sender, it derives `0 <HASH160(P_prime)>`. The price follows the committed
menu, with explicitly specified integer rounding and fee rules.

The application checks that the actual transaction output has the derived script
and priced amount. It also checks every remaining output, reserve balance and
miner fee. The model exercises a single high-tier menu: 940,000 inbound sats at
1.01, minus 1,000 sats, yields a 948,400-sat payout. It also tests a different
payment and key yielding a different permitted destination.

The real guest must support every sender form it advertises. The model covers
compressed P2WPKH only. It assumes payment authentication through a labeled test
object and performs no SPV, M16 or witness-commitment verification.

This enables direct customer payout from the reserve when the program allows it.
An operator can generate and relay the proof without holding a discretionary
reserve-spending key. Operator reimbursement can be another committed program
relation covering both legs and a uniquely bound claim.

## 6. Replay resistance across the reserve

Transaction binding prevents reuse of a receipt on another spending transaction.
A persistent claim history prevents generating a fresh receipt for the same
payment. These are separate properties.

For the IOB application:

```
N = H_tag(origin_id || inbound_payment_outpoint)
require N absent from old_claim_root
new_claim_root = insert(old_claim_root, N)
```

The application checks membership/nonmembership and the update. Consensus pins
the state through the currently unspent proof output and its authorized successor.
INIT starts from the approved empty state. The origin and program remain immutable.

A valid chain contains at most one live state output per origin in v0: INIT binds
its origin to a one-time funding outpoint and creates one state; STEP consumes
one state and creates at most one successor. This induction assumes collision
resistance and normal UTXO double-spend validation.

Evidence must also be bound to its intended origin. Independent origins can each
have empty claim histories. The production IOB guest therefore needs an
origin-specific deposit script or an authenticated explicit origin tag in the
payment. For a derived deposit script, the policy commits to a base key and
derivation rule; the script is computed from origin_id afterwards. Including
that derived script inside the origin hash would introduce a circular commitment.
Merely salting the nullifier with an origin does not prove that the payment
belongs there. The model's `AuthenticatedPayment.origin` assumes that
association has been established and tests rejection of a mismatch.

The current desk's shared menu address and local JSON journal do not provide
these properties automatically. They need migration in a native proof-vault path.

Public journal updates must let an independent prover reconstruct the authenticated
claim set. The production accumulator and data-availability format remain to be
specified. The model uses a sorted-set hash solely to test the state relation.

This version serializes spends through one state UTXO. Batching can process many
payments in one transition. Independent reserve shards would require a design
for mutually exclusive claim assignment or shared nullifier-state consumption;
this draft makes no sharding-throughput claim.

## 7. Fixed, bounded verification

A consensus profile must specify exact maximum sizes, algebraic domains, query
counts and recursion limits, including strict rejection of malformed values.
Verification has a worst-case bound determined by that profile. The proof carries
no authority to select its own security parameters or resource charge.

Every INIT and STEP consumes a fixed profile-defined verification charge.
The block must satisfy a separate aggregate proof-verification budget, with
ordinary block weight and signature limits still applied. Charge is checked
before expensive verification. The profile also bounds peak memory.

Mempool protection needs inexpensive structural checks, bounded admission queues
and verification-rate limits. An invalid proof can advertise a large fee which
will never be paid. Fees alone do not address unmined invalid-proof flooding.
Worst-case late-failing proofs belong in the benchmark corpus.

An application that never reaches an accepted finite execution has no valid
receipt under a sound proof system. Nodes execute only the bounded verifier.
An INIT certificate cannot certify that every future application computation
terminates; future accepted spends bring their own finite-execution evidence.

The test limits of 4 KiB proof/journal, 16 inputs/outputs and one toy cost unit per
receipt are test fixtures. They have no benchmark-based consensus justification.

## 8. Cryptographic boundary and BitVM connection

The initial experimental backend candidate is a strictly pinned transparent
STARK verifier, investigated using the existing SP1/BLAKE3-wrapped M16 work.
A normative profile must freeze all required algorithms and verification material,
with audited program-ID and public-statement authentication. A library name or
package version alone does not define consensus. No trusted setup is proposed.

The outer profile can verify a receipt for an application that verifies another
proof system inside its execution. Thus a circuit or Cairo/Stwo verifier can be
application code once a sound compatible adapter exists. Bitcoin nodes would
share the fixed outer verifier. Claims about adapter costs require measurement.

The current IOB README reports a 1,099,173-byte M16 final proof. Carried verbatim
as witness data, those bytes alone use approximately 27.5% of a 4,000,000-WU
block. A new universal-wrapper receipt could have a different size. This draft
provides no compression benchmark or consensus-verifier timing benchmark.

The native path accepts a validity receipt for the payment transition. Its safety
therefore does not require a BitVM challenge window or setup-key deletion for that
spend. Garbling is optional application machinery and is unnecessary when the
receipt already proves the underlying verifier and payout rule. Any external
bridge assumptions and user-request authorization still require their own proof
relations.

Receipt validity is the consensus requirement. Witness privacy requires a
separately specified and audited zero-knowledge configuration; output amounts
and recipient scripts remain public on Bitcoin.

Proof soundness and application correctness remain security-critical. A common
verifier flaw can affect every output using that profile. Program immutability
also complicates recovery from bugs. A reviewed migration/recovery relation can
be committed initially; adding an arbitrary admin bypass changes the trust model.

## 9. Fork scope and prior art

BIP141 reserves future witness versions. Restricting a reserved version's spends,
and rejecting creating transactions which lack the required INIT receipt, can be
structured as a soft fork because upgraded nodes accept a subset of transactions.
This remains subject to a complete compatibility analysis. A hard fork is not
required merely by proof verification. Deployment is unspecified.

Actual creation-time enforcement requires output-validation changes in addition
to the spend verifier. That is a substantial consensus change. The mathematical
interface is small, while the cryptographic and implementation audit is large.
Community acceptance is unknown.

Weiji Guo's OP_ZKP proposal already describes proof-based authorization with
transaction-derived public inputs. Its 2024 discussion and Tea/Horse work explore
transparent proving and recursive-verifier designs. This draft makes no invention
claim over native proof verification or dynamic proof-based spending.

Its proposed scope is an explicit INIT/STEP lifecycle, authenticated output
commitments, a fixed cost profile, canonical-chain anchoring and single-lineage
replay state for Spiral's dynamically derived payouts.

BIP443's state-carrying outputs are adjacent prior art. The fixed templates in
BIP446 concern a different component; this proposal carries its own transaction
binding and does not require BIP448 to enforce the described dynamic relation.

## 10. Work required before an implementation claim

1. Specify and independently review a real transparent verifier profile, including
   adversarial cost bounds and cross-platform deterministic verification vectors.
2. Implement output-origin checks, the exact envelope parser, ancestry binding,
   activation handling and proof-cost accounting in a Core regtest fork.
3. Build the IOB guest with authenticated sender evidence, the actual menu,
   origin-specific payment binding and a reconstructible nullifier accumulator.
4. Replace the test oracle with real generated INIT and STEP receipts. Run copied
   and mutated proofs against Core, including cross-origin fresh-proof attempts.
5. Measure proof size, proving latency, verifier worst-case time and memory,
   fee-bumping behavior and independent-prover recovery from the public journal.

## Sources checked 2026-11-11

- BIP141: https://bips.dev/141/
- BIP341 (annex and signature message): https://bips.dev/341/
- BIP342 (Script limits and upgrade semantics): https://bips.dev/342/
- BIP443: https://bips.dev/443/
- OP_ZKP initial author proposal:
  https://www.mail-archive.com/bitcoin-dev%40lists.linuxfoundation.org/msg12601.html
- OP_ZKP 2024 author update: https://groups.google.com/g/bitcoindev/c/YEXcac4FMGc
- Tea/Horse author repository: https://github.com/opzkp/tea-horse
- Spiral IOB implementation: ../../README.md and ../../iob/payout_key.py

## Model result

55 tests pass. The suite uses an explicitly ideal receipt oracle. It demonstrates
modeled origin binding, transaction binding, dynamic public-key-derived targets,
state replay rejection and test-budget accounting. It establishes no cryptographic
soundness or real Bitcoin consensus behavior. The default backend fails closed.
