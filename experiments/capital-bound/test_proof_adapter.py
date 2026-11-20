import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import subprocess
import sys

from proof_adapter import (RELATION, check_native_receipt, check_verification_receipt,
                           digest, import_bitvm, load_bundle, parse_json, read_bounded,
                           run_verifier, VerifierFailure)


def nova_fixture():
    # Deliberately invalid cryptographic bytes. These fixtures exercise binding
    # and scope checks and are never submitted as verified Nova proofs.
    raw = {"journal.bin": bytes(276), "proof.bin": b"NOT A NOVA PROOF"}
    pins = {"schema": "lnmarkets-nova-expect/v2", "relation": RELATION,
        "nova_version": "0.76.0", "verifier_key_sha256": "42" * 32,
        "verifier_key_serialized_bytes": 17, "journal_sha256": digest(raw["journal.bin"]),
        "steps": 2, "initial_state": ["00" * 32] * 8,
        "final_state": ["01" * 32] * 8}
    raw["manifest.json"] = json.dumps({"schema": "lnmarkets-nova-bundle/v2",
        "claim": pins, "proof_sha256": digest(raw["proof.bin"])}).encode()
    receipt = {"schema": "lnmarkets-nova-verification/v2", "relation": RELATION,
        "nova_version": "0.76.0", "status": "compressed_verified_limited_relation",
        "nova_compressed_verified": True, "verifier_key_rebuilt_from_current_circuit": True,
        "independently_supplied_expectations_matched": True,
        "native_signature_checks_in_this_process": False,
        "standalone_signature_snark_proved": False, "bitcoin_spendability_proved": False,
        "proof_sha256": digest(raw["proof.bin"]), "native_journal_sha256": pins["journal_sha256"],
        "verifier_key_sha256": pins["verifier_key_sha256"],
        "verifier_key_serialized_bytes": pins["verifier_key_serialized_bytes"],
        "rows": pins["steps"], "final_state": pins["final_state"],
        "compressed_bytes": len(raw["proof.bin"])}
    return pins, raw, receipt


def bitvm_fixture():
    # Source-shaped synthetic events only; no Bitcoin transaction is valid here.
    transactions = {}
    events = []
    def mined(check, height, marker):
        txid = marker * 64
        transactions[check] = {"txid": txid, "hex": "00", "vsize": 100, "weight_wu": 400}
        events.append({"event": "confirmed_spend", "height": height, "check": check,
                       "txid": txid, "block_hash": "ff" * 32, "vsize": 100, "weight_wu": 400})
        return txid
    txid = mined("honest_funding", 100, "1")
    events.append({"event": "funding_confirmed_before_selection", "height": 100,
                   "scenario": "honest", "funding_outpoint": txid + ":0", "block_hash": "ff" * 32})
    events.append({"event": "challenge_selected_after_funding", "height": 100,
                   "scenario": "honest", "selected_index": 3})
    challenge = mined("honest_challenge", 101, "2")
    events.append({"event": "durable_labels_released_after_confirmed_challenge", "height": 101,
                   "scenario": "honest", "challenge_txid": challenge, "label_count": 128})
    mined("honest_response", 102, "3")
    mined("honest_payout_first_valid_block", 107, "4")
    receipt = {"schema": "babe-pilot/funded-regtest/v1", "status": "passed", "network": "regtest",
        "graph_binary_sha256": "ab" * 32, "release_binary_sha256": "cd" * 32,
        "scope": {"full_application_withdrawal": False, "reorg_rollback_exercised": False,
                  "independent_operator_challenger_processes": False},
        "events": events,
        "scenarios": [{"name": "honest", "terminal": "operator_payout", "confirmed": True}]}
    return receipt, transactions


class ProofAdapterTests(unittest.TestCase):
    def test_real_public_nova_fixture_artifact_binding(self):
        directory = Path(__file__).parent / "fixtures" / "nova-v2"
        provenance = json.loads((directory / "provenance.json").read_text())
        for path, info in provenance["files"].items():
            raw = (directory / path).read_bytes()
            self.assertEqual(len(raw), info["bytes"])
            self.assertEqual(digest(raw), info["sha256"])
        pins, raw, _ = load_bundle(directory / "bundle", directory / "expected.json",
            "17c2b3b9533f6d227b9859e7bdd0d667498e7474b70eb97c14a98381563ae043")
        self.assertEqual(pins["steps"], 2)
        self.assertEqual(len(raw["proof.bin"]), 12376)
        check_native_receipt(json.loads((directory / "native-prepare.json").read_text()), pins)

    def test_actual_funded_ci_receipt_matches_all_recorded_scenarios(self):
        directory = Path(__file__).parent / "fixtures" / "babe-funded-ci"
        provenance = json.loads((directory / "provenance.json").read_text())
        raw = (directory / "receipt.json").read_bytes()
        catalogue = (directory / "transactions.json").read_bytes()
        self.assertEqual(digest(raw), provenance["receipt_sha256"])
        self.assertEqual(digest(catalogue), provenance["transactions_sha256"])
        self.assertTrue(provenance["all_recorded_source_hashes_match_pinned_head"])
        self.assertEqual(len(provenance["source_audit"]), 21)
        output = import_bitvm(parse_json(raw), parse_json(catalogue))
        self.assertEqual(len(output["observations"]), 63)
        self.assertEqual(len(output["mined_transactions_as_reported"]), 13)
        self.assertEqual(output["total_mined_vsize_as_reported"], 5429)
        self.assertEqual([x["funding_to_terminal_blocks_as_reported"]
                          for x in output["scenarios"]], [12, 5, 7, 3])
        self.assertEqual(output["capital_events"], [])
        self.assertFalse(output["evidence_verified"])

    def test_strict_json_and_bounded_files(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]'):
            with self.assertRaises(ValueError):
                parse_json(raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data"
            path.write_bytes(b"12345")
            with self.assertRaises(ValueError):
                read_bounded(path, 4)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                read_bounded(link, 10)

    def test_manifest_and_expected_file_are_independently_bound(self):
        pins, raw, _ = nova_fixture()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for filename, value in raw.items():
                (directory / filename).write_bytes(value)
            expected = directory / "receiver-pins.json"
            data = json.dumps(pins).encode()
            expected.write_bytes(data)
            self.assertEqual(load_bundle(directory, expected, digest(data))[0], pins)
            with self.assertRaisesRegex(ValueError, "file digest"):
                load_bundle(directory, expected, "00" * 32)
            (directory / "proof.bin").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "proof bytes"):
                load_bundle(directory, expected, digest(data))
            (directory / "proof.bin").write_bytes(raw["proof.bin"])
            pins["final_state"][0] = "02" * 32
            changed = json.dumps(pins).encode()
            expected.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "independent expectations"):
                load_bundle(directory, expected, digest(changed))

    def test_actual_v2_verifier_shape_and_scope_are_enforced(self):
        pins, raw, receipt = nova_fixture()
        check_verification_receipt(receipt, pins, raw)
        mutations = {"schema": "lnmarkets-nova-verification/v1",
            "relation": "lnmarkets/opaque-accounting/v1",
            "status": "compressed_proven_limited_relation", "bitcoin_spendability_proved": True,
            "native_signature_checks_in_this_process": True,
            "standalone_signature_snark_proved": True,
            "independently_supplied_expectations_matched": False,
            "rows": True, "proof_sha256": "00" * 32,
            "native_journal_sha256": "00" * 32, "verifier_key_sha256": "00" * 32,
            "final_state": ["02" * 32] * 8}
        for key, value in mutations.items():
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                changed = copy.deepcopy(receipt)
                changed[key] = value
                check_verification_receipt(changed, pins, raw)

    def test_wrong_executable_pin_fails_before_process_creation(self):
        pins, raw, _ = nova_fixture()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for filename, value in raw.items():
                (directory / filename).write_bytes(value)
            expected = directory / "receiver-pins.json"
            data = json.dumps(pins).encode()
            expected.write_bytes(data)
            binary = directory / "executable"
            binary.write_bytes(b"This must never execute")
            with self.assertRaisesRegex(ValueError, "executable differs"):
                run_verifier(binary, "00" * 32, directory, expected, digest(data))

    def test_cli_preserves_failed_attempt_and_emits_no_verified_event(self):
        pins, raw, _ = nova_fixture()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for filename, value in raw.items():
                (directory / filename).write_bytes(value)
            expected = directory / "receiver-pins.json"
            data = json.dumps(pins).encode()
            expected.write_bytes(data)
            binary = directory / "executable"
            binary.write_bytes(b"This must never execute")
            output = directory / "failed.json"
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("proof_adapter.py")),
                "verify-nova", "--verifier", str(binary), "--verifier-sha256", "00" * 32,
                "--expect", str(expected), "--expect-sha256", digest(data),
                "--bundle", str(directory), "--out", str(output)],
                capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["events"], [])
            self.assertFalse(receipt["proof_cryptographically_verified"])
            self.assertIn("executable differs", receipt["error"])

    def test_timeout_kills_verifier_and_retains_resource_failure(self):
        pins, raw, _ = nova_fixture()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for filename, value in raw.items():
                (directory / filename).write_bytes(value)
            expected = directory / "receiver-pins.json"
            data = json.dumps(pins).encode()
            expected.write_bytes(data)
            binary = directory / "executable"
            executable = b"mocked pinned executable"
            binary.write_bytes(executable)
            process = mock.Mock(pid=12345)
            process.wait.side_effect = [subprocess.TimeoutExpired("verify", 1), -9]
            with mock.patch("proof_adapter.subprocess.Popen", return_value=process), \
                    mock.patch("proof_adapter.os.killpg") as kill, \
                    self.assertRaises(VerifierFailure) as context:
                run_verifier(binary, digest(executable), directory, expected, digest(data), timeout=1)
            kill.assert_called_once()
            self.assertEqual(context.exception.returncode, -9)
            self.assertEqual(context.exception.resources["timeout_seconds"], 1)

    def test_native_receipt_binding_preserves_its_separate_scope(self):
        pins, _, _ = nova_fixture()
        receipt = {"schema": "lnmarkets-bitvm3-nova/v2", "relation": RELATION,
            "status": "expected_claim_prepared_native_validated_unproved",
            "native_bip340_and_oracle_checks": True,
            "native_signature_checks_in_this_process": True,
            "row_transcript_sha256_constrained": True,
            "row_transcript_digests_constrained_as_opaque_witnesses": False,
            "sha256_nullifier_and_transaction_checks_outside_nova": True,
            "standalone_signature_snark_proved": False, "bitcoin_spendability_proved": False,
            "native_journal_sha256": pins["journal_sha256"],
            "nova_poseidon_root_z0": pins["initial_state"][4],
            "nova_poseidon_root_zn": pins["final_state"][4],
            "rows": 2, "nova_state_arity": 8, "nova_step_count": 2}
        check_native_receipt(receipt, pins)
        receipt["native_journal_sha256"] = "00" * 32
        with self.assertRaisesRegex(ValueError, "journal"):
            check_native_receipt(receipt, pins)

    def test_label_delivery_never_becomes_capital_release(self):
        receipt, transactions = bitvm_fixture()
        result = import_bitvm(receipt, transactions)
        self.assertFalse(result["evidence_verified"])
        self.assertEqual(result["capital_events"], [])
        self.assertFalse(result["capital_release_authorized"])
        self.assertEqual(result["scenarios"][0]["funding_to_terminal_blocks_as_reported"], 7)
        self.assertIsNone(result["scenarios"][0]["elapsed_observer_seconds"])
        self.assertIsNone(result["scenarios"][0]["capital_recovered_sat"])
        self.assertEqual(result["total_mined_vsize_as_reported"], 400)
        labels = [x for x in result["observations"] if x["source_event"].startswith("durable_labels")]
        self.assertFalse(labels[0]["capital_release_authorized"])

    def test_bitvm_rejects_unmatched_and_duplicate_transaction_evidence(self):
        for mode in ("wrong_txid", "wrong_size", "duplicate", "missing_terminal", "wrong_block"):
            receipt, transactions = bitvm_fixture()
            if mode == "wrong_txid":
                transactions["honest_response"]["txid"] = "ab" * 32
            elif mode == "wrong_size":
                transactions["honest_response"]["vsize"] = 101
            elif mode == "duplicate":
                receipt["events"].insert(1, copy.deepcopy(receipt["events"][0]))
            elif mode == "missing_terminal":
                receipt["events"].pop()
            else:
                receipt["events"][1]["block_hash"] = "ab" * 32
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                import_bitvm(receipt, transactions)

    def test_bitvm_rejects_scope_upgrades_and_early_label_delivery(self):
        for field in ("full_application_withdrawal", "reorg_rollback_exercised",
                      "independent_operator_challenger_processes"):
            receipt, transactions = bitvm_fixture()
            receipt["scope"][field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "scope"):
                import_bitvm(receipt, transactions)
        receipt, transactions = bitvm_fixture()
        labels = receipt["events"].pop(4)
        labels["height"] = 100
        receipt["events"].insert(0, labels)
        with self.assertRaisesRegex(ValueError, "precedes funding"):
            import_bitvm(receipt, transactions)

    def test_bitvm_requires_terminal_coverage_for_each_funded_scenario(self):
        receipt, transactions = bitvm_fixture()
        receipt["scenarios"] = []
        with self.assertRaisesRegex(ValueError, "terminal for every"):
            import_bitvm(receipt, transactions)


if __name__ == "__main__":
    unittest.main()
