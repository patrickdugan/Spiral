# Resource bound and native measurements

## Proposed charge

The research profile charges 50 units for an executed OP_MULADDMOD using the
same per-input counter that BIP 342 uses for charged signature operations.
Its starting balance is 50 plus the serialized size of that input's complete
witness, including CompactSize fields, script, control block and any annex.[1]
This price is provisional. Nothing here establishes production DoS safety.

`metering.py` calculates the complete witness serialization size. Its tests
include 252/253 CompactSize boundaries and the witness-item-count prefix.
Caller-supplied accounting in a host model cannot replace consensus-derived
witness length in an actual interpreter.

## An input-splitting bound

Let I be the number of spending inputs whose budgets pay for these calls,
W_i their serialized witness lengths, and N the total number of executed
50-unit operations across them, including charged signature checks. Then

```
50 N <= sum(W_i) + 50 I.
```

Each input has at least 41 non-witness bytes: a 36-byte outpoint, one byte
for even an empty scriptSig length, and a four-byte sequence. At four weight
units per non-witness byte, the block weight B therefore obeys [2]

```
B >= sum(W_i) + 164 I.
```

Combining these inequalities gives

```
50 N <= B - 114 I < B,  for I >= 1.
```

Thus a four-million-weight block contains fewer than 80,000 such charged
operations under this proposed price. For I=1 the conservative integer bound
is 79,997. Uncounted outputs, headers, other inputs and framing can only lower
that ceiling. It is an upper bound, not an achievable packing result.
Splitting a witness among extra inputs cannot evade the accounting through
the 50-unit initial bonus.

The earlier hypothetical 744,425-operation verifier needs 37,221,250 units.
Executing every one of those operations inside one block exceeds this
research profile's arithmetic allowance before considering other work.
This motivates step-local challenges. The calculation does not assert that
744,425 is a minimum for any optimized verifier.

## Independent native arithmetic

`native/muladdmod.cpp` independently validates the encodings and computes
multiply-add by binary double-and-add. It uses a 33-byte accumulator and no
arbitrary-precision library. For w-byte operands it performs 8w rounds, each
with at most two modular additions. Each addition sums operands below m and
requires at most one subtraction of m.

The supplied Python byte-wise implementation instead builds a full product
and performs binary long reduction. Python integer arithmetic serves as the
mathematical oracle. GCC and Clang compile the single C++ implementation;
they are two builds, not two independently written native algorithms.

The verification runner checks all 12,037 valid arithmetic vectors against
each native build. Each independently rejects 293 malformed operand vectors
and five malformed transport lines. Both builds enable UBSan with recovery
disabled. The native program's CLI and allocation behavior are research
scaffolding outside the proposed consensus semantics.

## Measured local microbenchmark

The committed `results/verification.json` records five samples of 4,000 calls
for each width. The measurement includes the native decoder and result
allocation. Each sample changes one operand while retaining a dense modulus
and multiplier. Reported medians from this run are:

| Operand width | Median time per call |
| --- | ---: |
| 1 byte | 0.179 microseconds |
| 4 bytes | 1.016 microseconds |
| 8 bytes | 2.295 microseconds |
| 16 bytes | 6.359 microseconds |
| 32 bytes | 21.921 microseconds |

Compiler: GCC 14.2, C++17, -O2 -DNDEBUG. The benchmark binary omits sanitizers;
the differential-test binaries include them. This is a shared-container,
single-machine sample of one operand family. It neither establishes a
worst-case runtime nor justifies the 50-unit price. Checksums are recorded
to keep the arithmetic results observable to the compiler.

Before deployment, compare complete blocks against a Bitcoin Core baseline
on several CPU families, and examine widths and moduli chosen adversarially.
BIP 440's published methodology is relevant to that review.[3]

## Comparison with restored arithmetic

BIP 441 expresses broader arithmetic under tapleaf 0xc2 and relies on BIP
440's transaction-wide Varops model.[3][4] This draft keeps 0xc0 and a fixed
32-byte bound. A comparison must include conversion between this proposal's
fixed-width residues and BIP 441's normalized unsigned outputs, along with
all authentication costs. No measured advantage over BIP 441 is claimed.

[1] https://bips.dev/342/

[2] https://bips.dev/141/

[3] https://bips.dev/440/

[4] https://bips.dev/441/
