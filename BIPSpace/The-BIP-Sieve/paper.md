# The BIP Sieve: How Bitcoin Upgrades Earn Consent

**Version 0.2 | Research draft | 13 November 2026**

Spiral / BIPSpace. This research paper studies proposal selection and develops a review framework for the repository's recent designs.

## Abstract

Bitcoin proposals pass through several kinds of selection. Authors must specify a rule precisely enough for independent implementation. Reviewers examine what it permits and who bears its cost. Software projects decide what they can maintain, while users and miners choose which rules to enforce. An activation campaign adds another decision about timing and coordination. A proposal can advance through some of these stages while remaining unresolved at another.

This paper calls that process the *BIP sieve*. It combines a purposive historical cohort with a reproducible frame of 39 consensus-labelled documents assigned during 2011–2017. Document status is recorded separately from network outcomes. The expanded frame includes transaction redesigns outside the block-size campaigns, although their closure causes remain unestablished. A ledger of 14 attributed concerns preserves responses and the versions under discussion.

The framework separates compatibility from validation cost and represents applications through their minimum consensus dependencies. It applies six review gates to CHECKSIBLINGVERIFY, MULADDMOD, Keyless CHECKSIG, ProvenSpend, and Canonical Proof Authority. A matched one-shot claim model reproduces the paired-output construction's terminal outcomes using a merged output. Exact serialization adds 84 base bytes for the paired route under the stated profile. This result identifies a concrete burden of proof for an additional sibling predicate: demonstrate an application benefit that requires separate protected outputs. Native execution and real proof artifacts remain further experiments.

## 1. Question, scope, and evidence

### 1.1 What political acceptability means here

An upgrade earns political acceptance when enough independently acting participants are willing to maintain a shared chain under its rules. The relevant willingness includes continued participation by people who bear costs without directly using the new application. Consensus software makes these choices operational. A node enforces rules through validation; a miner chooses which valid transactions and blocks to produce.

The definition concerns Bitcoin protocol governance. BIP3 assigns an editorial role to the archive, where each publication represents its authors' proposal. Community support requires separate evidence. This paper records document publication and implementation milestones alongside the eventual network outcome. [BIP3]

The useful practical question is: **which objections can a design answer through specification, evidence, or a different allocation of responsibilities?** Reviewers need a complete account of the spending policies a change permits, including those enabled through composition.

### 1.2 Unit of observation

The primary unit is a *proposal episode*: a specified design, its target network and a particular implementation or activation attempt. Related episodes carry a common family identifier. This prevents the CSV bundle from becoming several independent successes merely because its specification spans several BIPs. Competing P2SH designs remain separately inspectable within their shared family.

The accompanying [cohort ledger](cohorts.json) preserves the distinction between current BIP metadata and outcomes such as deployment on Bitcoin mainnet, an explicitly suspended campaign, or launch of a separate chain. Conceptual contributions to a later design are recorded as lineage evidence. Open proposals remain censored at the cutoff: their eventual outcome has yet to be observed.

The snapshot of the official BIP repository is b34d9f751791d4feb22feff4f2ed00bcac83961b. The initial Spiral inspection used cfafbec4ae072b859f0140b2487baac14fac3a44; version 0.2 also inspects 76071a0195f48961386e46d56df7b5e0276637fc. Its new presigned application graph leaves the sibling, ProvenSpend and Keyless specifications unchanged. Recent designs on separate branches and bitcoin-rs pull requests are pinned individually. Source dates describe publication where available; the common observation date is 13 November 2026. The [portfolio evidence](portfolio-evidence.json) records the revision check.

### 1.3 Source and inference rules

Specifications establish proposed semantics. Release notes and recorded chain events establish deployment milestones. An author's message establishes what that participant said and decided. Statements about why an entire community acted require additional evidence.

Historical interpretations below are analytical inferences from those sources. The sample deliberately includes contrasting outcomes and useful boundary cases, so it cannot support an estimated probability that a randomly chosen BIP will succeed. It also overrepresents well-documented controversies. Many ideas disappear before receiving a BIP number, leaving a substantial missing denominator.

Current status vocabulary deserves care. BIP3 uses Draft, Complete, Deployed and Closed. Its migration combined several earlier closure labels, including Withdrawn and Rejected, into Closed. The ledger retains the present label and describes the underlying event where evidence permits. BIP2 remains useful as historical process evidence, including its advice to keep proposals focused. [BIP3] [BIP2]

### 1.4 A reproducible historical frame

The [historical frame](historical-frame.json) enumerates every row labelled Consensus in the pinned official index, then applies an inclusive assignment-date interval from 1 January 2011 through 31 December 2017. The extraction examines 63 documents, retains 39 and records why the other 24 fall outside the interval. A [small extractor](research/extract_historical_frame.py) checks the index against each document's header. Every inspected source file matches its official Git blob. [BIPINDEX]

This is a retrospective coverage audit introduced after version 0.1. It uses current documents whose assignment dates fall within the interval; a design's present wording can postdate that assignment. Documents sharing one deployment still remain separate archive rows. The descriptive metadata table appears in Appendix A, alongside the BIP18 case that makes its interpretation limits concrete.

Nine of the eleven HF-labelled documents in this frame concern block-size limits. BIP131 and BIP134 add other design goals. Their inclusion widens the comparison while leaving causal effects unidentified. Publication records can expose an omitted design, but the explanation of its outcome requires further historical evidence.

## 2. Classifying a change before discussing its politics

### 2.1 Compatibility is relative to a baseline

Fix baseline rules R, a shared predecessor history H, and the future domain being evaluated. Let V(R | H) be the set of continuations accepted under those conditions.

A soft-fork restriction satisfies

$$
V(R' \mid H)\subseteq V(R\mid H).
$$

A change has a hard-fork component when

$$
\exists x\in V(R'\mid H)\setminus V(R\mid H).
$$

A package can both add and remove accepted continuations. Its incompatible part still needs explicit treatment. This formulation follows the ordinary compatibility distinction used in Bitcoin Core's 2016 statement. The statement also expresses that project's preference for compatible upgrades and voluntary software choice; it is evidence of a participant's position. [CORE2016]

The history qualification matters. BIP90 replaced old signaling calculations with fixed enforcement heights and acknowledges different judgments on sufficiently deep counterfactual chains. A classification should state the history and deployment horizon to which its claim applies. [BIP90]

### 2.2 Four variables that a fork label leaves open

| Variable | Question for reviewers |
|---|---|
| Compatibility | Which previously invalid continuation becomes valid, or which previously valid continuation becomes invalid? |
| Expressive reach | What new spending policies can applications compose from the change? |
| Validation burden | What computation, memory, bandwidth and persistent state can hostile valid usage require? |
| Allocation of authority | Who may initiate, veto, recover or redirect an application's state transition? |

A small change to an opcode handler can alter a broad class of spending policies. A large cryptographic verifier can enter through a reserved extension point and still restrict the old acceptance set. Each property needs its own argument.

Tapscript provides several such extension points, including unknown key types and OP_SUCCESS opcodes. They permit later rules to constrain spends accepted by earlier software. Ordinary earlier nodes continue applying their earlier rules, so full enforcement of the new conditions depends on upgraded validation. [BIP342]

### 2.3 Changes outside consensus

BIP324 concerns encrypted peer transport. BIP125 specifies transaction replacement signaling and mempool behavior. Their adoption changes how software communicates or admits transactions without assigning them an SF or HF label. They appear as scope controls in the ledger. Canonical Proof Authority belongs in this same broad classification exercise: its retrieved draft is an application protocol with dependencies on experimental consensus primitives. [BIP324] [BIP125] [CPA]

Relay policy remains relevant to a consensus proposal's usefulness. A valid transaction graph may need a workable path through mempools, fee replacement and mining. Conversely, an individual miner's willingness to include a transaction supplies no general relay guarantee.

## 3. Historical cohorts

### 3.1 P2SH: selection among compatible designs

The early P2SH family supplies a particularly useful comparison because the competing proposals shared a compatibility class.

| Design | Current status | Observed outcome |
|---|---|---|
| BIP12 OP_EVAL | Closed | Original design retired as the P2SH route developed |
| BIP16 Pay to Script Hash | Deployed | Chosen mainnet mechanism; its rules specify the April 2012 start |
| BIP17 CHECKHASHVERIFY | Closed | Competing opcode design remained undeployed |
| BIP18 hashScriptCheck | Complete | Author describes the protocol as identical to BIP16, with different implementation framing |

All sought to let a recipient describe spending conditions through a short address. BIP12 records objections to interpreter complexity and executing serialized data as Script; its written recursion bound is two. BIP16's rationale defends a limited special-case construction and its fit with existing infrastructure. BIP17 proposed an alternative NOP-based check. BIP18 presents the BIP16 protocol through a different description and deprecation policy. Its Complete label therefore requires a semantic relationship record before any attempt to count independent deployment outcomes. [BIP12] [BIP16] [BIP17] [BIP18]

The inference is that compatibility admitted several candidates to serious consideration. Reviewers still faced questions about interpreter behavior, integration work and the relationship between a mechanism and its intended use. An acceptance model containing only an SF indicator would leave this within-family selection unexplained.

### 3.2 Deployed repairs and contract primitives

| Episode | Consensus change | Verified enforcement milestone |
|---|---|---|
| BIP34 | Height in coinbase | Height 227,931 |
| BIP66 | Strict DER signature encoding | Height 363,725 |
| BIP65 | CHECKLOCKTIMEVERIFY | Height 388,381 |
| BIP68/112/113 | Relative timelocks and locktime evaluation | Height 419,328 |

BIP90 records the first three enforcement heights. BIP34 also reports a last version-1 block at a different height, which refers to a separate event. The CSV deployment notice supplies its lock-in and enforcement milestones. [BIP90] [CSVNOTICE]

These changes answered identifiable engineering needs. Coinbase height supported transaction uniqueness. Strict signature encoding reduced dependence on a library parser's behavior, while absolute and relative timelocks enabled contract conditions tied to time or coin age. The CSV documents describe related functions that were deployed together. [BIP34] [BIP66] [BIP65] [BIP68] [BIP112] [BIP113]

BIP66 also supplies a deployment warning. The July 2015 alert records invalid forks after miners had reached the signaling threshold. Some miners extended blocks without performing the validation their signaling implied. A proposal can therefore cross a coordination threshold while enforcement remains defective. The political sieve needs an operational evidence gate that can catch this gap. [DERALERT]

Legible use cases and manageable implementation obligations are candidate explanations for these deployments. The present evidence leaves their relative influence unresolved. CSV also shows why coherent bundling can help: its components jointly express a useful contract capability, and their documents require coordinated deployment.

### 3.3 SegWit: feature acceptance and activation disputes

SegWit joins several outcomes that require separate coding. BIP141 defines the witness structure and consensus accounting. BIP143 changes signature hashing, and BIP147 adds NULLDUMMY. BIP144 is a peer-services specification associated with the deployment. Core's wallet guide records enforcement at height 481,824. [BIP141] [BIP143] [BIP147] [BIP144] [SEGWITGUIDE]

The original release used BIP9 signaling. BIP91 subsequently specified lower-threshold coordination around the existing deployment, while BIP148 specified a timed mandatory-signaling rule. These mechanisms pursued a shared goal. Their marginal contribution to the eventual outcome requires evidence beyond the specification texts. BIP149 specified a second deployment conditional on the earlier attempt missing its deadline, which keeps its Closed status distinct from the already deployed feature. [CORE0131] [BIP9] [BIP91] [BIP148] [BIP149]

SegWit also supplies a historical example of alternative compatibility routes. Gregory Maxwell's December 2015 roadmap describes an earlier hard-fork SegWit design used in Elements Alpha and the later soft-fork design proposed for Bitcoin. The environments and implementations differed, which limits what can be inferred from that lineage about the effect of fork class. [ROADMAP2015]

SegWit's stated benefits also crossed application boundaries, including malleability handling and changes to validation costs. That breadth offered several reasons to adopt the same infrastructure. It also required careful scope management; promised future capabilities need separate evidence from features present at activation. [SEGWITBENEFITS]

### 3.4 Block-size hard forks: a correlated political cohort

| Episode | Proposed change or target | Outcome at the cutoff |
|---|---|---|
| BIP101 | Scheduled increase beginning at 8 MB | Closed; its rules did not become Bitcoin mainnet rules |
| BIP102 | One-time increase to 2 MB | Closed; its rules did not become Bitcoin mainnet rules |
| BIP109 | 2 MB with additional sigop and hashing limits | Closed; its stated activation deadline passed |
| SegWit2x second phase | Coordinated 2 MB hard fork after SegWit | Organizers suspended the scheduled attempt |
| Bitcoin Cash UAHF | Deliberately separate chain | A distinct network launched in August 2017 |

BIP101 framed increasing capacity as an answer to growing transaction demand. Its discussion also records concerns about full-node costs and propagation advantages. BIP102 had a compact specification with a large compatibility consequence: earlier full nodes would reject larger blocks. BIP109 included explicit resource-accounting changes, so its outcome supplies no support for attributing failure simply to an absence of cost controls. [BIP101] [BIP102] [BIP109]

On 8 November 2017, SegWit2x organizers suspended the upcoming increase. Their message attributed the decision to insufficient consensus and the risk of dividing the community. This paper uses the statement as evidence of their assessment and action. The original endpoint was unavailable during retrieval; a contemporaneous full copy preserves the author, timestamp and signatories. [S2X]

Bitcoin Cash belongs in a different outcome category. Its UAHF specification deliberately required an initial block exceeding the old limit and supplied replay protection. Its first-party history dates the separate network's launch to 1 August 2017. Successful creation of a continuing chain and a coordinated upgrade of Bitcoin mainnet have different success criteria. [UAHF] [BCHHISTORY]

These campaigns occurred in an overlapping dispute about capacity, fees and the costs of participating in validation. Their proposed incompatibility arrived together with those issues. The cohort therefore supports a historical description of failed common-chain campaigns and a successful separate-chain launch. It cannot identify a general causal penalty for every conceivable hard fork.

The 2016 Core statement supplies direct evidence that compatibility itself mattered to an influential software project. The comparison still needs proposals with similar goals, evidence and costs before it can separate that preference from the surrounding controversy. [CORE2016]

### 3.5 Taproot: scope discipline and a bounded activation attempt

The Schnorr/Taproot/Tapscript bundle deployed at height 709,632. BIP341 explains its scope tradeoff: including every desirable change would hinder review, while excessive fragmentation would burden wallets and services. Its selected package left independently addable features for later work. [BIP340] [BIP341] [BIP342]

Core 0.21.1 implemented Speedy Trial with a limited signaling window and delayed minimum activation height. David Harding's contemporary explanation attributes the proposal to Russell O'Connor and describes it as acceptable to several previously disagreeing participants. That is first-person evidence for compromise over process. [CORE0211] [SPEEDY]

BIP343 proposed a mandatory-signaling alternative. Its current Closed status follows a changelog entry recording that it had become irrelevant and lacked known deployments. The capability it sought was already deployed through another route. Coding this as a failed Taproot feature would erase the distinction between a goal and one activation strategy. [BIP343]

The analytical lesson concerns the organization of decisions. Review of the capability, agreement on a bounded activation attempt, and preparation for enforcement can proceed with different evidence. Combining them into a single yes/no position makes it harder to locate the remaining disagreement.

### 3.6 Conceptual survival and open proposals

The MAST lineage shows another outcome. BIP114 is Closed, while BIP116 and BIP117 remain Draft. Taproot acknowledges earlier Merkle-branch work by researchers associated with these constructions. The evidence supports intellectual contribution to a later deployed design. It preserves the differences between their exact interfaces and deployment packages. [BIP114] [BIP116] [BIP117] [BIP341]

| Current design | Status at the source snapshot | Relevant review question |
|---|---|---|
| BIP118 ANYPREVOUT | Draft | How are rebinding and application authorization constrained? |
| BIP119 CHECKTEMPLATEVERIFY | Draft | Which useful templates and resource guarantees justify its interface? |
| BIP347 OP_CAT | Complete | What follows from bounded concatenation when composed with other primitives? |
| BIP348 CHECKSIGFROMSTACK | Draft | Which message-signing and delegation applications justify the extension? |
| BIP360 P2MR | Draft | What does removing the key path accomplish under the stated threat model? |
| BIP440/441 arithmetic restoration | Draft | Does generalized metering support the proposed larger execution envelope? |
| BIP446/448 template and rebindable bundle | Draft | Which components are needed for the demonstrated applications? |

These are open observations. Complete describes OP_CAT's specification stage; network enforcement is a separate fact. The inspected Core interpreter retains the older extension behavior for the relevant key, opcode and witness paths. [BIP118] [BIP119] [BIP347] [BIP348] [BIP360] [BIP440] [BIP441] [BIP446] [BIP448] [COREINTERPRETER]

Cost criticism must identify an actual mechanism. CTV specifies a bounded template check and requires cached transaction components to avoid excessive repeated hashing. CAT retains a 520-byte element bound in its proposed Tapscript version. Future contract transitions can form a continuing state machine while each individual validation remains finite. The relevant questions concern metered work, reachable policies and who can force others to bear their cost. [BIP119] [BIP347]

### 3.7 Emergency and maintenance controls

The March 2013 database split involved an accidental incompatibility, an emergency mining rollback, temporary restrictions and a later upgrade or configuration deadline. Core 0.8.1 and the accompanying notice document the compatibility timetable. This episode belongs outside ordinary elective-proposal comparisons because immediate shared danger changed the available choices. [BIP50] [CORE081] [DBDEADLINE]

BIP90 supplies a maintenance control, with a practical historical baseline that matters to its compatibility analysis. Together these cases prevent a misleading all-or-nothing story about Bitcoin's ability to change. They also show why a count of text labels would lose relevant events.

### 3.8 Transaction redesigns outside the capacity campaigns

The wider frame adds design comparisons that the initial block-size cohort omitted.

| Document | Recorded route | Proposed work |
|---|---|---|
| BIP131 Coalescing Transactions | HF | Aggregate spending through wildcard inputs sharing a script |
| BIP134 Flexible Transactions | HF | Introduce a new transaction encoding and a reorganized signature commitment |
| BIP140 Normalized TXID | SF | Add normalized identifiers for signature checking through an extensible opcode |

All three documents currently carry Closed metadata. BIP131 changes how groups of UTXOs are claimed and accounted for. BIP134's compatibility section requires older validating clients to upgrade to understand its new transaction format. BIP140 uses a NOP extension and tracks an additional identifier while ordinary outpoints retain their existing form. [BIP131] [BIP134] [BIP140]

The last two share malleability goals, with substantially different validation machinery. They supply candidates for a comparison of storage and signature-processing costs under a common workload. Their archival status leaves the cause of closure unresolved. The cohort ledger records that evidential limit.

## 4. What this history can support

### 4.1 Several distinct sources of resistance

The cases motivate a set of mechanisms to investigate:

| Mechanism | Evidence that can address it |
|---|---|
| Existing users face a compatibility deadline | A precise transition plan, upgrade lead time and treatment of dissenting software |
| Validation imposes shared costs | Hostile-valid-input benchmarks, memory bounds and cache analysis |
| The interface enables policies reviewers have not assessed | A complete account of composition and application reach |
| The benefit depends on other unactivated work | Minimum dependency sets and independently useful applications |
| Operational readiness differs from signaling | End-to-end enforcement checks across actual software paths |
| A feature and its activation procedure have different constituencies | Separate records of technical review and deployment objections |
| A proposal's exact interface is displaced by another design | A lineage record preserving the useful contribution |

These mechanisms remain hypotheses, with their relative importance awaiting a wider study.

Some burdens fall on different people. Application users may gain lower trust requirements while node operators incur validation work. Maintainers inherit a permanent obligation to preserve exact semantics. Miners encounter transaction-selection and propagation effects. Wallet developers must construct and explain the spending conditions. Holders care about continuity and credible rules even when they never use the application. A proposal needs to make that distribution inspectable.

### 4.2 Why simple historical success rates mislead

An estimate such as P(deployed | SF) requires a sampling frame. Selecting famous successful soft forks and famous failed hard forks builds the answer into the sample. Selecting only numbered proposals excludes ideas filtered out before publication.

Time matters too. A recent draft has had less opportunity to activate than a decade-old proposal. A closed activation campaign can be followed by a successful feature deployment. Related BIPs share authors, code and political circumstances, so their outcomes are correlated.

This version therefore uses comparative episodes and explicit uncertainty about causal attribution. A later statistical study should register its target outcome, reconstruct proposal revisions and include still-open observations. It would need clustered analysis by family and sensitivity checks for missing proposals.

### 4.3 Fair comparison of SF and HF routes

The strongest comparison asks the same application to meet the same security and resource requirements under alternative implementations. It records the changed acceptance sets, complete dependencies and permanent maintenance obligations.

| Goal | Compatible route to examine | Incompatible route to examine | Comparison condition |
|---|---|---|---|
| More transaction capacity | Witness restructuring and efficiency improvements | Larger blocks accepted beyond the old base limit | Match workload and validation/propagation budgets |
| New Script operation | A reserved opcode or future script version | New acceptance in a legacy context that currently fails | Identify the exact previously rejected spend |
| Transaction-bound proof authority | Unknown-key restriction with authenticated Script computation | Broaden existing CHECKSIG acceptance | Preserve the same application statement and existing ownership semantics |
| Large arithmetic | Bounded operation or metered future tapleaf | Relax limits in an already enforced context | Match numeric range and worst-case resource use |
| Native proof outputs | Restrict a reserved witness space and add creation conditions | Rewrite acceptance of existing output classes | Specify initialization and legacy-fund treatment |

A direct HF encoding can simplify implementation while creating migration obligations and changing the treatment of existing coins. Measuring a compatible construction's witness size and validation work helps establish the cost of preserving earlier acceptance rules. The table records prospective comparisons whose implementations and security arguments remain to be completed.

### 4.4 A versioned objection ledger

The [objection ledger](objections.json) records fourteen concerns and design tradeoffs. Each entry identifies the speaker or reporting author and preserves the response found in the source. Publication dates remain distinct from a BIP's assignment date. A proposed experiment is labelled as our analytical response; the participant's willingness to reconsider after it remains unobserved.

The March 2021 Speedy Trial discussion shows why this detail matters. Matt Corallo questioned whether the proposed signaling interval would preserve coordination and suggested fewer periods beginning later. David Harding defended participants' choice of rules and explained the compromise behind the schedule. Corallo then clarified his goal of keeping the node community together. The exchange gives direct evidence about the objectives used to judge an activation procedure. [SPEEDYCORALLO] [SPEEDYHARDINGREPLY] [SPEEDYCORALLOCLARIFY]

Another exchange identified a parameter interaction. Luke Dashjr argued that a period in Andrew Chow's proposed schedule overlapped a BIP8(True) plan and could produce different enforcement heights. Chow preferred arranging the follow-up around Speedy Trial and remained open to adjusting the periods. Enumerating the two schedules is a concrete way to examine that concern. Its relevance to shipped software depends on the final parameters. [SPEEDYCHOWPARAMS] [SPEEDYDASHJR] [SPEEDYCHOWREPLY]

The ledger also preserves mitigations already present in a design. CTV's repeated-hashing concern comes with specified caching requirements. Its co-spending discussion motivates commitments to input count and input index. Those records call for checking the stated remedies in implementations and applications. They retain the difference between a hazard considered by an author and an unresolved defect. [BIP119]

## 5. A sieve based on evidence

### 5.1 Review gates

For a design p and evidence package e, define six review gates. Each records one of pass, open or fail, with a source or experiment explaining the value.

| Gate | Required evidence |
|---|---|
| G1: meaning | Exact bytes, domains, failure behavior and compatibility argument |
| G2: resources | Deterministic cost accounting, hostile cases and supported execution environments |
| G3: authority | A complete explanation of permitted spends, retained assumptions and recovery |
| G4: usefulness | An implemented application with a measured alternative baseline |
| G5: composition | Dependency analysis and interactions with existing or proposed rules |
| G6: deployment | Operational enforcement, review ownership and an explicit activation procedure |

Gate results describe the evidence available for review. Community consent also depends on participants' objectives and tolerance for risk, so someone can accept every technical finding and still oppose the change.

An objection ledger should record its author and date, the affected version, a concrete concern, the proposed response and the evidence that would change its status. Objections about an earlier design stay attached to that version. This prevents both carrying a repaired bug forward and silently treating a newer implementation as if it had inherited every earlier test result.

The method also leaves room for irreducible disagreement. A participant may prefer a smaller base-layer policy space even after a proposed extension meets its performance bounds. That is a substantive preference about Bitcoin's future. A paper can describe it and compare its consequences without inventing a technical defect to explain it.

### 5.2 Compatibility composition

**Proposition 1.** For a nonempty family of proposed restrictions, suppose each has an acceptance set V_i contained in baseline V_0, and a combined implementation accepts exactly their intersection. Then the combination is a soft-fork restriction of that baseline.

**Proof.** An element of the intersection belongs to every V_i, each of which is contained in V_0.

The implementation premise carries the engineering work. A combined patch needs an argument that its selectors coexist and its caches use the correct identities. Failure paths must preserve the intended intersection through the actual validation code.

### 5.3 Minimum dependency sets

Let M(u) be the set of inclusion-minimal primitive sets that implement application u under a stated security profile. If A_p means primitive p is activated, then the application's activation requirement is

$$
\operatorname{Ready}_{\rm consensus}(u)
=\bigvee_{D\in M(u)}\ \bigwedge_{p\in D} A_p.
$$

Existing activated primitives can be removed from each displayed set after recording the baseline. The application still needs its own implementation and operational evidence.

**Proposition 2.** Adding a mandatory primitive to a fixed route can only narrow the activation states that satisfy that route. Providing an additional genuinely sufficient alternative route can only expand the activation states that satisfy the disjunction.

This follows directly from conjunction and disjunction. It says nothing about how often either state occurs in the real world. The corresponding probability bound P(A and B) <= min(P(A), P(B)) requires no independence assumption, but supplying numerical probabilities would require data absent from this paper.

A count of dependencies also fails to measure their total burden. One native proof verifier may demand more novel cryptographic review than several small Script extensions. The ledger must retain the content of each dependency.

### 5.4 A small checker can authorize a large policy space

Consider a transaction digest check accepting d exactly when d equals the consensus digest. Its implementation can be short. If Script can construct d from authenticated computation, the combined policy can constrain a transaction's outputs and successor program.

The marginal consensus code and the reachable contract family are therefore different quantities. Review should report both. This is the relevant lesson for Keyless CHECKSIG and for other reusable introspection primitives.

A resource bound also needs the correct unit. Constant work per invocation can coexist with many invocations per block. A fixed verifier can coexist with large witnesses. A finite transaction can leave an indefinitely stalled application state. Separate measurements are needed for validation, economic cost and eventual completion.

### 5.5 Merging outputs in a one-shot claim

**Proposition 3.** Consider a claim admitted through a fresh UTXO root, represented by protected outputs V and C, with values P and B. Suppose the only permitted spends of either protected coin are terminal actions that consume both. The coins share the relevant confirmation age, and external contracts never refer to either independently. Construct M with value P+B and a policy enforcing the same abstract authorization and terminal output vector. If admission checks complete policies and denominations, and the template commitments satisfy their collision-resistance assumption, replacing the pair by M preserves the projected terminal outcomes and exclusion of a second spend.

**Proof.** Map the live pair to the live merged coin and forget their outpoint identities. For each authorized terminal action, the stated premises give the merged policy the same authorization decision, age condition and terminal output vector. The converse follows from the same premises. Execution consumes every protected coin in either representation, so the other terminal action subsequently lacks its required input.

An input-sensitive verifier needs an explicit translation when execution moves from the connector at input 1 to the merged coin at input 0. The proposition assumes that this translation preserves the abstract statement. It also holds protected fees and the external fee-child rules fixed. Section 8 exercises these premises in a bounded model; a compiler and its actual proof circuit must establish them for a deployed application.

## 6. Applying the sieve to Spiral's recent designs

### 6.1 Portfolio and version boundaries

| Design | Retrieved layer and compatibility route | Inspected source |
|---|---|---|
| CHECKSIBLINGVERIFY | Consensus SF through a Tapscript extension | Spiral main cfafbec4 |
| MULADDMOD | Consensus SF through an OP_SUCCESS slot | Spiral arithmetic branch 7f5ad9f9; bitcoin-rs PR 1 |
| Keyless CHECKSIG / TXCOMMIT | Consensus SF through an unknown-key restriction | Spiral cfafbec4; bitcoin-rs PR 2 |
| ProvenSpend / P2PROOF | Candidate SF using a reserved output space and creation checks | Spiral main cfafbec4 |
| Canonical Proof Authority | Application protocol over experimental primitives | bitcoin-rs PR 3, 29ca5190 |

The sibling and ProvenSpend drafts currently reside under the in-and-out-burger research tree. Arithmetic has its own branch. CPA is retrievable in bitcoin-rs, where its branch is stacked on the distinct Keyless integration. The source map pins each proposal to the location and revision inspected for this paper. [SIBLING] [MULADD] [KCS] [PROVEN] [CPA]

These are different review units. Their common interest in BitVM and proof-authorized spending provides applications to compare, while their consensus claims need separate treatment.

### 6.2 CHECKSIBLINGVERIFY: justify the additional predicate

The proposed opcode checks a bounded relationship between two actual outpoints: designated distinct outputs must originate in the same transaction. The finite BitVM graph profile combines it with BIP446 OP_TEMPLATEHASH. Its minimum template dependency is that primitive; BIP448's wider package adds other functions. [SIBLING] [BIP446] [BIP448]

The adoption case is legible. A same-parent predicate can bind a principal output to the intended challenge connector without embedding a circular future transaction identifier. Its direct work reads a constant descriptor and existing transaction fields.

The burden falls on incremental utility. The draft itself considers a baseline in which principal occupies the contested output and a template handles the graph. A measured comparison must show why the separate-output design earns an additional consensus predicate.

The security claim should retain its scope. Consensus pairing can remove deletion-dependent authorization of specified graph edges. Application admission must still identify the economic claim, while garbling, data availability and timely challenges require their own evidence. A funded recovery test should include every path that can move principal.

Section 8 supplies the first comparison under explicit one-shot assumptions. The merged model already expresses the same terminal authority with fewer protected coins. The next useful gate is an application that needs the separate roles, followed by actual proof execution and funded recovery. A demonstrated advantage would give reviewers a reason to carry the additional predicate's permanent cost.

### 6.3 MULADDMOD: bounded arithmetic needs a complete workload

MULADDMOD computes

$$
r=(ab+c)\bmod m
$$

with a bounded modulus width and canonical fixed-width residues. Its draft proposes a provisional charge against the Tapscript budget. The operation has an independent consensus interface; an application supplies authentication and the conditions that release funds. [MULADD]

The bitcoin-rs integration records funded regtest arithmetic disputes and independent arithmetic-vector checks. Its live beneficiary and operator signatures remain part of that fixture's authority. The existing audit records 25,300 randomized differential evaluations and 38 checks in a four-node campaign that includes reorganizations. One constructed transaction executes 73,845 arithmetic operations at 3,988,196 WU; its reported median node wall time is 4.9437 seconds on an AMD Ryzen AI 9 365 host. These are measurements of the pinned implementation and machine. The receipts preserve missed-window outcomes alongside successful disputes. [MULADDPR] [MULADDAUDIT] [MULADDRECEIPT]

BIP441, using BIP440's metering, supplies a broader arithmetic alternative through a future tapleaf. The bounded primitive must show where its encoding, execution cost or review surface benefits the same workload. A wider package can spread its review cost across more applications, which makes the chosen comparison workload consequential. [BIP440] [BIP441]

A strong gate would execute an identical authenticated dispute using existing Script, MULADDMOD and restored arithmetic. It should measure the complete witness and cold validation cost across supported architectures. Malformed committed values and missed challenge windows belong in the protocol evidence because arithmetic correctness alone leaves those cases open.

### 6.4 Keyless CHECKSIG: transaction binding and its consequences

TXCOMMIT gives one exact unknown-key selector a digest-checking meaning. Script must produce a 32-byte candidate matching the actual Taproot sighash under a distinct key-version domain. An invalid nonempty candidate aborts. This preserves the proposed restriction of the existing unknown-key behavior. [KCS]

Its own primitive needs no concatenation opcode. The current dynamic-output compilers use CAT to construct authenticated messages. The P2MR profile removes the key path structurally; the bitcoin-rs NUMS P2TR profile retains the associated elliptic-curve assumption. Those security profiles therefore have different minimum activation sets. [KCSNATIVE] [BIP360]

Spiral's recorded Core regtest job accepted a block containing 72 linked Circle-STARK example transitions. The full block weighed 3,439,221 WU, and the run rejected an altered terminal payout. It used a 32-row Fibonacci instance with eight query groups. These measurements establish that specific experimental execution path. A proof at a stated production soundness target, authorizing an external economic claim, remains an additional gate. [KCSRUN] [KCSSTATE]

A separate bitcoin-rs milestone binds a disclosed F17 recurrence to its actual payout and exact precompiled successor. Its guide records four paths and eight confirmed native transitions, with 39 rejection cases. Fixed transaction context and a finite disclosed computation define this result's scope. The larger proof-system application needs its own statement-binding and recovery evidence. [KEYLESSSTATE]

Earlier review identified obligations in the pinned Spiral prototype involving sighash-fragment placement, custom P2MR control bytes and continuation of staged verification. Those observations stay attached to that source. The later bitcoin-rs compiler constructs fixed transaction context and needs its own version-specific assessment.

Reusing a familiar transaction digest and extension mechanism gives reviewers less novel consensus machinery to assess. Its covenant reach should be presented directly: authenticated computation can determine outputs and a successor policy. Reviewers need the resulting contract class, full validation costs and liveness conditions alongside the small checker.

A staged protocol must establish that every admitted prefix has an authorized continuation or recovery. The recorded completion run leaves hostile-prefix admission and unavailable continuations as separate obligations. A deployment case needs funded tests of those paths and a rule governing who may begin verification.

### 6.5 ProvenSpend: a broad consensus obligation can still use an SF route

ProvenSpend describes a proof-output lifecycle. INIT verifies admissibility when an output is created, and STEP verifies later state transitions bound to the actual transaction. Its own compatibility section proposes restricting reserved witness spends and rejecting creations that omit required initialization evidence. A full compatibility analysis remains open. [PROVEN]

The scope includes an output-creation hook and a cryptographic verifier whose exact profile has yet to be chosen. Its current model uses an ideal receipt oracle. The model can test transition rules, while genuine proofs and measured hostile costs require a concrete implementation.

This design makes a useful political control. Its logical interface can be stated compactly, yet every validating implementation would inherit proof-system parameters, transcript rules and failure handling. A shared error could affect every application using that verifier. Freezing such machinery in consensus creates a different review burden from a reusable byte or transaction primitive.

The draft has an independent transaction-binding design and no stated BIP448 requirement. Its witness-version placeholder also needs allocation review against P2MR. A small dependency count would conceal the internal size of the native package.

The next gate is a selected transparent proof profile with genuine INIT and STEP receipts, deterministic resource accounting, and an independently implemented verifier. The application should demonstrate authenticated provenance and consumption of claim state.

### 6.6 Canonical Proof Authority: preserve the application boundary

CPA defines a ProgramID for a normalized program and an AuthorityID that includes the verifier and policy interpretation. A state commitment specializes the receiving script. Its normalization identifies specified structural transformations; arbitrary equivalent circuits can retain different identifiers. Repeated funding of an address still creates separate outpoints. [CPA]

The current bitcoin-rs implementation adds a disclosed-trace application over Keyless CHECKSIG and CAT using P2TR. Its published guide describes finite precompiled successors and retained parent guards. Private-witness verification, credential authentication and singleton lineage remain open. The hosted research job at the inspected revision records 42 tests, four confirmed transitions and 49 rejections. These counts describe the named application fixture. [CPAGUIDE] [CPARUN]

The application layer allows the naming and delegation discipline to be studied without adding a new consensus rule for every descriptor field. Its deployment still inherits the primitives needed by its chosen profile. The paper should therefore ask whether the application clarifies authority, conserves allowances across delegation and binds a verifier to the intended program.

Program enumeration produces public identifiers. A secret signing scalar requires a source of secrecy beyond a public circuit description. The CPA draft states that constraint explicitly. Its address-machine intuition is useful when it refers to reproducible policy identity and deterministic authorized outputs.

The next gate is independent canonicalization vectors followed by a cryptographic private-witness proof authorizing the same transition, with explicit clone, replay and revocation behavior. Claims about uniqueness must identify the authenticated bootstrap coin and the enforced successor rule.

### 6.7 An explicit HF CHECKSIG comparison

The retrieved portfolio contains no separate normative HF-only CHECKSIG specification. This paper therefore defines a comparison question.

Suppose a variant accepts a complete spend through an ordinary CHECKSIG path that the baseline rejects, under otherwise identical valid transaction conditions. It has a hard-fork component under the definition in section 2. A variant that constrains an existing permissive extension point can follow the soft-fork route. The exact acceptance change settles the classification.

The HF comparison should identify what that incompatibility buys: lower total validation cost, a substantially simpler proof interface, or a capability whose compatible construction has an unacceptable burden. It must also specify effects on existing ownership, replay boundaries and migration. A broad statement that proof authority is “more native” supplies no quantitative answer.

This comparison preserves the ambition of direct proof-authorized Bitcoin execution while making its tradeoffs reviewable. A future specification can be inserted into the ledger once its rules and baseline are explicit.

### 6.8 An application baseline under deployed rules

Spiral revision 76071a adds a presigned BitVM3 claim graph. Its committed Core regtest receipt records eleven passing checks, including the payout window and signed recipient binding. Reject-label disproof consumes the dishonest claim output before its payout can spend it. The harness supplies synthetic labels and a synthetic statement. This execution evidence concerns the transaction graph. [IOBRECEIPT] [IOBHARNESS]

Desk presigning and retained keys remain part of the demonstrated authority model, alongside correct garbling and delivery of input labels. That gives proposed covenant routes a concrete baseline: hold the economic claim fixed, then identify which signing or setup obligation the new rules remove and which obligations remain. Real garbled verification requires its own artifacts and receipt. [IOBGRAPH]

## 7. Dependency routes and the next evidence

Existing activated Bitcoin rules, including BIP341/342, form the baseline for the following table. Entries name the extra consensus primitives required by the inspected profile; each row also requires correct application code.

| Profile | Extra consensus route | Evidence still needed |
|---|---|---|
| Sibling predicate alone | CHECKSIBLINGVERIFY | Interpreter equivalence and bounded cost |
| Documented paired BitVM graph | CHECKSIBLINGVERIFY plus TEMPLATEHASH | Incremental benefit over a merged contested output |
| Bounded arithmetic step | MULADDMOD | Complete authenticated-workload comparison |
| Dynamic Keyless profile with NUMS P2TR | TXCOMMIT plus CAT | Application relation, compiler correctness and recovery |
| Structurally key-path-free Keyless profile | TXCOMMIT plus CAT plus P2MR | Same obligations and output-profile conformance |
| Current CPA profile | TXCOMMIT plus CAT, using NUMS P2TR | Canonical authority and delegation evidence |
| ProvenSpend lifecycle | Native proof-output package, including INIT and STEP | Concrete cryptographic profile and creation validation |
| Presigned claim-graph baseline | Existing activated rules | Genuine garbled verification under the recorded signing and setup assumptions |

The table gives review a place to begin. It also exposes possible ways to simplify a project. An application can retain a clear descriptor format while switching verifier backends. A finite claim graph can compare one protected output with a coupled pair. A proof system can be measured outside consensus before its parameters become a permanent validation commitment.

A candidate should enter an activation discussion with its remaining dependencies visible. An application-specific prototype can guide research even while several dependencies remain open.

## 8. First matched application result

### 8.1 Contract and execution boundary

[BIP-SIEVE-MATCH-01](benchmarks/REPORT.md) compares the unchanged pinned paired validator with a separately implemented merged-output model. One admitted claim has principal P, bond B and predetermined settlement and recovery outputs. The routes share ideal authorization predicates and confirmation age. Protected parents pay zero fees; an independently authorized child supplies fees through a fixed anchor.

The experiment appends the same assertion anchor to both representations because the draft includes it while the upstream constructor omits it. Actual Taproot policies and cryptographic proof bodies remain idealized. Reconfirmation changes the modeled coin age; the experiment contains no live chain engine. Its [results](benchmarks/results.json) and [harness](benchmarks/sibling_vs_merged.py) preserve those boundaries.

### 8.2 Observed graph behavior

| Executed comparison | Result |
|---|---:|
| Bounded paired/merged decisions | 4,800 evaluated pairs |
| Pairs accepted by both validators | 720 |
| Disagreements with each other or the abstract claim predicate | 0 |
| Matched transaction mutations rejected by both routes | 16 |
| Intended same-parent pairs accepted | 64 |
| Cross-parent connector substitutions rejected | 4,032 |
| Fee-child scenarios preserving protected value | 6 |
| Synthetic reconfirmation-age boundary cases | 6 |
| Duplicate-root and destination-collision controls preserving state on rejection | 9 |

The grid varies principal and bond values, then examines authorization and maturity boundaries for both terminal branches. Some boundary heights coincide when the delay is one block, so the count describes evaluated comparisons. An independent decoder and template implementation also reproduce the equality result in nineteen official BIP446 basic vectors. Sixteen annex-absent digests match the imported paired model. The checked condition is the template equality in those simple vector scripts. [BIP446VECTORS]

Complete independently funded roots expose a different boundary. When admission assigns two roots to one 1,000,000-sat liability, both routes permit 2,000,000 sat of principal to be paid. Same-parent checking authenticates a local pairing. A unique economic liability requires admission control or shared state that prevents a second authorization.

### 8.3 Serialized cost under the declared profile

The additional 34-byte protected output contributes 8 value bytes, a one-byte script length and 34 script bytes. The additional native-witness input contributes 32 transaction-ID bytes, a four-byte output index, one empty-scriptSig byte and a four-byte sequence. Their sum is

$$
\Delta B = 43+41=84\ \text{base bytes}.
$$

| Complete path component | Merged base bytes | Paired base bytes |
|---|---:|---:|
| Assertion | 104 | 147 |
| Terminal payout or recovery | 147 | 188 |
| Total | 251 | 335 |

For the specified two-leaf envelope, the extra principal witness contributes 117 bytes and the connector adds fourteen program bytes. With unchanged CompactSize prefixes, the complete path difference is

$$
\Delta W=4(84)+117+14=467\ \text{WU}.
$$

The serialized assertion-plus-payout fixtures weigh 1,382 WU for merged and 1,849 WU for paired. Their separately rounded virtual sizes differ by 117 vbytes. A recovery-program size sweep produces differences of 467 or 469 WU; the latter occurs when only the paired program crosses the 253-byte CompactSize boundary. Weight uses BIP141 accounting. [BIP141]

These witness figures use opaque proof bytes and a declared tree layout. A concrete compiler can change that layout. Full Taproot commitment validation and native execution time remain outside this measurement, while the 84-base-byte increment follows directly from the fixed transaction shapes.

### 8.4 Consequence for proposal selection

The one-shot profile already has a route through TEMPLATEHASH alone at the model level. Its principal-moving paths meet the merged-output premises, so the extra sibling predicate needs an application benefit from preserving independent output roles. A larger proof payload shared by both routes leaves this structural comparison intact.

This is useful negative evidence for a particular minimality claim. A protocol with independently composable connectors can change the premises and deserves a fresh comparison. The next experiment must specify that role separation, preserve the same liability accounting and instantiate the actual verifier.

## 9. Research programme for version 0.3

### 9.1 Establish outcomes within the declared frame

The current historical frame establishes document coverage. The next pass should recover first public specifications and major revisions, then attach implementation milestones and explicit deployment attempts to the included designs. Each recorded objection needs a primary source and an affected version.

An independent coder should review the network target, compatibility baseline and outcome. Disagreements should remain in the dataset until resolved. The hard-fork comparison needs additional cases outside the block-size dispute, with emergency repairs and intentional separate-chain launches retained as distinct categories.

### 9.2 Test specific hypotheses

| Hypothesis | Observation that would test it |
|---|---|
| Shared validation costs dominate objections after a clear utility demonstration | Versioned objections change after hostile-cost evidence while the application's utility stays fixed |
| Activation disagreement persists independently of feature agreement | The same participants endorse semantics while giving different reasons for rejecting activation schedules |
| Dependency clarity improves review efficiency | Comparable review threads resolve objections faster after a complete minimal-route specification |
| Alternative implementations clarify the case for a new primitive | Reviewers can identify a reproducible application gain after a matched baseline comparison |

These hypotheses concern observable review behavior. A future study should define coding rules and time windows before measuring them. Public message volume is a poor proxy for the number or economic importance of people enforcing a rule; the study must report that limitation.

### 9.3 Extend matched application comparisons

For the recent portfolio, choose a common claim and record its authorized inputs, payout, successor state and failure conditions. Then implement only the variants that can express that exact claim under their stated assumptions.

Measure the complete transaction graph and the resources needed to validate hostile cases. Record witness availability, challenge timing, fee changes and recovery. For proof-authorized validity paths, include fresh proofs for incorrect public statements. For optimistic paths, include a missed challenge deadline and a reorganization after assertion.

The arithmetic comparison should hold operand range and authenticated wire commitments fixed. The transaction-binding comparison should hold payout and replay semantics fixed. Native proof verification should be compared with a Script construction at an explicitly chosen soundness target.

### 9.4 Publication and review deliverables

Version 0.3 should extend outcome coding across the historical frame and execute a concrete verifier under the paired and merged contracts. A separate application should identify an independently useful connector role if it seeks to establish additional value for the sibling predicate. Every proposed readiness improvement should point to the evidence that changed its gate.

A later activation recommendation would require a wider body of review than this repository can supply. The immediate deliverable is an inspectable specification and experiment package that makes unresolved choices concrete.

## 10. Limits of the present draft

The historical cohort is purposive and contains correlated families. Current document status sometimes compresses several earlier outcomes. Some contemporary messages survive through copies, whose provenance is recorded below. The paper treats political mechanisms as hypotheses and participant statements as attributed evidence.

The recent portfolio contains research implementations with different proof and authorization boundaries. Existing native test counts come from pinned guides and inspected runs. The new experiment executes a structural model and serializes declared byte layouts. Its ideal authorization predicates and symbolic policy commitments leave native consensus enforcement to further work. The formal propositions concern set inclusion, dependency logic and a conditional mapping between one-shot claim states.

The most immediate open comparison is the additional value of each new primitive for one complete authorized spend. That experiment should include its recovery behavior and the costs imposed on an independent validating node.

## Appendix A. Current metadata in the historical frame

The extractor records the following archive labels for the 39 included documents. These counts include related components and activation rules. They are document counts under the declared selection rule.

| Current index layer | Deployed | Complete | Draft | Closed | Total |
|---|---:|---:|---:|---:|---:|
| Consensus soft fork | 14 | 1 | 5 | 8 | 28 |
| Consensus hard fork | 0 | 0 | 0 | 11 | 11 |

BIP18 illustrates why semantic outcome coding must follow extraction: its author describes protocol identity with BIP16 despite the documents' different status labels. Closed likewise compresses several earlier closure categories. The [frame file](historical-frame.json) retains every included row and every date exclusion, with its source blob and exact URL.

## Sources and provenance

BIP references resolve to the pinned official repository snapshot. Release notes and original discussions retain their publication URLs. The cohort ledger includes the same provenance fields.

The SegWit2x reference identifies Mike Belshe's 8 November 2017 “Segwit2x Final Steps” message through a contemporaneous full copy. Its original mailing-list address is https://lists.linuxfoundation.org/pipermail/bitcoin-segwit2x/2017-November/000685.html; that endpoint was unavailable during this review. The paper attributes the suspension rationale to the signatories.

Bitcoin Cash's technical source is the Bitcoin ABC v0.16.0 UAHF specification. Its first-party history supplies the observed launch date. Current proposal statuses were checked against official BIP text; the inspected Core source supplies additional implementation context for the named unfinished extensions.


The [source index](references.json) records exact URLs, repository pins and source-provenance notes. The [cohort ledger](cohorts.json) keeps historical episodes alongside the separately versioned recent portfolio.

<!-- reference-definitions -->
[BIP2]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0002.mediawiki "Bitcoin Improvement Proposal 2"
[BIP3]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0003.md "Bitcoin Improvement Proposal 3"
[BIP9]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0009.mediawiki "Bitcoin Improvement Proposal 9"
[BIP12]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0012.mediawiki "Bitcoin Improvement Proposal 12"
[BIP16]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0016.mediawiki "Bitcoin Improvement Proposal 16"
[BIP17]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0017.mediawiki "Bitcoin Improvement Proposal 17"
[BIP18]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0018.mediawiki "BIP 18: hashScriptCheck"
[BIP34]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0034.mediawiki "Bitcoin Improvement Proposal 34"
[BIP50]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0050.mediawiki "Bitcoin Improvement Proposal 50"
[BIP65]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0065.mediawiki "Bitcoin Improvement Proposal 65"
[BIP66]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0066.mediawiki "Bitcoin Improvement Proposal 66"
[BIP68]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0068.mediawiki "Bitcoin Improvement Proposal 68"
[BIP90]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0090.mediawiki "Bitcoin Improvement Proposal 90"
[BIP91]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0091.mediawiki "Bitcoin Improvement Proposal 91"
[BIP101]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0101.mediawiki "Bitcoin Improvement Proposal 101"
[BIP102]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0102.mediawiki "Bitcoin Improvement Proposal 102"
[BIP109]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0109.mediawiki "Bitcoin Improvement Proposal 109"
[BIP112]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0112.mediawiki "Bitcoin Improvement Proposal 112"
[BIP113]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0113.mediawiki "Bitcoin Improvement Proposal 113"
[BIP114]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0114.mediawiki "Bitcoin Improvement Proposal 114"
[BIP116]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0116.mediawiki "Bitcoin Improvement Proposal 116"
[BIP117]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0117.mediawiki "Bitcoin Improvement Proposal 117"
[BIP118]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0118.mediawiki "Bitcoin Improvement Proposal 118"
[BIP119]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0119.mediawiki "Bitcoin Improvement Proposal 119"
[BIP125]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0125.mediawiki "Bitcoin Improvement Proposal 125"
[BIP131]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0131.mediawiki "BIP 131: 'Coalescing Transaction' Specification (wildcard inputs)"
[BIP134]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0134.mediawiki "BIP 134: Flexible Transactions"
[BIP140]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0140.mediawiki "BIP 140: Normalized TXID"
[BIP141]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0141.mediawiki "Bitcoin Improvement Proposal 141"
[BIP143]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0143.mediawiki "Bitcoin Improvement Proposal 143"
[BIP144]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0144.mediawiki "Bitcoin Improvement Proposal 144"
[BIP147]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0147.mediawiki "Bitcoin Improvement Proposal 147"
[BIP148]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0148.mediawiki "Bitcoin Improvement Proposal 148"
[BIP149]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0149.mediawiki "BIP 149: Segregated Witness (second deployment)"
[BIP324]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0324.mediawiki "Bitcoin Improvement Proposal 324"
[BIP340]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0340.mediawiki "Bitcoin Improvement Proposal 340"
[BIP341]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0341.mediawiki "Bitcoin Improvement Proposal 341"
[BIP342]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0342.mediawiki "Bitcoin Improvement Proposal 342"
[BIP343]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0343.mediawiki "Bitcoin Improvement Proposal 343"
[BIP347]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0347.mediawiki "Bitcoin Improvement Proposal 347"
[BIP348]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0348.md "Bitcoin Improvement Proposal 348"
[BIP360]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0360.mediawiki "Bitcoin Improvement Proposal 360"
[BIP440]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0440.mediawiki "Bitcoin Improvement Proposal 440"
[BIP441]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0441.mediawiki "Bitcoin Improvement Proposal 441"
[BIP446]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0446.md "Bitcoin Improvement Proposal 446"
[BIP448]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0448.md "Bitcoin Improvement Proposal 448"
[BCHHISTORY]: https://bitcoincash.org/ "Bitcoin Cash first-party history"
[BIP446VECTORS]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0446/basics.json "BIP446 basic template test vectors"
[BIPINDEX]: https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/README.mediawiki "Official BIP index at the historical-frame snapshot"
[CORE0131]: https://bitcoincore.org/en/2016/10/27/release-0.13.1/ "Bitcoin Core 0.13.1 released"
[CORE0211]: https://bitcoincore.org/en/releases/0.21.1/ "Bitcoin Core 0.21.1 release notes"
[CORE081]: https://bitcoin.org/en/release/v0.8.1 "Bitcoin-Qt version 0.8.1 released"
[CORE2016]: https://bitcoincore.org/en/2016/01/07/statement/ "Bitcoin Core statement on consensus upgrades"
[COREINTERPRETER]: https://github.com/bitcoin/bitcoin/blob/9183edd25e60aa410bc3e4728989a1d75c309a09/src/script/interpreter.cpp "Bitcoin Core interpreter at inspected revision"
[CPA]: https://github.com/patrickdugan/bitcoin-rs/blob/29ca519031fcd67f467881e16ba73e0eb1211759/docs/research/bip-canonical-proof-authority.md "Canonical Proof Authority research draft"
[CPAGUIDE]: https://github.com/patrickdugan/bitcoin-rs/blob/29ca519031fcd67f467881e16ba73e0eb1211759/docs/research/canonical-proof-authority.md "Canonical Proof Authority bitcoin-rs integration guide"
[CPARUN]: https://github.com/patrickdugan/bitcoin-rs/actions/runs/43399348447 "bitcoin-rs CPA research workflow run 43399348447"
[CSVNOTICE]: https://bitcoincore.org/en/2016/06/21/csv-softfork-instructions/ "CSV softfork instructions"
[DBDEADLINE]: https://bitcoin.org/en/alert/2013-03-15-upgrade-deadline "Bitcoin fork: March 2013 upgrade deadline"
[DERALERT]: https://bitcoin.org/en/alert/2015-07-04-spv-mining "Some miners generating invalid blocks"
[IOBGRAPH]: https://github.com/patrickdugan/Spiral/blob/76071a0195f48961386e46d56df7b5e0276637fc/in-and-out-burger/iob/bitvm3.py "Iob Graph"
[IOBHARNESS]: https://github.com/patrickdugan/Spiral/blob/76071a0195f48961386e46d56df7b5e0276637fc/in-and-out-burger/scripts/bitvm3_regtest.py "Iob Harness"
[IOBRECEIPT]: https://github.com/patrickdugan/Spiral/blob/76071a0195f48961386e46d56df7b5e0276637fc/in-and-out-burger/results/bitvm3-regtest.json "Iob Receipt"
[KCS]: https://github.com/patrickdugan/Spiral/blob/cfafbec4ae072b859f0140b2487baac14fac3a44/BIPSpace/Keyless-CHECKSIG/bip-keyless-checksig.md "Keyless CHECKSIG research draft"
[KCSNATIVE]: https://github.com/patrickdugan/bitcoin-rs/blob/188e2d78fbb623a12a42772120a2aa4e437905c1/docs/research/keyless-checksig.md "Keyless CHECKSIG bitcoin-rs integration guide"
[KCSRUN]: https://github.com/patrickdugan/Spiral/actions/runs/43224248696 "Spiral Core regtest research workflow run 43224248696"
[KCSSTATE]: https://github.com/patrickdugan/Spiral/blob/cfafbec4ae072b859f0140b2487baac14fac3a44/BIPSpace/Keyless-CHECKSIG/state-linked-verifier.md "Keyless CHECKSIG state-linked verifier guide"
[KEYLESSSTATE]: https://github.com/patrickdugan/bitcoin-rs/blob/188e2d78fbb623a12a42772120a2aa4e437905c1/docs/research/keyless-state-machine.md "Keyless State"
[MULADD]: https://github.com/patrickdugan/Spiral/blob/7f5ad9f95fce8c40919e360000ca86c7119ceb5c/BIPSpace/Bounded-Modular-Arithmetic/DRAFT.md "Bounded Modular Arithmetic for Tapscript research draft"
[MULADDAUDIT]: https://github.com/patrickdugan/bitcoin-rs/blob/c64e452211575c7cc6e28c448ef67fae93756e82/docs/research/muladdmod-security-audit.md "Muladd Audit"
[MULADDPR]: https://github.com/patrickdugan/bitcoin-rs/pull/1 "bitcoin-rs PR 1: bounded modular arithmetic integration"
[MULADDRECEIPT]: https://github.com/patrickdugan/bitcoin-rs/blob/c64e452211575c7cc6e28c448ef67fae93756e82/docs/research/muladdmod-audit-results.json "Muladd Receipt"
[PROVEN]: https://github.com/patrickdugan/Spiral/blob/cfafbec4ae072b859f0140b2487baac14fac3a44/in-and-out-burger/research/provenspend/bip-provenspend.md "ProvenSpend research draft"
[ROADMAP2015]: https://bitcoincore.org/en/2015/12/07/roadmap/ "Capacity increases for the Bitcoin system"
[S2X]: https://bitcointalk.org/index.php?topic=2376285.0 "Mike Belshe et al., Segwit2x Final Steps; contemporaneous copy of original message"
[SEGWITBENEFITS]: https://bitcoincore.org/en/2016/01/26/segwit-benefits/ "Segregated Witness Benefits"
[SEGWITGUIDE]: https://bitcoincore.org/en/segwit_wallet_dev/ "Segregated Witness Wallet Development Guide"
[SIBLING]: https://github.com/patrickdugan/Spiral/blob/cfafbec4ae072b859f0140b2487baac14fac3a44/in-and-out-burger/research/checksiblingverify/bip-XXXX-checksiblingverify.mediawiki "CHECKSIBLINGVERIFY research draft"
[SPEEDY]: https://gnusha.org/pi/bitcoindev/20210306034343.fhwrxmq6gbb2os5m@ganymede/ "David A. Harding, Taproot activation proposal: Speedy Trial"
[SPEEDYCHOWPARAMS]: https://gnusha.org/pi/bitcoindev/5be46169-8f38-da73-4112-fba2aff6dfcb@achow101.com/ "Andrew Chow, proposed Speedy Trial parameters"
[SPEEDYCHOWREPLY]: https://gnusha.org/pi/bitcoindev/f75938e8-6e81-b13b-e085-ca91971ce23f@achow101.com/ "Andrew Chow, reply on scheduling a follow-up deployment"
[SPEEDYCORALLO]: https://gnusha.org/pi/bitcoindev/2a6955d6-d242-89f5-d622-82889d499cc0@mattcorallo.com/ "Matt Corallo, reply on Speedy Trial signaling window"
[SPEEDYCORALLOCLARIFY]: https://gnusha.org/pi/bitcoindev/a76b9eee-0015-105c-2c8d-6131a91e95e3@mattcorallo.com/ "Matt Corallo, clarification of coordination objective"
[SPEEDYDASHJR]: https://gnusha.org/pi/bitcoindev/202103150251.46902.luke@dashjr.org/ "Luke Dashjr, activation-window overlap concern"
[SPEEDYHARDINGREPLY]: https://gnusha.org/pi/bitcoindev/20210306202350.qdcpvxgedn6qhuxa@ganymede/ "David A. Harding, reply on self-determination and timing"
[UAHF]: https://github.com/Bitcoin-ABC/bitcoin-abc/blob/v0.16.0/doc/abc/uahf-technical-spec.md "Bitcoin ABC v0.16.0 UAHF technical specification"
