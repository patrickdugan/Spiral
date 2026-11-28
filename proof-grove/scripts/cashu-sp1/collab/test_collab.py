"""Unit and live localhost HTTP integration tests for the Cashu collaborative proving kit."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from collab import contributor, coordinator, kit, measure_regtest, schema, verifier


def _synthetic_shard_index(num_shards: int = 300) -> tuple[dict, str]:
    shards = []
    offset = 12
    for i in range(num_shards):
        length = 1024
        shards.append(
            {
                "offset": offset,
                "length": length,
                "sha256": schema.sha256_bytes(f"shard-{i}".encode("utf-8")),
            }
        )
        offset += length
    idx = {
        "schema": schema.SHARD_INDEX_SCHEMA,
        "archive_size_bytes": offset,
        "archive_sha256": schema.sha256_bytes(b"synthetic-archive"),
        "program_vk_digest": schema.sha256_bytes(b"synthetic-program-vk"),
        "public_output_sha256": schema.sha256_bytes(b"synthetic-public-output"),
        "shards": shards,
    }
    return idx, schema.sha256_bytes(json.dumps(idx, sort_keys=True).encode("utf-8"))


def _build_test_kit(root: Path, num_shards: int = 260):
    src_bins = root / "bins"
    src_inputs = root / "inputs"
    kit_dir = root / "kit"
    src_bins.mkdir()
    src_inputs.mkdir()

    norm_py = src_bins / "normalize-core-cuda.py"
    red_py = src_bins / "replay-reduction-cuda.py"
    cpu_py = src_bins / "replay-reduction-cpu.py"
    norm_py.write_text(measure_regtest.CALIBRATION_NORMALIZER_SRC, encoding="utf-8")
    red_py.write_text(measure_regtest.CALIBRATION_REDUCER_SRC, encoding="utf-8")
    cpu_py.write_text(measure_regtest.CALIBRATION_CPU_CHECKER_SRC, encoding="utf-8")

    idx, idx_sha = _synthetic_shard_index(num_shards)
    run_json = src_inputs / "run.json"
    prog_key = src_inputs / "program-key.json"
    core_vk = src_inputs / "core-vk.bin"
    elf = src_inputs / "cashu-withdrawal.elf"
    run_json.write_text(json.dumps({"network": "regtest", "shard_index_sha256": idx_sha}) + "\n", encoding="utf-8")
    prog_key.write_text(json.dumps({"program_vk_digest": idx["program_vk_digest"]}) + "\n", encoding="utf-8")
    core_vk.write_bytes(b"vk-public-only")
    elf.write_bytes(b"\x7fELF-public-guest")

    run_sha = schema.sha256_file(run_json)
    manifest = kit.package_kit(
        kit_dir,
        network="regtest",
        binaries={"normalize-core-cuda": norm_py, "replay-reduction-cuda": red_py},
        public_inputs={
            "core-vk.bin": core_vk,
            "program-key.json": prog_key,
            "run.json": run_json,
            "cashu-withdrawal.elf": elf,
        },
        shard_index_sha256=idx_sha,
        run_manifest_sha256=run_sha,
        program_vk_digest=idx["program_vk_digest"],
        public_output_sha256=idx["public_output_sha256"],
    )
    orders = schema.groups_from_shard_index(idx, idx_sha, run_manifest_sha256=run_sha, network="regtest")
    return {
        "kit_dir": kit_dir,
        "manifest": manifest,
        "orders": orders,
        "cpu_py": cpu_py,
        "cpu_sha": schema.sha256_file(cpu_py),
        "run_json": run_json,
        "prog_key": prog_key,
    }


class HygieneAndPinTests(unittest.TestCase):
    def test_rejects_wallet_and_key_material_in_kit_and_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _build_test_kit(Path(tmp))
            # Planting a wallet.dat inside the contributor kit must fail verification.
            (env["kit_dir"] / "wallet.dat").write_bytes(b"secret")
            with self.assertRaisesRegex(schema.CollabError, "wallet.dat"):
                kit.verify_kit(env["kit_dir"])

        with self.assertRaisesRegex(schema.CollabError, "private_key"):
            schema.assert_no_key_material_in_obj({"work_order": {"private_key": "11" * 32}})
        with self.assertRaisesRegex(schema.CollabError, "forbidden key material"):
            schema.assert_no_key_material_in_obj({"note": "xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi"})

    def test_tampered_binary_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _build_test_kit(Path(tmp))
            reducer = env["kit_dir"] / "bin" / "replay-reduction-cuda"
            reducer.write_bytes(reducer.read_bytes() + b"\n# tampered\n")
            with self.assertRaisesRegex(schema.CollabError, "sha256 pin mismatch"):
                kit.verify_kit(env["kit_dir"])

    def test_real_37309_shard_group_slicing(self):
        idx, idx_sha = _synthetic_shard_index(37_309)
        orders = schema.groups_from_shard_index(idx, idx_sha, run_manifest_sha256="aa" * 32)
        self.assertEqual(len(orders), 292)
        self.assertEqual(orders[0]["group_id"], "000000")
        self.assertEqual((orders[0]["shard_start"], orders[0]["shard_end"], orders[0]["group_shards"]), (1, 128, 128))
        self.assertEqual(orders[-1]["group_id"], "000291")
        self.assertEqual((orders[-1]["shard_start"], orders[-1]["shard_end"], orders[-1]["group_shards"]), (37_249, 37_309, 61))


class CoordinatorAndTrustGateTests(unittest.TestCase):
    def test_dead_worker_reassignment_and_bad_root_rejection_over_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = _build_test_kit(root, num_shards=128 * 10)  # 10 groups
            compose_dir = root / "compose"
            state_dir = root / "state"

            engine = coordinator.CoordinatorEngine(
                work_orders=env["orders"],
                compose_dir=compose_dir,
                state_dir=state_dir,
                cpu_checker_path=env["cpu_py"],
                cpu_checker_sha256=env["cpu_sha"],
                run_json_path=env["run_json"],
                program_key_path=env["prog_key"],
                direction="backward",
                lease_ttl_s=20.0,
                heartbeat_timeout_s=1.5,
                heartbeat_interval_s=0.3,
            )
            server = coordinator.make_http_server(engine, "127.0.0.1", 0)
            url = f"http://127.0.0.1:{server.server_address[1]}"
            srv = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            srv.start()
            try:
                # 1. Dead worker grabs 3 groups and crashes.
                abandoned = measure_regtest._run_dead_worker(url, "dead-vm-01", groups_to_abandon=3)
                self.assertEqual(abandoned, ["000009", "000008", "000007"])

                # 2. Malicious worker submits 5 corrupted/forged root classes.
                bad_res = measure_regtest._run_malicious_worker(url, "malicious-01")
                self.assertEqual(len(bad_res), 5)
                self.assertTrue(all(not r["accepted"] for r in bad_res))
                self.assertEqual(
                    {r["reason"] for r in bad_res},
                    {"sha256_mismatch", "bad_cuda_status", "vk_or_manifest_mismatch", "cpu_verify_failed", "stale_or_expired_lease"},
                )
                # Confirm zero bad roots landed in compose/groups!
                self.assertEqual(list((compose_dir / "groups").iterdir()), [])

                # 3. Wait past heartbeat timeout so all 3 of dead-vm-01's leases are expired & reclaimed.
                time.sleep(1.7)
                engine.reap_expired_leases()
                self.assertEqual(engine.workers["dead-vm-01"].leases_expired, 3)

                # 4. Two honest workers finish all 10 groups cleanly.
                t1 = threading.Thread(
                    target=contributor.run_worker_loop,
                    kwargs={"kit_dir": env["kit_dir"], "coordinator_url": url, "worker_id": "a6000-01", "poll_sleep_s": 0.0},
                )
                t2 = threading.Thread(
                    target=contributor.run_worker_loop,
                    kwargs={"kit_dir": env["kit_dir"], "coordinator_url": url, "worker_id": "a6000-02", "poll_sleep_s": 0.0},
                )
                t1.start()
                t2.start()
                t1.join(timeout=30)
                t2.join(timeout=30)

                stats = engine.write_summary()
                self.assertEqual(stats["verified_groups"], 10)
                self.assertEqual(stats["pending_groups"], 0)
                self.assertEqual(stats["leased_groups"], 0)
                self.assertEqual(stats["rejected_roots_total"], 5)
                self.assertGreaterEqual(stats["reassignments_total"], 7)
                for gid in abandoned:
                    self.assertEqual(engine.groups[gid]["status"], "verified")
                    self.assertIn(engine.groups[gid]["verified_by"], ("a6000-01", "a6000-02"))
                # All 10 group slots populated atomically with reduction.bin + result.json + cpu-verify.json.
                self.assertEqual(len(list((compose_dir / "groups").iterdir())), 10)
            finally:
                server.shutdown()
                server.server_close()

    def test_atomic_merge_does_not_overwrite_existing_verified_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compose = root / "compose"
            order = {"group_id": "000042"}
            slot1 = verifier.merge_verified_group_root(
                compose, order, b"first-root", {"status": "cuda_reduction_verified"}, {"status": "cpu_reduction_inputs_verified"}
            )
            slot2 = verifier.merge_verified_group_root(
                compose, order, b"second-root", {"status": "cuda_reduction_verified"}, {"status": "cpu_reduction_inputs_verified"}
            )
            self.assertEqual(slot1, slot2)
            self.assertEqual((slot1 / "reduction.bin").read_bytes(), b"first-root")


if __name__ == "__main__":
    unittest.main()
