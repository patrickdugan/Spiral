# PoW Research Lab

**General proof-of-work research. Satirical nickname: Olde Coin Pump.**

The coin joke stays in this paragraph. The deliverable is an offline experiment
harness for checking mathematical witnesses and measuring bounded search. Scope
excludes token issuance, trading, wallets, RPC and network deployment. Placement
in this repository carries no assertion of Spiral/Block endorsement or grant
allocation. The capital-accounting paper and its models are unchanged.

## Run

Python 3.10+ and its standard library are sufficient. From the repository root:

```sh
python -m unittest discover -s pow-research -p 'test_*.py' -v
python pow-research/pow_lab.py --seeds 8 --budget 4096 --out pow-research/results/baseline.json
python pow-research/verify_evidence.py
```

The default campaign has 48 instances. Reproducible operation counters and proof
digests go into JSON. The retained receipt is `evidence/baseline.json`; the full
report can be regenerated. `verify_evidence.py` checks source hashes and compares
the canonical report digest against that receipt. Timing and electricity require
separate measurement; the report leaves energy and economic-security fields null.

## Implemented puzzles

| Family | Search and witness | Bound / interpretation |
| --- | --- | --- |
| Hashcash | Double SHA-256 below a target; nonce witness | 4..16 target bits; synthetic header format |
| Cunningham I | Terms `O*2^i-1`; prime certificates | 2..6 individual primes; even origin |
| Cunningham II | Terms `O*2^i+1`; prime certificates | Same limits |
| Bi-twin | Interleave `O*2^i-1`, `O*2^i+1` | Length counts individual primes |
| SAT | Exhaustively search assignments to a fixed, unplanted 3-CNF | 3..16 variables, 1..128 clauses; UNSAT retained |
| ECDLP | Recover a scalar for a context-derived point | Curve `y^2=x^3+7 mod 211`, order 199 |

Candidate search, instance generation, certificate generation and verification
have separate operation counters. A modular exponentiation and a SHA-256 call
have different costs. The code does not add them into an implied work currency.
Context-digest serialization/hashing is excluded from the counters and marked
explicitly in the report. The scan budget counts candidates, which is a different
unit in each family. Comparing equal budgets cannot establish equal difficulty.

Prime witnesses contain full-factorization Lucas/Pratt certificates, checked
recursively with bounded integers. A separate trial-division search and an
independent sieve supply finite test oracles. The wire format rejects extra
fields and duplicate keys; numeric bounds exclude booleans. Certificate trees,
wire bytes and search budgets have hard caps.

## What “Cunningham collisions” means here

The tests separate exact chain duplication from shared primes in suffixes.
Alternative valid primality certificates give the same mathematical artifact ID.
Literal witness replay against a changed context fails. A retained counterexample
then searches a fresh ticket that maps to the same small origin and successfully
reuses the chain and its certificates. That is deliberate evidence of work reuse
in this toy construction.

The artifact registry key excludes certificates and context. It identifies an
exact ordered chain within one family. Overlap is reported separately; a family
change and a suffix remain distinct artifacts. Global exclusion, withholding,
reorg rollback and maximal-chain normalization remain research tasks. There is no
historical deduplication rule in the verifier.

**This harness is not Primecoin consensus code.** Its tiny hash-to-origin domain
permits table precomputation. Production Primecoin binds origin divisibility to a
header hash and uses fractional difficulty with probable-prime tests [S2]. A claim
that this lab fixes a deployed Primecoin vulnerability would exceed the evidence.

## Baseline receipt

The eight-seed campaign uses a 4,096-candidate budget for every instance:

| Family | Solved / 8 | Other outcomes | Total candidates tested |
| --- | ---: | --- | ---: |
| Hashcash | 7 | 1 budget exhaustion | 10,211 |
| Cunningham I | 8 | None | 590 |
| Cunningham II | 8 | None | 541 |
| Bi-twin | 8 | None | 142 |
| SAT | 6 | 2 exhaustively UNSAT | 3,934 |
| Toy ECDLP | 8 | None | 995 |

All 45 emitted witnesses pass the independent verifier. These are deterministic
small-instance fixtures. They establish executable behavior and expose failure
modes; inference about production mining requires a separate sampling protocol.
The baseline is protected by 32 named tests, including exhaustive enumeration of
the 199-point toy group and a sieve comparison over integers 0..4095.

See [RESEARCH.md](RESEARCH.md) for assumptions, the certificate soundness argument
and the next experiments. Python's integer arithmetic and SHA-256 implementation
remain inside the trusted computing base. Machine-checked formal proofs are future
work.

## Sources

[S1] Satoshi Nakamoto, *Bitcoin: A Peer-to-Peer Electronic Cash System*, section 4:
https://bitcoin.org/bitcoin.pdf

[S2] Sunny King, *Primecoin: Cryptocurrency with Prime Number Proof-of-Work*,
July 7, 2013, pages 2..4: https://primecoin.io/primecoin-paper.pdf

[S3] Vaughan R. Pratt, *Every Prime Has a Succinct Certificate*, SIAM Journal on
Computing 4(3), 1975: https://doi.org/10.1137/0204018

[S4] Russell Impagliazzo and Ramamohan Paturi, *On the Complexity of k-SAT*,
JCSS 62(2), 2001: https://doi.org/10.1006/jcss.2000.1727

[S5] RFC 9380, *Hashing to Elliptic Curves*, 2023:
https://www.rfc-editor.org/rfc/rfc9380.html

Sources checked October 29, 2026. S4 supplies historical complexity terminology;
this prototype makes no claim about the current truth of ETH or a claimed new
ECDLP algorithm. The originating social-media claims remain unverified here.
