# Cashu SP1 Collaborative Proving Kit & Coordinator

Distributes SP1 Core recursion group folding (`GROUP_SIZE = 128`, 292 independent groups for a ~37k-shard withdrawal proof) across any number of untrusted contributor machines without exposing any Bitcoin wallet, private key, or Cashu blinding secret.

## Trust model

- **Contributors are untrusted.** A contributor receives only pinned binaries (`normalize-core-cuda`, `replay-reduction-cuda`), public proving inputs (`core-vk.bin`, `program-key.json`, `run.json`, `cashu-withdrawal.elf`), and a one-group work order (`work-order-NNNNNN.json` + its ~186 MiB raw shard slice).
- **Zero wallet or key material.** `schema.py` and `kit.py` reject any wallet, cookie, WIF, PEM, xprv/tprv, or secret field in the contributor kit or work orders.
- **Two-gate verification on the coordinator host (`verifier.py`):**
  1. **Gate 1 (CUDA receipt):** checks `status == "cuda_reduction_verified"`, exact `sha256(reduction.bin)`, `program_vk_digest`, `run_manifest_sha256`, `shard_index_sha256`, `group_id`, and shard ordinal range.
  2. **Gate 2 (Independent CPU verifier):** verifies the SHA-256 pin of `replay-reduction-cpu` on the coordinator, stages `reduction.bin` + `run.json` + `reduction-failure/manifest.json`, and invokes `replay-reduction-cpu ... --check-inputs`, requiring `status == "cpu_reduction_inputs_verified"` and matching `child_sha256`, `program_vk_digest`, `run_manifest_sha256`, and `range`.
  3. **Gate 3 (Atomic live-reducer merge):** atomically renames `<staging>` into `<compose_dir>/groups/NNNNNN/` (`reduction.bin`, `result.json`, `cpu-verify.json`) without clobbering existing slots, matching `compose_core_bounded.py`'s `group_part()` + `verify_part()` reuse path.
- **End-to-end soundness:** a bad root costs only verification time, never soundness, because the final compressed proof is independently re-verified end-to-end with `sp1-sdk-light` (`compressed_proof_verified`).

## Modules

| File | Role |
|---|---|
| `schema.py` | Canonical schemas, SHA-256 binary/input pinning, `nb3/sp1-core-shard-index/v1` 128-shard group slicing, zero-key hygiene guard |
| `kit.py` | Packages/verifies the contributor kit (`kit-manifest.json` + optional `.tar.gz`) and builds standalone one-group work orders (`work-order-NNNNNN.json` + verified shard slice) |
| `verifier.py` | Coordinator two-gate verifier (`cuda_reduction_verified` + `replay-reduction-cpu --check-inputs`) and atomic `<compose_dir>/groups/NNNNNN/` merger |
| `coordinator.py` | Multi-threaded HTTP lease coordinator (`backward` assignment ahead of the local reducer, heartbeat + TTL dead-worker reaper/reassignment, append-only `events.jsonl`, per-contributor throughput & rejected-root telemetry) |
| `contributor.py` | Zero-key contributor worker (HTTP lease/heartbeat/submit loop and offline `--one-group` mode) |
| `measure_regtest.py` | End-to-end regtest protocol measurement against the pinned 37,309-shard / 292-group regtest `core-shard-index.json` |
| `test_collab.py` | Unit and live localhost HTTP integration tests |

## Deployment commands (proving PC & contributors)

### 1. Coordinator (on the proving PC, with pinned `replay-reduction-cpu`)

```bash
python3 -B -m collab.coordinator \
  --shard-index "$VERIFIED/shard-index.json" \
  --shard-index-sha256 "$INDEX_PIN" \
  --run-json "$JOB/run/run.json" \
  --program-key "$FIRST/program-key.json" \
  --cpu-checker "$PWD/outputs/cashu-core-compose-counted-build/replay-reduction-cpu" \
  --cpu-checker-sha256 "869cd0ec0f4de33ccb9549cfaf97f162a89f4dcb7ece72816187e7b1b39fd3ab" \
  --compose-dir "$PARENTS" \
  --state-dir "$PWD/outputs/collab-state" \
  --archive "$ARCHIVE" \
  --direction backward \
  --heartbeat-timeout 120 \
  --lease-ttl 1800 \
  --host 0.0.0.0 --port 8787
```

### 2. Contributor (untrusted GPU machine, zero wallet/key material)

```bash
python3 -B -m collab.kit verify ./contributor-kit --manifest-sha256 "$KIT_PIN"
python3 -B -m collab.contributor \
  --kit-dir ./contributor-kit \
  --manifest-sha256 "$KIT_PIN" \
  --coordinator "http://<coordinator-host>:8787" \
  --worker-id "a6000-01"
```

Standalone one-group work order (no HTTP needed):

```bash
python3 -B -m collab.kit work-order \
  --shard-index "$VERIFIED/shard-index.json" \
  --run-manifest-sha256 "$MANIFEST_PIN" \
  --group 291 --archive "$ARCHIVE" --out-dir ./order-000291

python3 -B -m collab.contributor \
  --kit-dir ./contributor-kit \
  --one-group ./order-000291/work-order-000291.json \
  --shards-slice ./order-000291/shards-000291.bin \
  --out-dir ./out-000291
```

## Regtest measurement & evidence boundary

- **Measured receipt:** `proof-grove/evidence/collaborative-proving/regtest-measurement.json` (`evidence_level: "regtest_protocol_calibration"`).
- **What ran live:** full 292-group / 37,309-shard regtest work-order slicing from the pinned Spiral archive (`5446141e…db556a9b`), zero-key kit verification, localhost HTTP coordinator + 4 honest workers + 1 dead worker abandoning 3 groups (all 3 reaped & reassigned) + 1 adversarial worker submitting 5 bad root classes (5/5 rejected, 0 bad roots merged), coordinator subprocess `--check-inputs` verification on all 292 groups, and atomic population of `groups/000000..000291/`.
- **What awaits the proving PC / testnet4:** running the identical kit & coordinator with the compiled `normalize-core-cuda`, `replay-reduction-cuda`, and `replay-reduction-cpu` binaries against a live 54 GB Core archive.
