# Research contract and open obligations

## The experiment

An expected challenge C binds the protocol version, puzzle family, parent,
payload digest, epoch, beacon and all difficulty parameters. A verifier receives
C from its caller. The witness cannot select a cheaper family or redefine those
parameters. The synthetic beacon is a deterministic test fixture; a deployed
beacon would need a separate unpredictability and bias analysis.

Hashcash seeks `SHA256d(domain || id(C) || nonce) < 2^(256-bits)`.
Under an independent uniform-output model, success per fresh input is `2^-bits`.
This is target/preimage-style search. A hash collision is a different relation.

Prime search maps the same ticket into a deliberately small even origin space.
SAT derives its formula solely from C and fixes the proof nonce to zero. The
elliptic-curve target comes from a small try-and-increment map on the toy curve;
its distribution is biased and it does not implement RFC 9380. The target's
scalar is discovered by exhaustive search. The code never accepts a miner-chosen
curve, base point or target public key.

Worst-case running-time statements address the hardest instances. A mining
protocol needs a sampler and a cost distribution under its actual adversarial
choices. Relevant questions include cheap instances, unsatisfiable instances,
preprocessing, grinding and privately held algorithms. A reduction to SAT needs
its parameter expansion accounted for. Large constants in an upper bound supply
no lower bound on the cheapest miner's work.

## Certificate soundness argument

The base certificate proves 2. For n > 2, the verifier checks the complete
factorization `n-1 = product(q_i^e_i)` using recursively certified distinct primes,
checks `a^(n-1) = 1 mod n`, and requires
`gcd(a^((n-1)/q_i)-1, n) = 1` for every q_i.

For any prime r dividing n, let d be the multiplicative order of a modulo r.
The first modular equality implies `d | n-1`. Each gcd check forces the full
q_i-adic exponent of n-1 to divide d. Therefore `d = n-1`. Since `d | r-1`,
we have `r >= n`; as r divides n, `r = n` and n is prime. Recursive certificates
strictly decrease n, so induction reaches the base case. Bounds keep execution
finite and may reject otherwise valid oversized certificates.

This is a mathematical argument for the predicate. Correspondence between the
Python implementation and a formal specification still needs a checked proof.
Prime certificates certify primality. Search hardness needs independent evidence.

## Retained counterexamples

| ID | Executable witness | Interpretation |
| --- | --- | --- |
| C01 | 341 passes a base-2 Fermat test and fails exact primality | A probable-prime predicate has a different contract; this alone establishes no Primecoin exploit |
| C02 | `[5,11,23,47]` overlaps `[11,23,47]` | Exact deduplication leaves suffix work overlap |
| C03 | Two valid witnesses for prime 5 | Certificate bytes can differ for the same mathematical result |
| C04 | Distinct tickets produce the same tiny origin | Canonical serialization leaves mathematical reuse possible |
| C05 | A fresh context hits an already certified origin | Literal anti-replay checks alone leave preprocessing/reuse opportunities |
| C06 | Two baseline 3-CNF instances are UNSAT after all 1,024 assignments | Exhausting all assignments yields no accepting witness in this SAT-witness lane |
| C07 | A private 10x shortcut with initial share 0.1 gives effective share 10/19 | Fixed-input relative throughput can cross a majority under the stated model |

C07 uses `alpha*s / (1-alpha+alpha*s)` for fixed resource allocations and a
uniform multiplicative speedup. Retargeting can restore an aggregate arrival
rate while this relative advantage persists in that simplified model. Market
entry, heterogeneous puzzle speedups and capital expenditure are outside it.

## Measurement contract

Every result retains its challenge and seed, candidate budget, stopping reason,
proof digest and byte count. Reported operation categories are deliberately
unpriced. Certificate generation includes repeated primality checks; generation
cost cannot be hidden inside a verification-only benchmark. Null energy and
monetary fields mean unmeasured quantities. Historic mining expenditure, current
attack cost and the cost of a different mathematical operation require separate
units and models. A claim about a larger thermocap needs those measurements.

## Next experiments

1. Pin and build an upstream Primecoin revision. Replay accepted/rejected
   fixtures through its real verifier and record header bounds, fractional
   difficulty and prime-chain normalization. Keep upstream behavior separate
   from this experimental verifier.
2. Measure precomputed-chain reuse across origin-space sizes and held-out
   challenges. Compare exact artifact deduplication with suffix/overlap policies,
   including memory growth and rollback after a synthetic reorg.
3. Add solver-vs-solver lanes with preregistered distributions and censored
   time-to-solution tails. Preserve unsatisfiable SAT cases. Any planted-SAT lane
   must state who knows the witness and quantify easy-instance selection.
4. Compare primality-certificate cost with larger bounded candidates; add real
   hardware measurements before energy claims. A toy curve remains adequate for
   interface tests; realistic ECDLP experiments require separately audited
   sampling and an explicitly bounded benchmark plan.

Existing `paper/`, `model/`, `audit/` and imported harnesses stay outside this
change. The path-filtered CI runs only this directory's tests and receipt replay.
