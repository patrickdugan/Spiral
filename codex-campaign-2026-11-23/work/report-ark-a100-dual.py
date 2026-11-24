"""Summarize the retrieved Ark and MNR-04 A100 pilot evidence."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import statistics
import tarfile


def collect(file):
    with tarfile.open(file, "r:gz") as archive:
        index = {entry.name.removeprefix("./"): entry for entry in archive if entry.isfile()}

        def read(name):
            if name in index:
                return archive.extractfile(index[name]).read()
            return None

        def encoded_json(name):
            value = read(name)
            return json.loads(value) if value else None

        def number(name):
            value = read(name)
            return int(value) if value else None

        ark = encoded_json("pilot-result.json")
        nova = encoded_json("mnr04/benchmark.json")
        proof_file = read("mnr04/proof/proof.bin")
        guest_result = read("compressed.bin")
        nv = read("gpu-samples.csv") or b""
        gpu_rows = []
        for row in csv.reader(io.StringIO(nv.decode())):
            try:
                gpu_rows.append(tuple(int(value.strip()) for value in row[1:4]))
            except (ValueError, IndexError):
                continue
        ark_rate = ark["per_minute"]["shard"] if ark and ark["status"] == "throughput_sample" else None
        if nova:
            proof = nova["independent_verification"]
            if not proof_file or hashlib.sha256(proof_file).hexdigest() != proof["proof_sha256"]:
                raise RuntimeError("exported MNR-04 proof does not match independent worker verifier")
            if nova["core"]["native"]["txid"] != proof["native"]["txid"]:
                raise RuntimeError("independent MNR-04 proof does not name the Core transaction")
            if not (proof["nova_txid_verified"] and proof["wrong_txid_claim_refused"]):
                raise RuntimeError("MNR-04 independent checks did not pass")
        result = {
            "archived_core_checkpoints": 1727,
            "archived_recursion_checkpoints": 6624,
            "baseline_laptop_fresh_core_per_minute": 4.8,
            "ark": ark,
            "mnr04": nova,
            "ark_speedup_vs_observed_laptop": ark_rate / 4.8 if ark_rate is not None else None,
            "ark_compressed_sha256": hashlib.sha256(guest_result).hexdigest() if guest_result else None,
            "ark_compressed_sdk_verified": False,
            "ark_full_chain_verified": False,
            "provisioning_orchestrator_exit": number("orchestrator-exit-code"),
            "mnr04_exit": number("nova-exit-code"),
            "gpu": (read("gpu-start.txt") or b"").decode().strip() or None,
            "gpu_peak_mib": max((row[1] for row in gpu_rows), default=None),
            "gpu_median_util_percent": statistics.median(row[0] for row in gpu_rows) if gpu_rows else None,
            "provenance": encoded_json("provenance.json"),
        }
    return result


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("export", type=Path)
    cli.add_argument("report", type=Path)
    args = cli.parse_args()
    report = collect(args.export)
    with args.report.open("x", encoding="utf8") as file:
        json.dump(report, file, indent=2)
        file.write("\n")


if __name__ == "__main__":
    main()
