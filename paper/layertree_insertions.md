# LayerTree as a fourth settlement object: proposed insertions for *Where the Capital Bound Moves*

Status: a proposal. Nothing in `paper/tex/main.tex` is changed by this file. Where a passage below is
written out, it is written so that it can be pasted in; where it is a suggestion, it says so.

**Source.** Osuntokun, *LayerTree: A Shared Bitcoin UTXO with an O(1) Unilateral Exit*, draft dated
2026-10-15, stamped commit `ba8422e` (the short version, 42 pages, `https://layertree.tech/paper/main.pdf`),
and the repository `lightninglabs/layertree` at `ba8422e`: `spec/fee-analysis.md`, `spec/scripts/sizes.md`,
and the paper sources `table-ark.tex`, `table-compare.tex`, `table-sizes.tex`, `table-lifetime.tex`,
`table-batch.tex`, `appendix-assumptions.tex`, `appendix-compare.tex`, `appendix-ops.tex`,
`short-trust.tex`, `short-vouchers.tex`, `appendix-vouchers.tex`, `body-receive.tex`, `body-credit.tex`,
`body-channel-budget.tex`, `short-channels.tex`, `body-eval.tex`, `body-tiers.tex`. Table numbers below are
the short version's: Table 3 measured `EXIT_1` sizes; Table 4 who can do what (its Appendix B); Table 5 one
exit by variant (Appendix D); Table 7 batch shapes; Table 10 lifetime bytes per member; Table 11 latency and
liveness; its Table 12 is the comparison with shared-output constructions.

**Conventions, repeated wherever a number appears.** Every vB figure is a whole transaction on the
draft's own model: measured script and witness plus a 129-byte control block (the eight-leaf reference
taptree; each doubling adds 8 vB to every spend), on a 946 WU skeleton with one payout, 774 WU without a
payout, 550 WU for FULL's fee-from-payout exit, 172 WU per further payout, vB = ⌈WU/4⌉ once per
transaction. The model leaves out the witness item count and length prefixes (10.5 vB on a FULL `EXIT_1`
at D = 16, 10 in CCV, 42.5 in MID, 44.75 in MIN; `spec/scripts/weights.md`); the transaction-tree baseline
it compares against omits anchors and their fee children, the relative timelock at the leaf, and every
round-level cost of a deployed Ark (the round transaction, connectors, forfeits, refreshes). Dense profile,
FULL tier, D = 16 unless stated. The exit is **one transaction and O(D) bytes** (1,020 vB at D = 16); this
file does not use "O(1)" without saying in what.

---

## 1. Insertion points

Section and paragraph of the current `main.tex`, then one line on what goes there.

| Where | What |
|---|---|
| §1 Introduction, roadmap paragraph, after the BIP 448 sentence | One sentence: a fourth object, LayerTree, proposed and not deployed, under which the bound acquires a byte-rate term beside the capital term, and a throughput constraint. |
| §2 Related work, "Ark and covenants", after the BIP 448 sentence | Two sentences placing LayerTree: a covenant shared output with a one-transaction, O(D)-byte unilateral exit; four opcode tiers, none active; vouchers in place of out-of-round transfers; cite the draft and the repository at `ba8422e`. State that BIP 448 does not reach any LayerTree tier (every tier needs `OP_TX` or BIP-443 and `OP_CAT`; BIP 448 supplies only the CSFS that FULL and CCV also assume). |
| §4.1, Table 2 | New row $T$ (Part 2 below). Caption: "…and the LayerTree leaf $T$, whose opcodes are likewise inactive." |
| §4.1, paragraph "Three things the table makes visible" | Qualifying clause on the second thing: the VTXO is no longer the only object with an obligation on the holder's calendar; the LayerTree leaf has a lease, but its expiry pays the holder on chain rather than forfeiting to the operator, so the obligation is to renew or be paid out, not to refresh or lose. |
| §4.3, after Proposition 3's cost sentence ("the holder must refresh before $\tau$, the server can decline to include a holder in a round") | Clause: under $T$ the holder renews a lease or is paid out, and the operator can decline a graft or a co-signed update but not an exit (Table 4). |
| §4.3, last paragraph (the server's own channels) | One sentence: the same tier sits on a LayerTree operator's Lightning channels, since receipts into credit leaves arrive there, so $\hat f_S$ is common to $V$ and $T$ and the comparison between them is on what each fronts inside the object. |
| §4.4, after the paragraph on the recovery rule and after Figure 3 | Part 3: the $T$ ratio, the parameters $T_u$, $T_\ell$, $G$, $W$, and the sentence that nothing is fronted at a spend under $T$, so the recovery question is Ark's and not a property of shared outputs. |
| §4.5, end | Forward reference to `model/layertree.ts`: Tables 5 and 10 of the draft reproduced; no grid cell for $T$, because its capital term depends on the receive share and the top-up period, which the grid's demand (one netted balance per agent) does not separate. |
| §4.6 The star topology | Qualifying sentence: a LayerTree is also a star at the operator for Lightning receipts, but a voucher between members crosses no operator and no cut the operator sees until redemption. |
| §5.1, after "That is what Section 4 said of the virtual output, and here it is said without a server" | One sentence: the LayerTree leaf is a third form of the same thing, no direction at the member tier, one output for all, the operator needed to graft and to co-sign an update but not to pay, redeem or exit. |
| §5.2 The clock on capacity | Sentence: the factory's $R_a$ has an on-chain counterpart in LayerTree's `REWRITE`$_h$, 151 vB per changed leaf at $h = 6$ with only the changed owners signing (Table 7): a reallocation clock that is a transaction, not a signing round, and that needs the operator. |
| §5.3, churn paragraph, "an Ark isolates its holders from one another" | Qualifying clause: as does a LayerTree, whose operator grafts and evicts alone, paying an evicted member in full at 158 to 203 vB per leaf in a cohort sweep or 1,020 vB alone (Table 7), with no capital of the operator's held against the departure. |
| §5.3, first paragraph, "one member's failure costs chain space of order $k$ unless the state is itself a tree of templates…" | Qualifying clause: or a covenant tree of the LayerTree kind, where one member leaves in one transaction of O(D) bytes and the shared output survives, recreated under the new root, for the rest. |
| §5.4 The ratio with three objects | A fourth term and the accounting decision applied: the operator's own stock toward members is the pre-funded credit leaves plus whatever graft value it fronts. |
| §6.5, "proof cost sets a minimum capital to participate" | Part 6: a second floor at the settlement object: the exit's fee, and a confirmed fee coin for every unilateral path but FULL's fee-from-payout exit. |
| §6.6, after the BIP 448 paragraph | Part 5: the voucher is not an escrow; which of Proposition 7's properties it lacks and which it does not need. |
| §7.1, Table 5 (observers) and the paragraph "Under the VTXO one observer sees everything within its Ark" | Qualify: a LayerTree operator co-signs grafts and updates and sees every on-chain transition, but a voucher in flight and a channel-leaf payment are not shown to it; $O_{\mathrm{server}}$ under $T$ is partial where under $V$ it is total; $O_{\mathrm{chain}}$ under $T$ sees every transition of one output. |
| §7.4 The warden's statistics | Part 4's contention attack and its cost per block; a statistic $O_{\mathrm{chain}}$ computes from the output's spend chain alone. |
| §7.5, "The lever is the authority field" | Qualify the server as policy enforcement point: Table 4's operator cannot delay an exit beyond [C], move or reduce another leaf, or freeze value it did not graft and fund; a LayerTree operator is a weaker enforcement point than an Ark server, and a weaker evasion point for a swarm that runs one. |
| §8 Preregistration | New item: a $T$ cell with $T_u$, $T_\ell$, receive share, funding mode, $\kappa$, $\beta$ as parameters; the contention cost against the honest bid. |
| §9 Limitations | $T$ is conditional on opcodes none of which is active, three tiers assuming an opcode in a tapleaf version its proposal does not define; the UC proof is in the full version, not read; the draft's Ark baseline omits round overhead; its vB model omits prefixes and anchors; fee pinning is outside [C]. |
| Appendix A | Symbols: $T$, $P_a$, $G$, $T_u$, $T_\ell$, $W$, $\kappa$, $\beta$, $\Delta(q)$, $b_T$. |
| Appendix B | `model/layertree.ts`: cost tables, Tables 5 and 10 reproduced, [C], the floors; twenty-one tests. |

**Existing Ark claims that need a qualifying clause because LayerTree is the counterexample.**

1. Table 2, row $V$: expiry "28 d, server-set" and liveness "refresh before $\tau$". A shared output need not expire; a LayerTree's output has no expiry and its per-leaf lease pays the member on expiry. The clause: expiry and forfeit are Ark's design, not a property of shared outputs.
2. §4.3, "it recovers forfeited or expired value by sweeping a round after its absolute timelock": under $T$ expiry pays the member and nothing is forfeited to the operator.
3. §4.4, "the forfeited input is either swept only at its absolute expiry … or presented to the next round": the recovery rule is a question about Ark's fronting at a spend; under $T$ nothing is fronted at a spend, and the operator's fronting is the credit leaf, before the receipt.
4. §4.3, Proposition 3's reading "the server can decline to include a holder in a round": under $T$ the operator can decline a graft and a co-signed update, not an exit, a voucher redemption or an eviction's payout.
5. §5.3, exit of order $k$ and "the pool survives only in the subtrees beside it": under $T$ one member leaves in one transaction and the output survives.
6. §5.3, "an Ark isolates its holders from one another": a LayerTree does too, with no operator capital held against departures.
7. §7.1, "the server co-signs every transfer … a total warden": under $T$ the operator co-signs updates and grafts, not vouchers; the warden is partial.
8. Wherever the paper describes a tree exit as a path of transactions (Table 2, row $V$, "branch + leaf broadcast"; the draft's own comparison at Table 12 lists Ark at $O(\log N)$ transactions): under a covenant tree of the LayerTree kind the path is a witness in one transaction. Say "transactions" or "bytes" each time.

---

## 2. Settlement-object entry

**Table 2 row** (same seven columns; wording matched to the existing rows):

```latex
$T$ LayerTree leaf & owner key; a Merkle-sum path to a root tweaked into the output key, predicates in the taptree & the spend confirms; no timelock & one transaction, $O(D)$ bytes: 1{,}020\,vB dense FULL $D=16$ (762 at $D=8$, 1{,}149 at $D=20$; MID 1{,}355, MIN 1{,}473, CCV 908); owner online to rebuild after a competing spend unless a tower holds $\mathrm{EXIT}^{t}$ & renew the lease or be paid out; a confirmed fee coin for every unilateral path but FULL's fee-from-payout exit & operator (graft, co-sign, evict after lease paying in full, detach, stall partial vouchers; cannot move or reduce a leaf or delay an exit beyond [C]); co-members, for throughput only; a voucher's issuer until redemption confirms & none on the output; a lease per leaf, set at entry; eviction pays the member \\
```

**Prose entry**, to follow the paragraph after Table 2:

> The LayerTree leaf $T$ is the fourth object. Its *state* is a leaf (amount, exit key, owner key, evictor key, `evict_after`, nonce, `seq`) at a position in an off-chain Merkle-sum tree of depth $D$; the output commits to the root through the internal key, the predicates are the taptree, and every spend proves the changed positions against the committed root and recreates the output under the new one. *Authorisation* is per Table 4 of the draft: the owner exits at any time, co-signs updates, issues vouchers and carves its leaf; the evictor pays a leaf out in full after its lease; the operator grafts, co-signs, evicts, detaches a cohort and fills empty positions, and cannot move or reduce another leaf, delay an exit beyond [C], or freeze value it did not graft and fund; anyone redeems a valid voucher or relays a transition. The *exit* is one transaction and $O(D)$ bytes with no timelock: 1,020 vB at $D = 16$ in FULL on the draft's model (1,030 serialised), 762 to 1,149 across $D = 8$ to $20$, 1,355 in MID, 1,473 in MIN, 908 in CCV (Tables 3 and 5); the owner must be online to build it and to rebuild it after a competing spend, unless it has signed an $\mathrm{EXIT}^{t}$ authorisation that a tower holds (1,046 vB). There is *no expiry on the output*; each leaf carries a lease, after which its evictor may pay it out on chain, 158 to 203 vB per leaf in a cohort sweep (Table 7); keeping a position costs a renewal per period, 151 vB per member in a signed cohort rewrite or 2,616 vB alone. The *covenant dependency* is one of four tiers (the draft's Table 6): FULL (tapleaf `0xC2`: `OP_CAT`, splice and bit operations, `OP_TX`, CSFS, the EC opcodes), MID (`0xC0`: `OP_CAT`, `OP_TX`, CSFS, `OP_TWEAKADD`; 4-byte numerics cap a tree at $2^{31}$ sat and force exact payouts), MIN (`0xC0`: `OP_CAT`, `OP_TWEAKADD`; introspection from a signature under the generator, assumption [MIN]; only `EXIT`$_1$ and `SPLIT`, so no vouchers and no channel leaves), and CCV (BIP-443 and `OP_TX`). None is active, and three tiers assume an opcode in a tapleaf version its proposal does not define (the draft's Table of assumptions, [A-1] to [A-6]). BIP 448 supplies the CSFS that FULL and CCV assume and nothing else a tier needs.

---

## 3. The capital bound under the LayerTree regime

The paper's bound for $V$ (Proposition 3 and Equation 1) has two terms on the server side: the pooled stock $\hat f_S$ and the forfeit lock $W_S$, the value fronted at spends and refreshes until the recovery rule releases it. Under $T$ the second term does not exist and the first does not pool.

**What replaces the round-rollover term.**

*(a) Graft funding.* A cohort enters by one `JOIN`$_h$ on the operator's signature: about 679 vB for 256 members, 2.7 vB each, at $D = 16$ (Table 7; an estimate from the measured `JOIN`$_0$ at $D = 8$, which walks the same eight levels). If the operator funds the grafted value from its fee input, it fronts the cohort's balances, $G = \sum_a g_a$, from the graft's confirmation until each member pays, off-chain afterwards or beforehand by a hash-locked voucher; who is online is the operator alone. If members fund their own leaves, each adds a 58 vB key-path input, the join is a signing round among the funders, a funder who drops out invalidates the others, and $G = 0$; who is online is every funder at once. Either way a member checks its own path inside the graft before funding, since a grafted node with no real tree behind it freezes its value.

*(b) Lease renewal.* A position is held until `evict_after`. Renewing it costs 151 vB per member in a `REWRITE`$_6$ that every renewing member signs (a member who does not sign keeps its old lease), or 2,616 vB alone, an `UPDATE` and a whole-balance `SPLIT` (1,030 + 1,586; Table 7). The period $T_\ell$ is the operator's choice at entry. No capital of either party is bound by the lease; what is bound is the member's position, and what releases it is renewal or eviction, the latter paying the member on chain at the evictor's cost in fees.

*(c) Credit-leaf pre-funding for inbound Lightning receipts.* A member receives over Lightning into a credit leaf the operator owns, with the member's key as exit key, in any tier but MIN. The operator settles the payer's HTLC first and then signs the member a cumulative voucher for the running total. A voucher draws only what the leaf holds, so the operator pre-funds the leaf and tops it up by an amount-only `REWRITE`$^{x}_h$, about 122 vB per credit leaf batched per cohort (the draft's Appendix E.3; its rewrite variant is not among the measured rows of `sizes.md`, so the figure is carried as the draft's), which voids no voucher. The pre-funded capital $P_a$ is the operator's, bound in the tree from top-up until the member co-signs a settlement (`UPDATE`$^{x}$, 1,048 vB, or a cohort `REWRITE`$^{x}_h$, about 164 vB a leaf) that lowers the amount by what has been paid out, usually against a leaf of the member's own in the next graft. On every path the operator can take alone, an exit, an eviction, excess beyond what has been vouched is the member's: the forfeit runs the opposite way to Ark's, from operator to member, so the operator's incentive is to pre-fund little and top up often. The member's exposure is one payment, the one the operator has settled and not yet vouched for; no order of the steps removes it.

*(c′) The pending-leaf receive.* A tree that names a reclaim key and carries the merge voucher `CLAIM`$^{hm}$ and the reclaim-form rewrite (FULL, MID and CCV) replaces the one-payment exposure with an atomic form: a pending leaf $P_a$ the operator owns, with the member's key as exit key and the reclaim key as evictor, and a landing leaf $L_a$ of the member's beside it; each payment is a hash-locked voucher that moves value from $P_a$ into $L_a$ against the member's preimage; once per window $W$ the operator moves the settled total and takes back what was never claimed. Here $P_a$ is bound for $W$ and released by the operator alone; the member bears no payment exposure; the cost is a landing leaf per member and a settlement per window, which the full version prices at two transactions of 8,347 and 9,155 vB for 64 pairs at $2^{16}$ members, about 273 vB a pair (full version only).

**What is bound, by whom, for how long, released by what.**

| Term | Bound by | In | For | Released by |
|---|---|---|---|---|
| $P_a$, credit leaf | operator | the tree, per member | from top-up until settlement; unbounded if the member is absent, and then forfeit to the member at eviction | the member's co-signature (`UPDATE`$^{x}$ or cohort rewrite) |
| $P_a$, pending leaf | operator | the tree, per member | the settle window $W$ | the reclaim rewrite, operator alone |
| $G$, operator-funded graft | operator | the tree, per cohort | from graft confirmation to the member's payment; zero if members prepay by voucher | the member's payment |
| the member's position | member | the tree | until `evict_after` | renewal (151 or 2,616 vB) or eviction (paid out) |
| the fee coin | member | an on-chain UTXO | for the life of the position | never, while the member wants any unilateral path but FULL's fee-from-payout exit |
| the output's spend slots | everyone | the tree output | per block | $\kappa$ confirmations per block ([C]) |

**The modified formula.** With the paper's accounting of §5.4, each object charged its operator's own stock and the tier on the operator's network channels charged to none,

$$
\mathrm{Locked}_T(t) \;=\; \sum_a P_a(t) \;+\; G(t),
\qquad
P_a \;\approx\; (1+m)\, r_a\, T_u ,
$$

where $r_a$ is the member's receipt rate into its credit leaf and $T_u$ the top-up period (or $W$, in the pending-leaf form); nothing is fronted at a spend, so there is no $\mathrm{Vol}\cdot\bar L$ term. Against the channel,

$$
\frac{\mathcal D_C}{\mathcal D_T} \;\approx\; \frac{H \sum_a \hat f_a}{H \sum_a (1+m)\, r_a T_u \;+\; \int_0^H G} ,
$$

and beside it a byte-rate the paper's duration does not price,

$$
b_T \;=\; \frac{122}{T_u} + \frac{151}{T_\ell}\ \text{vB per member per block (cohort of 64)},
$$

plus about 3 vB per member at entry and 158 vB at a cohort exit over the lifetime. The parameters added are $D$ and the tier (exit bytes), $T_u$, $T_\ell$, the funding mode and $G$, $W$, the receive share of demand, and $\kappa$, $\beta$ of Part 4.

**Scale, outside the model.** The credit leaf converts the channel's long-horizon forecast of a peak net balance into a short-horizon forecast of gross receipts. On the grid's zero-drift cell (receipts of 5,000 sat at probability 0.02 per round of six blocks, 100 sat a round), a daily top-up ($T_u = 144$ blocks) at margin 0.25 sizes $P_a$ at 3,000 sat, against the oracle channel stock of about 104,000 sat per agent on the same cell (Table 3's 20,818,750 sat over 200 agents): about 35 times less capital, bought with 0.88 vB per member per block on chain. The grid cannot confirm this, because its agents net receipts against spends in one balance and a credit leaf is receive-only; the figure is indicative and is stated as such. At MIN there is no credit leaf and no receive term.

---

## 4. Throughput as a first-class constraint

**Assumption [C], as the draft states it** (its §6, Table of assumptions). At most $\kappa \ge 1$ spends of a tree output confirm per block, and while an honest spend is pending at the prevailing feerate at most $\beta$ conflicting adversarial spends confirm ahead of it. $\kappa$ is mempool policy, not consensus: 25 under Bitcoin Core's ancestor and descendant limits before version 31, at most 64 under its cluster limit since (verified: `src/policy/policy.h` at `v31.1` has `DEFAULT_ANCESTOR_LIMIT 25`, `DEFAULT_DESCENDANT_LIMIT 25`, `DEFAULT_CLUSTER_LIMIT 64`), and as low as 1 once anyone hangs descendants off a payout; $\beta$ is the adversary's fee budget against the honest bid. An honest spend with $q$ others queued ahead confirms within

$$
\Delta(q) \;=\; \Delta_L\left(\left\lceil \frac{\beta + q}{\kappa} \right\rceil + 1\right)
$$

blocks, $\Delta_L$ the chain's own delay. The draft uses $\kappa = 25$: 10,000 cooperating leaves leaving at once take 400 blocks (157 at 64), so a tree is sized by exit throughput and not by depth. **Fee pinning is outside [C]**, in the draft's own words, and therefore outside anything the paper would say with these numbers.

**Sharding.** `DETACH`$_h$ moves an aligned cohort into a tree output of its own under the same rules and `tree_id`, 780 vB at $h = 8$ (then 762 vB per exit in the detached tree at $D = 8$); vouchers survive it. Each output is spent independently, so $\kappa$ applies per shard, and the operator decides the shard size. In the paper's terms it is the operator's one lever on the object's throughput, and it is the operator's alone (Table 4).

**For the paper's table of objects**, a throughput column: $C$, independent outputs, no shared bound; $V$, a round's unroll is $D$ transactions per member but on outputs that become independent as the branch is published; $C_k$, one output per hyperedge, so the same $\kappa$ applies to a multiparty channel's state updates and the paper's §5.3 should say so; $T$, $\kappa$ per tree output, shardable by `DETACH`.

**The contention attack, for the warden model (§7.4).** A corrupt member can carve its own balance back and forth, the draft's own example: each carve is one spend of the tree output, conserves value, and costs only its fee; `SPLIT` needs the owner alone at 1,586 vB, a `CLAIM` on a self-issued voucher 1,618 vB. To keep an honest 1,020 vB exit out of one block the attacker needs $\kappa$ such spends confirmed ahead of it at no less than the honest bid, so its cost per block of delay is $\kappa$ carves at the honest feerate: 39,650 vB at $\kappa = 25$, about 39 times the honest exit's fee per block; 101 kvB at 64; 1,586 vB, 1.6 times, at $\kappa = 1$. That ratio is what $\beta$ prices, and it is also the attack's signature: every transition of the output is public, so $O_{\mathrm{chain}}$ sees a sequence of carves on one leaf with no payout, at a rate near $\kappa$, from the spend chain alone, with no probing and no observer inside the tree. A statistic, not a defence: the defence is the honest bid, [C]'s $\beta$, and `DETACH` to a smaller output. The paper's statement that a monitor should sit at the server and the registry gets a third place under $T$, the output's spend chain, which anyone can watch.

---

## 5. Voucher against escrow

The draft's voucher is a BIP-340 signature by a source leaf's owner over $H(\mathsf{tree\_id} \| \hat\ell_{\mathrm{src}} \| \ell_{\mathrm{claim}})$: anyone holding it redeems it with `CLAIM` (1,618 vB at $D = 16$, no payout output; 1,636 for `CLAIM`$^{x}$), which checks the signature with CSFS and nothing else. It is voidable by the issuer, who can advance the source's `seq` first, or by the source's evictor after the lease, until the redemption confirms; a cumulative voucher re-signed for the running total needs no contest window, since the latest dominates; the hash-locked form paired with an HTLC on the same hash is an ordered exchange and not an atomic swap, under five rules no script enforces (the party the HTLC pays draws the preimage; the voucher resolves second; the issuer leaves `seq` alone from offer to redemption or failure; the holder redeems as soon as it learns the preimage and bears the issuer risk until that confirms; the holder first checks that the source's lease outlasts the HTLC's expiry plus $\Delta(q)$). The dedicated credit leaf removes the voiding, since every transition that could void needs the exit key, and leaves the issuer's liveness as the holder's exposure.

Against the paper's escrow $E$ (Proposition 7):

| Property of $E$ | The voucher |
|---|---|
| enforces a provable statement in $\mathcal R_{\mathrm{svc}}$ | enforces nothing about the world; it is an authorisation to carve, conditional at most on a hash preimage |
| a false Assert is slashed by any single challenger at a cost independent of $B$ | no assertion, no slash; over-redemption is prevented by the covenant, over-issuance and voiding are not |
| a true Assert is released after $\Delta$ | redeemable at once, with no window; and voidable until confirmed |
| a bond $B$ independent of the payment | the collateral is the source leaf's balance, which is the payment |
| a deadline | none; script cannot give a voucher a deadline, hence the five rules |
| setup: a committee that deletes a key, a garbled circuit per assertion, a proof-system setup | none; one CSFS check |

What the voucher lacks that the paper's bond needs: statement verification, slashing, a deadline, and collateral separate from the sum paid. What it does not need: a challenge period, a challenger, a committee, a proof system, because it makes no claim beyond "this leaf may be carved so", whose only risk is the issuer's own voiding or absence. The conclusion for the paper: a voucher can carry the connector's *payment* and the Ark out-of-round transfer's role, with the trade the draft states (undone by the issuer alone until confirmed, against undone by sender and server together); it cannot carry the connector's *bond*. $\mathcal R_{\mathrm{svc}}$'s release on an attested service ratio is not a LayerTree predicate, and the paper's §6.6 route to it, a CSFS-checked attestation, lives outside the tree.

---

## 6. The fee-coin requirement

Only FULL's fee-from-payout `EXIT`$_1$ pays its fee from the tree's value (550 WU skeleton, 921 vB at $D = 16$). Every other unilateral path needs a confirmed on-chain coin of the member's own: the exact exit that MID, MIN, CCV and every channel leaf use (1,020 vB), a channel leaf's force close (about 1,681 vB: the exit that creates the funding output, an update, a settlement and their two anchor children), and the credit-leaf fallback, `CLAIM`$^{x}$ then the exact exit (1,636 + 1,020 = 2,656 vB). The draft's Table E.4 and `spec/fee-analysis.md` give, at 2, 10 and 50 sat/vB:

| Path | Fee coin | vB | 2 sat/vB | 10 sat/vB | 50 sat/vB |
|---|---|---|---|---|---|
| `EXIT`$_1$, fee from the payout (FULL) | no | 921 | 1,842 | 9,210 | 46,050 |
| `EXIT`$_1$ or exact exit, fee input | yes | 1,020 | 2,040 | 10,200 | 51,000 |
| channel-leaf force close | yes | 1,681 | 3,362 | 16,810 | 84,050 |
| `CLAIM`$^{x}$ then exact exit | yes | 2,656 | 5,312 | 26,560 | 132,800 |

Break-even balances, fee equal to balance, are the fee columns; the smallest economical leaf adds the 330 sat P2TR dust limit: exogenous $\max(\text{fee}, 330) + 1$, so 2,041 / 10,201 / 51,001 sat; endogenous fee + 331, so 2,173 / 9,541 / 46,381 sat. Below 26,560 sat at 10 sat/vB the credit-leaf fallback costs more than it recovers.

What this does to the paper. The grid's agents hold balances of order $10^3$ to $10^5$ sat (bursts of 5,000; peaks around $10^4$ to $10^5$). At 10 sat/vB the plain exit takes 9,210 to 10,200 sat, so a balance at the lower end of that range cannot leave alone at a profit, and §6.5's minimum capital to participate gets a second floor at the settlement object, $10^4$ sat for a plain leaf and $2.7\times10^4$ for a credit-leaf fallback at that rate, before the proof layer is reached. A member with no on-chain coin has exactly one unilateral path, FULL's fee-from-payout exit on a plain leaf: it cannot force-close a channel leaf and cannot exercise the credit-leaf fallback, so the Lightning-receive flow is enforceable only by members who hold a UTXO, which the paper's population, agents paying from low balances with no bank, may not. At MID, MIN and CCV there is no fee-from-payout exit at all. The paper should say that $T$'s exit cost $X$ is a function of the member's holdings outside the object, which no other row of Table 2 has.

---

## 7. Channel leaves

The paper prices liveness as an obligation $\Lambda$ and an exit as a cost and a delay $X$, both qualitatively; *Connector Calculus* lists CLTV delta among the policy variables a connector carries and does not price it. No capital term follows. What can go into the $T$ row's $X$ and $\Lambda$, if channel leaves are mentioned at all: a channel leaf's force close is about 1,681 vB against 684 vB for a simple taproot channel's open plus force close on the same model (the simple taproot channels extension BOLT, lightning/bolts PR 995, verified merged 2026-05-04); its HTLC deadline budget is $\mathsf{cltv\_expiry\_delta} \ge G_{\mathrm{exit}} + 1 + \beta_{\mathrm{chan}} + 1 + \mathsf{csv\_delay} + 1 + G_{\mathrm{sweep}}$, about 220 blocks with $\mathsf{csv\_delay} = 144$, $G_{\mathrm{exit}} = 72$, $G_{\mathrm{sweep}} = 2$ and $\beta_{\mathrm{chan}} = 0$, against lnd's default of 80; at $\kappa = 25$ and $\beta = 0$ about 1,775 channel leaves may close in one window ($\beta + q \le 71\kappa$), and larger hubs shard; a proof that channel leaves compose is open, in the draft's words. The composition gap is the item to carry into Limitations if the row carries the numbers.

---

## 8. `model/` changes

`model/layertree.ts` and `model/layertree.test.ts`, added. No predicate is implemented; the file is cost tables and the two bounds.

- `WITNESS_WU`: the measured total witness weights from `spec/scripts/sizes.md` at `ba8422e` for the rows the proposal quotes; `SKELETON_WU` and `txVb` apply the draft's transaction model.
- `table5()` reproduces the draft's Table 5, one exit by variant, and `table10()` its Table 10, lifetime bytes per member, both exactly as printed; `operationVb()` reproduces the Table 7 figures that derive from measured rows (`EXIT`$_2$ and its 665 vB margin, joins, `UPDATE`, `UPDATE`$^{x}$, `CLAIM`, `CLAIM`$^{h}$, `CLAIM`$^{x}$, `SPLIT`, the 2,616 vB renewal as `UPDATE` + `SPLIT`, the two sweeps at 203 and 158 vB per leaf, `DETACH`$_8$ at 780 vB, the 2,656 vB fallback). The 122 vB top-up and the 151 vB cohort renewal are carried as the draft's figures (`RECURRING_VB`), since their rewrite variants are not among the measured rows.
- `confirmationBlocks` is $\Delta(q)$; `drainBlocks`, `channelLeavesPerWindow` and `contentionCost` are the worked figures of Part 4; `KAPPA` names the three policy values.
- `minimumLeafSat` and `feeCoinTable` are Part 6.
- `LayerTreeParams`, `lockedPerMember`, `bytesPerMemberPerBlock`, `exitVb`, `tierHostsVouchers` are Part 3's terms with the parameters named there (depth, tier, $\kappa$, $\beta$, lease period, top-up period, receipt rate and margin, funding mode and graft exposure).
- Two tests: the tables reproduce; the [C] figures, the floors and the capital terms follow from the stated parameters. Twenty-one tests pass in `model/`.

Described in Appendix B, if adopted, in the same terms as the other witnesses: the tables are reproduced on the draft's own model and prove nothing about the opcodes or the protocol.

---

## 9. Factual gaps and sourcing

**(i) Measured against modelled.**
- Measured: script bytes, witness data and control block per transition (`sizes.md`), by a Python interpreter and a Go implementation byte-exact against golden scripts; serialised sizes in `weights.md` for a subset.
- Modelled: every vB figure (skeleton, ⌈WU/4⌉, prefixes excluded; about 1% low in FULL and CCV, about 3% in MID and MIN); the 256-slot `JOIN`$_8$ at 679 vB (an estimate from `JOIN`$_0$ at $D = 8$); the sweep leaf counts (every fifth position empty in the measured tree); the Lightning baseline (240 / 152 / 138 vB); the transaction-tree baseline ($150D + 111$, anchors and timelock omitted, no round, connector, forfeit or refresh priced; "not a measurement of any specific Ark implementation", the draft's words); the lifetime rows of Table 10, which enter Ark as two 43 vB outputs with the round's shared overhead left out.
- Arithmetic from assumptions: $\kappa = 25$ is a policy value; 400 and 157 blocks; 1,775 channel leaves; the contention ratio; the break-even balances.
- Not reproducible from `sizes.md`: 122 vB per credit-leaf top-up and 151 vB per cohort renewal (their rewrite variants are not listed); 1,681 vB for a channel-leaf force close (its components are not listed). The 2,616 vB renewal is `UPDATE` + `SPLIT` and reproduces.

**(ii) Full version only.** The ideal functionality, the UC simulator and proof (its Appendix "The UC Proof"), the inline Lean statements, the full predicate and party tables, and the pending-receive settlement figures (8,347 and 9,155 vB for 64 pairs at $2^{16}$ members). The short version states the UC theorem's hypotheses (idealised hashes, taproot binding in the random-oracle model, [C], a static adversary corrupting the operator and any members) and defers the proof. Not read here.

**(iii) Dependent on an inactive opcode.** Every tier. FULL needs `OP_TX` (a draft on a personal fork, defined for `0xC2`), CSFS in `0xC2` (BIP-348 defines it for `0xC0`), and the EC-ops draft, which is by the draft's author; MID assumes `OP_TX` in `0xC0` with `CScriptNum` outputs, "which no proposal defines"; CCV assumes BIP-443 in `0xC2` and its sigop cost, open upstream; opcode numbers collide (`OP_TX` and `OP_EC_POINT_NEGATE` both claim `0xbd`; BIP-443 and `OP_EC_POINT_ADD` both `0xbb`); [MIN] is a cryptographic assumption (a signature under the generator with $s = e + 1$ binds the script-built message to the real one). The draft proposes no opcode and says so.

**(iv) Citations needing independent verification, and what was checked.**
- Simple taproot channels, "lightning/bolts PR #995, merged May 2026": verified. The pull request "extension-bolt: simple taproot channels (feature 80/81)" is merged, `merged_at` 2026-05-04, and `bolt-simple-taproot.md` is on master.
- Bitcoin Core mempool limits, "25 before version 31, 64 under the cluster limit": verified against `src/policy/policy.h` at tag `v31.1`.
- lnd's default `cltv_expiry_delta` of 80: not re-checked here.
- The draft's own stamp: the PDF says commit `ba8422e`; `paper/version.tex` at `ba8422e` says `GitHash 74cdcab`, so the PDF was built from a tree whose generated version file differs from the committed one. Cite the PDF by its stamped hash and date and note the discrepancy.
- The abstract's "3,019 executable checks" does not match the evaluation section's own counts (1,610 FULL, 1,391 MID, 57 MIN, 4,295 CCV, 220 channel-leaf, 133 for the hypothetical opcode); the sum of any subset I can see is not 3,019. Do not carry the number.
- The hypothetical native Merkle-sum opcode (388 and about 520 vB) is "a measurement, never a tier", unproposed; do not carry it as a cost of anything.
- The title's "O(1)" is O(1) in transactions and O(D) in bytes; the paper should say which every time, and the draft's abstract does.

---

## Appendix: three sentences for the preamble of any inserted passage

For the author's convenience, the qualifiers the brief asked to be stated inline rather than carried as clean numbers:

- "on the draft's transaction model, which omits witness length prefixes (about 1% in FULL and CCV, 3% in MID and MIN) and, in its baselines, anchors and fee children";
- "fee pinning on the shared output is outside the draft's assumption [C] and outside this paper";
- "the draft's Ark baseline is a transaction-tree model, $D$ transactions of 150 vB and a 111 vB claim, which prices no round transaction, connector, forfeit or refresh; the comparison therefore favours LayerTree by the round overhead it leaves out, and the paper's Table 3, which does price the forfeit lock, is not comparable to it without that term".
