"""Verify a bounded prefix of saved Cashu Core STARKs without stopping the prover."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic

from core_progress import CORE_HEADER_SIZE, SHA256, execution_interval, execution_reference, load_metadata


MAX_SHARD_BYTES = 2 * 1024 * 1024
MAX_SHARDS = 512
MAX_EVENT_BYTES = 8192
PREFIX_REJECTION = ("Error: verifying the complete Core shard chain\n\nCaused by:\n"
                    "    invalid public values: next_pc != HALT_PC: execution should have halted")


def check_pin(path, expected):
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"{path.name} differs from its independent SHA-256 pin")


def event_keys(path, count):
    if not 1 <= count <= MAX_SHARDS:
        raise ValueError("expected a bounded Core prefix")
    keys = {}
    with path.open("rb") as stream:
        while raw := stream.readline(MAX_EVENT_BYTES + 1):
            if len(raw) > MAX_EVENT_BYTES:
                raise ValueError("Core progress event exceeds its byte limit")
            if not raw.endswith(b"\n"):
                break
            row = json.loads(raw)
            if row.get("kind") != "shard" or row.get("replayed") is not False:
                continue
            key = row.get("key")
            if not isinstance(key, str) or not re.fullmatch("[0-9a-f]{16}", key) or key in keys:
                raise ValueError("invalid or repeated Core progress event key")
            keys[key] = None
            if len(keys) == count:
                return keys
    raise ValueError("the checkpoint has not saved the whole requested prefix")


def stage_prefix(run, archive, count, nonce, reserve_bytes):
    locations = event_keys(run / "progress.jsonl", count)
    with os.scandir(run / "memo/shard") as children:
        for entry in children:
            key = entry.name[:16]
            if key in locations and SHA256.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False):
                if locations[key] is not None:
                    raise ValueError("ambiguous Core memo directory key")
                locations[key] = Path(entry.path)
    if any(path is None for path in locations.values()):
        raise ValueError("a saved Core memo directory is missing")

    next_clock = 1
    index = []
    with archive.open("xb") as stream:
        stream.write(struct.pack("<IQ", 0, count))
        for path in locations.values():
            _, memo = load_metadata(path / "manifest.json")
            with (path / "out0").open("rb") as proof:
                body = proof.read(MAX_SHARD_BYTES + 1)
            if not CORE_HEADER_SIZE < len(body) <= MAX_SHARD_BYTES:
                raise ValueError("Core memo proof exceeds its prefix audit budget")
            pin = hashlib.sha256(body).digest()
            if pin != bytes(memo["out0_sha256"]):
                raise ValueError("Core memo proof differs from its saved digest")
            pts = execution_interval(body[:CORE_HEADER_SIZE], nonce)
            if pts is None or pts[0] != next_clock:
                raise ValueError("saved Core prefix does not advance a contiguous execution clock")
            next_clock = pts[1]
            if shutil.disk_usage(archive.parent).free < reserve_bytes + len(body):
                raise ValueError("staging the Core prefix would cross the scratch reserve")
            stream.write(body)
            index.append({"memo": path.name, "proof_sha256": pin.hex(), "bytes": len(body), "clock_interval": pts})
    return index


def verify_starks(args, archive, public):
    started = monotonic()
    verified = subprocess.run([args.verifier.resolve(), "--parallel-shards", args.elf.resolve(), archive, public,
                               args.core_key.resolve(), args.core_key_sha256, args.program_vk_digest], capture_output=True,
                              text=True, timeout=240, check=False)
    stderr = verified.stderr.rstrip()
    if (verified.returncode != 1 or verified.stdout or not stderr.endswith(PREFIX_REJECTION)
            or not stderr.startswith(f"Verifying {args.count} Core shards\n")):
        raise ValueError(f"the pinned verifier did not reach its incomplete-chain check: {stderr[-2048:]}")
    return stderr, monotonic() - started


def audit(args):
    manifest_data, manifest = load_metadata(args.run / "run.json")
    manifest_digest = hashlib.sha256(manifest_data).hexdigest()
    if manifest_digest != args.manifest_sha256:
        raise ValueError("run manifest differs from its independent pin")
    receipt_data, receipt = load_metadata(args.execution_receipt)
    _, trace_clock = execution_reference(manifest, receipt)
    if trace_clock is None:
        raise ValueError("the independent guest trace clock is required")
    config = manifest["config"]
    nonce = tuple(config["nonce"]) if config.get("controller_nonce") is True else (0, 0, 0, 0)
    check_pin(args.elf, config["elf_sha256"])
    check_pin(args.core_key, args.core_key_sha256)
    check_pin(args.verifier, args.verifier_sha256)
    with TemporaryDirectory(prefix="cashu-core-prefix-", dir=args.scratch) as directory:
        archive = Path(directory) / "incomplete.bin"
        started = monotonic()
        shards = stage_prefix(args.run, archive, args.count, nonce, args.scratch_reserve_bytes)
        staging_seconds = monotonic() - started
        end = shards[-1]["clock_interval"][1]
        if end >= trace_clock + 1:
            raise ValueError("expected unfinished execution under the pinned guest clock")
        with archive.open("rb") as stream:
            archive_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        transcript, seconds = verify_starks(args, archive, manifest["expected_public_sha256"])
    return {"schema": "proof-grove/cashu-core-prefix-audit/v1", "status": "individual_core_shard_starks_verified",
            "complete_core_archive_verified": False, "complete_public_chain_verified": False,
            "run_manifest_sha256": manifest_digest, "elf_sha256": config["elf_sha256"],
            "expected_final_public_sha256": manifest["expected_public_sha256"], "trace_clock_reference": trace_clock,
            "execution_receipt_sha256": hashlib.sha256(receipt_data).hexdigest(), "core_key_sha256": args.core_key_sha256,
            "program_vk_digest": args.program_vk_digest, "verifier_sha256": args.verifier_sha256,
            "shard_count": args.count, "incomplete_archive_sha256": archive_digest, "execution_clock_end": end,
            "staging_seconds": staging_seconds, "verification_seconds": seconds, "verifier_transcript": transcript,
            "shards": shards}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "execution-receipt", "elf", "core-key", "verifier", "scratch", "out"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    for name in ("manifest-sha256", "core-key-sha256", "program-vk-digest", "verifier-sha256"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--count", type=int, default=MAX_SHARDS)
    parser.add_argument("--scratch-reserve-bytes", type=int, default=0)
    args = parser.parse_args()
    pins = (args.manifest_sha256, args.core_key_sha256, args.program_vk_digest, args.verifier_sha256)
    if args.out.exists() or args.scratch_reserve_bytes < 0 or any(not SHA256.fullmatch(pin) for pin in pins):
        parser.error("use a new receipt, canonical SHA-256 pins and a nonnegative scratch reserve")
    try:
        result = audit(args)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Cashu Core prefix audit refused: {error}\n")
    print(json.dumps({key: value for key, value in result.items() if key not in ("shards", "verifier_transcript")}))


if __name__ == "__main__":
    main()
