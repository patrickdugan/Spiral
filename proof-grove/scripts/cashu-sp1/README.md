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

For the live raw settlement run, add `--out "$RESUME_REPORT/execution-clock-window.json"`
to publish the receipt-backed measurement to Neon. Refresh the sample to keep
the Core execution projection visible. It expires after 30 minutes and covers
the measured execution clock up to the start of Core archive assembly.

For capacity at archive assembly, `project_core_storage.py` reports estimates
from observed filesystem growth and from the sampled proof data extents.
With `--measure-btrfs-extents`, it reads shard files published at least two
minutes ago so compressed writeback can settle without an explicit flush.
The extent estimate covers memo data and projected archive bytes. Use the
filesystem-growth estimate to account for the other allocations observed
between the storage baseline and the sample. The archive estimate sizes saved
shards from the sampled mix and sizes remaining execution work from execution
shards. The sample must contain at least two contiguous execution intervals.
The `same_sample_mix` scenario also projects future non-execution work at
the sampled proportions. These proportions can vary as proving advances.
Recursive artifacts require additional space.

The raw recursion launcher budgets group storage using the verified shard
index. It checks the Btrfs free space together with the Windows free space
behind the virtual disk. Allocation on E: preserves the 8 GiB host reserve and
the 2 GiB filesystem reserve. The D:-backed ext4 fallback preserves 16 GiB on
D: plus the 16.5 GiB M13 spill image and 8 MiB of VHDX metadata. The placement
receipt pins the selected site to the archive index. Resuming uses the same
site and rechecks its reserves.

The raw archive runner can try the CPU-calibrated CUDA normalizer from
`outputs/cashu-core-cuda-normalizer-linked-batch-stock-setup`. It reads
`cpu-calibrated.sha256` as the executable pin. Before using the candidate for
any group, it gives the first unfinished group's indexed shard one bounded
CUDA attempt and independently verifies the leaf with the stock CPU checker.
The runner logs the measured check or the fallback to its installed worker.

The raw M14 release uses raw scratch when both outputs fit. Its fallback
writes the original fanout format through the Windows WSL share into the
pinned zstd-compressed Btrfs checkpoint volume. Ciphertexts and labels stay
on a Windows drive. Placement budgets the fanout against both Btrfs free
space and Windows E: backing space. The process guard rechecks both reserves.
The saved placement fixes the backend and paths for retry.

The Windows NTFS control reserved the logical size of a freshly compressed
file in addition to its allocated extents. New M14 attempts select Btrfs for
compressed scratch. Saved NTFS packages remain readable.

The raw M13 wrap uses a dedicated 16.5 GiB ext4 spill image on D:. The
launcher prepares a regular image before attaching it to WSL and pins the
mounted filesystem UUID. The wrap worker checks that UUID and the 16 GiB
allocator capacity. The launcher waits for the wrap worker to exit before
unmounting, detaching and exclusively opening the disposable image to reclaim
its backing capacity. M14 measures D: again before choosing its tape location.

## Audit saved Core shards during proving

Use `audit_core_prefix.py` with the pinned streaming verifier and independently
derived Core key. It copies only a bounded prefix to a disposable archive and
compares the memo digests and execution timestamps before running native STARK
verification. The streaming verifier must reach its incomplete-chain rejection
after checking each shard. The separate whole-archive verifier remains the gate
for the complete public transition and final committed output.

Use `--after-offset` with the resumed worker's saved journal offset to audit
the latest fresh completions from that attempt. This mode includes execution
and non-execution shards. It records the sampled digests and checks that a
changed public word fails the native shard check on a disposable copy.

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

The compressed raw launcher prefers the existing prover build on the Windows
SSD when it is executable in WSL. The same binary digest is checked for the
SSD and WSL-installed copies. The run directory and archive stay on the
separately mounted checkpoint volume. The resume attempt records its actual
binary path in `input-pins.log` and retains the launcher it ran.

After archive publication, `verify_core_settlement.sh` holds the Core worker
lock while it checks the staged archive. If the raw parallel verifier times
out after 300 seconds without output, the runner retains that attempt's logs
and tries the same pinned verifier in serial mode once. The retry requires
the same archive identity, zero OOM events and no published index. A native
verification error propagates its original exit status. The full archive
receipt is published only after the program, public output and index checks.

Run `bash test_core_verify_watchdog.sh` for the subprocess and retry controls.
Run `test-core-continuation.ps1` to exercise the exit classification.
