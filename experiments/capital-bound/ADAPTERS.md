# Nova verification and BitVM observation adapters

`proof_adapter.py` connects the capital experiment to the existing LNMarkets
Nova CLI and the funded BABE regtest receipt format. It uses Python's standard
library. Verification executes a pinned local Rust binary on CPU; it does not
build the prover or start proof generation.

Run the commands below from `experiments/capital-bound/` in the Spiral checkout.

## Source versions

The LNMarkets checkout inspected for this adapter is
`patrickdugan/zk-rusto-no-bitcoino` at
`f6a8d129285869f339c86f1e2e7f1124bc09c37a`. The active relation is
`lnmarkets/sha256-transcript-accounting/v2`. It hashes the 600-byte signed
transcript inside R1CS and binds its economic fields. Native BIP340 checks,
application-message derivation and Bitcoin spendability have separate evidence
boundaries. The repository's independent single-signature proof does not yet
compose those obligations into the Pallas batch relation.

Sources:

- [Nova artifact interface](https://github.com/patrickdugan/zk-rusto-no-bitcoino/blob/f6a8d129285869f339c86f1e2e7f1124bc09c37a/LNMarkets/nova/src/artifact.rs)
- [Current Nova scope and recorded measurements](https://github.com/patrickdugan/zk-rusto-no-bitcoino/blob/f6a8d129285869f339c86f1e2e7f1124bc09c37a/LNMarkets/nova/README.md)
- [Funded BABE runner at b404ea4](https://github.com/patrickdugan/zk-rusto-no-bitcoino/blob/b404ea4566c7ac28b702f8e0d4c0f1fded3b5691/integrations/bitvm3-nova/babe-pilot/scripts/run-regtest.py)
- [Funded graph's exercised boundary](https://github.com/patrickdugan/zk-rusto-no-bitcoino/blob/b404ea4566c7ac28b702f8e0d4c0f1fded3b5691/integrations/bitvm3-nova/babe-pilot/INTEGRATION.md)

## Verify an existing Nova bundle

Supply a trusted verifier build and receiver-owned expected claims. Both file
hashes are required. The expected-claim file must come from an independent
preparation process. A matching hash establishes identity; the operator still
has to select trustworthy expectations and a trustworthy verifier binary.

```sh
python3 proof_adapter.py verify-nova \
  --verifier /absolute/path/to/lnm-nova \
  --verifier-sha256 TRUSTED_EXECUTABLE_SHA256 \
  --bundle /absolute/path/to/bundle \
  --expect /absolute/path/to/receiver-expected.json \
  --expect-sha256 TRUSTED_EXPECTED_FILE_SHA256 \
  --native-receipt /absolute/path/to/prepare-receipt.json \
  --run-id capital-bound-run-001 \
  --height 0 \
  --out nova-verification.json
```

The optional native receipt is bound to the same journal, roots and row count.
Its signatures are not rechecked by the adapter. The output records it as a
bound, unauthenticated receipt. A receiver can preserve that receipt alongside
its own native validation evidence.

Before invoking the Rust program, the adapter checks the v2 schema, exact
manifest/expected claim equality and the byte hashes of the proof and journal.
It snapshots those inputs and the pinned executable into a private temporary
directory. The executed command is always `verify --bundle ... --expect ...`.
The Rust verifier rebuilds its key from the compiled circuit and verifies the
compressed proof against the retained claim.

The adapter uses two Rayon threads, a 2 GiB address-space limit, a 180-second CPU
limit and a configurable wall timeout of at most 180 seconds. Each output stream
is limited to 64 KiB. GPU visibility is disabled. The runtime must support POSIX
resource limits. RSS is reported in Linux KiB, matching the intended CI worker.
Use a fresh CLI process for each measurement because the child-process RSS
high-water mark belongs to that adapter process's lifetime.

A successful result contains one `proof_verified` event. It preserves the actual
UTC observation time and the exact verifier-receipt digest. Its chain height is
explicitly caller metadata. It authorizes no release of funds.

`proof_cryptographically_verified` concerns the limited Nova relation. The
separate `evidence_verified` field remains false because this adapter does not
authenticate the capital ledger or Bitcoin chain state. Combining this event
with a CSV probe must preserve that distinction: the Nova proof and the CSV
transaction have no application-level authorization link yet.

The adapter writes only new output files. Failed verification produces a failure
receipt at `--out`, an empty event list and a nonzero exit status. Child failures
and timeouts retain their resource measurements. A rejected input records the
validation error before execution. Include these attempts when comparing costs.

## Import the funded BABE run

```sh
python3 proof_adapter.py import-bitvm \
  --receipt /absolute/path/to/funded-run/receipt.json \
  --transactions /absolute/path/to/funded-run/transactions.json \
  --out bitvm-observations.json
```

This consumes `babe-pilot/funded-regtest/v1`, matching the pinned runner. It
cross-checks each claimed mined transaction against the supplied transaction
catalogue, verifies consistent weight/vsize fields, rejects duplicates and
matches each declared terminal outcome to its recorded mined spend.

The output preserves lifecycle observations and reported funding-to-terminal
block spans. `durable_labels_released_after_confirmed_challenge` describes the
release of labels. It never becomes a capital-release event.

The source receipt contains no observer timestamps or complete economic reserve
ledger. Consequently the importer emits an empty `capital_events` list and
reports amounts and elapsed seconds as unavailable. Transaction IDs and chain
membership remain unauthenticated claims. The node adapter must establish the
active chain and attach the canonical reserve lineage before those observations
can influence a capital-saving result. Input hashes bind the exact imported
receipt and transaction catalogue.

## Checks

```sh
python3 -m unittest -v test_proof_adapter.py
```

The small tests use deliberately invalid cryptographic fixture bytes to exercise
binding and malformed-input rejection. They do not label those fixtures as
proofs. A separate recorded smoke run invokes the actual existing v2 verifier
on its persisted two-contract proof.

## Executed smoke run

`results/2026-11-21/nova/nova-v2-verifier-attempt.json` records a successful separate-process
verification of the existing 12,376-byte two-contract proof. The adapter measured
33.341 seconds of wall time, 60.601 seconds of user CPU and 500,352 KiB of peak
child RSS. That peak is about 489 MiB. The output binds the binary, receiver
expectations and each artifact by SHA256. It retains the original observation
time and full limited-relation verifier receipt.

An earlier attempt ended with SIGKILL and empty stderr under a 120-second CPU
limit. Its cause remains unresolved. The retained attempt ledger records that
failure and zero emitted proof events. The successful retry used a 180-second
CPU limit and the same 2 GiB address-space limit; its measured CPU use stayed
below both CPU limits.

The source context records the adapter hash used for that run. Subsequent edits
strengthened the BitVM importer and added automatic failed-attempt receipts to
the CLI, including a resource receipt after timeout cleanup.
`results/2026-11-21/nova/nova-v2-verifier-source.py` preserves the executed adapter source; its
SHA256 matches the receipt's `source_context.adapter_sha256` exactly.

## CI fixtures

`fixtures/nova-v2/` contains the 12,376-byte proof, 276-byte journal, manifest and
receiver-owned expected claims. Those four inputs total 15,989 bytes. The
optional native preparation receipt adds 1,590 bytes. `provenance.json` records
each byte count and hash, along with the generating source revision. The
fixture contains no private witness or executable.

CI can build `lnm-nova` from pinned source commit
`f6a8d129285869f339c86f1e2e7f1124bc09c37a`, with `cargo build --locked --release`
against `LNMarkets/nova/Cargo.toml`. Hash that locally built binary for the
adapter's executable pin. The fixture's verifier-key identity and expected-file
hash stay fixed. Verification reuses the existing proof and performs no new
proving. Keep the two-thread and resource bounds in the invocation.

`fixtures/babe-funded-ci/` contains only the public receipt and transaction
catalogue from [workflow run 44376453388](https://github.com/patrickdugan/zk-rusto-no-bitcoino/actions/runs/44376453388).
The downloaded archive matched GitHub's recorded SHA256 before extraction.
Its provenance file retains the artifact identity and the input hashes.

The receipt identifies merge commit `e4a2f74d09177ba96e62fc19d362e3545dac012a`
and reports a dirty working tree. All 21 source hashes recorded by that runner
match the corresponding files at workflow head
`b404ea4566c7ac28b702f8e0d4c0f1fded3b5691`; the comparison is retained in
the fixture provenance.

The importer accepted all four actual scenarios and 63 observations, including
13 claimed mined transactions totaling 5,429 vbytes. Funding-to-terminal spans
are 12 blocks for assertion timeout, 5 for withheld labels, 7 for an honest
payout and 3 for refutation. `results/2026-11-21/bitvm/babe-ci-observations.json` preserves the
normalized observations. These are imported CI measurements; the adapter
emits no capital release and supplies no observer-time estimate. The normal
unit suite checks both real fixture formats without building Rust or mining.
