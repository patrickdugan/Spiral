# Reuse the Cashu V3 recursion checkpoint

These scripts inspect the pinned A6000 settlement archive and prepare
adjacent verified proofs for the stock SP1 6.9 compose prover.
The archived run uses a zero effective controller nonce. The archive SHA-256
is `b2786320ba2abc774a8e2438db8272d0f94b409dd47008992c4b7bb4baf2ed26`.

Set `TOOLS` to this directory and `PROVER` to the ZK Rusto `nb3-prover`
crate. Set `ARCHIVE` to the downloaded checkpoint, `LEAF` to the already
verified normalized leaf, and `PROGRAM_KEY` to the independently derived
SP1 program-key receipt for the pinned Cashu V3 guest.

```bash
python3 -B "$TOOLS/test_archive.py"
python3 -B "$TOOLS/index_archive.py" "$ARCHIVE" "$LEAF" candidate-index.json
python3 -B "$TOOLS/plan_prefix.py" "$ARCHIVE" candidate-index.json audit
cargo run --release --manifest-path "$PROVER/Cargo.toml" --example audit-recursion-memos \
  -- audit "$PROGRAM_KEY" audit/entries.txt > audit/verified.jsonl
python3 -B "$TOOLS/prepare_compose.py" audit compose-input
cargo run --release --manifest-path "$PROVER/Cargo.toml" --example replay-reduction-cpu \
  -- compose-input "$PROGRAM_KEY" "$(cat compose-input/manifest-sha256.txt)" compose-out --arity-only
```

The index proposes links between public rows. The auditor verifies each
selected proof and its program key, recursion-key membership and proof nonce.
To check the entire available prefix, stage it in a separate directory and
verify the stock receipts against the exact proof bytes and connecting public
rows. The planner keeps one proof body in memory while staging the archive.

```bash
python3 -B "$TOOLS/plan_prefix.py" "$ARCHIVE" candidate-index.json full-audit --full-prefix
cargo run --release --manifest-path "$PROVER/Cargo.toml" --example audit-recursion-memos \
  -- full-audit "$PROGRAM_KEY" full-audit/entries.txt > full-audit/verified.jsonl
python3 -B "$TOOLS/verify_prefix.py" full-audit full-prefix-receipt.json
python3 -B "$TOOLS/prepare_compose.py" full-audit interior-input --start-ordinal 2 --arity 3
```

The full-prefix receipt records the original compressed archive hash, stock
verifier transcript hash, covered shard count and both endpoint commitments.
The combine step accepts two to four adjacent proofs from the verified audit.
The compose prover checks the ordered witness and emits a new proof when it
fits the local resources. The planned composition covers an execution prefix.
On the measured WSL host, the two-child witness executed successfully. The
CPU prover reached both the 2 GiB and 2.5 GiB hard limits during proving with
zero swap. The verified source reduction and leaves remain reusable.
Complete settlement still requires a stock SP1 proof with the pinned public
output and a separate Bitcoin enforcement test.

## Measure an active Core checkpoint

Give the sampler the Core run directory and the successful trace-free
execution receipt for the same ELF and public digest.

```bash
python3 -B "$TOOLS/core_progress.py" "$RUN_DIR" "$NATIVE_RECEIPT"
```

The sampler reads 756 bytes per saved shard. It checks the run's effective
nonce and counts contiguous execution timestamps from the first shard.
It reports the covered clock against the independent guest's total clock.
The count represents checkpoint metadata. Non-execution shards, proof
verification, recursive compression, wrapping and settlement each require
separate measurements.

For a resumed run, pass the current report directory with its
`progress-baseline-bytes.txt` and a prior coverage report for the same
manifest. This reads only the recent fresh shard headers and measures a
contiguous window of at least 180 seconds. Coverage requires a reference from
the executor's `clk()` in the `sp1_core_timestamp` domain. Earlier receipts
carry only `global_clk()`, the instruction counter, so their reports leave the
estimate unset. When the live frontier exceeds a same-domain reference, the
report gives the excess and leaves the percentage and estimate unset. Core
archive verification establishes the completed shard range independently.
See the [pinned SP1 executor counters](https://github.com/succinctlabs/sp1/blob/b8387fa61e1361d90ee7de49f551863418ca0f08/crates/core/executor/src/minimal/arch/x86_64/mod.rs#L201-L216).

```bash
python3 -B "$TOOLS/measure_core_window.py" "$RUN_DIR" "$RESUME_REPORT" "$PRIOR_COVERAGE"
```

Supply `--execution-receipt RECEIPT` to update the reference for a saved
window. The sampler checks the new receipt against the same ELF and public
digest. Finished attempts can use their archived `progress.jsonl` snapshot.

For capacity at archive assembly, `project_core_storage.py` reports estimates
from observed filesystem growth and from the sampled proof data extents.
With `--measure-btrfs-extents`, it reads shard files published at least two
minutes ago so compressed writeback can settle without an explicit flush.
The extent estimate covers memo data and projected archive bytes. Use the
filesystem-growth estimate to account for the other allocations observed
between the storage baseline and the sample.

## Audit saved Core shards during proving

Use `audit_core_prefix.py` with the pinned streaming verifier and independently
derived Core key. It copies only a bounded prefix to a disposable archive and
compares the memo digests and execution timestamps before running native STARK
verification. The streaming verifier must reach its incomplete-chain rejection
after checking each shard. The separate whole-archive verifier remains the gate
for the complete public transition and final committed output.

```bash
python3 -B "$TOOLS/audit_core_prefix.py" --run "$RUN_DIR" --manifest-sha256 "$RUN_SHA256" \
  --execution-receipt "$NATIVE_RECEIPT" --elf "$ELF" \
  --core-key "$CORE_KEY" --core-key-sha256 "$CORE_KEY_SHA256" --program-vk-digest "$PROGRAM_VK_DIGEST" \
  --verifier "$VERIFIER" --verifier-sha256 "$VERIFIER_SHA256" --count 512 \
  --scratch "$SCRATCH" --scratch-reserve-bytes "$SCRATCH_RESERVE_BYTES" --out "$AUDIT_RECEIPT"
```

[Pinned SP1 Core public values](https://github.com/succinctlabs/sp1/blob/b8387fa61e1361d90ee7de49f551863418ca0f08/crates/hypercube/src/air/public_values.rs) · [Pinned SP1 shard proof encoding](https://github.com/succinctlabs/sp1/blob/b8387fa61e1361d90ee7de49f551863418ca0f08/crates/hypercube/src/verifier/proof.rs)

## Continue the live Windows Core checkpoint

From the campaign workspace, pass the active compressed attempt and its
continuation report to `watch-cashu-raw-continuation.ps1`. The watcher uses
the attempt's published Windows supervisor and verifier handles. After a
clean guard stop it waits for three healthy host samples before calling
the workspace's checkpoint resume launcher. A Linux Core progress timeout
can trigger one automatic retry per watcher invocation. Archive-write
stalls, OOM kills and unknown exits leave a terminal receipt for inspection.
The resume launcher checks the pinned run manifest, exclusive worker lock
and absence of an assembled proof before creating another attempt.

Run `test-core-continuation.ps1` to exercise the exit classification.
