# The BIP Sieve

**How Bitcoin Upgrades Earn Consent**

Version 0.1 is a research paper dated 13 November 2026. It examines how Bitcoin
proposals move through technical review and coordination, using historical
outcomes to frame the questions facing Spiral's recent designs.

Read [the paper](paper.md) for the argument. Its historical sections cover
P2SH, timelocks, SegWit, Taproot and the block-size campaigns, with open
proposals and emergency repairs recorded under their own outcome categories.
The final sections examine CHECKSIBLINGVERIFY, MULADDMOD, Keyless CHECKSIG,
ProvenSpend and Canonical Proof Authority.

## Evidence files

| File | Contents |
|---|---|
| [cohorts.json](cohorts.json) | 30 historical episodes, current proposals and scope controls; 5 recent portfolio records; coding rules and source links |
| [references.json](references.json) | Primary-source index, exact repository revisions and provenance notes |

The cohort was selected to expose useful differences. Its records share design
families and political circumstances, so the paper uses them for comparison
while leaving numerical adoption estimates open.

## Review focus

Historical corrections should identify the episode and the source that changes
its coding. Technical comments should specify the proposal revision and the
application's security profile. The paper's six review gates provide a place
to attach unresolved concerns and experiments that could answer them.

The next version calls for broader historical sampling and a matched
application benchmark. Compatibility, resource use and the authority required
to move funds each need evidence under the same workload.

## Source snapshot

The official BIP snapshot is
b34d9f751791d4feb22feff4f2ed00bcac83961b.
Spiral main was inspected at
cfafbec4ae072b859f0140b2487baac14fac3a44.
The source index pins proposals developed on other branches and in
patrickdugan/bitcoin-rs individually.
