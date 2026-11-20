#!/usr/bin/env python3
"""Bounded adapters for LNMarkets Nova v2 and funded BABE regtest observations.

The Nova command executes an explicitly pinned local verifier. Neither command
authenticates Bitcoin chain state or authorizes a capital release.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
import time

RELATION = "lnmarkets/sha256-transcript-accounting/v2"
MAX_METADATA = 32 * 1024
MAX_RECEIPT = 4 * 1024 * 1024
MAX_PROOF = 64 * 1024 * 1024
MAX_EXECUTABLE = 256 * 1024 * 1024
MAX_OUTPUT = 64 * 1024
MEMORY_LIMIT = 2 * 1024 * 1024 * 1024
CPU_LIMIT = 180
PINS_KEYS = {"schema", "relation", "nova_version", "verifier_key_sha256",
             "verifier_key_serialized_bytes", "journal_sha256", "steps",
             "initial_state", "final_state"}


class VerifierFailure(ValueError):
    def __init__(self, message, resources, returncode):
        super().__init__(message)
        self.resources = resources
        self.returncode = returncode


def integer(value, label, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{label}: invalid exact integer")
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def hex32(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label}: expected canonical lowercase SHA256/32-byte hex")
    return value


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON field: {key}")
        obj[key] = value
    return obj


def parse_json(raw):
    def reject_constant(value):
        raise ValueError(f"non-finite JSON constant: {value}")
    try:
        value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def read_bounded(path, limit):
    path = Path(path)
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
        raise ValueError(f"{path.name}: expected bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("opened input is not a regular file")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name}: input exceeds byte limit")
    return data


def check_pins(pins):
    if set(pins) != PINS_KEYS:
        raise ValueError("unexpected or missing expected-claim fields")
    if (pins["schema"], pins["relation"], pins["nova_version"]) != (
            "lnmarkets-nova-expect/v2", RELATION, "0.76.0"):
        raise ValueError("unsupported Nova relation or version")
    for key in ("verifier_key_sha256", "journal_sha256"):
        hex32(pins[key], key)
    integer(pins["verifier_key_serialized_bytes"], "key bytes", 1, 512 * 1024 * 1024)
    integer(pins["steps"], "steps", 1, 32)
    for key in ("initial_state", "final_state"):
        if not isinstance(pins[key], list) or len(pins[key]) != 8:
            raise ValueError("Nova state must have exactly eight elements")
        for field in pins[key]:
            hex32(field, key)


def load_bundle(bundle, expected, expected_sha256):
    """Bind received artifacts to receiver-owned pins; this is not a proof check."""
    expected_raw = read_bounded(expected, MAX_METADATA)
    if digest(expected_raw) != hex32(expected_sha256, "expected file hash"):
        raise ValueError("independent expected-claim file digest differs")
    pins = parse_json(expected_raw)
    check_pins(pins)
    raw = {"manifest.json": read_bounded(Path(bundle) / "manifest.json", MAX_METADATA),
           "journal.bin": read_bounded(Path(bundle) / "journal.bin", 276),
           "proof.bin": read_bounded(Path(bundle) / "proof.bin", MAX_PROOF)}
    manifest = parse_json(raw["manifest.json"])
    if set(manifest) != {"schema", "proof_sha256", "claim"}:
        raise ValueError("unexpected or missing bundle manifest fields")
    if manifest["schema"] != "lnmarkets-nova-bundle/v2" or manifest["claim"] != pins:
        raise ValueError("received claim differs from independent expectations")
    if len(raw["journal.bin"]) != 276 or digest(raw["journal.bin"]) != pins["journal_sha256"]:
        raise ValueError("journal bytes differ from expected claim")
    if not raw["proof.bin"] or digest(raw["proof.bin"]) != hex32(manifest["proof_sha256"], "proof hash"):
        raise ValueError("proof bytes differ from manifest")
    return pins, raw, expected_raw


def check_verification_receipt(receipt, pins, raw):
    wanted = {"schema": "lnmarkets-nova-verification/v2", "relation": RELATION,
              "nova_version": "0.76.0", "status": "compressed_verified_limited_relation",
              "nova_compressed_verified": True,
              "verifier_key_rebuilt_from_current_circuit": True,
              "independently_supplied_expectations_matched": True,
              "native_signature_checks_in_this_process": False,
              "standalone_signature_snark_proved": False,
              "bitcoin_spendability_proved": False,
              "proof_sha256": digest(raw["proof.bin"]),
              "native_journal_sha256": pins["journal_sha256"],
              "verifier_key_sha256": pins["verifier_key_sha256"],
              "verifier_key_serialized_bytes": pins["verifier_key_serialized_bytes"],
              "rows": pins["steps"], "final_state": pins["final_state"],
              "compressed_bytes": len(raw["proof.bin"])}
    for key, expected in wanted.items():
        actual = receipt.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(f"verifier receipt differs at {key}")


def check_native_receipt(receipt, pins):
    """Only bind an imported native receipt; authenticity remains a caller duty."""
    wanted = {"schema": "lnmarkets-bitvm3-nova/v2", "relation": RELATION,
              "native_bip340_and_oracle_checks": True,
              "native_signature_checks_in_this_process": True,
              "row_transcript_sha256_constrained": True,
              "row_transcript_digests_constrained_as_opaque_witnesses": False,
              "sha256_nullifier_and_transaction_checks_outside_nova": True,
              "standalone_signature_snark_proved": False,
              "bitcoin_spendability_proved": False,
              "native_journal_sha256": pins["journal_sha256"],
              "nova_poseidon_root_z0": pins["initial_state"][4],
              "nova_poseidon_root_zn": pins["final_state"][4],
              "rows": pins["steps"], "nova_state_arity": 8,
              "nova_step_count": pins["steps"]}
    for key, expected in wanted.items():
        actual = receipt.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(f"native receipt differs at {key}")
    if receipt.get("status") not in {"native_validated_unproved",
            "expected_claim_prepared_native_validated_unproved",
            "recursive_proven_limited_relation", "compressed_proven_limited_relation"}:
        raise ValueError("unsupported native receipt status")


def _limits():
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_verifier(verifier, verifier_sha256, bundle, expected, expected_sha256,
                 height=0, run_id="capital-bound", native_receipt=None, timeout=120):
    if os.name != "posix":
        raise ValueError("bounded verifier execution requires POSIX resource limits")
    integer(height, "height")
    integer(timeout, "timeout", 1, 180)
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id is required")
    pins, raw, expected_raw = load_bundle(bundle, expected, expected_sha256)
    executable = read_bounded(verifier, MAX_EXECUTABLE)
    if digest(executable) != hex32(verifier_sha256, "verifier executable hash"):
        raise ValueError("verifier executable differs from trusted hash")
    native_raw = None
    if native_receipt is not None:
        native_raw = read_bounded(native_receipt, MAX_METADATA)
        check_native_receipt(parse_json(native_raw), pins)
    # Private snapshots keep the verified bytes independent of later source edits.
    import resource
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="capital-bound-nova-") as folder:
        directory = Path(folder)
        frozen_bundle = directory / "bundle"
        frozen_bundle.mkdir()
        for filename, data in raw.items():
            (frozen_bundle / filename).write_bytes(data)
            (frozen_bundle / filename).chmod(0o400)
        frozen_expected = directory / "expected.json"
        frozen_expected.write_bytes(expected_raw)
        frozen_expected.chmod(0o400)
        frozen_executable = directory / "lnm-nova"
        frozen_executable.write_bytes(executable)
        frozen_executable.chmod(0o500)
        command = [str(frozen_executable), "verify", "--bundle", str(frozen_bundle),
                   "--expect", str(frozen_expected)]
        environment = os.environ.copy()
        environment.update(RAYON_NUM_THREADS="2", CUDA_VISIBLE_DEVICES="",
                           HIP_VISIBLE_DEVICES="", RUST_BACKTRACE="0")
        # A verifier pin identifies a trusted local build. Loader injection would
        # defeat that boundary even if the on-disk executable stayed unchanged.
        for key in ("LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
                    "DYLD_LIBRARY_PATH"):
            environment.pop(key, None)
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout,
                stderr=stderr, env=environment, cwd=directory, start_new_session=True,
                preexec_fn=_limits)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise ValueError("bounded Nova verification timed out") from error
            stdout.seek(0)
            output = stdout.read(MAX_OUTPUT + 1)
            stderr.seek(0)
            error_output = stderr.read(MAX_OUTPUT + 1)
            if len(output) > MAX_OUTPUT or len(error_output) > MAX_OUTPUT:
                raise ValueError("verifier output exceeded bound")
            if returncode:
                usage = resource.getrusage(resource.RUSAGE_CHILDREN)
                resources = {"wall_seconds": time.monotonic() - start,
                    "user_cpu_seconds": usage.ru_utime - before.ru_utime,
                    "system_cpu_seconds": usage.ru_stime - before.ru_stime,
                    "child_max_rss_kib_linux": usage.ru_maxrss,
                    "address_space_limit_bytes": MEMORY_LIMIT,
                    "cpu_limit_seconds": CPU_LIMIT, "timeout_seconds": timeout}
                raise VerifierFailure(f"Nova verifier failed with status {returncode}: "
                    + error_output.decode("utf-8", errors="replace")[-1200:], resources, returncode)
    receipt = parse_json(output)
    check_verification_receipt(receipt, pins, raw)
    ended = datetime.now(timezone.utc)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    event = {"kind": "proof_verified", "proof_id": "nova:" + digest(raw["proof.bin"]),
             "height": height, "time_s": int(ended.timestamp()), "run_id": run_id,
             "proof_scope": RELATION, "source_receipt_sha256": digest(output),
             "chain_height_is_caller_metadata": True, "capital_release_authorized": False}
    return {"schema": "capital-bound/nova-adapter/v1", "run_id": run_id,
            "status": "limited_nova_relation_verified", "relation": RELATION,
            "proof_cryptographically_verified": True, "evidence_verified": False,
            "native_authorization_verified_by_adapter": False,
            "native_receipt_bound_but_unauthenticated": native_raw is not None,
            "bitcoin_spendability_proved": False, "capital_release_authorized": False,
            "started_at_utc": started, "observed_at_utc": ended.isoformat(),
            "verifier_executable_sha256": digest(executable),
            "expected_file_sha256": digest(expected_raw),
            "native_receipt_sha256": digest(native_raw) if native_raw is not None else None,
            "source_artifacts": {name: {"bytes": len(data), "sha256": digest(data)}
                                 for name, data in raw.items()},
            "verifier_receipt_sha256": digest(output), "verifier_receipt": receipt,
            "resources": {"wall_seconds": time.monotonic() - start,
                "user_cpu_seconds": after.ru_utime - before.ru_utime,
                "system_cpu_seconds": after.ru_stime - before.ru_stime,
                "child_max_rss_kib_linux": after.ru_maxrss,
                "rss_scope": "child high-water mark for this adapter process; use a fresh CLI process",
                "address_space_limit_bytes": MEMORY_LIMIT, "cpu_limit_seconds": CPU_LIMIT,
                "timeout_seconds": timeout, "rayon_threads": 2, "gpu_used": False},
            "events": [event]}


def import_bitvm(receipt, transactions):
    """Import actual funded-run shapes; preserve their claimed evidence boundary.

    Input receipts have heights but no observer clock or complete reserve ledger.
    This adapter intentionally emits observations, never capital ledger events.
    """
    if (receipt.get("schema"), receipt.get("status"), receipt.get("network")) != (
            "babe-pilot/funded-regtest/v1", "passed", "regtest"):
        raise ValueError("expected funded BABE regtest receipt v1")
    scope = receipt.get("scope", {})
    for field in ("full_application_withdrawal", "reorg_rollback_exercised",
                  "independent_operator_challenger_processes"):
        if scope.get(field) is not False:
            raise ValueError(f"unsupported funded receipt scope: {field}")
    for key in ("graph_binary_sha256", "release_binary_sha256"):
        hex32(receipt.get(key), key)
    if not isinstance(transactions, dict):
        raise ValueError("transactions must be a JSON object")
    events = receipt.get("events")
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError("expected bounded event list")
    observations, mined, funding, terminal = [], {}, {}, {}
    last_height = 0
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        height = integer(event.get("height"), "event height")
        if height < last_height:
            raise ValueError("funded v1 receipt has a height rollback")
        last_height = height
        kind = event.get("event")
        if not isinstance(kind, str) or not kind:
            raise ValueError("event name required")
        observed = {"source_index": index, "source_event": kind, "height": height,
                    "observation_authenticated": False}
        if "scenario" in event:
            observed["scenario"] = event["scenario"]
        if kind == "confirmed_spend":
            check, txid = event.get("check"), hex32(event.get("txid"), "transaction id")
            tx = transactions.get(check)
            if not isinstance(tx, dict) or tx.get("txid") != txid:
                raise ValueError("confirmed spend differs from transaction catalogue")
            if txid in mined or check in terminal:
                raise ValueError("duplicate confirmed transaction")
            encoded = tx.get("hex")
            if not isinstance(encoded, str) or not encoded or len(encoded) > 2 * MAX_RECEIPT \
                    or not re.fullmatch(r"(?:[0-9a-f]{2})+", encoded):
                raise ValueError("invalid bounded transaction encoding")
            vsize = integer(event.get("vsize"), "vsize", 1)
            weight = integer(event.get("weight_wu"), "weight", 1)
            if vsize != (weight + 3) // 4 or tx.get("vsize") != vsize \
                    or tx.get("weight_wu") != weight:
                raise ValueError("transaction size fields disagree")
            block = hex32(event.get("block_hash"), "block hash")
            mined[txid] = {"txid": txid, "check": check, "height": height,
                           "vsize": vsize, "weight_wu": weight,
                           "block_hash": block, "transaction_bytes_sha256": digest(bytes.fromhex(encoded)),
                           "transaction_id_recomputed": False}
            terminal[check] = mined[txid]
            observed.update(mined[txid])
        elif kind == "funding_confirmed_before_selection":
            scenario = event.get("scenario")
            outpoint = event.get("funding_outpoint")
            if not isinstance(scenario, str) or scenario in funding or not isinstance(outpoint, str) \
                    or not re.fullmatch(r"[0-9a-f]{64}:(0|[1-9][0-9]*)", outpoint):
                raise ValueError("invalid or duplicate scenario funding")
            transaction = terminal.get(scenario + "_funding")
            if transaction is None or transaction["txid"] != outpoint.split(":")[0] \
                    or transaction["height"] != height or transaction["block_hash"] != event.get("block_hash"):
                raise ValueError("funding observation lacks matching mined transaction")
            funding[scenario] = {"height": height, "funding_outpoint": outpoint}
            observed["funding_outpoint"] = outpoint
        elif kind in {"challenge_selected_after_funding", "durable_labels_released_after_confirmed_challenge"}:
            scenario = event.get("scenario")
            if scenario not in funding or height < funding[scenario]["height"]:
                raise ValueError("selection or label delivery precedes funding")
            if kind == "durable_labels_released_after_confirmed_challenge":
                challenge = terminal.get(scenario + "_challenge")
                if challenge is None or challenge["txid"] != event.get("challenge_txid"):
                    raise ValueError("label delivery lacks the matching mined challenge")
                observed["capital_release_authorized"] = False
        observations.append(observed)
    scenarios = receipt.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) > 10000:
        raise ValueError("expected bounded scenario list")
    results, seen = [], set()
    suffixes = {"assertion_timeout": "_first_valid_block", "withholding": "_first_valid_block",
                "operator_payout": "_payout_first_valid_block", "disprove": "_disprove"}
    for scenario in scenarios:
        name = scenario.get("name")
        end = scenario.get("terminal")
        if not isinstance(name, str) or name in seen or name not in funding or end not in suffixes \
                or scenario.get("confirmed") is not True:
            raise ValueError("invalid confirmed scenario")
        seen.add(name)
        final = terminal.get(name + suffixes[end])
        if final is None or final["height"] < funding[name]["height"]:
            raise ValueError("scenario terminal has no matching mined spend")
        results.append({"name": name, "terminal": end, **funding[name],
            "terminal_height": final["height"], "terminal_txid": final["txid"],
            "funding_to_terminal_blocks_as_reported": final["height"] - funding[name]["height"],
            "capital_recovered_sat": None, "elapsed_observer_seconds": None})
    return {"schema": "capital-bound/bitvm-observations/v1", "network_as_supplied": "regtest",
            "evidence_verified": False, "bitcoin_spendability_proved": False,
            "capital_release_authorized": False, "capital_events": [],
            "source_scope": scope, "observations": observations, "scenarios": results,
            "mined_transactions_as_reported": list(mined.values()),
            "total_mined_vsize_as_reported": sum(tx["vsize"] for tx in mined.values()),
            "limits": "Imported receipt consistency only. Observer timestamps, canonical backing lineage, amounts, fees, active-chain authentication and actual reuse require the node adapter."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    nova = sub.add_parser("verify-nova")
    for field in ("verifier", "verifier-sha256", "bundle", "expect", "expect-sha256", "out"):
        nova.add_argument("--" + field, required=True)
    nova.add_argument("--native-receipt")
    nova.add_argument("--height", type=int, default=0)
    nova.add_argument("--run-id", default="capital-bound")
    nova.add_argument("--timeout", type=int, default=120)
    bitvm = sub.add_parser("import-bitvm")
    bitvm.add_argument("--receipt", required=True)
    bitvm.add_argument("--transactions", required=True)
    bitvm.add_argument("--out", required=True)
    args = parser.parse_args()
    if Path(args.out).exists():
        parser.error("output path already exists")
    try:
        if args.command == "verify-nova":
            result = run_verifier(args.verifier, args.verifier_sha256, args.bundle, args.expect,
                args.expect_sha256, args.height, args.run_id, args.native_receipt, args.timeout)
        else:
            receipt = read_bounded(args.receipt, MAX_RECEIPT)
            transactions = read_bounded(args.transactions, 16 * MAX_RECEIPT)
            result = import_bitvm(parse_json(receipt), parse_json(transactions))
            result["source_receipt_sha256"] = digest(receipt)
            result["source_transactions_sha256"] = digest(transactions)
        with open(args.out, "x", encoding="utf-8") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"status": result.get("status", "observations_imported"),
                      "output": args.out, "evidence_verified": False,
                      "capital_release_authorized": False}))


if __name__ == "__main__":
    main()
