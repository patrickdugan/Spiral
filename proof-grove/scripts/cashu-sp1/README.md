# Reuse the Cashu V3 recursion checkpoint

These scripts inspect the pinned A6000 settlement archive and prepare the
leading reduction and its next leaf for the stock SP1 6.9 compose prover.
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
The compose prover checks the ordered witness and emits a new proof when it
fits the local resources. The planned composition covers an execution prefix.
Complete settlement still requires a stock SP1 proof with the pinned public
output and a separate Bitcoin enforcement test.
