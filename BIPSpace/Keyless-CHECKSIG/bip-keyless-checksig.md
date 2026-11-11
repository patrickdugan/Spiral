---
BIP: TBD
Layer: Consensus (soft fork)
Title: Keyless CHECKSIG: Transaction Commitments via Tapscript Unknown-Key Types
Author: Research draft (Spiral / BIPSpace)
Status: Research / unsubmitted
Type: Specification
Created: 2026-11-11
License: BSD-3-Clause
Requires: 341, 342
Optional companion proposals: 347, 360
---

# Keyless CHECKSIG: Transaction Commitments via Tapscript Unknown-Key Types

## Abstract

Define a new, explicitly selected meaning for a Tapscript unknown-key type
in the existing OP_CHECKSIG, OP_CHECKSIGVERIFY, and OP_CHECKSIGADD operations.

For this key type, a nonempty 32-byte item is interpreted as an expected
transaction-commitment digest. Consensus computes the corresponding BIP341
Taproot signature hash from the real spending transaction, and accepts that
item only when it matches byte-for-byte.

Scripts can thereby prove that a witness-derived computation authorizes the
*actual* transaction, including its dynamic outputs, without requiring any
private key or verifying a conventional signature. The application verifier
and any transparency/zero-knowledge proof live in the script, rather than
inside this proposed checking mode.

The new rule alone provides no authorization. A script that merely supplies
an arbitrary digest and calls this mode is effectively anyone-can-spend.

This is an **unsubmitted consensus research proposal**. Its selector and
key-version have no allocated semantics; it has no Bitcoin Core patch, no
network activation, and no demonstrated general STARK verifier.

## Motivation

Bitcoin's existing CHECKSIG machinery already defines a transaction commitment
with amounts, spent scriptPubKeys, outpoints, sequences and outputs.
BitVM's computing primitives can check complex claims in script, particularly
if the separate OP_CAT proposal is activated. The remaining bridge between
"this computation is authorized" and "this is the actual transaction" can
be a digest comparison using the established Taproot sighash algorithm.

This gives a clear composition target for keyless, committee-free validity
applications. For a reserve payout, script checks proof statements about a
recipient and amount, reconstructs the appropriate transaction commitment,
and checks that commitment using the new mode.

## Specification

### Scope and deployment

The new semantics apply only to Tapscript signature-opcode execution under
BIP342, when the key argument matches the dedicated TXCOMMIT key-type
selector exactly.

The prototype selector is a **33-byte research sentinel**:

~~~
TXCOMMIT_KEY = 0x02 ||
  SHA256("BIPSpace/Keyless-CHECKSIG/TXCOMMIT-draft")
~~~

This is **not an opcode assignment** and not an adopted key type. The current
prototype uses key_version = 0x02 to domain-separate its signature hash from
BIP342 0x00 and BIP118's proposed 0x01. Allocation and collision review
with other unknown-key-type proposals would precede a real BIP submission.
Unmatched unknown key types retain existing BIP342 behavior.

### Exact verification rule

For OP_CHECKSIGVERIFY on the selected key type:

1. Pop the key and the candidate digest as a normal BIP342 signature check.
2. If the candidate is empty, apply BIP342's existing empty-signature behavior
   (CHECKSIG pushes false, CHECKSIGVERIFY aborts, CHECKSIGADD leaves n).
3. Otherwise count the invocation against the existing per-input Tapscript
   sigops budget, decrementing that budget by 50.
4. Require the candidate to be exactly 32 bytes. An invalid length MUST abort
   execution immediately.
5. Compute the actual digest using the BIP341 TapSighash tagged hash with
   epoch 0x00, SigMsg(SIGHASH_DEFAULT, ext_flag=1), the executing tapleaf hash,
   TXCOMMIT key_version, and the last OP_CODESEPARATOR position.
6. If the candidate differs from the actual digest, execution MUST abort.
7. Otherwise, process the check as a successful nonempty BIP342 unknown-key
   check: OP_CHECKSIG yields true, OP_CHECKSIGVERIFY proceeds and OP_CHECKSIGADD
   increments its integer by one.

In compact form:

~~~
if key != TXCOMMIT_KEY:
    use BIP342 existing rules
elif candidate == empty:
    use BIP342 existing empty-signature rules
else:
    charge 50 existing BIP342 sigops budget
    require len(candidate) == 32
    expected = TapSighash(
        0x00 || SigMsg(SIGHASH_DEFAULT, ext_flag=1) ||
        tapleaf_hash || TXCOMMIT_key_version || codesep_pos_le32)
    require candidate == expected  # failure ABORTS
    continue as successful nonempty signature opcode
~~~

SIGHASH_DEFAULT is fixed for this initial design, with the effect of ALL
outputs and ALL inputs. No ANYONECANPAY, SINGLE, NONE, or ANYPREVOUT mode
is permitted for the selected key type. Annex handling follows BIP341,
including its input-witness commitment. Taproot's existing SHA256 message
component caches are eligible for reuse.

P2MR inputs, should BIP360 activate, follow that proposal's definition of
the Tapscript common signature message. The prototype uses script-path
ext_flag 1 and no annex.

The rule makes **no changes** to ordinary 32-byte Schnorr public keys.

### Why failure is immediate

BIP342 accepts nonempty candidates for unknown key types. A proposed soft
fork must restrict this acceptance set. Returning false would allow an older
script construction using OP_NOT to turn a newly rejected candidate into
a successful branch, creating a new accepted spend. An invalid nonempty
TXCOMMIT candidate therefore fails script evaluation immediately.

This distinction is normative for CHECKSIG, CHECKSIGVERIFY and CHECKSIGADD.

### Security of the digest

BIP341 covers the transaction's input outpoints, amounts and scriptPubKeys,
sequences and ordered outputs when using SIGHASH_DEFAULT.

The commitment also binds the executing script path through the tapleaf hash
and code-separator position. A separate key_version prevents accidental
digest reuse between different signature-checking domains.

The script supplies an **expected** digest, which can be computed from a
witness-provided BIP341 message or from a proof verifier's public result.
The new mode compares that digest to consensus's **actual** transaction
message. Witness information may describe a false transaction, but the
check will reject the false description, subject to SHA256 security.

The rule does not parse or verify an application-specific transaction
statement. The surrounding script is responsible for establishing that the
recipient, value and successor state described by the witness meet policy.

## Keyless output construction

This proposal does not require changing Bitcoin's existing output format.
For a vault with no key path, use a separately activated script-only output
such as BIP360 P2MR.

BIP360's current P2MR draft treats depth-zero script trees as anyone-can-spend.
Use a two-leaf tree, with one executable verifier leaf and one permanently
unspendable OP_RETURN leaf. The resulting commitment is a TapBranch root,
with no key path or private key required for reserve authorization.

The prototype composes:
- BIP341 BIP342 TapSighash and CHECKSIG rules (deployed),
- a newly defined TXCOMMIT unknown-key mode (unactivated),
- BIP347 OP_CAT in Tapscript (separate proposal, not activated),
- BIP360 P2MR (separate draft, not activated).

No application should fund this construction before every needed consensus
change has activated. Under the current BIP342 rules, nonempty arguments
to this unknown public-key type are accepted without digest verification.
The tests deliberately demonstrate this difference.

## Executable dynamic-output experiment

The reference Script, generated by reference.py, is 177 bytes.

At funding time the script commits to a Merkle root covering two allowed
32-byte x-only recipient keys, and to a fixed payout value of 948,400 sats.
A funding output of 949,400 sats is created, leaving a 1,000-sat miner fee.

At spending time, the witness supplies:

~~~
[TapSighash prefix, TapSighash suffix, recipient key,
 Merkle sibling hash, direction]
~~~

The script:
1. Verifies the recipient's SHA256 Merkle membership using OP_CAT and OP_SHA256.
2. Constructs an actual serialized CTxOut (8-byte value, 1-byte script size,
   P2TR OP_1 PUSH32 and selected recipient).
3. Computes sha_outputs with OP_SHA256.
4. Reconstructs the 212-byte BIP341 script-path signature message using
   witness-provided prefix and suffix bytes.
5. Calculates the TapSighash tagged hash with OP_CAT and OP_SHA256.
6. Passes the resulting 32-byte digest to TXCOMMIT CHECKSIGVERIFY.
7. Returns OP_TRUE.

The prefix/suffix contain transaction data supplied *after funding*, including
the funding outpoint and a tapleaf commitment. They cannot be hard-coded at
funding time without creating a circular self-reference. A dishonest prefix
cannot authorize another transaction because the final digest is compared
to consensus's actual TapSighash.

The script permits either funded-allowlist recipient to be selected after the
reserve exists. It thereby tests true transaction-output targeting through
the proposed digest-checking interface. It is intentionally limited to one
output and a two-key allowlist.

The recipient keys are normal spending keys for the final payout. "Keyless"
refers to the reserve's **authorization**. It does not remove a recipient's
need to control their destination or prove the application policy.

### A future transparent proof verifier

A general L1 validity application would replace the Merkle membership check
with an on-chain verifier for a transparent proof. That verifier would establish,
for example, that M16's payment is authenticated, that sender derivation and
pricing are correct, that a claim was not served previously, and that the
actual transaction commitment contains the required payout and updated state.

The proof verifier's accepted public digest must be the same digest consumed
by TXCOMMIT. A proof of an unrelated public value has no authorization force.

The proof system, verification transcript, statement format, historical-chain
binding, script size and block validation cost are unsolved deployment tasks.
Compiling a working STARK verifier into Script is substantially more work
than this single new CHECKSIG mode. The existing public STARK-in-Script
efforts should be measured before feasibility claims.

## Resource bounds

TXCOMMIT uses a fixed amount of BIP341 signature-message hashing plus a
32-byte equality check. Every nonempty invocation is charged under the
existing BIP342 50-unit per-input budget. The new rule includes no looping
and does not invoke any application verifier.

The application verification script remains constrained by existing Tapscript
stack and witness limits. BIP347 CAT, if activated, retains the 520-byte
individual stack-item limit. Both compiled script size and proof witness
weight are constrained by the usual block weight limits.

A fixed per-check charge matches the extension's intended operational cost.
A full consensus implementation must benchmark cache behavior, repeated
invocations, adversarial late failures and mempool admission behavior.

## Prior art and security considerations

Keyless CHECKSIG is a narrower transaction-introspection primitive. It is
related to Bob McElrath's SIGHASH_NOSIG and Poelstra's Schnorr/CAT
transaction-commitment trick. BIP118 also proposes interpreting unknown
Tapscript key types; this design must not collide with its assigned syntax.

A standalone TXCOMMIT check permits any spender to pass the actual digest.
Authorization comes from surrounding Script logic and its committed program.
Any unvalidated branch, public commitment that anyone can satisfy, or
unspendable fallback mistakenly made spendable can open the reserve.

P2MR eliminates key-path authorization in its proposed design. The verifier
or program may still contain cryptographic keys as part of a specific
application, which must be evaluated separately.

Collision resistance and the Script program's correctness are critical.
With generalized proof verification, soundness of the proof system becomes a
consensus-critical application assumption. Shared application/verifier bugs
may affect every deployed reserve that commits to those programs.

Scripts which commit the future complete spending transaction digest inside
their own funding output are generally circular: the digest depends on the
funding outpoint and the locking script. The compiled example does not do
this. It commits to policy and constructs the digest after the coin exists.

## Test vectors and implementation status

reference.py implements the BIP341 signature-message algorithm, a narrow
experimental Tapscript bytecode interpreter, P2MR two-leaf root construction,
and the compiled 177-byte example script. It implements no actual network
consensus changes or node RPC calls.

test_reference.py includes:
- all seven signature-hash checks extracted from bitcoin/bips official
  bip-0341/wallet-test-vectors.json;
- valid spends to either chosen recipient from the same simulated vault;
- outpoint, amount, sequence, version, locktime and output tampering;
- Merkle proof rejection, MINIMALIF, control-branch and 520-byte checks;
- comparison of BIP342 old unknown-key and proposed new behavior;
- key-version and annex domain-separation checks.

On 2026-11-11 all 33 tests passed in GitHub Actions. The 33 total includes
one test method which checks seven official BIP341 vectors.

Run with:

~~~
python -m unittest discover -s BIPSpace/Keyless-CHECKSIG -p test_reference.py -v
python BIPSpace/Keyless-CHECKSIG/reference.py
~~~

## Work before a production candidate

A Bitcoin Core validation patch is needed to test the proposed unknown-key
selector and abort semantics against real Script validation. The separate
OP_CAT and P2MR proposals would need compatible regtest activation. The demo
must then be repeated with actual funded outputs, mutated outputs, dust/fee
tests and adversarial witness cases.

Replacing the two-key proof with a transparent cryptographic computation
verifier is the next research milestone. Its worst-case verification cost,
script size and on-chain proof size determine whether this design is
practical for a true keyless L1 BitVM.

## References

- BIP341: https://bips.dev/341/
- BIP342: https://bips.dev/342/
- BIP347 OP_CAT: https://bips.dev/347/
- BIP360 P2MR: https://bips.dev/360/
- BIP118 ANYPREVOUT (unknown-key extension): https://bips.dev/118/
- Bitcoin official wallet test vectors:
  https://github.com/bitcoin/bips/blob/master/bip-0341/wallet-test-vectors.json
- SIGHASH_NOSIG proposal:
  https://mirror.b10c.me/lists/bitcoindev/CAD5xwhjLPQDOg4vA1a-NbFn4kDm%2Ba6ZYCmvQKkfDjaPzRH%2BjMA@mail.gmail.com/T/
- Andrew Poelstra, CAT and Schnorr tricks:
  https://www.wpsoftware.net/andrew/blog/cat-and-schnorr-tricks-i.html
