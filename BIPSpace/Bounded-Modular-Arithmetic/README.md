# Bounded Modular Arithmetic for Tapscript

**OP_MULADDMOD** computes `(a*b+c) mod m` on canonical unsigned operands of
at most 32 bytes. This is an unsubmitted soft-fork research draft, v0.2.
Its BIP number, opcode byte and deployment mechanism remain unassigned.
The proposed 50-unit charge still needs consensus-level benchmarking.

Read the [draft](DRAFT.md), [BitVM integration model](INTEGRATION.md), and
[resource analysis](RESOURCE_ANALYSIS.md). The complete original Python
arithmetic model and its 27 tests are included here.

## Reproduce

Python 3.10+ and both GCC and Clang with C++17 support are required for the
full verification run. No Python packages or blockchain connection are used.

```
cd BIPSpace/Bounded-Modular-Arithmetic
python verify.py --benchmark
```

The runner writes `results/tests.txt` and `results/verification.json`.
A normal `python -m unittest discover -s . -p 'test_*.py' -v` also works;
its native suite skips if either compiler is unavailable. `verify.py`
requires both and treats any skipped test as failure.

## Recorded results

59 tests passed, with no failures, errors or skips. The original Python
backends agree on 12,037 vectors. Each native compiler build independently
matches those vectors and rejects 293 malformed inputs. The two builds use
GCC 14.2 and Clang 17 with undefined-behavior sanitization enabled.

The authenticated-trace model enumerates 243 five-register traces over F_3.
Exactly one is valid; all 242 invalid traces have an accepted challenge.
It separately tests public-input substitution, false output claims,
noncanonical encodings, cross-instance replay and changed source indices.

Every source hash used for these results is in the verification receipt.
Native benchmark timings are local measurements. GitHub CI has its own run
status and should not be inferred from the local receipt.

## Contents and scope

| File | Role |
| --- | --- |
| `muladdmod.py`, `test_muladdmod.py` | Original mathematical oracle and byte-wise reference, with regression tests. |
| `native/muladdmod.cpp`, `test_native.py` | Independent decoder and bit-serial arithmetic; compiler and sanitizer checks. |
| `dispute.py`, `test_dispute.py` | Host-side authenticated register traces and four challenge predicates. |
| `metering.py`, `test_metering.py` | Witness-size accounting and the input-splitting bound. |
| `verify.py`, `results/` | Reproduction runner, source hashes, logs and measured receipts. |

Bitcoin Core integration is outstanding. The host Merkle checks need a
separately demonstrated Script authentication backend. Encoding violations
need a successful challenge branch of their own because an opcode failure
aborts Script. Fee management, data availability and the transaction graph
remain external obligations.

This work adds no trusted setup. It also leaves existing proof-system and
garbling setup assumptions in place. The arithmetic-aware dispute compiler
is a research target; no deployed verifier or complete bridge is delivered.
