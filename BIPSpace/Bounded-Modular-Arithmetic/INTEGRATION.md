# Arithmetic-aware BitVM disputes

Research revision v0.2, 2026-11-12. The executable model is `dispute.py`.
Its authentication runs on the host. It provides no Bitcoin Script Merkle
verifier, transaction graph, proof-of-availability protocol or fund release.

## Committed computation

Use a straight-line register program. Public inputs occupy registers
`0..s-1`. Gate k writes register `s+k`, with three source indices smaller
than `s+k`:

```
z[s+k] = (z[a_k] * z[b_k] + z[c_k]) mod m
```

The verifier fixes the program and modulus. It also pins the public inputs,
expected final result, and a 32-byte instance identifier supplied by the
funding/claim protocol. `Program.context` hashes their unambiguous encoding.
The identifier has meaning only when that outer protocol binds it to the
actual funded claim.

Trace leaves commit to the context, register index, value length and bytes.
Leaf, internal-node, and padding hashes use separate domain tags. Padding
extends to a power of two with indexed padding hashes. The authenticated
length remains the actual register count. An opening must have exactly the
expected depth and cannot address padding. Four openings expose a gate's
operands and result; the verifier obtains their required indices from the
fixed program.

## Four independently specified challenge predicates

| Predicate | Authenticated violation |
| --- | --- |
| Input | A public input register differs from the fixed statement. |
| Encoding | A register has the wrong width or represents a value >= m. |
| Arithmetic | Four canonical register openings violate their fixed gate. |
| Output | The last register differs from the expected public result. |

Checking arithmetic alone misses a fully consistent execution over substituted
inputs. It also misses a correct trace attached to a false public output.
The tests retain examples of both errors.

### Conditional local soundness and completeness

Assume the hash commitment binds each register to one byte string, and that
the surrounding claim authenticates the fixed context. An accepted predicate
then proves a violation of that committed claim.

For completeness, assume every committed leaf is available and within the
model's 520-byte leaf bound. If all encoding predicates are false, every
register denotes one canonical residue. If all input predicates are false,
the initial registers equal the required inputs. Induction over gate order
then shows that false arithmetic predicates force every later register to
equal the unique program execution. Finally, a false output predicate forces
its last value to equal the required result.

Contrapositively, an available, invalid committed claim has an input,
encoding, arithmetic or output witness. This statement assumes cryptographic
binding; the finite test suite cannot establish SHA256 collision resistance.
It says nothing about obtaining missing data or getting a challenge mined.

The small exhaustive fixture enumerates all 3^5 = 243 canonical traces for a
five-register program over F_3. Exactly one trace is valid. The checker finds
a challenge for each of the other 242. Larger tests modify every register of
a two-gate F_17 program and exercise replay and substitution attacks.

## Script compilation boundary

For already authenticated, canonical operands, the arithmetic predicate is:

```
<a> <b> <c> <pinned m> OP_MULADDMOD <authenticated d> OP_EQUAL OP_NOT
```

`OP_EQUAL` emits a canonical Script boolean before `OP_NOT` consumes it.
A raw modular residue must never be treated as a Script number or boolean.
For example, the residue 128 is byte `80`; Bitcoin Script interprets that
byte as negative zero for truth testing. A two-byte residue one (`0100`)
also fails tapscript MINIMALIF. These hazards have dedicated tests.[1][2]

A malformed operand makes OP_MULADDMOD fail the script. Failure cannot be
caught and converted into a successful fraud spend. The compiler must supply
an independently executable encoding-dispute branch, or enforce canonical
encoding through its authenticated representation. The host's
`encoding_fraud` predicate records this obligation; it does not implement
that branch in Script. Its cost belongs in the eventual transaction estimate.

Python Merkle authentication in this model needs a separately demonstrated
Script backend. OP_MULADDMOD supplies neither concatenation nor a Merkle
instruction. Existing BitVM commitment techniques are another possible
backend, with their own setup and size costs. No dependency is silently
activated by this proposal.

## Useful compositions

Write F(a,b,c)=(ab+c) mod m. Horner evaluation advances h with F(h,x,c_i),
using one fused call per coefficient under the demonstrated initialization.
An inverse witness u is accepted by checking F(a,u,0)=1; composite rings
require a unit, and zero divisors may have no inverse.

For a fixed quadratic basis u^2=nu and x=a+bu, y=c+du:

```
t = F(b,d,0)
v = F(a,c,0)
real = F(nu,t,v)
q = F(a,d,0)
imag = F(b,c,q)
```

Five fused calls compute the product. Over a prime field, nu must be a
nonsquare for this quotient to be a field. The test uses m=17, nu=3. Choosing
a basis or modulus remains part of the fixed program. This cost excludes
stack movement and authentication. It is not an end-to-end savings estimate.

## Application to Spiral

The first target is one field-arithmetic fragment from the existing
`../Keyless-CHECKSIG/verifiers/` workbench. Keep the exact public statement
and recovery semantics fixed while replacing only the arithmetic backend.
Record whole transaction weight, including value authentication and any
encoding-dispute branches. Measure witness availability and full challenge
latency separately.

Pairing checks, curve membership, subgroup checks and exceptional point
cases remain necessary wherever the original verifier requires them.
Implementing multiply-add alone does not validate Nova, a STARK, or a bridge
claim. The existing Boolean garbling compiler receives no automatic speedup.

The prior sibling covenant addresses the principal/connector outpoints.
The arithmetic opcode has no authority over those coins. A complete design
must still prove the root funding constraint and every recovery path,
including Taproot key-path and alternate-leaf bypass checks.

## Bitcoin Core acceptance gates

1. Choose an opcode only after coordination. In activated 0xc0 tapscript,
   remove that byte from the OP_SUCCESS pre-scan and dispatch its new meaning.
   Bytes inside pushed data remain data. A remaining OP_SUCCESS opcode keeps
   its existing behavior. The new arithmetic executes only on an active
   control-flow path; unexecuted branches incur no arithmetic charge.
2. Check four operands, canonical encodings, and the shared budget before
   arithmetic. Retain all ordinary stack limits and final-stack checks.
   Legacy Script and other leaf versions keep their existing semantics.
3. Import the valid and malformed vectors into interpreter tests. Exercise
   mixed CHECKSIG/arithmetic scripts, exact budget exhaustion, malformed
   pushes, branches, MINIMALIF, and both activation states.
4. Benchmark adversarial full blocks on multiple architectures. Include
   even/composite moduli, alternating widths and moduli, and malformed paths.
   Freeze a resource price only after that work. Run differential fuzzing.

These gates remain open. The C++ file is a standalone arithmetic program.

## Sources

[1] BIP 342, tapscript rules and MINIMALIF: https://bips.dev/342/

[2] Bitcoin Core, CastToBool: https://github.com/bitcoin/bitcoin/blob/master/src/script/interpreter.cpp
