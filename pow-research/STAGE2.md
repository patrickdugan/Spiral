# PoW Research Stage 2: source-derived scoring and fork-local claims

**Evidence class:** bounded synthetic model. **No native Primecoin execution.**

The nickname *Olde Coin Pump* remains explicitly satirical. This subfolder
studies general mathematical PoW properties; it issues no tokens and integrates
with no wallet or network.

## Pinned upstream and correspondence

Primary source: `primecoin/primecoin` commit
`8acbee471c69a39bdb04ac2a941edb7112fb5dfa` (2026-02-27).

- `src/prime.h`, Git blob `b3d9766289a1d27f738a38181047792a1eba50c1`:
  header floor `2^255`, origin cap `2^2000-1`, 8.24 target layout,
  initial target 7, minimum target 6, and chain-type identifiers.
- `src/prime.cpp`, Git blob `5cd7669c0cbca70ad851d4ce27052bc059defc21`:
  Fermat fraction at lines 88-106; ELL continuation at 108-144; target
  arithmetic at 146-218; probable-chain and bi-twin composition at 305-356;
  full PoW checks and multiplier normalization at 385-477.
- `primecoin_reference.py` independently re-expresses **only** these predicates
  in bounded Python. It permits tiny origins for transparent, cheap fixtures.
  It does **not** parse raw Bitcoin headers, implement CBigNum semantics for
  malformed encodings, adjust network difficulty, or claim byte-for-byte
  consensus correspondence. The production source also limits chain origins
  and checks header hashes; the toy mode explicitly bypasses those constraints.
- A true differential lane needs a built, hash-pinned upstream binary and
  real/constructed header+multiplier vectors, including rejection cases, with
  accepted/rejected outputs from the native `CheckPrimeProofOfWork` function.

## Source-derived counterexamples

**S2-01 Normalization:** For tiny fixture `header_hash=3`, multiplier `4`,
origin `12`, target length `2`, the full origin's best chain has length 3 plus
fraction. Halving the multiplier yields origin `6`, where the bi-twin length is
5 plus fraction. The bounded model rejects the longer non-normalized multiple.
Multiplier 1 and origin 12 is accepted under the same toy difficulty. Real
Primecoin's permitted target length starts at 6, so this is a control-flow
fixture, not a candidate mainnet block.

**S2-02 Probable-prime contracts:** 341 is a base-2 Fermat pseudoprime and is
composite by trial division. Primecoin's proof-of-work chain scoring uses
probable-primality checks; v1's Lucas/Pratt certificate predicate is stronger.
Replacing the former with the latter would be a protocol change, not an
upstream-compatible patch. No real consensus exploit is claimed.

**S2-03 Cross-check disagreement:** At tiny origin 2730, the ELL and
Fermat-only scored lengths differ on the second-kind chain. The source-derived
bounded acceptance model rejects the candidate because Primecoin explicitly
checks that both scores agree. This explains why independently porting only
one class of primality test misses a consensus condition.

**S2-04 Odd bi-twin scoring:** Primecoin constructs the bi-twin chain length
from the two Cunningham lengths, choosing the shorter chain's fraction and
accounting for one extra final prime on the longer first-kind side. The v1
`pow_lab.py` interleaves a fixed ordering of terms for toy certificates; the
score from `primecoin_reference.py` represents the source's scoring convention.

## Synthetic origin reuse

`reuse_campaign.py` processes six contexts of 128 candidates per context and
four origin-domain widths. An origin is
`2 * (1 + (SHA256d(ticket) mod (2^(bits-1)-1)))`. This forced modulo is solely
a toy device, absent from Primecoin's actual header-hash-times-multiplier
construction. The procedure counts within-context duplicates and fresh-context
hits on earlier origins separately.

| bits | possible origins | tickets | unique origins | intra-context reuse | cross-context reuse |
| --: | --: | --: | --: | --: | --: |
| 8 | 127 | 768 | 127 | 299 | 342 |
| 10 | 511 | 768 | 396 | 74 | 298 |
| 12 | 2047 | 768 | 637 | 22 | 109 |
| 14 | 8191 | 768 | 741 | 3 | 24 |

The counts partition the 768 tickets into first discoveries, same-context
repeat origins, and new-context hits on earlier origins. They are **origin
mapping collisions**, not SHA-256 collisions, timing results, or findings about
Primecoin mainnet mining economics.

## Fork-local registry experiments

`reorg_registry.py` is a separate policy emulator. It treats claims as already
arithmetically verified, and tests three **counterfactual** acceptance rules:

- `exact`: reject identical mathematical chain artifacts on one ancestry.
- `suffix`: reject a contiguous same-family subchain reused on one ancestry.
- `overlap`: reject any shared prime across claims on one ancestry, including
  across families. This can exclude substantial legitimate mathematical work.

Sibling branches may each hold the same artifact because only one ancestry is
active after the externally selected tip. Reorganization reconstructs the
active artifact set from that tip. Test scenarios show rollback and activation
of branch-specific discoveries. A naive global-first-seen exclusion would make
validation depend on observations from rejected branches and miner withholding.

The registry specifies neither proof-of-work fork choice nor chainwork. Its
claim objects are mathematical *metadata* and the harness is not a consensus
validator. A prospective chain would also need ancestor validation, proof
binding, resource budgets, chain-selection tests, adversarial propagation,
withholding, and incentive analysis before introducing any duplicate rule.

## Execute and review

```sh
python -m unittest discover -s pow-research -p 'test_*.py' -v
python pow-research/verify_evidence.py
python pow-research/verify_phase2.py
python pow-research/reuse_campaign.py
```

The stage-2 receipt pins the scripts, source-derived upstream identifiers and
canonical campaign SHA-256. Native differential testing and hardware-energy
measurements remain explicit open obligations.
