# BitVM sibling covenant research

Research proposal for a **soft-fork** tapscript opcode, `OP_CHECKSIBLINGVERIFY`, to bind each BitVM principal UTXO to a connector created by the same transaction. This is an unsubmitted BIP draft, with **no assigned BIP number or opcode byte**.

## Proposed relationship

The opcode takes a 12-byte fixed, little-endian descriptor:

```
uint32 own_parent_vout
uint32 peer_input_index
uint32 peer_parent_vout
```

Executing at input `i`, it requires the referenced peer input `j` to exist, `j != i`, parent output positions to differ, and:

```
prevout(i).vout == own_parent_vout
prevout(j).vout == peer_parent_vout
prevout(i).txid == prevout(j).txid
```

For a fixed two-input terminal spend, the principal at input 0 checks (0,1,1), while its connector at input 1 checks (1,0,0). Both terminal branches spend both coins: delayed operator reimbursement or verified fraud recovery. Each branch additionally constrains the complete outgoing amounts and destinations using a template covenant such as draft BIP 446.

## Status and limitations

The **full five-file original research bundle** (BIP-style MediaWiki proposal, symbolic transaction model, 43 unit tests and machine-readable report) is preserved in the ChatGPT Library as `bitvm-sibling-covenant-draft.zip` (November 11, 2026). This repository directory is a concise, reviewable staging copy of the proposal and its independent minimal smoke tests. The full model's reported 43/43 tests and 552/552 rejected cross-graph substitutions are historical results from that bundle, **not tests run by GitHub CI here**.

Run the checked-in smoke tests:

```bash
python -m unittest discover -s research/bitvm-sibling-covenant -p 'test_*.py' -v
```

These smoke tests verify the proposed outpoint relation only; they do not validate real Bitcoin Script semantics or proof soundness. A production proposal needs consensus integration, Taproot leaf/key-path auditing, setup certificates, witness availability, policy/fee tests and adversarial network trials.

## Scope boundaries

- A copied connector with the same script must fail because its **parent txid** differs.
- Both settlement and disproval must consume the paired principal and connector together. Their conflicting UTXO inputs provide mutual exclusion only after confirmation.
- At payout maturity the miner may choose either valid conflicting transaction; watchtowers must get fraud evidence confirmed earlier.
- Multiple distinct admitted graph roots can still reimburse one underlying economic claim unless claim admission enforces global uniqueness.
- A setup or verifier bug is outside the proposed opcode's security boundary.
- Per-coin loss caps do not preclude correlated loss across many graphs.
- The base reserve root and all Taproot leaves must be audited for unconstrained bypasses; a NUMS internal key is needed.
- A one-output contested principal with template-only recovery is an important **baseline** against which this additional opcode must show material advantages.

## Prior art

Anthony Towns, 2025 BitVM discussion: https://delvingbitcoin.org/t/how-ctv-csfs-improves-bitvm-bridges/1591/8

Related draft BIPs: https://bips.dev/446/ ; https://bips.dev/448/ ; https://bips.dev/342/ ; https://bips.dev/346/ ; https://bips.dev/443/

See [DESIGN.md](DESIGN.md) and the standalone [smoke tests](test_sibling_rule.py).