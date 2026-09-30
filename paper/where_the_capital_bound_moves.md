# Where the Capital Bound Moves

## Settlement Objects, Proof-Carrying Registries, and a Warden Model for Agent Payment Networks

**Authors:** Dugan

**Program:** Spiral

**Version:** Model draft, September 30, 2026. Builds on the audited baseline (a0a3140) and the adversarial follow-up of September 11, 2026.

## Abstract

The two earlier Spiral campaigns, read together, establish one result that the surrounding text under-states: on sampled public Lightning topology with synthetic hidden state, an adaptive agent buys almost nothing over a wallet that retries, and whatever a population gains comes from committing scarce capital in the direction demand happens to persist. The constraint is not intelligence. It is the settlement object: a bilateral, pre-funded, direction-partitioned channel whose inbound side must be provisioned before demand is known. This paper models three objects that change where that constraint sits, none of which removes it. Ark virtual outputs replace the directional pre-funding guess with volume-priced server capital and a liveness obligation that autonomous agents, unlike humans, satisfy at negligible cost. Zero-knowledge statements over a settled-resource set close the premise the identity-split theorem was missing, so a reward layer can be Sybil-bounded without identities. Optimistic escrows in the BitVM3 pattern make a bond enforceable against an uncooperative operator with a 93-vB disprove, which converts the follow-up's "bond is a field, not an account" finding into a typed on-chain object. Each is stated as a typed resource with a finality clock, an exit cost, a liveness obligation, and a counterparty exposure, and the earlier ledger is extended so that cross-object transfers are settlement events rather than notational relabelings. A warden model then fixes which observer sees what under each object and bounds what a covert coalition of agents can earn: no better than the authenticated capital it controls placed under stationary demand, which the earlier campaigns measured at roughly six success points. The steganographic question is therefore second-order to the capital question, and the paper says what a preregistered study of the first-order question needs. Nothing here is a live measurement; every protocol figure is cited from its implementer's current documentation or from a peer-reviewed construction, and every obligation left open by the earlier papers is either discharged by a named mechanism or restated as still open.

**Keywords:** Lightning Network, Ark, virtual UTXO, BitVM, covenants, zero-knowledge proofs, Sybil resistance, autonomous agents, covert coordination, settlement finality

## 1. What the earlier campaigns actually found

Connector Calculus [R1] and its audit [R2] were written as a liquidity paper and a critique of one. Their strongest joint finding is elsewhere. In the sealed public-topology campaigns, bounded retries improve success over one-shot routing by 5.14 points; terminal-feedback learning adds 0.35 points, inside the predeclared equivalence band; exact hidden-state knowledge adds 1.11 points, and the audit shows that under free failures the oracle's advantage is an attempt budget rather than information. Equal-budget failure-aware capital placement beats random placement by 6.13 points when demand is stationary and by nothing distinguishable from zero after a shift [R1, §9.8; R2, §6–7]. The hive coordination bonus was a configured input [R1, hive supplement].

Read as a whole, that is a negative result about agent advantage within the tested interfaces, and a positive result about capital: the deployable gain belongs to whoever commits scarce directional capacity where demand will persist. A routing intelligence cannot relax the bound because the bound is not a property of routing. It is a property of the object being routed over, and the object has three features that together produce the finding: it is bilateral, so each unit of capacity is pinned to one edge; it is pre-funded, so capital is committed before demand is known; and it is direction-partitioned, so ℓ_{i,+}+ℓ_{i,−}=χ_i holds per channel and inbound capacity on one side is outbound on the other and must be supplied by someone who guessed correctly.

The claim that Lightning "will never work" for an agent economy without further settlement machinery is, in that form, not falsifiable and not what the evidence supports. The falsifiable form is narrower. For a population of high-frequency, low-balance, always-online payers, the cost of the inbound-provisioning guess dominates the cost of routing, and no policy in the routing layer reduces it. A settlement object that prices capital by volume rather than by balance forecast, and that lets a server allocate inbound at the moment of a spend rather than before it, changes the cost function the agents face. Whether it changes it favorably is a measurable ratio, defined in §3. That is the sense in which this paper is about where the bound moves rather than whether it exists.

### 1.1 Contributions and their obligations

First, a typed settlement-object model in which on-chain outputs, channel balances, Ark virtual outputs, and optimistic escrows are instances of one resource tuple, and the ledger of [R2] is extended so that transfers between objects are settlement events with clocks rather than relabelings (§2). Second, a relocation result for the prefix cut bound of [R2, §5] under a server-mediated object, with the liquidity-duration ratio that decides which object is cheaper for a given demand process (§3). Third, a proof-carrying registry that discharges the authenticated-uniqueness premise of the identity-split theorem, with the relation stated and the verifier named (§4). Fourth, an escrow state machine with the BitVM3 cost and honesty parameters, which discharges the audit's finding that bonds are fields (§5). Fifth, a warden model that fixes the observer for each object and bounds the coordination gain available to a covert coalition (§6). Sixth, the preregistration outline for the one experiment that would test the first-order claim (§7).

Every one of these is a model. The proving system is not run; the recovered project's out-of-memory failures are still the last local record. No Ark server, BitVM operator, or Lightning node is contacted. Protocol parameters (28-day lifetime, 144-block exit, 93-vB disprove) are those published by implementers at the cited dates and are configurable or revisable; the model treats them as parameters, not constants.

## 2. Settlement objects as typed resources

### 2.1 The resource tuple

Let a settlement object be

```math
\rho=(\mathcal{A},\,v,\,F,\,X,\,\Lambda,\,\Gamma,\,\tau),
```

where 𝒜 is the spend authority (a script or a signer set), v the value, F the finality clock (a function from elapsed time or block height to a settled/pending status), X the unilateral exit (a cost and a delay), Λ the liveness obligation the holder carries to keep the object trustless, Γ the set of parties whose misbehavior can cost the holder money or access, and τ the expiry after which the object's trust assumptions change. The ledger of [R2] had only ℓ and χ; it had no clock, no exit, and no counterparty, which is exactly why its virtual connector could be "declared" and never executed.

| Object | 𝒜 | F | X | Λ | Γ | τ |
|---|---|---|---|---|---|---|
| U: on-chain output | script | k confirmations | none | none | consensus only | ∞ |
| C: channel balance (directional) | 2-of-2 + HTLC | HTLC settle, bilateral | commitment tx + to_self_delay | watch for breach | counterparty liveness | ∞, direction-locked |
| V: Ark VTXO | user ∧ server (MuSig2), or user after CSV | round tx confirmation; arkoor pending | branch + leaf broadcast, CSV 144 (~24 h) | refresh before τ | server (censor), sender+server (collude on pending) | 28 d, server-configurable |
| E: optimistic escrow | script: release after Δ, or slash on disprove | challenge period Δ | on-chain already | ≥1 honest challenger online | setup committee (1-of-n deletes key) | program-defined |
| E′: native covenant escrow | template-enforced script | template match | on-chain already | none | consensus only | program-defined |

Parameters for V are from the Second documentation as of September 2026 [R3, R4]; E from BitVM3 [R7]; E′ is included for comparison and is not available, since no covenant opcode is active on mainnet at the cited date [R8].

Three observations the table makes visible. The channel is the only object whose value is direction-partitioned: a VTXO of value v is spendable to any counterparty the server will co-sign for, so there is no inbound side to provision. The VTXO is the only object with a hard liveness obligation on the holder's calendar, and it is the object whose obligation an autonomous process meets most cheaply. The escrow is the only object whose finality is a game rather than a count, and its Γ is not a counterparty but a committee.

### 2.2 The extended ledger

Replace the ledger of [R2, §9] with

```math
X_n=(\ell^{U},\,\ell^{C},\,\ell^{V},\,\ell^{E},\,h,\,\mathcal{U},\,\mathcal{J},\,\kappa_n),
```

where each ℓ^{·} is the holdings vector for that class, h the pending holds as before, 𝒰 the registry (now proof-carrying, §4), 𝒥 the journal, and κ_n the vector of clocks: block height, and per-object elapsed time since issuance. The per-channel constraint ℓ^{C}_{i,+}+ℓ^{C}_{i,−}=χ_i is retained for class C only. Class V carries a per-holder constraint 0 ≤ ℓ^{V}_u and a per-server liability described in §3. Class E carries a per-escrow state from §5.

A cross-class transfer is a settlement event σ = (from-class, to-class, amount, clock-condition). It is journaled at initiation, held in h, and moves ℓ only when its clock condition fires. Examples: U→C is a funding transaction with condition "k confirmations"; V→C is an HTLC-scripted VTXO spent by the server into a Lightning HTLC, with condition "HTLC settled"; C→V is the mirror; V→U is a cooperative offboard or a unilateral exit with condition "CSV 144 elapsed"; U→E is escrow deposit; E→U is release after Δ or slash on disprove.

**Proposition S1 (cross-class conservation at settled states).** Let a finite set of settlement events be journaled, and let every event's clock condition have fired or been aborted. Then Σ over classes of Σ over holders of ℓ, plus fees paid to relays and miners, plus amounts slashed, equals the same sum at the initial state plus external funding. During pending intervals the identity holds only with h included on both sides.

The proof is the same bookkeeping as [R2, L1] with one addition: an aborted event releases its hold and moves nothing. What the proposition rules out is the move the earlier virtual connector made implicitly, which was to count a declared cross-system claim as liquidity before its clock fired. What it does not establish is that any particular clock fires: an Ark round may not confirm, an HTLC may time out, a challenge period may end in a slash. Those are the finality assumptions per object, and they are inputs.

## 3. Where the cut bound goes

### 3.1 The channel bound, restated

For a node set A on Lightning, [R2, §5] gives the necessary prefix condition on cumulative settled crossings,

```math
O_A(n)-I_A(n)\le L_A(0)+K_A(n)\quad\text{for every }n,
```

where K_A(n) is net directional stock added by funding, splicing, or leasing, each of which is a U→C event with a confirmation clock. For a set of agents that mostly pay outward, I_A is small and the inequality binds on K_A, which is to say on someone having pre-funded inbound toward A's counterparties or outbound from A. That someone must forecast. The forecast error is the cost the earlier campaigns could not reduce by any routing policy.

### 3.2 The server bound

Let a server S issue VTXOs to a holder set A. Holders have no directional stock. Model the server's liquidity as a stock R_S(n) with three sinks and two sources per round r: it funds new VTXOs at refresh, fronts Lightning spends at the moment of spend, and funds offboards; it recovers forfeited or expired VTXO value when a round's absolute timelock allows a sweep, and it receives inbound HTLC settlements on its own channels. The Second documentation states the sinks as the three liquidity operations and states that forfeits are insurance, with recovery by sweeping the round after its timelock [R4, R5].

Write V_A(n) for total VTXO value held by A, W_S(n) for value the server has committed to rounds and not yet recovered, and B_S for the server's on-chain and channel capital. Then for A served by S,

```math
O_A(n)-I_A(n)\le V_A(0)+K^{S}_A(n),\qquad\sum_{A}K^{S}_A(n)\le B_S-W_S(n),
```

where K^{S}_A(n) is what the server has allocated to A at the moment of A's spends. The first inequality is the same shape as the channel bound. The second is new: it aggregates over every holder the server serves, and it is time-indexed through W_S, which at any moment is the value of outputs the server has fronted (at a spend, a refresh, or an offboard) whose forfeits it cannot yet sweep because their absolute expiry has not passed.

**Proposition S2 (bound relocation).** Under a server-mediated object, the per-cut directional constraint on A is replaced by an aggregate constraint on the server's uncommitted capital. The constraint is not removed; it is pooled across holders and indexed by VTXO lifetime instead of by edge direction. A coalition of holders cannot raise Σ_A K^{S}_A above B_S − W_S by any pattern of coordination; it can only change which holders consume it and when.

The proof is by definition of W_S and the fact that the server co-signs every issuance. What the proposition buys is precise: the forecast the channel model demanded per edge is replaced by a forecast per server of aggregate volume, which is a lower-variance quantity for the same population, and the direction problem disappears because a VTXO has no direction. What it costs is also precise: the holder must be online to refresh before τ, the server can decline to include a holder in a round, and a pending arkoor payment is trusted until the round confirms [R3]. For an autonomous agent the first cost is near zero, the second is a censorship exposure the channel model shares in the form of a counterparty who can force-close, and the third is a per-payment settlement delay of at most one round interval, hourly by default [R3].

### 3.3 The ratio that decides

Second's own simulation reports that an LSP's liquidity requirement is driven by changes in user balances and an Ark server's by payment volume, and that the comparison flips with top-up frequency: weekly top-ups favor the LSP by 2.5×, quarterly top-ups favor Ark by 3.73×, and dollar-cost-averaging stackers favor Ark by 6.65× [R5]. Those are their numbers under their assumptions (28-day expiry, refresh two days before expiry), and this paper does not reproduce them. What it does is name the quantity.

Define, for a demand process D over a horizon H, the liquidity duration of an object as capital-time locked per unit delivered,

```math
\mathcal{D}_{\rm obj}(D,H)=\frac{1}{\mathrm{Vol}(D,H)}\int_0^H \mathrm{Locked}_{\rm obj}(t)\,dt .
```

For the channel, Locked_C(t) is the pre-funded inbound stock, which must be set to a forecast f̂_a of the peak balance each agent a will hold in its channel over the horizon (the running maximum of receipts minus spends) and held for the horizon whether or not the peak is reached; underestimates fail receipts, which is the failure the earlier campaigns measured from the routing side, and overestimates sit idle. For the VTXO, Locked_V(t) is W_S(t), which is the sum over forfeited-but-unswept outputs of their value, each locked from the moment of spend or refresh until its absolute expiry, so it scales with volume times the mean residual lifetime L̄ at forfeit. Writing H for the horizon and Vol for delivered volume,

```math
\frac{\mathcal{D}_C}{\mathcal{D}_V}\;\approx\;\frac{H\sum_a \hat f_a}{\mathrm{Vol}\cdot \bar L}.
```

The ratio exceeds one when pre-funded capacity sits idle for long relative to the VTXO lifetime: many agents whose individual demand is bursty and hard to forecast, so that Σ_a f̂_a is large against pooled volume, over a horizon long against 28 days. It falls below one when balances recycle within one channel faster than the lifetime, so that a small pre-funded envelope serves a large volume: a few agents in steady bidirectional flow with fixed counterparties. Second's simulation has the same shape from the human side: weekly top-ups favor the LSP because the channel's capacity is reused every week while Ark locks each spend for up to 28 days, and quarterly top-ups favor Ark because the channel must hold a quarter's lump idle [R5].

What the ratio says about agents is then conditional and specific. An agent population is not favored by Ark because it is high-frequency; high frequency to a fixed counterparty is the channel's best case. It is favored when the population is large, its per-agent demand is idiosyncratic, its counterparties vary, and the forecast margin Σ_a f̂_a that a channel operator would have to carry across all of them exceeds what a single server locks by fronting spends as they occur. The pooling in S2 is the whole effect, and the liveness obligation that makes pooling safe is the one an autonomous process meets for free.

That is the defensible version of the claim that Lightning does not serve an agent population without a different settlement object. It is a conjecture about a ratio, and §7 says how to measure it on the retained simulator.

### 3.4 What happens to the ghost solver

A consequence for the earlier apparatus. If agents hold VTXOs and pay Lightning invoices through the server's HTLC-scripted outputs [R4], the graph the agents see is a star with the server at its center, and the server's own channels are the only edges with direction. The cut deficits of [R1, §4.3] then live on the server's channel set, not among the agents. The ghost solver's job is to size and place the server's Lightning capacity given the aggregate demand its VTXO holders present, and a ghost edge compiles to a topological or leased connector on the server side. The agent tier has no ghost edges. The earlier machinery is not discarded; it is moved one tier up and applied to a smaller, better-observed graph.

## 4. Proofs: closing the registry premise

### 4.1 The premise

The identity-split theorem [R1, Prop. 5; R2, L4] holds for a fixed integer allocation R_u to a scarce resource u with an authenticated weight w_u. The audit found the implementation fabricating weights by taking unrelated maxima and accepting duplicate capital under distinct identifiers [R2, §11]. Its conclusion was that a registry 𝒰 must decide which jointly authenticated record defines w_u, and it left the authentication as an obligation.

Authentication has two obvious routes. One is identity: the reward allocator knows who owns what. The other is exposure: a claimant proves it controls a settled object of at least the claimed value, and proves that no other claimant is using the same object, without revealing which object. The first route defeats the purpose of a permissionless service market and is what the manuscript's §10 said it would not demand. The second is a standard zero-knowledge construction and this section states it.

### 4.2 The unique-exposure relation

Let 𝒮_n be the set of settled objects at step n in the classes U, C, V, E, each with an identifier id_ρ, a value v_ρ, and an authority 𝒜_ρ that a key k_ρ satisfies (for a single-signer object, pk_ρ = KeyGen(k_ρ); for a multisignature authority, the claimant's share). Let cm be a commitment to a claimant identity secret s, used only to link a claim to the identity that will be paid. Define the relation

```math
\mathcal{R}_{\rm cap}=\Big\{\big((cm,\,v,\,nf,\,\mathrm{root}_n),\,(s,\,k_\rho,\,\rho,\,\pi_\rho)\big):\ cm=\mathrm{Com}(s),\ \rho\in\mathcal{S}_n\text{ via }\pi_\rho,\ k_\rho\ \text{satisfies}\ \mathcal{A}_\rho,\ v_\rho\ge v,\ nf=\mathrm{PRF}_{k_\rho}(id_\rho)\Big\},
```

where root_n is a commitment to 𝒮_n (a Merkle root over the settled set as the verifier knows it), π_ρ a membership path, and nf a nullifier keyed by the object's own authority, not by the claimant. A claim is a statement (cm, v, nf, root_n) with a proof. The registry accepts it if the proof verifies and nf is not already in the registry's nullifier set. The registry records (cm, v, nf); it does not learn ρ. The choice of key matters: had nf been keyed by s, a single controller could claim ρ once per identity by choosing a fresh s each time, which is the split the theorem is supposed to exclude.

**Proposition S3 (Sybil-bounded weight).** If the proof system for 𝓡_cap is knowledge-sound and PRF is a pseudorandom function, then for every settled object ρ the total weight the registry attributes to claims backed by ρ is at most v_ρ, whatever the number of claimant identities, except with negligible probability. If the proof system is zero-knowledge, the registry learns nothing about ρ beyond v_ρ ≥ v and the nullifier.

The bound follows because every valid claim on ρ carries nf = PRF_{k_ρ}(id_ρ), which is a function of ρ alone once k_ρ is fixed by 𝒜_ρ, so a second claim on the same ρ collides in the nullifier set and is rejected; a claim with a different nf on ρ would require a different key satisfying 𝒜_ρ, which for a single-signer object does not exist and for a threshold object is bounded by the threshold and can be handled by deriving nf from the aggregate key. Knowledge soundness reduces a claim without k_ρ to a break of the proof system. This is the Zcash nullifier argument transplanted from spend-once to claim-once, and it is the exact premise the identity-split theorem needed. With it, L4 is no longer conditional on an unauthenticated dictionary; it is conditional on a proof system and on the verifier's view of 𝒮_n being correct.

### 4.3 The service relation

The manuscript's §10.1 wanted a connector to prove "that a service window existed" without revealing customers. State it. Let a connector κ receive requests over [t_0, t_1] from counterparties who each sign an attestation a_j = Sig_j(κ, t_j, outcome_j). Define

```math
\mathcal{R}_{\rm svc}=\Big\{\big((\kappa,\,t_0,\,t_1,\,m,\,k),\,(\{a_j\}_{j=1}^{m})\big):\ \text{each }a_j\text{ verifies under a key in the registry's counterparty set},\ t_j\in[t_0,t_1],\ \#\{j:\mathrm{outcome}_j=\mathrm{honored}\}\ge k\Big\}.
```

A service receipt is a statement (κ, t_0, t_1, m, k) with a proof. The reward layer uses k/m as the service weight for the window. The counterparties are not revealed; the keys must be in a set the verifier trusts, which reintroduces a registry of counterparties, but one that need only attest to key validity, not to transactions. This is the version of "accountability attaches to the economic action, not to a biography of the software" that can be verified.

### 4.4 Who verifies

On Bitcoin nothing in consensus verifies a SNARK. The verifier of a claim on 𝓡_cap or 𝓡_svc is therefore one of three parties: the reward allocator, which is a trusted server; the Ark server, which is already trusted for co-signing and is well placed to hold root_n for class V; or an optimistic game in which an operator asserts the statement and any challenger can disprove it on-chain. The third is §5. The honest statement of the ZK requirement is then: a permissionless reward layer over Lightning needs a verifier for statements about hidden capital and hidden service, and on Bitcoin that verifier is either a party you trust or a BitVM game whose cost you pay.

Two obligations remain open and are not discharged here. The proving cost for 𝓡_cap over a Merkle path and a PRF is small by current standards; the proving cost for 𝓡_svc over m signatures grows with m and is the statement whose memory budget the recovered project failed to meet. And root_n for class C is a problem: channel balances are not a public settled set, so a claim on channel capital can only prove channel existence and capacity from gossip, not directional balance. That is the same public/private split the whole program began with, and proofs do not cross it.

## 5. Enforcement: the bond as an object

### 5.1 What the audit found

Every bond in the earlier implementation was a number in a record, released or slashed by arithmetic on the same record, and the audit showed a negative slash, an over-release, and a bond declared after the endpoint's wealth was exhausted [R2, §11]. Its instruction was that bonding needs an account. Under the tuple of §2, an account is an object of class E: an on-chain output whose script releases to the operator after a period Δ unless a valid disprove consumes a connector output first.

### 5.2 The escrow state machine

Let an escrow be E(B, κ, Δ) with bond B for connector κ. Its states are

```math
\mathrm{Locked}\ \xrightarrow{\ \text{Assert}(\pi)\ }\ \mathrm{Claimed}\ \xrightarrow{\ \Delta\text{ elapsed, no Disprove}\ }\ \mathrm{Released},\qquad \mathrm{Claimed}\ \xrightarrow{\ \text{Disprove}(\ell^{*})\ }\ \mathrm{Slashed}.
```

Assert is the operator's on-chain commitment to a statement, in the BitVM3 pattern a garbled-encoding-extractable signature on a SNARK proof of the release condition. Disprove is any challenger's revelation of a false-output label, which is a hash-lock spend. Released is the operator's spend of the reserve and the still-unspent connector output after the relative timelock. The release condition is a statement in 𝓡_svc with k/m above the bonded threshold, or, for a simpler first deployment, a statement that a counterparty attestation of failure does not exist, which is a non-membership statement and harder; the paper's recommendation is the positive form.

The parameters as published [R7]: an Assert of about 2.4 kvB, a Disprove of about 93 vB, an off-chain garbled circuit of about 41 GB for a Groth16 verifier, six minutes to evaluate, one honest challenger online at all times, and a setup committee honest at setup with at least one signer deleting its key afterward. The operator's capital cost is B locked for Δ plus the Assert fee; the challenger's cost is the Disprove fee and the evaluation time. Soundness is Theorem 7.2 of [R7] under those assumptions and the random-oracle model.

**Proposition S4 (enforceable bond).** Under the BitVM3 assumptions, an escrow E(B, κ, Δ) whose release condition is a statement in a SNARK-provable relation is enforceable against an uncooperative operator: a false Assert is slashed by any single honest challenger at a cost independent of B, and a true Assert is released after Δ. The bond is therefore an account in the audit's sense exactly when 𝒰 records the escrow's outpoint and 𝒥 records its state, and the ledger's release arithmetic is replaced by the object's own transitions.

The proposition is conditional on assumptions that a Lightning node does not otherwise carry: a committee, a challenger, and a 41-GB setup per operator per program. It is the correct scale for a bond on a connector whose horizon is days and whose value is large relative to Assert fees. It is the wrong scale for per-payment enforcement, and this is the place to say what "BitVM-secured covenants" can and cannot do for Lightning itself.

### 5.3 Scale: escrows, not HTLCs

A native covenant opcode enforces a template on every spend at consensus cost; that is what LN-Symmetry and the CTV+CSFS proposals want for channel updates [R8]. An optimistic game enforces a statement once per assertion at the cost of a setup and a challenge period. The two differ by orders of magnitude in per-use cost and in latency, and the difference decides what each secures. BitVM secures objects at the scale of a bridge reserve or a service bond: one Assert per horizon, one Disprove if needed. It does not secure objects at the scale of an HTLC: the 41-GB circuit is per operator per program, and Δ is measured in blocks, not in the milliseconds a hop update takes. So the sentence "Lightning needs BitVM-secured covenants" is true for the bond layer and false for the channel layer, and the model here uses it only for class E.

Native covenants, if activated, replace E with E′: no committee, no challenger, Δ ≈ 0 for template-enforced spends, and the release condition restricted to what script can check, which excludes SNARK verification without further opcodes. As of the cited date no such opcode is active; activation parameters for CTV have been proposed with a 2026 signaling start [R8, R9]. The model keeps E′ as a comparison column and does not depend on it.

## 6. The warden

### 6.1 Observers by object

The earlier papers asked what agents could do on Lightning "in a steganographic setup" and then, correctly, declined to answer without a warden. Fix the wardens. There are four observers, and each object exposes a different trace to each.

| Observer | C: channel | V: VTXO | E: escrow |
|---|---|---|---|
| O_chain | opens, closes, splices, force-close scripts | round transactions, exits, offboards; aggregate per round | deposits, Asserts, Disproves, releases |
| O_gossip | channel_update, node_announcement, policy changes | nothing per holder | nothing |
| O_peer | HTLC amount, timing, CLTV, preimage on one hop | the HTLC the server forwards on its own channel; the holder is behind the server | nothing |
| O_server | none (no server) | every VTXO transfer: parties, amount, time, co-signed | operator's view of its own escrow |

Under the channel, no single observer sees a whole path, which is the property Lightning's privacy literature studies and which its probing and timing attacks partially erode [R10, R11]. Under the VTXO, one observer sees everything within its own Ark: the server co-signs every transfer and therefore knows sender, receiver, amount, and time for every payment it hosts. A server is a total warden for its holders. With the proofs of §4 the server need not publish what it sees, and with a permissionless escrow it need not be trusted to allocate rewards, but its view is not reduced by either.

### 6.2 Three things called coordination

The word covers three activities that need different treatment.

Explicit messaging. Onion payloads carry TLV records, and custom records are a legitimate, specified use [R12]; gossip carries node aliases, colors, and policy fields that any node may set [R13]. An agent population that wants to exchange symbols can do so in these fields at near-unbounded capacity, and detection is traffic analysis, not content analysis. Steganography through amount classes and timing is the expensive way to do what the protocol already permits cheaply. This mode is not the interesting one and should not be studied first.

Implicit coordination. Agents infer shared state from public events with no message at all: a fee update, a failure pattern, an on-chain open. This is not a channel in the information-theoretic sense and has no capacity; it is a Schelling structure, and its monitoring signature is correlation of control loops rather than any payload. It is plausible for AI populations and is what the manuscript's §7.7 gestured at.

Capital coordination. Agents under common control claim rewards, place capital, or manufacture demand as if independent. This is the mode the reward layer must resist and the one the earlier apparatus was built for.

### 6.3 What a coalition can earn

Let a coalition S of agents share a controller and a covert channel of unbounded capacity in the explicit mode. Let the reward layer use the registry of §4 and the escrow of §5. What can S earn beyond what the same agents earn independently?

**Proposition S5 (coordination gain bound).** Under S3, the coalition's total authenticated weight is at most the total value of the distinct settled objects it controls. Under the earlier placement campaigns, the gain available from placing a fixed capital budget with full knowledge of persistent demand is the stationary-hotspot effect, measured at 6.13 points (4.91 to 7.35) over random placement and at nothing distinguishable from zero after a demand shift [R1, §9.8]. Under a service weight that nets value circulated among the claimant's own attesting counterparties, manufactured demand earns no service weight. Therefore the coalition's gain from coordination, in the tested model, is bounded above by the stationary-placement effect on its own capital and is zero under demand shift, whatever the capacity of its channel.

The bound is conditional on three things, each of which is a monitoring target. It assumes S3, so a failure of the registry's proof system or of the verifier's view of 𝒮_n is the first attack. It assumes the placement effect measured on synthetic hidden state transfers, so a demand process with more persistence than tested is the second. It assumes a netting statistic that actually discriminates, and here the earlier baseline is a warning rather than a support: on the hive fixtures a network-wide gross-to-net churn ratio failed as a discriminator, with benign multilateral commerce netting more strongly (12.63) than either labeled pattern (about 7.56), while the features that ranked the fixtures correctly were repeated-edge and repeated-cycle shares under partial observation [R1, hive supplement]. The reference model reproduces the failure and adds a second one. Netting restricted to the direct attesting set of a claim in 𝓡_svc catches reciprocal wash between two parties, misses a four-member relay exactly as the earlier detector did, and saturates toward one when benign trade is dense enough that most counterparties attest. What separates the fixtures is the share of the claimant's volume lying on a directed cycle through the claimant of bounded length whose every edge recurs above a multiplicity threshold; that statistic is computable from the registry's view of claims plus a warden's view of the flows among attesters, and its threshold must scale with observation coverage and volume. Whether it survives realistic benign structure, where short cycles through a busy node recur for ordinary reasons, is open and is the third attack surface. None of the three is a covert-channel problem. All three are capital and observation problems.

The consequence for research order is the paper's main methodological claim. A capacity-versus-detectability curve for a steganographic channel over Lightning payment shape would be a real result, and §7 says how to get it, but it would bound a quantity that S5 already bounds by other means. The first-order question is whether S3 holds and whether the gross-to-net statistic sees enough. Those are the experiments to run.

### 6.4 The warden's test

Formally, the warden observes a trace T from one of the rows of the table and decides between H_0, that the agents generating T draw independent demand from a declared process D, and H_1, that a subset S shares a controller. The likelihood ratio is not computable in general because H_1 is composite. Three statistics are computable and are what the financial-abuse evaluation in the retained code begins to implement: repeated-cycle share through the claimant, which ranked the labeled fixtures above benign commerce in the earlier baseline (ROC AUC 1.00 on deliberately simple fixtures, characterized there as a harness sanity check and not field performance) and separates the reference model's fixtures at full and at 12% observation; nullifier collision rate at the registry, which is exactly zero under honest claims and positive under duplicated capital; and service-versus-demand inconsistency, which is a registry claim of service weight k/m against a demand estimate that does not support it. The naive network-wide churn ratio and the direct-attester netting ratio are not on the list, for the reasons given in §6.3.

What the objects add to the warden is a choice of where to stand. Under V, the server sees the relay set completely and needs no probing; under C, no one does, and the statistic must be estimated from partial hops, which the earlier baseline modeled as an observer seeing 11–13% of events. A safety monitor that wants the capital-coordination signal should therefore sit at the server tier and at the registry, not on the gossip network, and should measure whether cross-server circulation defeats it. That is a different recommendation from the traffic-analysis instinct, and the model supports it.

## 7. The experiment that would test the first-order claim

Preregister the following on the retained simulator, extended with the class-V ledger of §3 and the registry of §4; no live component is required for any of it.

1. Fix a demand process family with three parameters: number of agents, per-agent burstiness (the ratio of an agent's imbalance envelope to its own volume), and horizon relative to VTXO lifetime. Sample the two corners the earlier campaigns did not test: many agents, bursty idiosyncratic demand, varying counterparties, horizon long against 28 days; and few agents, steady bidirectional flow to fixed counterparties, recycling within a day.
2. For each cell, compute 𝒟_C and 𝒟_V by simulation over the horizon with the published Ark parameters as defaults (28-day lifetime, hourly rounds, refresh two days before expiry), a forfeit-to-sweep lock rule for the server, and a channel model that must pre-fund inbound to a forecast envelope carrying a declared safety margin, with payment failures counted when the realized envelope exceeds the forecast. Report the ratio with a cluster-robust interval across sampled topologies. The claim of §3.3 is falsified if the ratio does not exceed one in the first corner or does not fall below one in the second.
3. Implement 𝓡_cap with a real proof system on the settled set of the simulator (not the recovered project's failed configuration: a Merkle path and a PRF, nothing more) and measure prover time and memory. Report whether a claim can be produced within a stated budget. This discharges or renews the ZK obligation on evidence.
4. Run the identity-split experiment of [R1] against the registry: one capital source, 1 to 32 identities, all claims through 𝓡_cap. Aggregate reward must be invariant, and the nullifier-collision statistic must detect every duplicate. Report both.
5. Run the hive-lab common-control fixtures [R1, hive supplement] with ground-truth labels through the three warden rows: O_peer under C, O_server under V, and a mixed C/V relay set. Report ROC per row. The prediction of §6.4 is that O_server dominates O_peer and that the mixed set degrades both.
6. Only then, and as a bounded appendix, define a codebook over amount and timing, a prior over payloads, and a guessing-advantage task for O_peer, and report the capacity–detectability curve. It should be read against S5, not as a headline.

Stopping rules, multiplicity, and the practical-equivalence band are as in the earlier preregistrations. The analysis code must canonicalize graph and candidate order, per the audit's reproducibility finding.

## 8. What each object fixes, and what stays open

| Obligation left by [R1]/[R2] | Discharged by | Still open |
|---|---|---|
| Virtual connector "depends on external settlement" | Class V object with clock, exit, liveness, counterparty (§2) | Live Ark measurement; pending-payment collusion |
| Inbound provisioning under forecast error | Bound relocation S2; liquidity-duration ratio (§3) | The ratio is a conjecture until item 2 of §7 runs |
| Registry 𝒰 "names obligations, does not authenticate" | Unique-exposure relation and S3 (§4) | Verifier; prover cost for 𝓡_svc; no settled set for channel balances |
| "Bond is a field, not an account" | Escrow object and S4 (§5) | Committee and challenger assumptions; per-program setup |
| Warden undefined; no privacy claim | Observer table and S5 (§6) | Cross-server circulation; items 5 and 6 of §7 |

Two assumptions run through everything and are not discharged. The Ark server is trusted not to censor and not to collude with a sender on pending payments; this is the same shape of assumption the channel model makes about a counterparty, but concentrated in one party per Ark. The BitVM3 committee is trusted at setup and one signer is trusted to delete a key; that is a weaker assumption than a federation's and a stronger one than consensus. A native covenant would remove the second and not the first.

## 9. Conclusion

The earlier campaigns showed that an agent's edge on Lightning is not in routing, and the audit showed that the papers' own accounting could not hold a bond, authenticate a claim, or execute a cross-system transfer. This paper treats those three failures as one: the settlement object was untyped. Typed, the channel's constraint is seen to be directional pre-funding; a virtual output relocates that constraint to a server's volume-priced capital and a liveness obligation that agents, uniquely, meet for free; a proof-carrying registry closes the premise the reward theorem was missing; and an optimistic escrow makes the bond an object with its own transitions. Each relocation has a named cost and a named trust assumption, and none is measured here.

The warden model's contribution is an ordering. Whatever a covert coalition of agents can say to itself over Lightning, what it can earn is bounded by the capital it can prove and the demand it cannot manufacture, at the scale of the stationary-placement effect. That bound is the thing to test first. The steganographic capacity is real and is last.

\pagebreak

# Exhibit A. Notation

| Symbol | Meaning |
|---|---|
| ρ = (𝒜, v, F, X, Λ, Γ, τ) | Settlement object: authority, value, finality clock, exit, liveness, counterparty set, expiry |
| ℓ^{U}, ℓ^{C}, ℓ^{V}, ℓ^{E} | Holdings by class |
| σ | Settlement event (from-class, to-class, amount, clock condition) |
| O_A, I_A, K_A | Cumulative outward, inward, added stock across cut A, as in [R2] |
| R_S, W_S, B_S | Server liquidity stock, committed-and-unrecovered value, total capital |
| 𝒟_obj(D, H) | Liquidity duration: locked capital-time per unit delivered |
| 𝓡_cap, 𝓡_svc | Unique-exposure and service relations |
| nf, cm, root_n, k_ρ | Nullifier keyed by the object's authority key k_ρ, claimant commitment, settled-set root |
| E(B, κ, Δ) | Escrow with bond B for connector κ and challenge period Δ |
| O_chain, O_gossip, O_peer, O_server | Warden rows |

# Exhibit B. Reference implementation

A small executable model accompanies this draft under `model/`, in TypeScript with no dependencies, runnable with `node --experimental-strip-types --test "model/*.test.ts"`. It implements the extended ledger with per-class holdings and clocked settlement events (S1); a server liquidity ledger with the forfeit-to-sweep lock rule, VTXO lifetimes, holder refresh, and the aggregate constraint, together with the peak-balance channel model, and a direction test of the §3.3 ratio on the two constructed corners of §7.1 (S2); a registry with claim-once nullifiers keyed by the object's authority over a simulated settled set (S3); the escrow state machine with the published BitVM3 size parameters (S4); and, for S5, three warden statistics on a coalition fixture: the naive network churn ratio, direct-attester netting, and repeated-cycle share, with the first two's failure modes asserted as such rather than tuned away. The proof system is not implemented; the registry verifies a simulated attestation with the same interface a verifier would expose, and the tests say so. The implementation witnesses the propositions on finite cases in the sense of [R2, §9.2]; it proves nothing about distributed execution, its fixtures are constructed, and it contacts no network.

### B.0 Test run

```text
ok 1 - S4: a false assertion is slashed by one honest challenger at a cost independent of the bond
ok 2 - S4: a true assertion cannot be disproved and releases only after Δ; operator pays Assert and capital lockup
ok 3 - S4: the audit's negative-slash and over-release defects cannot arise; the bond is an object with fixed transitions
ok 4 - S5 statistics on fixtures: naive churn has no stable direction; direct-attester netting saturates on dense benign trade and misses a 4-relay; repeated-cycle share separates
ok 5 - S1: cross-class conservation holds at every settled state and with holds during pending intervals
ok 6 - S1/L3: a rejected initiation is the identity on ledger state
ok 7 - S3: weight attributed to any settled object is at most its value regardless of identity count
ok 8 - S3: a nullifier keyed to a claimant secret would permit splitting; keying to the authority does not
ok 9 - S3: overclaiming value, stale roots, and unsettled objects are rejected
ok 10 - L4 with S3: identity splitting leaves coalition payout invariant and integer pool conserved up to floor
ok 11 - S2: per-holder and aggregate bounds hold; a coalition cannot exceed server capital by coordinating
ok 12 - S2 witness: forfeit locks the fronted value for the residual lifetime; refresh renews the lock
ok 13 - §3.3 direction: Ark favored on many-bursty-long, channel favored on few-steady-recycling
# tests 13
# pass 13
```

### B.1 `model/ledger.ts`

```ts
// Extended settlement ledger: per-class holdings and clocked settlement events.
// Witnesses Proposition S1 of paper/where_the_capital_bound_moves.md on finite cases.
// Centralized reference semantics. Not a Lightning, Ark, or Bitcoin implementation.

export type ObjectClass = "U" | "C" | "V" | "E";

export type ClockCondition =
  | { kind: "confirmations"; required: number }
  | { kind: "htlc"; }                // settled when preimage revealed (explicit fire)
  | { kind: "csv"; blocks: number }  // relative timelock from initiation height
  | { kind: "round"; roundId: string }
  | { kind: "challenge"; delta: number; disproved?: boolean };

export interface SettlementEvent {
  id: string;
  from: { cls: ObjectClass; holder: string };
  to: { cls: ObjectClass; holder: string };
  amount: number;
  fee: number;            // paid to relay/miner, leaves the holder sum
  clock: ClockCondition;
  initiatedAt: number;    // block height
  state: "pending" | "settled" | "aborted";
}

export interface LedgerSnapshot {
  holdings: number;       // sum over classes and holders of settled holdings
  held: number;           // sum of pending holds (h)
  feesPaid: number;
  slashed: number;
  external: number;       // external funding in minus out
}

const key = (cls: ObjectClass, holder: string): string => `${cls}:${holder}`;

export class SettlementLedger {
  private readonly l = new Map<string, number>();
  private readonly h = new Map<string, number>();
  private readonly journal = new Map<string, SettlementEvent>();
  private readonly confirmedRounds = new Set<string>();
  private readonly settledHtlcs = new Set<string>();
  height = 0;
  feesPaid = 0;
  slashed = 0;
  external = 0;

  fund(cls: ObjectClass, holder: string, amount: number): void {
    if (!Number.isInteger(amount) || amount <= 0) throw new Error("amount must be a positive integer");
    const k = key(cls, holder);
    this.l.set(k, (this.l.get(k) ?? 0) + amount);
    this.external += amount;
  }

  balance(cls: ObjectClass, holder: string): number {
    return this.l.get(key(cls, holder)) ?? 0;
  }

  held(cls: ObjectClass, holder: string): number {
    return this.h.get(key(cls, holder)) ?? 0;
  }

  available(cls: ObjectClass, holder: string): number {
    return this.balance(cls, holder) - this.held(cls, holder);
  }

  /** Prepare a cross-class event: reserve amount+fee on the source, journal it, move nothing. */
  initiate(ev: Omit<SettlementEvent, "state" | "initiatedAt">): SettlementEvent {
    if (this.journal.has(ev.id)) throw new Error(`duplicate event id ${ev.id}`);
    if (!Number.isInteger(ev.amount) || ev.amount <= 0) throw new Error("amount must be a positive integer");
    if (!Number.isInteger(ev.fee) || ev.fee < 0) throw new Error("fee must be a nonnegative integer");
    const src = key(ev.from.cls, ev.from.holder);
    const need = ev.amount + ev.fee;
    if (this.available(ev.from.cls, ev.from.holder) < need) {
      throw new Error("insufficient available balance");
    }
    // All checks precede any mutation (L3 / S1 rejection identity).
    this.h.set(src, (this.h.get(src) ?? 0) + need);
    const rec: SettlementEvent = { ...ev, initiatedAt: this.height, state: "pending" };
    this.journal.set(ev.id, rec);
    return rec;
  }

  advance(blocks: number): void {
    this.height += blocks;
  }

  confirmRound(roundId: string): void {
    this.confirmedRounds.add(roundId);
  }

  settleHtlc(eventId: string): void {
    this.settledHtlcs.add(eventId);
  }

  /** Whether an event's clock condition has fired at the current height. */
  clockFired(ev: SettlementEvent): boolean {
    const c = ev.clock;
    switch (c.kind) {
      case "confirmations": return this.height - ev.initiatedAt >= c.required;
      case "csv": return this.height - ev.initiatedAt >= c.blocks;
      case "round": return this.confirmedRounds.has(c.roundId);
      case "htlc": return this.settledHtlcs.has(ev.id);
      case "challenge": return this.height - ev.initiatedAt >= c.delta;
    }
  }

  /** Settle: release the hold, debit the source, credit the destination, pay the fee. */
  settle(eventId: string): void {
    const ev = this.journal.get(eventId);
    if (!ev || ev.state !== "pending") throw new Error("not pending");
    if (!this.clockFired(ev)) throw new Error("clock has not fired");
    const src = key(ev.from.cls, ev.from.holder);
    const dst = key(ev.to.cls, ev.to.holder);
    const need = ev.amount + ev.fee;
    this.h.set(src, (this.h.get(src) ?? 0) - need);
    this.l.set(src, (this.l.get(src) ?? 0) - need);
    if (ev.clock.kind === "challenge" && ev.clock.disproved) {
      // An escrow release that was disproved settles as a slash: the amount leaves the holder sum.
      this.slashed += ev.amount;
    } else {
      this.l.set(dst, (this.l.get(dst) ?? 0) + ev.amount);
    }
    this.feesPaid += ev.fee;
    ev.state = "settled";
  }

  /** Abort: release the hold, move nothing. */
  abort(eventId: string): void {
    const ev = this.journal.get(eventId);
    if (!ev || ev.state !== "pending") throw new Error("not pending");
    const src = key(ev.from.cls, ev.from.holder);
    this.h.set(src, (this.h.get(src) ?? 0) - (ev.amount + ev.fee));
    ev.state = "aborted";
  }

  snapshot(): LedgerSnapshot {
    let holdings = 0;
    for (const v of this.l.values()) holdings += v;
    let held = 0;
    for (const v of this.h.values()) held += v;
    return { holdings, held, feesPaid: this.feesPaid, slashed: this.slashed, external: this.external };
  }

  pending(): SettlementEvent[] {
    return [...this.journal.values()].filter((e) => e.state === "pending");
  }
}

/** S1 identity at settled states: holdings + fees + slashed == external. */
export function conservationGap(s: LedgerSnapshot): number {
  return s.holdings + s.feesPaid + s.slashed - s.external;
}
```

### B.2 `model/ledger.test.ts`

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { SettlementLedger, conservationGap } from "./ledger.ts";

test("S1: cross-class conservation holds at every settled state and with holds during pending intervals", () => {
  const L = new SettlementLedger();
  L.fund("U", "alice", 1_000_000);
  L.fund("U", "server", 5_000_000);

  // U→C funding (k confirmations), U→V board (round), C→E escrow deposit (confirmations), V→C HTLC spend.
  L.initiate({ id: "fund", from: { cls: "U", holder: "alice" }, to: { cls: "C", holder: "alice" }, amount: 400_000, fee: 300, clock: { kind: "confirmations", required: 3 } });
  L.initiate({ id: "board", from: { cls: "U", holder: "alice" }, to: { cls: "V", holder: "alice" }, amount: 200_000, fee: 200, clock: { kind: "round", roundId: "r1" } });
  assert.equal(L.available("U", "alice"), 1_000_000 - 400_300 - 200_200);
  assert.equal(conservationGap(L.snapshot()), 0);

  L.advance(3);
  L.settle("fund");
  assert.equal(L.balance("C", "alice"), 400_000);
  assert.equal(conservationGap(L.snapshot()), 0);

  assert.throws(() => L.settle("board"), /clock/); // round not confirmed
  L.confirmRound("r1");
  L.settle("board");
  assert.equal(L.balance("V", "alice"), 200_000);

  L.initiate({ id: "htlc", from: { cls: "V", holder: "alice" }, to: { cls: "C", holder: "server" }, amount: 50_000, fee: 50, clock: { kind: "htlc" } });
  L.abort("htlc"); // timed out: hold released, nothing moved
  assert.equal(L.balance("V", "alice"), 200_000);
  assert.equal(L.held("V", "alice"), 0);

  L.initiate({ id: "dep", from: { cls: "C", holder: "alice" }, to: { cls: "E", holder: "alice" }, amount: 100_000, fee: 100, clock: { kind: "confirmations", required: 1 } });
  L.advance(1);
  L.settle("dep");
  // Escrow release disproved: slashed leaves the holder sum but stays in the identity.
  L.initiate({ id: "rel", from: { cls: "E", holder: "alice" }, to: { cls: "U", holder: "alice" }, amount: 100_000, fee: 0, clock: { kind: "challenge", delta: 10, disproved: true } });
  L.advance(10);
  L.settle("rel");
  const s = L.snapshot();
  assert.equal(s.slashed, 100_000);
  assert.equal(conservationGap(s), 0);
  assert.equal(L.pending().length, 0);
});

test("S1/L3: a rejected initiation is the identity on ledger state", () => {
  const L = new SettlementLedger();
  L.fund("C", "bob", 1_000);
  const before = JSON.stringify(L.snapshot());
  assert.throws(() => L.initiate({ id: "x", from: { cls: "C", holder: "bob" }, to: { cls: "V", holder: "bob" }, amount: 2_000, fee: 0, clock: { kind: "htlc" } }), /insufficient/);
  assert.equal(JSON.stringify(L.snapshot()), before);
  assert.equal(L.held("C", "bob"), 0);
});
```

### B.3 `model/server.ts`

```ts
// Server-mediated object (Ark-style VTXO) liquidity model and the directional channel comparison.
// Witnesses Proposition S2 and computes the liquidity-duration ratio of §3.3 on two demand corners.
//
// Lock rule (from the implementer's published description of the three liquidity operations and
// forfeit sweeping): whenever a VTXO is forfeited (spent over Lightning, refreshed, or offboarded), the
// server fronts equivalent value now and recovers it only when that output's absolute expiry passes.
// Boarding and receiving are treated as liquidity-neutral for the server in this aggregate model.
// Parameters default to published values (28 d ≈ 4032 blocks, hourly rounds ≈ 6 blocks) and are inputs.

export interface ServerParams {
  lifetimeBlocks: number;
  roundInterval: number;
  refreshLead: number;
}

export const DEFAULT_SERVER: ServerParams = { lifetimeBlocks: 4032, roundInterval: 6, refreshLead: 288 };

interface Vtxo {
  id: string;
  holder: string;
  value: number;
  expiresAt: number;
  forfeited: boolean;
}

export class ArkServer {
  readonly params: ServerParams;
  readonly capital: number;    // B_S
  committed = 0;               // W_S: forfeited-but-unswept value the server has fronted
  height = 0;
  volumeDelivered = 0;
  private lockedIntegral = 0;  // ∫ W_S dt (value·blocks)
  private lastHeight = 0;
  private nextId = 0;
  private readonly vtxos = new Map<string, Vtxo>();
  readonly outward = new Map<string, number>();
  readonly inward = new Map<string, number>();
  readonly allocated = new Map<string, number>();

  constructor(capital: number, params: ServerParams = DEFAULT_SERVER) {
    this.capital = capital;
    this.params = params;
  }

  get uncommitted(): number {
    return this.capital - this.committed;
  }

  private static bump(m: Map<string, number>, k: string, v: number): void {
    m.set(k, (m.get(k) ?? 0) + v);
  }

  private accrue(): void {
    this.lockedIntegral += this.committed * (this.height - this.lastHeight);
    this.lastHeight = this.height;
  }

  advance(blocks: number): void {
    // W_S is piecewise constant between events; integrate over the interval before applying sweeps.
    this.lockedIntegral += this.committed * blocks;
    this.height += blocks;
    this.lastHeight = this.height;
    for (const [id, v] of this.vtxos) {
      if (v.forfeited && this.height >= v.expiresAt) {
        this.committed -= v.value; // sweep: fronted value recovered
        this.vtxos.delete(id);
      }
    }
    // Holders refresh outputs approaching expiry; a refresh is a forfeit plus a server-funded reissue.
    for (const v of [...this.vtxos.values()]) {
      if (!v.forfeited && v.expiresAt - this.height <= this.params.refreshLead) this.refresh(v.id);
    }
  }

  private newVtxo(holder: string, value: number): Vtxo {
    const v: Vtxo = { id: `v${this.nextId++}`, holder, value, expiresAt: this.height + this.params.lifetimeBlocks, forfeited: false };
    this.vtxos.set(v.id, v);
    return v;
  }

  /** Forfeit an output: the server fronts its value now and sweeps it at the output's expiry. */
  private forfeit(v: Vtxo): boolean {
    if (v.value > this.uncommitted) return false;
    v.forfeited = true;
    this.committed += v.value;
    return true;
  }

  /** Board or receive: a holder gains an output without drawing on server liquidity in this aggregate model. */
  receive(holder: string, value: number): string {
    const v = this.newVtxo(holder, value);
    ArkServer.bump(this.inward, holder, value);
    ArkServer.bump(this.allocated, holder, value);
    return v.id;
  }

  refresh(id: string): boolean {
    const old = this.vtxos.get(id);
    if (!old || old.forfeited) return false;
    if (!this.forfeit(old)) return false;
    this.newVtxo(old.holder, old.value);
    return true;
  }

  holderValue(holder: string): number {
    let s = 0;
    for (const v of this.vtxos.values()) if (v.holder === holder && !v.forfeited) s += v.value;
    return s;
  }

  /** Spend outward over Lightning. The server fronts the HTLC from uncommitted capital (S2 aggregate constraint). */
  spendLightning(holder: string, amount: number): boolean {
    if (!Number.isInteger(amount) || amount <= 0) throw new Error("amount must be a positive integer");
    if (this.holderValue(holder) < amount) return false;
    const inputs: Vtxo[] = [];
    let total = 0;
    for (const v of this.vtxos.values()) {
      if (total >= amount) break;
      if (v.holder === holder && !v.forfeited) { inputs.push(v); total += v.value; }
    }
    if (total > this.uncommitted) return false; // all-or-nothing check before any mutation
    for (const v of inputs) this.forfeit(v);
    const change = total - amount;
    if (change > 0) this.newVtxo(holder, change); // reissued from the fronted value
    ArkServer.bump(this.outward, holder, amount);
    ArkServer.bump(this.allocated, holder, amount); // K^S_A: the server allocated at spend time
    this.volumeDelivered += amount;
    return true;
  }

  /** 𝒟_V = ∫ W_S dt / volume delivered, in blocks. */
  liquidityDuration(): number {
    this.accrue();
    return this.volumeDelivered === 0 ? Infinity : this.lockedIntegral / this.volumeDelivered;
  }

  /** S2, first inequality, per holder: O − I ≤ V(0) + K with V(0)=0. */
  holderBoundHolds(holder: string): boolean {
    return (this.outward.get(holder) ?? 0) - (this.inward.get(holder) ?? 0) <= (this.allocated.get(holder) ?? 0);
  }

  /** S2, second inequality: what the server has allocated in fronting never exceeds capital. */
  aggregateBoundHolds(): boolean {
    return this.committed <= this.capital;
  }
}

/**
 * Directional channel model for the same demand. An operator (LSP) pre-funds inbound capacity toward
 * each agent to a forecast f̂_a = (1 + margin) × the agent's realized peak held balance (running maximum
 * of receipts minus spends), holds that capital for the whole horizon, and the replay fails a receipt
 * that would exceed remaining inbound capacity or a spend that exceeds the agent's balance. Returns
 * 𝒟_C in blocks, the failure count, and the locked capital.
 */
export function channelLiquidityDuration(
  perAgent: Map<string, Array<{ out: number; in: number }>>,
  horizonBlocks: number,
  margin: number,
): { duration: number; failures: number; locked: number } {
  let locked = 0;
  let volume = 0;
  let failures = 0;
  for (const steps of perAgent.values()) {
    let running = 0;
    let peak = 0;
    for (const s of steps) { running = Math.max(0, running + s.in - s.out); peak = Math.max(peak, running); }
    const forecast = Math.ceil(peak * (1 + margin));
    locked += forecast;
    let balance = 0;
    for (const s of steps) {
      if (s.in) { if (s.in > forecast - balance) failures += 1; else { balance += s.in; volume += s.in; } }
      if (s.out) { if (s.out > balance) failures += 1; else { balance -= s.out; volume += s.out; } }
    }
  }
  return { duration: volume === 0 ? Infinity : (locked * horizonBlocks) / volume, failures, locked };
}

/** Deterministic LCG. */
export function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; };
}
```

### B.4 `model/server.test.ts`

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { ArkServer, DEFAULT_SERVER, channelLiquidityDuration, rng } from "./server.ts";

test("S2: per-holder and aggregate bounds hold; a coalition cannot exceed server capital by coordinating", () => {
  const S = new ArkServer(1_300_000, { ...DEFAULT_SERVER, refreshLead: Number.NEGATIVE_INFINITY }); // holders never refresh: isolate the sweep clock
  const holders = ["a", "b", "c", "d"];
  for (const h of holders) S.receive(h, 400_000);
  // Each holder can spend at most what it holds, and the server can front at most its uncommitted capital.
  let fronted = 0;
  const results = holders.map((h) => { const ok = S.spendLightning(h, 300_000); if (ok) fronted += 300_000; return ok; });
  assert.deepEqual(results, [true, true, true, false]); // fourth spend exceeds B_S − W_S
  assert.equal(S.committed, 3 * 400_000); // full inputs forfeited (300k spent + 100k change reissued from the front)
  assert.ok(S.aggregateBoundHolds());
  for (const h of holders) assert.ok(S.holderBoundHolds(h));
  // Liquidity returns only at expiry: nothing is recoverable before the lifetime passes.
  S.advance(DEFAULT_SERVER.lifetimeBlocks - 1);
  assert.equal(S.committed, 3 * 400_000);
  S.advance(1);
  assert.equal(S.committed, 0);
  assert.ok(S.spendLightning("d", 300_000));
});

test("S2 witness: forfeit locks the fronted value for the residual lifetime; refresh renews the lock", () => {
  const S = new ArkServer(10_000, { lifetimeBlocks: 100, roundInterval: 1, refreshLead: 10 });
  S.receive("h", 1_000);
  S.advance(50);
  assert.ok(S.spendLightning("h", 1_000));
  assert.equal(S.committed, 1_000);
  S.advance(49);
  assert.equal(S.committed, 1_000);
  S.advance(1);
  assert.equal(S.committed, 0);
  // liquidity duration = 1000 × 50 blocks / 1000 delivered = 50 blocks (residual lifetime at forfeit)
  assert.equal(S.liquidityDuration(), 50);
});

/**
 * §3.3 corner test. Same demand fed to both objects. This is a qualitative witness of the ratio's
 * direction on two constructed corners, not a reproduction of any published figure.
 */
function corner(kind: "many-bursty" | "few-steady", seed: number) {
  const r = rng(seed);
  const lifetime = 4032;
  const horizon = 8 * lifetime;         // long against the VTXO lifetime
  const roundBlocks = 6;
  const steps = horizon / roundBlocks;
  const agents = kind === "many-bursty" ? 200 : 3;
  const perAgent = new Map<string, Array<{ out: number; in: number }>>();
  for (let a = 0; a < agents; a++) perAgent.set(`a${a}`, []);
  const S = new ArkServer(Number.MAX_SAFE_INTEGER / 4, { lifetimeBlocks: lifetime, roundInterval: roundBlocks, refreshLead: 288 });
  for (let t = 0; t < steps; t++) {
    for (const [name, arr] of perAgent) {
      let out = 0, inn = 0;
      if (kind === "many-bursty") {
        // Rare, large, idiosyncratic outflows funded by earlier inflows; per-agent envelope ≫ per-agent volume per step.
        if (r() < 0.02) inn = 5_000;
        if (r() < 0.01) out = 4_000;
      } else {
        // Steady bidirectional flow with fixed counterparties, recycling within the day.
        out = 100 + Math.floor(r() * 10); inn = 100 + Math.floor(r() * 10);
      }
      arr.push({ out, in: inn });
      if (inn) S.receive(name, inn);
      if (out && S.holderValue(name) >= out) S.spendLightning(name, out);
    }
    S.advance(roundBlocks);
  }
  const ch = channelLiquidityDuration(perAgent, horizon, 0.25);
  return { dV: S.liquidityDuration(), dC: ch.duration, failures: ch.failures };
}

test("§3.3 direction: Ark favored on many-bursty-long, channel favored on few-steady-recycling", () => {
  const mb = corner("many-bursty", 1);
  const fs = corner("few-steady", 2);
  assert.ok(Number.isFinite(mb.dV) && Number.isFinite(mb.dC) && Number.isFinite(fs.dV) && Number.isFinite(fs.dC));
  assert.ok(mb.dC / mb.dV > 1, `expected ratio > 1 on many-bursty, got ${mb.dC / mb.dV}`);
  assert.ok(fs.dC / fs.dV < 1, `expected ratio < 1 on few-steady, got ${fs.dC / fs.dV}`);
});
```

### B.5 `model/registry.ts`

```ts
// Proof-carrying registry with claim-once nullifiers keyed by the object's authority key.
// Witnesses Proposition S3 on finite cases. The proof system is NOT implemented: `verify` checks a
// simulated attestation with the interface a verifier would expose (statement + witness → boolean),
// and the tests say so. Substituting a real SNARK changes nothing in the registry logic.

import { createHmac, createHash } from "node:crypto";

export interface SettledObject { id: string; value: number; authorityKey: string; }

export interface Statement { cm: string; v: number; nf: string; root: string; }

export interface Witness { s: string; k: string; obj: SettledObject; }

export const commit = (s: string): string => createHash("sha256").update(`cm|${s}`).digest("hex");
export const prf = (k: string, id: string): string => createHmac("sha256", k).update(id).digest("hex");

export class SettledSet {
  private readonly objs = new Map<string, SettledObject>();
  add(o: SettledObject): void { this.objs.set(o.id, o); }
  has(id: string): boolean { return this.objs.has(id); }
  get(id: string): SettledObject | undefined { return this.objs.get(id); }
  /** Deterministic commitment to the set contents; stands in for a Merkle root. */
  root(): string {
    const h = createHash("sha256");
    for (const id of [...this.objs.keys()].sort()) {
      const o = this.objs.get(id)!;
      h.update(`${id}|${o.value}|${o.authorityKey}\n`);
    }
    return h.digest("hex");
  }
}

/** Simulated verifier for R_cap: membership, authority, value bound, nullifier derivation. */
export function verifyCapClaim(set: SettledSet, st: Statement, w: Witness): boolean {
  if (st.root !== set.root()) return false;
  if (!set.has(w.obj.id)) return false;
  const live = set.get(w.obj.id)!;
  if (live.value !== w.obj.value || live.authorityKey !== w.obj.authorityKey) return false;
  if (w.k !== live.authorityKey) return false;          // k_ρ satisfies A_ρ (single-signer model)
  if (live.value < st.v) return false;
  if (commit(w.s) !== st.cm) return false;
  return prf(w.k, live.id) === st.nf;                     // nf keyed by the object's authority, not the claimant
}

export class Registry {
  private readonly nullifiers = new Set<string>();
  readonly claims: Statement[] = [];

  submit(set: SettledSet, st: Statement, w: Witness): "accepted" | "invalid" | "duplicate" {
    if (!verifyCapClaim(set, st, w)) return "invalid";
    if (this.nullifiers.has(st.nf)) return "duplicate";
    this.nullifiers.add(st.nf);
    this.claims.push({ ...st });
    return "accepted";
  }

  /** Total weight the registry attributes to a given nullifier (i.e. to the object behind it). */
  weightFor(nf: string): number {
    return this.claims.filter((c) => c.nf === nf).reduce((a, c) => a + c.v, 0);
  }

  totalWeight(): number {
    return this.claims.reduce((a, c) => a + c.v, 0);
  }

  /** Fixed-pool reward allocation, integer, remainder to no one (L4 without the rounding defect). */
  allocate(pool: number): Map<string, number> {
    const total = this.totalWeight();
    const out = new Map<string, number>();
    for (const c of this.claims) out.set(c.cm, (out.get(c.cm) ?? 0) + Math.floor((pool * c.v) / total));
    return out;
  }
}
```

### B.6 `model/registry.test.ts`

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { Registry, SettledSet, commit, prf, type Statement, type Witness } from "./registry.ts";

// NOTE: the proof system is simulated (see registry.ts). These tests witness the registry logic
// under the assumption that a real knowledge-sound proof would accept exactly what verifyCapClaim accepts.

function claim(set: SettledSet, objId: string, identity: string, v: number, k?: string): [Statement, Witness] {
  const obj = set.get(objId)!;
  const key = k ?? obj.authorityKey;
  const st: Statement = { cm: commit(identity), v, nf: prf(key, obj.id), root: set.root() };
  return [st, { s: identity, k: key, obj: { ...obj } }];
}

test("S3: weight attributed to any settled object is at most its value regardless of identity count", () => {
  const set = new SettledSet();
  set.add({ id: "utxo:1", value: 50_000, authorityKey: "k1" });
  set.add({ id: "vtxo:7", value: 20_000, authorityKey: "k7" });
  const R = new Registry();
  // One controller, 32 identities, one object: only the first claim lands.
  const outcomes = Array.from({ length: 32 }, (_, i) => R.submit(set, ...claim(set, "utxo:1", `id-${i}`, 50_000)));
  assert.equal(outcomes[0], "accepted");
  assert.ok(outcomes.slice(1).every((o) => o === "duplicate"));
  assert.equal(R.weightFor(prf("k1", "utxo:1")), 50_000);
  // A second, distinct object is independent.
  assert.equal(R.submit(set, ...claim(set, "vtxo:7", "id-99", 20_000)), "accepted");
  assert.equal(R.totalWeight(), 70_000);
});

test("S3: a nullifier keyed to a claimant secret would permit splitting; keying to the authority does not", () => {
  const set = new SettledSet();
  set.add({ id: "utxo:2", value: 10_000, authorityKey: "k2" });
  const R = new Registry();
  const [st1, w1] = claim(set, "utxo:2", "alpha", 10_000);
  const [st2, w2] = claim(set, "utxo:2", "beta", 10_000);
  assert.equal(st1.nf, st2.nf); // same object ⇒ same nullifier, whoever claims
  assert.equal(R.submit(set, st1, w1), "accepted");
  assert.equal(R.submit(set, st2, w2), "duplicate");
  // Forging a different nullifier requires a key that does not satisfy the authority: rejected as invalid.
  const [st3, w3] = claim(set, "utxo:2", "gamma", 10_000, "not-k2");
  assert.equal(R.submit(set, st3, w3), "invalid");
});

test("S3: overclaiming value, stale roots, and unsettled objects are rejected", () => {
  const set = new SettledSet();
  set.add({ id: "chan:3", value: 1_000, authorityKey: "k3" });
  const R = new Registry();
  const [over, wo] = claim(set, "chan:3", "x", 1_001);
  assert.equal(R.submit(set, over, wo), "invalid");
  const [st, w] = claim(set, "chan:3", "x", 1_000);
  set.add({ id: "chan:4", value: 5, authorityKey: "k4" }); // root moves
  assert.equal(R.submit(set, st, w), "invalid");
  const fresh = new SettledSet();
  const ghost: Witness = { s: "y", k: "k9", obj: { id: "ghost", value: 10, authorityKey: "k9" } };
  assert.equal(R.submit(fresh, { cm: commit("y"), v: 10, nf: prf("k9", "ghost"), root: fresh.root() }, ghost), "invalid");
});

test("L4 with S3: identity splitting leaves coalition payout invariant and integer pool conserved up to floor", () => {
  const set = new SettledSet();
  set.add({ id: "u:a", value: 100, authorityKey: "ka" });
  set.add({ id: "u:b", value: 100, authorityKey: "kb" });
  for (const m of [1, 2, 8, 32]) {
    const R = new Registry();
    for (let i = 0; i < m; i++) R.submit(set, ...claim(set, "u:a", `a-${i}`, 100)); // one accepted, m−1 duplicates
    R.submit(set, ...claim(set, "u:b", "b", 100));
    const alloc = R.allocate(120);
    const coalitionA = [...alloc.entries()].filter(([cm]) => cm !== commit("b")).reduce((s, [, v]) => s + v, 0);
    assert.equal(coalitionA, 60);
    assert.equal(alloc.get(commit("b")), 60);
  }
});
```

### B.7 `model/escrow.ts`

```ts
// Optimistic escrow state machine in the BitVM3 Assert/Disprove/Withdraw pattern.
// Witnesses Proposition S4 on finite cases. Cost parameters are those published in ePrint 2026/933
// (Assert ≈ 2.4 kvB, Disprove ≈ 93 vB) and are inputs, not measurements. The "proof" is a boolean
// oracle standing in for garbled-circuit evaluation of a SNARK verifier; substituting the real
// evaluation changes nothing in the state machine.

export interface EscrowParams {
  delta: number;        // challenge period in blocks
  assertVb: number;     // Assert transaction size, vB
  disproveVb: number;   // Disprove transaction size, vB
  feeRate: number;      // sat/vB
}

export const BITVM3_PUBLISHED: Omit<EscrowParams, "delta" | "feeRate"> = { assertVb: 2400, disproveVb: 93 };

export type EscrowState = "locked" | "claimed" | "released" | "slashed";

export interface Costs { operatorFees: number; challengerFees: number; capitalBlocks: number; }

export class Escrow {
  readonly bond: number;
  readonly params: EscrowParams;
  state: EscrowState = "locked";
  private claimedAt = -1;
  private asserted: boolean | null = null;
  readonly costs: Costs = { operatorFees: 0, challengerFees: 0, capitalBlocks: 0 };
  private lockedSince = 0;

  constructor(bond: number, params: EscrowParams, lockedAt = 0) {
    if (!Number.isInteger(bond) || bond <= 0) throw new Error("bond must be a positive integer");
    this.bond = bond;
    this.params = params;
    this.lockedSince = lockedAt;
  }

  /** Operator asserts the release statement. `statementHolds` is what an honest evaluator would find. */
  assert(height: number, statementHolds: boolean): void {
    if (this.state !== "locked") throw new Error("not locked");
    this.state = "claimed";
    this.claimedAt = height;
    this.asserted = statementHolds;
    this.costs.operatorFees += this.params.assertVb * this.params.feeRate;
  }

  /** Any challenger may disprove during the period; succeeds iff the asserted statement is false. */
  disprove(height: number): boolean {
    if (this.state !== "claimed") return false;
    if (height - this.claimedAt >= this.params.delta) return false; // period over
    this.costs.challengerFees += this.params.disproveVb * this.params.feeRate;
    if (this.asserted === false) {
      this.state = "slashed";
      this.costs.capitalBlocks += this.bond * (height - this.lockedSince);
      return true;
    }
    return false; // a true assertion has no false-output label to reveal
  }

  /** Operator withdraws after the period if no disprove consumed the connector output. */
  withdraw(height: number): boolean {
    if (this.state !== "claimed") return false;
    if (height - this.claimedAt < this.params.delta) return false;
    this.state = "released";
    this.costs.capitalBlocks += this.bond * (height - this.lockedSince);
    return true;
  }
}

/** Honest-challenger requirement: with n challengers of which h are honest, the game is safe iff h ≥ 1. */
export const safeUnderChallengers = (honest: number): boolean => honest >= 1;
```

### B.8 `model/warden.ts`

```ts
// Warden statistics of §6.3–6.4 on synthetic fixtures.
// The naive network-wide gross-to-net ratio is computed alongside the internal-volume ratio over a
// claim's attesting set, so that the failure mode the earlier hive baseline reported (naive churn does
// not discriminate) is reproduced rather than assumed away. These are fixtures, not measurements.

import { rng } from "./server.ts";

export interface Flow { payer: string; payee: string; amount: number; }

/** Naive statistic: gross volume over the sum of absolute net positions. Undefined (Infinity) when everything nets. */
export function naiveGrossToNet(trace: Flow[]): number {
  const net = new Map<string, number>();
  let gross = 0;
  for (const f of trace) {
    gross += f.amount;
    net.set(f.payer, (net.get(f.payer) ?? 0) - f.amount);
    net.set(f.payee, (net.get(f.payee) ?? 0) + f.amount);
  }
  let sumAbs = 0;
  for (const v of net.values()) sumAbs += Math.abs(v);
  return sumAbs === 0 ? Infinity : gross / sumAbs;
}

/**
 * Restricted statistic over the claim's set S = attesters ∪ {claimant}: the share of all volume touching S
 * whose both endpoints lie inside S. Manufactured demand circulates inside S; a merchant's customers mostly
 * transact outside it. Computable by any warden that sees the flows touching S.
 */
export function internalVolumeRatio(trace: Flow[], claimant: string, attesters: Set<string>): number {
  const inside = new Set(attesters); inside.add(claimant);
  let touching = 0;
  let internal = 0;
  for (const f of trace) {
    const a = inside.has(f.payer);
    const b = inside.has(f.payee);
    if (!a && !b) continue;
    touching += f.amount;
    if (a && b) internal += f.amount;
  }
  return touching === 0 ? 0 : internal / touching;
}

/** Counterparties who paid the claimant in the trace: the attesting set a service claim would carry. */
export function attestersOf(trace: Flow[], claimant: string): Set<string> {
  const s = new Set<string>();
  for (const f of trace) if (f.payee === claimant) s.add(f.payer);
  return s;
}

/** Benign multilateral trade: every agent pays random others; nets out strongly by construction. */
export function benignTrace(agents: string[], steps: number, seed = 7): Flow[] {
  const r = rng(seed);
  const out: Flow[] = [];
  for (let i = 0; i < steps; i++) {
    const a = agents[Math.floor(r() * agents.length)]!;
    let b = agents[Math.floor(r() * agents.length)]!;
    while (b === a) b = agents[Math.floor(r() * agents.length)]!;
    out.push({ payer: a, payee: b, amount: 100 });
  }
  return out;
}

/** Coalition fixture: a cyclic relay of k members, embedded in benign background traffic. */
export function coalitionTrace(agents: string[], coalition: string[], steps: number, seed = 11): Flow[] {
  const bg = benignTrace(agents.filter((a) => !coalition.includes(a)), steps, seed);
  const cyc: Flow[] = [];
  for (let i = 0; i < steps; i++) {
    const a = coalition[i % coalition.length]!;
    const b = coalition[(i + 1) % coalition.length]!;
    cyc.push({ payer: a, payee: b, amount: 100 });
  }
  return [...bg, ...cyc];
}

/** Partial observer: keeps each flow with probability p (O_peer-style coverage). */
export function sample(trace: Flow[], p: number, seed = 3): Flow[] {
  const r = rng(seed);
  return trace.filter(() => r() < p);
}

/**
 * Repeated-cycle share: the fraction of the claimant's flows lying on a directed cycle through the
 * claimant of length ≤ maxLen whose every edge recurs at least minMultiplicity times. This is the
 * feature family the earlier hive detector used; it sees a relay of any bounded length, where the
 * direct-attester statistic sees only reciprocal pairs.
 */
export function repeatedCycleShare(trace: Flow[], claimant: string, maxLen = 4, minMultiplicity = 10): number {
  const m = new Map<string, number>();
  const succ = new Map<string, Set<string>>();
  const ek = (u: string, v: string) => `${u}>${v}`;
  for (const f of trace) {
    m.set(ek(f.payer, f.payee), (m.get(ek(f.payer, f.payee)) ?? 0) + 1);
    if (!succ.has(f.payer)) succ.set(f.payer, new Set());
    succ.get(f.payer)!.add(f.payee);
  }
  const heavy = (u: string, v: string) => (m.get(ek(u, v)) ?? 0) >= minMultiplicity;
  // Edges (u→v) that lie on some heavy cycle through the claimant of length ≤ maxLen.
  const onCycle = new Set<string>();
  const walk = (path: string[]) => {
    const last = path[path.length - 1]!;
    for (const nxt of succ.get(last) ?? []) {
      if (!heavy(last, nxt)) continue;
      if (nxt === claimant) {
        if (path.length >= 2) for (let i = 0; i < path.length; i++) onCycle.add(ek(path[i]!, path[i + 1] ?? claimant));
        continue;
      }
      if (path.length < maxLen && !path.includes(nxt)) walk([...path, nxt]);
    }
  };
  walk([claimant]);
  let total = 0;
  let hit = 0;
  for (const f of trace) {
    if (f.payer !== claimant && f.payee !== claimant) continue;
    total += f.amount;
    if (onCycle.has(ek(f.payer, f.payee))) hit += f.amount;
  }
  return total === 0 ? 0 : hit / total;
}
```

### B.9 `model/escrow_warden.test.ts`

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { Escrow, BITVM3_PUBLISHED, safeUnderChallengers, type EscrowParams } from "./escrow.ts";
import { naiveGrossToNet, internalVolumeRatio, attestersOf, benignTrace, coalitionTrace, sample, repeatedCycleShare } from "./warden.ts";

const P: EscrowParams = { ...BITVM3_PUBLISHED, delta: 144, feeRate: 2 };

test("S4: a false assertion is slashed by one honest challenger at a cost independent of the bond", () => {
  const small = new Escrow(10_000, P);
  const large = new Escrow(10_000_000_000, P);
  for (const e of [small, large]) {
    e.assert(100, false);
    assert.ok(e.disprove(120));
    assert.equal(e.state, "slashed");
    assert.equal(e.costs.challengerFees, BITVM3_PUBLISHED.disproveVb * P.feeRate);
  }
  assert.equal(small.costs.challengerFees, large.costs.challengerFees);
  assert.ok(safeUnderChallengers(1) && !safeUnderChallengers(0));
});

test("S4: a true assertion cannot be disproved and releases only after Δ; operator pays Assert and capital lockup", () => {
  const e = new Escrow(500_000, P, 0);
  e.assert(10, true);
  assert.equal(e.disprove(50), false);
  assert.equal(e.state, "claimed");
  assert.equal(e.withdraw(10 + P.delta - 1), false);
  assert.ok(e.withdraw(10 + P.delta));
  assert.equal(e.state, "released");
  assert.equal(e.costs.operatorFees, BITVM3_PUBLISHED.assertVb * P.feeRate);
  assert.equal(e.costs.capitalBlocks, 500_000 * (10 + P.delta));
});

test("S4: the audit's negative-slash and over-release defects cannot arise; the bond is an object with fixed transitions", () => {
  const e = new Escrow(25_000, P);
  assert.throws(() => new Escrow(-1_249, P));
  e.assert(0, true);
  assert.throws(() => e.assert(1, true)); // no double claim
  assert.ok(e.withdraw(P.delta));
  assert.equal(e.withdraw(P.delta + 1), false); // no second release
  assert.equal(e.disprove(P.delta + 1), false); // nothing left to disprove
});

test("S5 statistics on fixtures: naive churn has no stable direction; direct-attester netting saturates on dense benign trade and misses a 4-relay; repeated-cycle share separates", () => {
  const agents = Array.from({ length: 40 }, (_, i) => `n${i}`);
  const benign = benignTrace(agents, 4_000);
  const relay4 = coalitionTrace(agents, ["n0", "n1", "n2", "n3"], 4_000);
  const relay2 = coalitionTrace(agents, ["n0", "n1"], 4_000);
  const claimant = "n0";

  // Naive statistic: large in every world. (Here the relays score higher; in the hive baseline benign scored higher.
  // Either way the direction is fixture-dependent, which is the point.)
  for (const t of [benign, relay4, relay2]) assert.ok(naiveGrossToNet(t) > 5);

  // Direct-attester netting: catches the reciprocal pair; misses the four-member relay (as the hive baseline did);
  // and on dense benign trade the attesting set is almost everyone, so the ratio saturates instead of staying low.
  const ivr = (t: typeof benign) => internalVolumeRatio(t, claimant, attestersOf(t, claimant));
  assert.ok(ivr(relay2) >= 0.99, `2-relay ${ivr(relay2)}`);
  assert.ok(ivr(relay4) < 0.5, `4-relay ${ivr(relay4)}`);
  assert.ok(ivr(benign) > 0.5, `benign saturation ${ivr(benign)}`); // documented failure mode, not a pass condition

  // Repeated-cycle share through the claimant separates both relays from benign at this density.
  assert.ok(repeatedCycleShare(relay4, claimant) >= 0.99);
  assert.ok(repeatedCycleShare(relay2, claimant) >= 0.99);
  assert.ok(repeatedCycleShare(benign, claimant) < 0.2);

  // Partial observation (~12% coverage, O_peer-style) preserves the cycle-share separation on these fixtures
  // because the relays are high-volume; the multiplicity threshold must scale with coverage × volume in general.
  const thin = (t: typeof benign) => sample(t, 0.12);
  assert.ok(repeatedCycleShare(thin(relay4), claimant) >= 0.99);
  assert.ok(repeatedCycleShare(thin(benign), claimant) < 0.2);
});
```

\pagebreak

# Exhibit C. Errata to the frozen manuscript

Reproduced from paper/manuscript_errata.md; the manuscript itself is left byte-identical for the reasons stated there.

**Applies to:** paper/manuscript.md at baseline a0a3140 (author line corrected per audit/ATTRIBUTION_CORRECTION.md)

**Why a separate file:** audit/validate_bundle.py and audit/inference/receipt.json bind manuscript.md by hash and reject any edit beyond the single author-line correction. The corrections below are therefore recorded here rather than applied in place. A future preregistered campaign that re-freezes the baseline should apply them at that point and re-bind.

## E1. Patent citation (References)

Replace:

> Rubio, Lihki, Dugan, and Pizarro. 2020. *Graph Re-write Using Ghost Nodes for Target Value Rebalancing*. U.S. Patent Application 16/920,416.

with:

> Dugan, Patrick B., Daniel P. Pizarro, and Lihki J. Rubio. *Graph Re-write Using Ghost Nodes for Target Value Rebalancing*. U.S. Patent Application Publication US 2021/0004796 A1, published January 7, 2021; application 16/920,416, filed July 2, 2020; claims priority to provisional 62/869,730, filed July 2, 2019.

Inventor order, publication number, publication date, and provisional data are from the USPTO Patent Public Search record. The 2020 date in the frozen entry is the filing year; the publication year is 2021.

## E2. In-text attribution (§1, §2.4, §7.7 and elsewhere)

Every occurrence of "[Rubio, Dugan, and Pizarro 2020]" should read "[Dugan, Pizarro, and Rubio 2021]".

## E3. Lineage statement (§2.4, first paragraph)

The frozen text reads:

> The earlier ghost-node work proposes graph rewrites for target-value rebalancing [Rubio, Dugan, and Pizarro 2020]. The recovered project did not retain the application text, so this paper does not reproduce or extend its claims. It adopts only the high-level construction: augment a graph with a nonphysical node or edge, solve a balancing problem in that augmented space, then map the result back to permissible operations.

Two corrections. The published application text is public, so the "did not retain" hedge no longer justifies the scope restriction; the restriction stands on its own terms and should be stated as a choice. And the application's subject is decentralized derivatives clearing, where ghost nodes connect and net subgraphs toward a target settlement value; it is not a rebalancing method for payment channels. Suggested replacement, keeping the paragraph's structure:

> The earlier ghost-node work, filed in a clearing setting, uses graph rewrites to connect and net derivative subgraphs toward a target settlement value [Dugan, Pizarro, and Rubio 2021]. This paper adopts only the high-level construction, augmenting a graph with a nonphysical node or edge, solving a balancing problem in that augmented space, and mapping the result back to permissible operations; the transplant from settlement netting to directional channel liquidity is made here and is not a claim of the application.

## E4. Environment paths

The frozen manuscript contains no drive-letter paths. The companion documents (liquidity_on_trial.md, connector_calculus_critique.md) have been corrected in place; audit/README.md and the historical receipts retain their original staging paths as provenance and are not edited.

\pagebreak

# References

[R1] Dugan. *Connector Calculus: Ghost-Node Rewrites, Bonded Liquidity, and Adversarial Agent Routing on the Lightning Network*. Spiral reconstructed draft, August 2026; baseline a0a3140; corrections in paper/manuscript_errata.md. Hive supplement: paper/hive_lab.md.

[R2] Dugan. *Liquidity on Trial: Counterexamples and a Resource-Sensitive Semantics for Agent Payment Networks*. Spiral adversarial follow-up, September 11, 2026.

[R3] Second. *Ark VTXOs*. Second documentation, accessed September 30, 2026. https://second.tech/docs/learn/vtxo. States the two spending paths, the 144-block CSV exit, the 28-day server-configurable lifetime, hourly default refresh rounds, and the state-chain trust model for out-of-round spends.

[R4] Second. *Forfeits & connectors*. Second documentation, accessed September 30, 2026. https://second.tech/docs/learn/forfeits. States that forfeits cover refreshes and on-chain payments, that hash-locks replace connectors for rounds from 0.1.0-beta.6, and that Lightning payments use HTLC-based policies rather than forfeits.

[R5] Second. *Lightning liquidity: Ark servers and LSPs compared*. Second blog, May 1, 2025. https://second.tech/blog/ark-liquidity-research-01. Simulation results on liquidity requirements by top-up frequency; the three server liquidity operations; allocation at spend time.

[R6] Bitcoin Optech. *Ark protocol* topic page, accessed September 30, 2026. https://bitcoinops.org/en/topics/ark/. Round construction, expiry, unilateral exit, the sender–operator collusion caveat, and the 2026 timeline (hArk, Bark 0.5.0, Bark mainnet).

[R7] Linus, Robin, Ioannis Alexopoulos, Lukas Aumayr, Zeta Avarikioti, Matteo Maffei, and David Tse. *BitVM3: Efficient Bitcoin Bridges via Garbled Circuits*. IACR ePrint 2026/933, May 11, 2026, revised June 8, 2026. https://eprint.iacr.org/2026/933. Assert/Disprove/Withdraw flow, ~2.4 kvB Assert, ~93 vB Disprove, ~41 GB garbled Groth16 verifier, honest-committee-at-setup and one-honest-challenger assumptions, Theorems 7.1, 7.2, 7.8.

[R8] Bitcoin Optech. *OP_CHECKTEMPLATEVERIFY* topic page, accessed September 30, 2026. https://bitcoinops.org/en/topics/op_checktemplateverify/. 2025–2026 timeline entries; no mainnet activation recorded.

[R9] BlockEden. *Bitcoin's Covenant Renaissance*. April 21, 2026. https://blockeden.xyz/blog/2026/04/21/bitcoin-covenant-renaissance-op-ctv-lnhance-cat-bitvm2/. Secondary source for proposed CTV activation parameters (signaling start March 30, 2026); cited for that claim only and flagged as secondary.

[R10] Nisslmueller, Utz, Klaus-Tycho Foerster, Stefan Schmid, and Christian Decker. 2020. "Toward Active and Passive Confidentiality Attacks on Cryptocurrency Off-Chain Networks." arXiv:2003.00003.

[R11] Tikhomirov, Sergei, Rene Pickhardt, Alex Biryukov, and Mariusz Nowostawski. 2020. "Probing Channel Balances in the Lightning Network." arXiv:2004.00333.

[R12] Lightning protocol contributors. *BOLT 4: Onion Routing Protocol*, TLV payload format and custom records. https://github.com/lightning/bolts/blob/master/04-onion-routing.md. Accessed September 30, 2026.

[R13] Lightning protocol contributors. *BOLT 7: P2P Node and Channel Discovery*, node_announcement and channel_update fields. https://github.com/lightning/bolts/blob/master/07-routing-gossip.md. Accessed September 30, 2026.

[R14] Dugan, Patrick B., Daniel P. Pizarro, and Lihki J. Rubio. *Graph Re-write Using Ghost Nodes for Target Value Rebalancing*. US 2021/0004796 A1, published January 7, 2021; application 16/920,416, filed July 2, 2020; provisional 62/869,730, filed July 2, 2019. Cited for the ghost-node construction's provenance.
