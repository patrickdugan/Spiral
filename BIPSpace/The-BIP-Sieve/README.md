# The BIP Sieve

**How Bitcoin Upgrades Earn Consent**

Version 0.2 is a research paper dated 13 November 2026. It examines how Bitcoin
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
| [cohorts.json](cohorts.json) | 35 historical episodes, related designs and scope controls; 5 recent portfolio records |
| [historical-frame.json](historical-frame.json) | Reproducible extraction of all 63 consensus-labelled documents, retaining 39 assigned during 2011–2017 |
| [objections.json](objections.json) | 14 attributed concerns and tradeoffs with responses and affected versions |
| [portfolio-evidence.json](portfolio-evidence.json) | Revision checks, recorded native evidence and authority boundaries |
| [benchmarks/REPORT.md](benchmarks/REPORT.md) | Paired-versus-merged claim comparison, executable harness and serialized costs |
| [references.json](references.json) | Primary-source index, exact repository revisions and provenance notes |

The episode cohort was selected to expose useful differences. A separate
retrospective frame makes its coverage inspectable. Related documents share
design families and political circumstances; their archive labels require
further event coding before an adoption analysis.

## First matched result

The one-shot claim model preserves terminal outcomes when paired principal
and connector outputs are merged under the stated assumptions. The paired
route adds 84 base bytes across assertion and terminal spending. Under the
specified two-leaf witness envelope, its complete payout path adds 467 WU.

The experiment executes a structural model and measures byte layouts.
Actual proof circuits, full Taproot validation and live relay require further
experiments. Reproduction commands are in [research/README.md](research/README.md).

## Review focus

Historical corrections should identify the episode and the source that changes
its coding. Technical comments should specify the proposal revision and the
application's security profile. The paper's six review gates provide a place
to attach unresolved concerns and experiments that could answer them.

The next version calls for outcome coding across the historical frame and a
concrete verifier under both matched contracts. A separate application should
specify the independent connector role that would justify preserving two
protected outputs.

## Source snapshot

The official BIP snapshot is
b34d9f751791d4feb22feff4f2ed00bcac83961b.
The initial Spiral inspection used
cfafbec4ae072b859f0140b2487baac14fac3a44; this revision also inspects
76071a0195f48961386e46d56df7b5e0276637fc.
The source index pins proposals developed on other branches and in
patrickdugan/bitcoin-rs individually.
