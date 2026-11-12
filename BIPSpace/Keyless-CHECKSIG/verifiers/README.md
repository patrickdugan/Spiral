# Keyless CHECKSIG verifier workbench

Status: **research, non-consensus prototypes**. The unallocated TXCOMMIT
key type, BIP347 CAT, and BIP360 P2MR are required for the Script
experiments. These outputs must not be funded on the Bitcoin network.

## Verified implementations

| Component | Source | Tested result | Boundary |
| --- | --- | --- | --- |
| Transparent arithmetic trace in Script | [stark_trace.py](stark_trace.py) | Compiles 296 bytes of Tapscript-style code checking four F17 trace rows with transition s(i+1)=(s(i)+2) mod 17, hashes the trace into an OP_RETURN output and ties both outputs to actual BIP341 TapSighash with TXCOMMIT. Same simulated reserve permits two valid recipient/trace pairs. | **Full-trace AIR check, not scalable STARK, FRI or ZK**. Range excludes a zero-valued row. Runs in a subset Script VM, not Core. |
| Pallas IPA | [nova_ipa.py](nova_ipa.py) | A real standalone Bulletproof-style inner-product prover/verifier over Pallas, with a SHA256 transcript binding the public commitment, claimed inner product and 32-byte transaction context. Proofs for 2, 4 and 8 entries verify and mutations fail. | **An IPA primitive, not a complete Nova SNARK**. The public try-and-increment generator mapping and transcript are research-only, and differ from Nova 0.76. Not compiled into Script. |
| Nova public folding | [nova_fold.py](nova_fold.py) | Pallas relaxed-instance folding equations with transcript-bound challenge. Mutated commitments and states fail. | Cross-term correctness, R1CS, Pedersen witness binding and Nova's actual transcript are unimplemented. |
| Native compressed Nova 0.76 | [nova_native_verifier.rs](nova_native_verifier.rs), [runner](run_nova_native.sh) | Rust adapter calls the pinned existing full Nova Pallas/Vesta Spartan+IPA verification library and checks an independently pinned public-statement SHA256. | Native only, no Bitcoin consensus authorization. The runner was not executed in this session. The M12 header-chain statement does not authorize transaction outputs. |

The [BIPSpace verifier CI](https://github.com/patrickdugan/Spiral/actions/runs/43123997055)
passed **69 tests**, plus two valid 296-byte Script demonstrations. The
pre-existing [Keyless CHECKSIG CI](https://github.com/patrickdugan/Spiral/actions/runs/43047179384)
passed 33 further tests, including seven official BIP341 hash vectors.

~~~bash
python -m unittest discover -s BIPSpace/Keyless-CHECKSIG/verifiers -p 'test_*.py' -v
python BIPSpace/Keyless-CHECKSIG/verifiers/stark_trace.py
python BIPSpace/Keyless-CHECKSIG/verifiers/nova_ipa.py
python BIPSpace/Keyless-CHECKSIG/verifiers/nova_fold.py
~~~

The Bitcoin-style serialized example uses **1,141 weight units (286 vbytes)** for the left-hand Merkle branch and **1,142 WU** for the right-hand branch. These are serialization-model calculations, not Bitcoin Core acceptance or standardness results.

The research Script VM interprets only the fixture's opcodes. It omits
complete Bitcoin validation, mempool policy, UTXO checks and activation
rules. Every amount in these examples is simulated.

## Real compressed Nova SNARK adapter

The Rust adapter is intended to be installed as a new binary inside the
existing Nova M12 native crate of patrickdugan/zk-rusto-no-bitcoino. It
calls Nova 0.76.0's actual CompressedSNARK verifier under the pinned
Pallas/Vesta verifier key, then authenticates network, step count,
checkpoint, terminal state, VK digest and proof digest in the verified
1,164-byte statement.

The runner clones a fixed upstream commit
7893ff279dd01e581f14e3e2cbaf99c823173bae, injects the small CLI,
and runs the real testnet4 k=1 compressed SNARK fixture with its pinned
expected SHA256.

~~~bash
bash BIPSpace/Keyless-CHECKSIG/verifiers/run_nova_native.sh --fixture-k1
~~~

This is **opt-in heavy Rust compilation**, requiring Cargo, git, network
access and enough memory/disk. It is intentionally excluded from light
CI. For an existing Nova bundle and key:

~~~bash
bash BIPSpace/Keyless-CHECKSIG/verifiers/run_nova_native.sh \
    NHC1_OR_NHT4.bundle verifier_key.bin EXPECTED_PUBLIC_STATEMENT_SHA256
~~~

M12's k=1 fixture has a ~12 KB bundle and a 42.27 MB compressed
verifier key. M17 previously measured an 11,480-byte compressed
Spartan+IPA proof for a Bitcoin Script instance. These numbers are from
the upstream repositories, not new benchmarks here.

The verified M12 statement covers Bitcoin headers. To make a reserve
spend keyless and proof-authorized, a new application circuit must
commit to the exact TXCOMMIT digest, recipient, amount and successor
state as part of its proved public relation.

## Real transparent STARK feasibility

Two upstream implementations provide actual STARK verifiers:

- [Bitcoin Wildlife Sanctuary Circle STARK](https://github.com/Bitcoin-Wildlife-Sanctuary/bitcoin-circle-stark)
  includes M31/QM31 arithmetic, FRI, Fiat-Shamir and CAT/SHA256 Merkle
  verification primitives.
- [GOATNetwork WHIR in Bitcoin Script](https://github.com/GOATNetwork/bitcoin-stark-verifier)
  executes a real Plonky3 WHIR proof in a Bitcoin Script test and derives
  its queries and closing constraints from the transcript.

The GOATNetwork 2^20 / 20-query configuration reports 2,162 Poseidon2
permutations. At 572,228 script bytes per permutation, the hash work
alone is **1,237,156,936 bytes, or about 309 maximum-weight blocks**.
The current no-CAT form is not a deployable one-transaction L1 verifier.
A CAT/SHA256 redesign may change the costs substantially and needs
its own benchmarks.

The real M13 wrapped SP1 proof is ~1.1 MB, but its verifier also does
33,626 BLAKE3 compressions and 744,425 KoalaBear multiplications
under the earlier measurement. Proof size is only one part of the
resource budget.

A full STARK Script milestone requires: a real proof generated by
Plonky3 or Stwo, an independent native verification baseline, a
matching Script verifier whose Fiat-Shamir queries cannot be chosen
by the prover, the correct arithmetic and openings, and a checked
public TXCOMMIT digest extracted from the **proved** relation. Exact
total witness weight must fit one block for the L1 settlement design.

Our four-row AIR example opens the entire trace. It supplies an
executable Script/covenant integration regression test while the
full transparent verifier is developed.

## Direct Nova-on-Script feasibility

The direct version would compile the Pallas/Vesta curves, field
operations, Nova folding transcript and Spartan IPA verifier into
Script. The Python group/fold kernels describe some required equations
and have mutation tests, but a complete on-chain verifier requires
255-bit modular arithmetic, group operations and R1CS/PCS checks.
The existing M12 verifier already provides a correct native oracle
for a real compressed proof.

A Nova proof has no trusted-setup ceremony when using transparent
Pedersen/IPA commitments. It still relies on discrete-log hardness,
so this is a different security model from a hash-based STARK.

## Next engineering gates

1. Implement TXCOMMIT as a Bitcoin Core regtest-only prototype.
   Confirm consensus-mode failure semantics and existing BIP341 vectors.
2. Pin and run a real Plonky3/Stwo verifier in a Bitcoin Script
   interpreter, then append the Script TXCOMMIT binding. Record exact
   code/witness weight and adversarial late-failure cost.
3. Execute the pinned native Nova runner on its real M12 fixture.
   Replace the illustrative IPA and folding transcripts with the actual
   Nova serialized proof and challenge schedule.
4. Prove a payout relation that authenticates the payer, destination,
   amount, and replay-resistant successor state and exposes the
   precise spending transaction commitment.
5. Evaluate whether the complete Script witness and verifier fit a
   4,000,000-weight-unit block. If they do not, a multi-transaction
   challenge protocol remains the realistic design.

## Related sources

- [BIP341](https://bips.dev/341/) and [BIP342](https://bips.dev/342/)
- [BIP347](https://bips.dev/347/) and [BIP360](https://bips.dev/360/)
- [Microsoft Nova](https://github.com/microsoft/Nova)
- [Upstream M12 native Nova](https://github.com/patrickdugan/zk-rusto-no-bitcoino/tree/main/integrations/bitvm3-nova/m12/native)
- [Upstream M13 BLAKE3 SP1](https://github.com/patrickdugan/garbled-snark-verifier/tree/main/nova-bitvm3/m13/verify)
- [Upstream M17 Script in Nova](https://github.com/patrickdugan/garbled-snark-verifier/tree/main/nova-bitvm3/m17)
