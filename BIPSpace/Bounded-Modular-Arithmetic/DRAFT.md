# BIP draft: Bounded Modular Arithmetic for Tapscript

| Field | Value |
| --- | --- |
| BIP number | Unassigned |
| Title | Bounded Modular Arithmetic for Tapscript |
| Proposed opcode | OP_MULADDMOD; byte unassigned |
| Layer | Consensus (soft fork) |
| Status | Unsubmitted research draft v0.2 |
| Date | 2026-11-12 |
| Foundation | BIP 342, tapscript 0xc0 |
| Deployment | To be determined |

## Abstract

Introduce one instruction computing `r = (a*b+c) mod m`. All operands are
unsigned byte strings of at most 32 bytes. A canonical encoding gives each
residue one representation for its modulus. The instruction shares the
existing per-input validation budget. Its first target is adjudication of
an authenticated arithmetic step in a BitVM dispute.

## Motivation and prior art

BitVM's published M31/BabyBear library reports 1,415 weight units for a
base-field multiplication.[1] This is a published library baseline, not a
new measurement or an estimated saving for this proposal. Authentication
and transaction-graph costs must be included in a complete comparison.
BitVMX's analysis also distinguishes the benefits across dispute
architectures.[2]

BIP 441 proposes restored arithmetic under tapleaf 0xc2 and relies on BIP
440's Varops budget.[3][4] It can express multiply-add followed by reduction.
A separate bounded opcode needs to demonstrate a useful advantage in
implementation scope or complete dispute cost. No such measured advantage
over BIP 441 is claimed here.

Composite operations have prior art in the withdrawn BCH proposal covering
OP_MULMOD, OP_ADDMOD and related instructions.[5] The mathematical operation
is standard. This draft explores a fixed width bound, a fused operation and
a tapscript-specific encoding and resource policy.

## Proposed normative semantics

### Activation and dispatch

Assign an available OP_SUCCESSx byte through a separate deployment decision.
The new semantics apply only to activated 0xc0 tapscript. Legacy Script and
other tapleaf versions retain their existing behavior. Prior to activation,
the byte retains BIP 342's unconditional-success behavior.[6]

After activation, remove the assigned byte from the OP_SUCCESS pre-scan and
execute it under ordinary control flow. A byte within pushed data is data.
An unexecuted branch performs no arithmetic and incurs no new charge. Other
OP_SUCCESS bytes retain their existing behavior. Malformed pushes and
ordinary stack/final-stack rules remain applicable unless another existing
OP_SUCCESS rule terminates validation.

This restricts previously accepted spends and is soft-fork compatible under
BIP 342. Scripts depending on the new restriction must be funded only after
activation. No byte allocation or activation schedule is supplied here.

### Stack interface

Top of stack is on the right:

```
... a b c m OP_MULADDMOD
... r
```

Four elements are consumed; one is produced. This is not a VERIFY opcode.
A caller must check its result or use it in a later computation.

### Encoding

Let w be the length of the modulus element.

1. Require 1 <= w <= 32.
2. Interpret all operands as unsigned little-endian integers.
3. Require the modulus's last byte to be nonzero and m >= 2.
4. Require each of a, b and c to occupy exactly w bytes.
5. Require 0 <= a,b,c < m; out-of-range residues fail Script.
6. Return r in exactly w bytes, retaining high zero bytes as needed.

The modulus range is 2 <= m <= 2^256-1. Composite and even moduli are valid.
An application using a field must independently pin its required prime.
An empty element cannot encode zero. For a four-byte modulus the zero
residue is `00000000`; the one residue is `01000000`.

These encodings are unrelated to Script's signed-magnitude numbers. Raw
residues must be compared through OP_EQUAL or OP_EQUALVERIFY before boolean
use. Byte `80` denotes residue 128 here and negative zero in Script truth
conversion. Fixed-width one can also violate MINIMALIF.[6][7] The tests
preserve both hazards. Existing numeric instructions receive no new meaning.

### Arithmetic

Compute the mathematical integer a*b+c without truncation, then reduce
modulo m. The result satisfies 0 <= r < m. Under the operand bounds,

```
a*b+c <= (m-1)^2 + (m-1) = m^2-m < 2^512.
```

Example in one-byte encodings:

```
07 0b 03 11 -> 0c
```

This is (7*11+3) mod 17 = 12. Implementations may use any algorithm that
produces exactly these semantics for every valid encoding.

### Budget and failures

For the v0.2 research profile, each executed call consumes 50 units from the
same per-input counter used by BIP 342's charged signature operations.
Initialization remains 50 plus the serialized size of the complete input
witness, including CompactSize prefixes, script, control block and any
annex. Existing signature charges continue to use that counter.[6]

Fail for stack underflow, invalid encodings, out-of-range residues or
insufficient budget. Validate operands and charge before arithmetic.
Repeated calls are each charged, including calls reusing stack values.
All existing stack-size and stack-element limits remain in force.

The Python model keeps failures atomic for testing. Consensus requires
script failure; internal mutations before abort have no observable effect.

**The 50-unit price is provisional.** Native microbenchmarks in this package
provide no full-block or cross-architecture cost calibration. A deployment
specification must freeze a reviewed price and test mixed arithmetic and
signature workloads. See [RESOURCE_ANALYSIS.md](RESOURCE_ANALYSIS.md).

## BitVM integration

The companion [integration specification](INTEGRATION.md) fixes the program,
modulus, public inputs, expected final output and funding-instance identifier
in an authenticated context. It supplies separate predicates for incorrect
inputs, malformed encodings, false arithmetic, and false output claims.

Given canonical and authenticated values, the local arithmetic predicate is

```
d != F(a,b,c;m), where F(a,b,c;m) = (a*b+c) mod m.
```

For example, a=b=5, c=0 and m=17 imply d=8. An unpinned modulus of 7 would
make the false d=4 pass. Unauthenticated operands can instead turn a correct
execution into apparent fraud. Gate indices and the claimed final result
also need binding. Tests exercise each of these conditions.

An invalid encoding causes this opcode to fail the transaction. A compiler
must provide a separate successful encoding-dispute branch or enforce
canonical values through its authenticated representation. Script cannot
catch the opcode failure. The host model records this requirement without
claiming to implement that branch on Bitcoin.

Merkle authentication in `dispute.py` runs in Python. This opcode supplies
no concatenation, Merkle verification, transaction introspection, data
availability, or authority to release funds. A production compiler needs
a separately demonstrated authentication backend and recovery graph.

The prior sibling covenant binds principal/connector outpoints; it has a
separate security obligation. BIP 446's template commitment is another
independent proposal.[8] This arithmetic instruction has no activation
dependency on either. Existing setup, garbling and proof-system assumptions
remain unless a redesigned backend separately removes them.

## Useful compositions

Horner evaluation uses h_next=F(h,x,c_i). An inverse witness u can be checked
with F(a,u,0)=1, with the appropriate field or ring assumptions. The supplied
quadratic-extension example computes a product using five fused calls in
a fixed basis. See the integration note for the equations and tests.

Elliptic-curve verification continues to require all original point and
subgroup checks, including exceptional cases. No Nova, SNARK or STARK
verifier is built into the instruction. Existing Boolean garbling receives
no automatic performance improvement.

## Resource argument and implementation

For I metered inputs, total witness size W and N charged 50-unit operations,

```
50N <= W+50I, and block weight B >= W+164I,
therefore 50N <= B-114I < B.
```

The second inequality counts the minimum 41 non-witness bytes per input
at four weight units per byte.[9] A four-million-weight block therefore
allows fewer than 80,000 such charged calls. This is a conservative upper
bound, not an achievable packing result. Input splitting cannot evade it.
The hypothetical 744,425-call verifier exceeds that profile's entire block
allowance before any other work. Optimized verifier costs remain unmeasured.

The package includes Python integer and byte-wise implementations. Its
independent C++ decoder uses bit-serial double-and-add with a 33-byte
accumulator and at most 256 rounds. GCC and Clang build that one native
algorithm with UBSan enabled. Native code is standalone, not a Core patch.

## Reproduce and evidence

```
python verify.py --benchmark
```

The complete run passes 59 tests. The original 27 cases remain, including
12,037 differential arithmetic vectors: 8,280 exhaustive small-ring cases,
2,048 seeded all-width cases, and 1,709 boundary cases. Each native build
matches all 12,037 valid vectors and rejects 293 malformed operands, plus
five malformed transport lines.

The five-register F_3 fixture exhausts 243 canonical traces. Exactly one is
valid, and the model finds a challenge for the other 242. Its general
completeness argument assumes binding commitments and available trace data.
Source hashes, compiler details and local timings are recorded in
`results/verification.json`. GitHub CI reports its status independently.

Bitcoin Core consensus integration, actual transaction execution, complete
proof verification and challenge inclusion remain outstanding. No
end-to-end fee saving or consensus DoS price has been established.

## References

[1] https://github.com/BitVM/rust-bitcoin-m31-or-babybear

[2] https://bitvmx.org/knowledge/improving-bitvmx-with-bitcoin-soft-forks

[3] https://bips.dev/441/

[4] https://bips.dev/440/

[5] https://github.com/mr-zwets/Composite-Arithmetic-Opcodes

[6] https://bips.dev/342/

[7] https://github.com/bitcoin/bitcoin/blob/master/src/script/interpreter.cpp

[8] https://bips.dev/446/

[9] https://bips.dev/141/
