OP_CHECKSIBLINGVERIFY research draft
Prepared November 11, 2026

The specification is in bip-XXXX-checksiblingverify.mediawiki.
It is an unsubmitted proposal with no assigned BIP number or opcode byte.

The proposal checks whether two inputs spend specified outputs of the same
creating transaction. A reference BitVM profile combines that relation with
fixed output templates. Settlement and fraud recovery each consume the exact
principal/connector pair.

Run the executable model's tests with Python 3.11 or later:

    python3 -m unittest -v test_sibling_model.py

See model_report.json for the executed checks and their limits.

The model covers outpoint identity, transaction templates and abstract graph
transitions. Its cryptographic and admission predicates are explicitly ideal.
Real garbling, Taproot evaluation, node consensus validation and network relay
require implementation and testing against the actual Bitcoin/BitVM software.

Two scope boundaries are deliberate executable examples: separate funded
graphs can reimburse a duplicate economic claim if admission permits it; a
miner can choose the delayed payout once it matures if disproval has yet to
confirm. Every claim of safety in the draft carries those stated assumptions.

The same-parent construction is credited to Anthony Towns's April 2025 BitVM
discussion. The draft also includes a template-only merged-output baseline
for evaluating whether this specialized opcode earns its deployment cost.
