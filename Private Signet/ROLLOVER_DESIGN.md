# DLC ownership rollover: confirmed UTXO transition

Status: runnable Signet integration experiment added to PR #20. Test verdicts
are reported by the Signet CI job and local receipts when the runner executes.
The implementation uses stock Bitcoin Core Script and Taproot. It is
independent of the experimental TXCOMMIT, OP_CAT and P2MR patch.

## Research question

Can Carol take over Alice's DLC position after the original funding
output exists, such that Alice's already signed CET can no longer settle
after the transfer confirms?

Yes, on a chain where the old funding UTXO is consumed by a confirmed
transfer and the new funding UTXO uses Carol's authorization key.
This is an **on-chain cooperative rollover**. It does not solve private,
instant, permissionless off-chain DLC transferability.

## Transaction construction

Given an original funding output:

- UTXO F: 1,000,000 sats, Taproot script requires Alice and Bob signatures.
- Oracle event and outcome CETs are fixed, with Alice as the winning
  recipient in the ALICE_WINS branch.
- Alice's old CET is pre-signed and executable while F remains unspent.

After Alice agrees to sell to Carol and Bob participates:

1. Alice and Bob sign transaction R, spending F to a new Taproot output N
   with the Carol/Bob 2-of-2 script. R pays a 1,000-sat fee.
2. Carol and Bob jointly produce new oracle-adaptor pre-signatures for
   outcomes of N before R is broadcast. The new contract has 999,000 sats,
   paying 997,000 sats at settlement (a separate 2,000-sat fee).
3. Broadcast R, then mine a signed private-Signet block containing R.
   Both nodes verify F is spent and N exists with the intended script.
4. Submit Alice's original valid CET again. It attempts to spend F.
   Both nodes reject it as an already-spent input on the confirmed chain.
5. Try an Alice/Bob signature pair on N. The script now requires Carol's
   authorization, so the forgery is rejected.
6. Complete the new Carol/Bob adaptor CET using the same oracle outcome,
   mine it, and confirm the payout to Carol on both nodes.

Illustrative state graph:

~~~text
F: Alice/Bob DLC funding (1,000,000 sats)
     |
     |  R: Alice + Bob signatures, 1,000 sat fee
     v
N: Carol/Bob DLC funding (999,000 sats)
     |
     |  Carol + Bob adaptor CET, oracle attestation, 2,000 sat fee
     v
Carol: payout UTXO (997,000 sats)

Old Alice CET: tries to spend F -> rejected once R is confirmed.
~~~

For every signature, the BIP341 message includes the full input outpoint
and outputs. The new CET signs N as the funding outpoint, so an old CET
cannot simply be repointed at N and retain valid signatures.

## Proof boundary and adversary

- **Before R confirms:** Alice's original CET remains valid. Alice could
  broadcast it instead of R. A buyer should not unconditionally pay for
  the position before finality or a separately enforced atomic exchange.
- **After R confirms:** the old F input has been consumed, so a block
  trying to include the stale CET would violate Bitcoin's UTXO spending
  rules on that chain. The new funding script excludes Alice's key.
- **After a chain reorganization:** an alternate chain where R was not
  confirmed may again permit the old CET. Choose a confirmation threshold
  appropriate to the economic value; one block in this lab is a functional
  proof, not commercial settlement finality.
- **Bob's cooperation:** required for rollover and for new CET pre-signing.
  Bob can withhold agreement; Carol must receive and verify the new CETs
  before relying on the re-funded position. No proof of fair atomic payment
  from Carol to Alice is included.
- **Oracle:** the same synthetic oracle signs both epochs; no new oracle
  authenticity claim is made.
- **Script/key safety:** deterministic fixture keys and a locally controlled
  mining signer are valid for testing only. Deployments need independent
  key generation, reviewed crypto libraries, and actual fee management.

## Verification and files

- [rollover.py](ab/rollover.py): fresh Carol/Bob Taproot script, funded
  successor CETs, old funding-output transfer signatures, stale-key attack.
- [run_signet_rollover.py](ab/run_signet_rollover.py): three mined Signet
  stages and RPC receipts for Alice's stale CET before/after rollover.
- [test_rollover.py](ab/test_rollover.py): BIP341 message/signature
  checks and private-key exclusion, runnable without Core.
- CI uses the existing isolated Signet created by the preceding lab job.
  The output receipt kind is signet-dlc-ownership-rollover.

To run against an initialized and funded local private Signet:

~~~bash
python "Private Signet/ab/run_signet_rollover.py"
python "Private Signet/lab.py" agree
~~~

The critical observable is **old_CET_allowed_before_rollover = true**,
**old_CET_rejected_after_rollover = true**, **former_holder_keys_rejected
= true**, and **confirmed_new_owner_payout = true** on both Core nodes.

These results establish a baseline for designing an eventual keyless
transferable DLC. A script-only design that allows the same public witness
to spend an unchanged UTXO has no native way to learn that ownership moved.
A strong off-chain protocol would need an enforceable state update or
revocation mechanism, such as a Lightning-style penalty/revocation design,
a new on-chain state transition, or a separately defined covenant
mechanism, each with explicitly tested security assumptions.

Bitcoin itself establishes the one-spend property. Any additional
keyless transfer claim should reproduce that property under its own
authorization and state-transition rules.
