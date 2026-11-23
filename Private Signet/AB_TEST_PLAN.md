# Keyless-CHECKSIG / BitVM A/B protocol

Research scope: compare a vanilla Bitcoin/BitVM or DLC spend against the
proposed TXCOMMIT construction while keeping all coins and keys isolated.
A successful local custom-Signet block establishes that **our own authorized
signer included and our own validators accepted** a transaction. It does
not establish permissionless relay, outside miner interest, broad consensus,
or application security.

## Prerequisites and gates

1. Pin Bitcoin Core binary commit/tag and version, the official Signet miner
   source SHA, the exact BIP revision, transaction generator SHA, and any
   experimental Bitcoin Core consensus patch. Record node command lines,
   difficulty settings, network challenge, activation condition, tip,
   parent outputs, transaction weights and mempool settings.
2. Stock Core reference: fund and settle one fully signed vanilla test-only
   spend with realistic fees. Capture raw transaction bytes and txid.
   Confirm from two independent nodes at a specific block height.
3. Modified Core candidate: prove the actual TXCOMMIT digest computation
   in **consensus script validation**. Test every signature opcode variant,
   empty candidates, bad lengths, incorrect digests, and sigops charging.
   Also test ordinary Schnorr and unrelated unknown-key behavior unchanged.
4. Explicitly deploy *separate* experimental OP_CAT / P2MR patches if the
   transaction fixture uses them. Test their actual activation state.
   A reference.py interpreter cannot substitute for node enforcement.
5. Run matched instances with identical funding values, outputs, fee
   budgets and transaction-selection policy. Log the point where each
   version authorizes the payout, with independently generated recipient
   and amount fixtures.
6. Resolve conflicts between the mempool and block validation by collecting
   testmempoolaccept results, attempted relays, block templates and an
   actual validation result. Failures must retain the full RPC error message.
7. Demonstrate old-node/new-node soft-fork compatibility. A valid upgraded
   spend must be accepted by both; a forbidden nonempty TXCOMMIT candidate
   should be accepted by old consensus and rejected by upgraded consensus.
   Policy rejection by an old mempool does not by itself prove a fork.
8. Run adversarial fixtures: wrong output, wrong amount, wrong input
   outpoint, altered sequence/locktime, wrong tapleaf, annex and
   code-separator cases, incorrect Merkle sibling, missing proof, invalid
   digest length, replay and deliberately unconstrained digest.
9. Compare script bytes, witness weight, fee at fixed sat/vB, validation
   wall time, setup key count, required trust assumptions, and rejection
   reasons. Report unsuccessful trials and discovered consensus hazards.

## Required receipt fields

| Field | Interpretation |
|---|---|
| bitcoin_core_sha, patched_core_sha | Exact validator implementations |
| proposal_sha, test_generator_sha | Frozen experiment artifacts |
| signet_challenge, genesis_hash | Custom network identity |
| activation_height | Which proposed rules were enforced |
| node_name, node_version | Role and software revision |
| funding_txid, spending_txid, raw_tx_sha256 | Exact transaction provenance |
| tip_before, tip_after, accepted_in_block | Objective consensus observation |
| mempool_allowed, reject_reason | Policy and preflight observations |
| script_bytes, weight, vsize, sat_per_vbyte | Byte and fee costs |
| claimed_authorization, independent_verifier | Proof soundness boundary |
| test_case, fixture_seed, result | Reproducible A/B outcome |

The current lab.py emits local mining/probe receipts, satisfying only a
subset of these fields. The full schema is a **target**, to be implemented
once real raw BitVM/DLC fixtures and patched Core binaries exist.

## Experiment matrix

| Arm | Validator | Expected significance |
|---|---|---|
| V0 | Stock Core private Signet | Vanilla settlement and basic relay/inclusion |
| V1 | Stock Core private Signet | TXCOMMIT-style unknown key may pass without authorization, illustrating current behavior |
| K1 | Patched Core regtest | Valid constrained digest accepted |
| K2 | Patched Core regtest | Mutated commitment causes immediate abort |
| K3 | Patched Core regtest | Unconstrained digest demonstrates anyone-can-spend hazard |
| K4 | Patched custom Signet | Correct candidate included by authorized miner and independently validated |
| C1 | Old and patched validators | Old/new acceptance set and policy divergence |
| D1 | End-to-end DLC | Payout transferability and assumptions measured |

Keep regtest and signet chain identity separate. If old and new validators
split, preserve both tips and identify the exact consensus reason.
For experimental fork activation, publish the patch and configuration that
make validation rules deterministic. Never expose a seed key or claimed
vault authorization before negative fixtures pass.

## Follow-up engineering backlog

- Port the BIPSpace reference vectors into Bitcoin Core CScript tests,
  with no scripting-model shortcuts.
- Implement and audit the TXCOMMIT unknown-key selector and abort behavior;
  reject any unallocated selector collision with other proposals.
- Add real dynamic-output and allowlist fixtures tied to actual funded
  UTXOs, then a BitVM challenge/response and a DLC settlement.
- Record a Bitcoin Core patch SHA and capture CI output for kernel/
  functional tests with predictable activation.
- Add a patched Signet node and adversarial block construction once regtest
  verifies the consensus rule.
- Compare Bitcoin and Litecoin only after the Bitcoin baseline runs are
  stable, keeping chain-specific policy and activation separate.

Source BIP: [Keyless-CHECKSIG](../BIPSpace/Keyless-CHECKSIG/bip-keyless-checksig.md).
