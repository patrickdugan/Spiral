# BIP-SIEVE-MATCH-01: a finite claim with paired or merged outputs

**13 November 2026. Structural model and serialization experiment.**

The merged-output route reproduces the paired route's modeled settlement and recovery outcomes under the matched assumptions below. Across 4,800 decision pairs, both validators agree with an independent abstract claim predicate. The paired route adds 84 base bytes over assertion and terminal spending. A specified two-leaf witness layout adds 467 WU over the corresponding merged payout path.

These results concern a finite, admitted claim with ideal authorization predicates. Actual BitVM artifacts and native Bitcoin validation remain separate experiments.

## Source pins and execution

The unchanged paired validator comes from Spiral commit
76071a0195f48961386e46d56df7b5e0276637fc:

- [Sibling draft](https://github.com/patrickdugan/Spiral/blob/76071a0195f48961386e46d56df7b5e0276637fc/in-and-out-burger/research/checksiblingverify/bip-XXXX-checksiblingverify.mediawiki), blob 966f89911fd5b18a265aba089c7fa721c84888c1.
- [Paired model](https://github.com/patrickdugan/Spiral/blob/76071a0195f48961386e46d56df7b5e0276637fc/in-and-out-burger/research/checksiblingverify/sibling_model.py), blob 17c405958854f5e5e86914997ed7da7acf024c22.

Both blobs are identical to those inspected for paper version 0.1 at cfafbec4ae072b859f0140b2487baac14fac3a44.

The template check uses the [BIP446 specification](https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0446.md) and its [19 basic vectors](https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0446/basics.json), blob 4ed4ac04fd40051ba630ab17dfa736e4e5a5ee69. Weight follows [BIP141](https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0141.mediawiki). The two-leaf control-block envelope follows [BIP341](https://github.com/bitcoin/bips/blob/b34d9f751791d4feb22feff4f2ed00bcac83961b/bip-0341.mediawiki).

The dependency-free Python harness checks the upstream Git blob before importing it. It implements the merged comparator separately. An independent wire decoder checks serialized framing and the official template vectors.

Run from a checkout containing the paper:

    python BIPSpace/The-BIP-Sieve/benchmarks/sibling_vs_merged.py

If the model lives elsewhere, supply its pinned file:

    python sibling_vs_merged.py --upstream-model /path/to/sibling_model.py

The deterministic seed is 20261113. The program writes results.json beside the harness by default; --output selects another destination. The official vector JSON must remain beside the harness.

## Matched contract

| Property | Shared requirement |
|---|---|
| Economic object | One authentic admitted liability with a fixed claim, program and setup identity |
| Funds | Principal P and bond B |
| Settlement | Identical P and B destination scripts and amounts |
| Recovery | Identical liability-preserving terminal output vector |
| Authorization | Same ideal operator signature and graph/statement/setup-bound ideal fraud predicate |
| Timing | Same assertion confirmation height and block-based relative delay |
| Funding review | Exact denominations, complete spending policy and key-path exclusion are assumed checked; each admitted UTXO root is fresh |
| Fees | Zero-fee protected parent, a fixed zero-value anchor and independently authorized fee sponsorship |

The paired assertion creates V with P and C with B. Its terminal transaction spends both inputs. The merged assertion creates M with P+B, and its terminal transaction spends M. Both transactions produce the same terminal outputs.

The paired reference checks its sibling descriptors and per-input templates. Its connector carries the settlement authorization or fraud predicate. The merged model puts that predicate directly on M and uses the corresponding one-input template. The accepted branch therefore controls all protected value in both representations.

The source draft's assertion profile includes a fee anchor. The upstream constructor currently serializes only V and C. This experiment appends the same anchor fixture to each route and recomputes the outpoints; it leaves the upstream paired validator unchanged.

Both constructors validate every added destination against the original ledger before committing their temporary state. Repeated admission of an unspent root preserves its existing confirmation height and coins when rejected.

The anchor is a one-byte OP_TRUE serialization fixture. Its relay treatment is outside the experiment. Protected and terminal scripts use 34-byte commitment-shaped identifiers, while their full Taproot policy is idealized.

## Graph results

| Check | Executed result |
|---|---|
| Bounded decision comparison | 4,800 evaluated pairs; 720 accepted pairs; zero differential mismatches |
| Independent abstract contract | Zero mismatches against the specified authority and maturity predicate |
| Economic parameters | P of 1,000, 1,000,000 and MAX_MONEY−1,000,000 sat; B of 1 and 10,000 sat |
| Delays | 1, 6, 20, 144 and 65,535 blocks |
| Matched transaction mutations | 16 cases rejected by both routes |
| Conflicting terminal branches | Each branch can confirm first; later consumption of the same claim fails |
| Fee-child cases | Six cases preserve P and B, reject missing sponsor authorization and retain equal child base sizes |
| Synthetic reconfirmation | Six boundary cases reset the modeled maturity when the assertion height moves |
| Same-script connector substitutions | 64 intended pairs accepted; 4,032 cross-parent pairs rejected |
| Atomic UTXO admission | Nine collision cases rejected with every original coin and height preserved |
| Duplicated admission | Each route pays 2,000,000 sat of principal when two roots are admitted for the same 1,000,000-sat claim |

The decision grid varies claim truth, signature validity and fraud evidence. Heights span the assertion boundary and both sides of maturity. Delay one produces coincident boundary heights, so the total describes evaluated cases.

Mutations redirect principal, turn principal into fees, inflate the payout, append a sponsor input, alter a sequence, change version or locktime, and attempt a burn. Both branch families are exercised.

The reconfirmation cases restore a symbolic UTXO state and assign a later confirmation height to the protected outputs. They establish age handling in the model. A live node chain rollback and confirmed assertion-witness replacement still need execution evidence.

### Why the comparison supports the modeled result

Let the shared claim state be either live or consumed with a terminal output vector. Assume that admission has created fresh specified coins, the complete policies are enforced and the ideal authorization predicates have their stated meanings.

For settlement, each representation accepts at height H exactly when H is at least the assertion height plus the delay and the ideal operator signature passes. For recovery, each accepts when the ideal fraud evidence authenticates the committed false claim. The template fixes the same terminal output vector in either case.

Applying either accepted branch consumes every protected coin for that representation. Under the state mapping from the pair {V,C} to M, both transitions therefore produce the same economic state. This is a conditional argument for the specified one-shot model. The finite decision grid and trace checks exercise the implementation of that argument.

The public scripts can be cloned through fresh funding. Exact pairing rejects a connector from another parent, while independently admitted complete roots retain their own spending authority. Both constructions require an admission rule that assigns a unique liability or consumes a shared nullifier state.

The fresh-root checks protect existing UTXOs against being overwritten by the test constructors. Economic uniqueness requires a rule connecting different funded roots to their liability, as the two-root control demonstrates.

## Template-vector cross-check

The independent decoder and template-hash implementation reproduce the expected equality result for all 19 official basic vectors. Sixteen have no annex on the executing input; their computed digests also match the imported paired model.

The vector scripts have the simple form PUSH32, OP_TEMPLATEHASH, OP_EQUAL. This check covers their template-equality condition. Full signature and Taproot validation are outside this run. The independent implementation supports annex hashing for the vector cross-check; the matched claim profile continues to exclude annexes.

## Exact structural cost

With the single-byte counts used by this one-claim graph, the additional paired output costs

    8 value bytes + 1 script-length byte + 34 script bytes = 43 base bytes.

The additional native-witness input costs

    32 txid bytes + 4 index bytes + 1 empty-scriptSig byte + 4 sequence bytes = 41 base bytes.

Thus the paired route adds 84 base bytes over the two-stage path. The choice of shared terminal recipients and shared anchor encoding cancels from this difference.

| Transaction | Merged base bytes | Paired base bytes | Paired increment |
|---|---:|---:|---:|
| Assertion | 104 | 147 | 43 |
| Terminal payout or recovery | 147 | 188 | 41 |
| Complete path | 251 | 335 | 84 |

### Specified witness layout

For the witness calculation, each protected output has a two-leaf tree with 65-byte control blocks. The principal leaf contains a 14-byte literal sibling check followed by a 35-byte template check, totaling 49 bytes. Its extra witness serializes to 117 bytes, including the item count and length prefixes. The connector's program adds another 14-byte sibling check to the merged program's footprint.

When the added bytes leave CompactSize lengths unchanged, the complete path increment is

    4 × 84 + 117 + 14 = 467 WU.

The payout fixture uses a 64-byte operator signature and a delay of 20 blocks. It gives:

| Transaction | Merged weight | Paired weight | Increment |
|---|---:|---:|---:|
| Assertion | 586 WU | 758 WU | 172 WU |
| Payout | 796 WU | 1,091 WU | 295 WU |
| Complete payout path | 1,382 WU | 1,849 WU | 467 WU |

The sum of the separately rounded virtual sizes increases by 117 vbytes. At assumed rates of 1, 5 and 10 sat/vB, the arithmetic difference is 117, 585 and 1,170 sat, respectively. These are fee-rate scenarios; the experiment supplies no market fee estimate or package-acceptance result.

For recovery, the harness varies a common opaque verifier program over eight sizes from zero to 4,096 bytes and shared proof data over zero, 32, 520 and 4,096 bytes. Proof elements are split into chunks of at most 520 bytes. The shared payload cancels from the difference.

When the merged program has L+35 bytes and its paired counterpart has L+49 bytes, the increment is 467 WU plus the difference in their CompactSize prefix lengths. For L from 204 through 217, only the paired program crosses 253 bytes, yielding 469 WU. The other tested lengths yield 467 WU.

These weights belong to the stated envelope. The verifier bytes and control blocks serve as size fixtures; proof execution and Taproot commitment validity remain unmeasured. A different tree layout or an optimized compiler could change the witness difference. The 84-base-byte difference follows from the fixed output and input counts.

## Implication for the sieve

The matched one-shot model gives the merged route the same modeled authorization and terminal accounting with one fewer protected output and one fewer terminal input. The paired route performs two template checks and two sibling checks, while the merged route performs one template check.

This puts the next adoption question at the application boundary: what useful separation of output roles earns the additional primitive and bytes? A candidate benefit should survive a comparison using the same liability and recovery policy. Composing independently useful state machines or changing challenge organization could supply such a case, once their full contracts are specified.

The experiment supplies an initial baseline for that question. Native cold-validation benchmarks and funded recovery must use actual circuit artifacts, complete Taproot construction and a concrete relay profile. The ideal fraud predicate also leaves correctness of garbling and evidence delivery to the implementation being compared.
