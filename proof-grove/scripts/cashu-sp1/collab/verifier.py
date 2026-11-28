"""Coordinator-side untrusted root verification gate and atomic live-reducer merger.

Ports the two-gate trust boundary of `fleet.py` + `merge-cloud-group-roots.py`:
  Gate 1 — CUDA reducer receipt check (`cuda_reduction_verified` + exact group/VK/manifest/SHA-256 pins).
  Gate 2 — Independent CPU verification on the coordinator host via pinned
           `replay-reduction-cpu ... --check-inputs` (`cpu_reduction_inputs_verified`).
  Gate 3 — Atomic placement into `<compose_dir>/groups/NNNNNN/` (`reduction.bin`,
           `result.json`, `cpu-verify.json`) for reuse by `compose_core_bounded.py`.

A contributor is completely untrusted: contributor-supplied CPU check files are ignored;
the coordinator always runs its own pinned `replay-reduction-cpu --check-inputs`.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from .schema import (
    CPU_REDUCTION_MANIFEST_SCHEMA,
    CollabError,
    canonical_json,
    require_hex64,
    sha256_bytes,
    verify_pinned_file,
)


@dataclass(frozen=True)
class VerificationResult:
    accepted: bool
    reason: str
    reduction_sha256: str
    cpu_verify_seconds: float
    cpu_receipt: dict | None = None
    merged_slot: str | None = None


def check_cuda_receipt(work_order: dict, reduction_bytes: bytes, cuda_receipt: dict) -> tuple[bool, str, str]:
    """Gate 1: validate raw proof digest and CUDA reducer receipt against the assigned work order."""
    actual_sha = sha256_bytes(reduction_bytes)
    if not isinstance(cuda_receipt, dict):
        return False, "invalid_cuda_receipt", actual_sha
    if cuda_receipt.get("status") != "cuda_reduction_verified":
        return False, "bad_cuda_status", actual_sha
    rec_sha = cuda_receipt.get("reduction_sha256")
    if rec_sha != actual_sha:
        return False, "sha256_mismatch", actual_sha
    if cuda_receipt.get("program_vk_digest") != work_order["program_vk_digest"]:
        return False, "vk_or_manifest_mismatch", actual_sha
    if cuda_receipt.get("run_manifest_sha256") != work_order["run_manifest_sha256"]:
        return False, "vk_or_manifest_mismatch", actual_sha
    if cuda_receipt.get("shard_index_sha256") != work_order["shard_index_sha256"]:
        return False, "vk_or_manifest_mismatch", actual_sha
    if cuda_receipt.get("group_id") != work_order["group_id"]:
        return False, "group_mismatch", actual_sha
    if (
        cuda_receipt.get("shard_start") != work_order["shard_start"]
        or cuda_receipt.get("shard_end") != work_order["shard_end"]
        or cuda_receipt.get("group_shards") != work_order["group_shards"]
    ):
        return False, "range_mismatch", actual_sha
    if "range" not in cuda_receipt or not isinstance(cuda_receipt["range"], dict):
        return False, "missing_range", actual_sha
    return True, "ok", actual_sha


def run_cpu_verifier(
    *,
    work_order: dict,
    reduction_bytes: bytes,
    reduction_sha256: str,
    cuda_receipt: dict,
    cpu_checker_path: Path,
    cpu_checker_sha256: str,
    run_json_path: Path,
    program_key_path: Path,
    timeout_seconds: int = 180,
) -> tuple[bool, str, dict | None, float]:
    """Gate 2: independently run pinned `replay-reduction-cpu ... --check-inputs` on coordinator."""
    t0 = time.monotonic()
    verify_pinned_file(cpu_checker_path, cpu_checker_sha256, "replay-reduction-cpu")
    verify_pinned_file(run_json_path, work_order["run_manifest_sha256"], "run.json")

    with tempfile.TemporaryDirectory(prefix=f"cashu-cpu-verify-{work_order['group_id']}-") as tmp:
        stage = Path(tmp) / "input"
        cap = stage / "reduction-failure"
        out_dir = Path(tmp) / "out"
        cap.mkdir(parents=True)
        out_dir.mkdir(parents=True)
        shutil.copyfile(run_json_path, stage / "run.json")
        (cap / "child-00.bin").write_bytes(reduction_bytes)

        range_literal = canonical_json(cuda_receipt["range"])
        manifest = {
            "schema": CPU_REDUCTION_MANIFEST_SCHEMA,
            "is_complete": False,
            "group_id": work_order["group_id"],
            "shard_start": work_order["shard_start"],
            "shard_end": work_order["shard_end"],
            "group_shards": work_order["group_shards"],
            "shards_manifest_sha256": work_order["shards_manifest_sha256"],
            "range_literal": range_literal,
            "children": [
                {
                    "range_literal": range_literal,
                    "file": "child-00.bin",
                    "bytes": len(reduction_bytes),
                    "sha256": reduction_sha256,
                }
            ],
        }
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        manifest_sha = sha256_bytes(manifest_bytes)
        (cap / "manifest.json").write_bytes(manifest_bytes)

        checker = Path(cpu_checker_path).resolve()
        # Support native ELF/PE executables as well as Python calibration scripts (.py or shebang).
        first_line = checker.read_bytes()[:64]
        is_python = checker.suffix.lower() == ".py" or (first_line.startswith(b"#!") and b"python" in first_line.lower())
        if is_python:
            cmd = [
                sys.executable,
                "-B",
                str(checker),
                str(stage),
                str(Path(program_key_path).resolve()),
                manifest_sha,
                str(out_dir),
                "--check-inputs",
            ]
        else:
            cmd = [
                str(checker),
                str(stage),
                str(Path(program_key_path).resolve()),
                manifest_sha,
                str(out_dir),
                "--check-inputs",
            ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "cpu_verify_timeout", None, time.monotonic() - t0

        elapsed = time.monotonic() - t0
        if proc.returncode != 0:
            return False, "cpu_verify_failed", {"returncode": proc.returncode, "stderr": proc.stderr[-500:]}, elapsed

        result_path = out_dir / "result.json"
        if not result_path.is_file():
            return False, "cpu_verify_missing_receipt", None, elapsed
        try:
            cpu_receipt = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False, "cpu_verify_invalid_json", None, elapsed

        # Exact assertions mirroring run-cashu-v4-cuda-archive.sh lines 428-431.
        if (
            cpu_receipt.get("status") != "cpu_reduction_inputs_verified"
            or cpu_receipt.get("child_sha256") != [reduction_sha256]
            or cpu_receipt.get("run_manifest_sha256") != work_order["run_manifest_sha256"]
            or cpu_receipt.get("program_vk_digest") != work_order["program_vk_digest"]
            or cpu_receipt.get("range") != cuda_receipt["range"]
        ):
            return False, "cpu_verify_receipt_mismatch", cpu_receipt, elapsed
        return True, "ok", cpu_receipt, elapsed


def merge_verified_group_root(
    compose_dir: Path,
    work_order: dict,
    reduction_bytes: bytes,
    cuda_receipt: dict,
    cpu_receipt: dict,
) -> Path:
    """Gate 3: atomically place verified group root into `<compose_dir>/groups/NNNNNN/`.

    Never overwrites an already-present group slot (matching `merge-cloud-group-roots.py`
    and `compose_core_bounded.py` group reuse semantics).
    """
    groups_dir = Path(compose_dir).resolve() / "groups"
    groups_dir.mkdir(parents=True, exist_ok=True)
    target = groups_dir / work_order["group_id"]
    if target.exists():
        return target

    staging_parent = tempfile.mkdtemp(prefix=f".stage-{work_order['group_id']}-", dir=groups_dir)
    staged = Path(staging_parent) / work_order["group_id"]
    try:
        staged.mkdir()
        (staged / "reduction.bin").write_bytes(reduction_bytes)
        (staged / "result.json").write_text(
            json.dumps(cuda_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (staged / "cpu-verify.json").write_text(
            json.dumps(cpu_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.rename(staged, target)
        except OSError:
            if not target.exists():
                raise
    finally:
        shutil.rmtree(staging_parent, ignore_errors=True)
    return target


def verify_and_merge_submission(
    *,
    work_order: dict,
    reduction_bytes: bytes,
    cuda_receipt: dict,
    cpu_checker_path: Path,
    cpu_checker_sha256: str,
    run_json_path: Path,
    program_key_path: Path,
    compose_dir: Path,
    timeout_seconds: int = 180,
) -> VerificationResult:
    """Run Gates 1, 2, and 3 in strict order."""
    ok1, reason1, red_sha = check_cuda_receipt(work_order, reduction_bytes, cuda_receipt)
    if not ok1:
        return VerificationResult(False, reason1, red_sha, 0.0)

    ok2, reason2, cpu_receipt, elapsed = run_cpu_verifier(
        work_order=work_order,
        reduction_bytes=reduction_bytes,
        reduction_sha256=red_sha,
        cuda_receipt=cuda_receipt,
        cpu_checker_path=cpu_checker_path,
        cpu_checker_sha256=cpu_checker_sha256,
        run_json_path=run_json_path,
        program_key_path=program_key_path,
        timeout_seconds=timeout_seconds,
    )
    if not ok2:
        return VerificationResult(False, reason2, red_sha, elapsed, cpu_receipt=cpu_receipt)

    slot = merge_verified_group_root(
        compose_dir=compose_dir,
        work_order=work_order,
        reduction_bytes=reduction_bytes,
        cuda_receipt=cuda_receipt,
        cpu_receipt=cpu_receipt,
    )
    return VerificationResult(True, "verified_and_merged", red_sha, elapsed, cpu_receipt=cpu_receipt, merged_slot=str(slot))
