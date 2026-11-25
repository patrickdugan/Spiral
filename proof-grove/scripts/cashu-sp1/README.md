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
contiguous window of at least 180 seconds.

```bash
python3 -B "$TOOLS/measure_core_window.py" "$RUN_DIR" "$RESUME_REPORT" "$PRIOR_COVERAGE"
```

[Pinned SP1 Core public values](https://github.com/succinctlabs/sp1/blob/b8387fa61e1361d90ee7de49f551863418ca0f08/crates/hypercube/src/air/public_values.rs) · [Pinned SP1 shard proof encoding](https://github.com/succinctlabs/sp1/blob/b8387fa61e1361d90ee7de49f551863418ca0f08/crates/hypercube/src/verifier/proof.rs)
