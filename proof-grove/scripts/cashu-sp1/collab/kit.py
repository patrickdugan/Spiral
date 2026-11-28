"""Contributor kit packager, verifier, and one-group work-order builder.

Builds a self-contained, zero-wallet, zero-key contributor kit containing:
  - `kit-manifest.json` with SHA-256 pins for every binary and public proving input;
  - pinned `bin/normalize-core-cuda` and `bin/replay-reduction-cuda`;
  - pinned public inputs (`inputs/core-vk.bin`, `inputs/program-key.json`,
    `inputs/run.json`, `inputs/cashu-withdrawal.elf`);
  - the standalone `contributor.py` runner.

Also extracts exact one-group work orders (`work-order-NNNNNN.json` + optional
contiguous ~186 MiB shard slice `shards-NNNNNN.bin`) verified shard-by-shard
against `core-shard-index.json`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import stat
import sys
import tarfile

from .schema import (
    GROUP_SIZE,
    KIT_SCHEMA,
    REQUIRED_KIT_BINARIES,
    REQUIRED_KIT_PUBLIC_INPUTS,
    CollabError,
    assert_kit_directory_clean,
    assert_no_key_material_in_obj,
    assert_no_key_material_in_path,
    canonical_json,
    groups_from_shard_index,
    load_shard_index,
    require_hex64,
    sha256_bytes,
    sha256_file,
    verify_pinned_file,
)


def package_kit(
    output_dir: Path,
    *,
    network: str,
    binaries: dict[str, Path],
    public_inputs: dict[str, Path],
    shard_index_sha256: str,
    run_manifest_sha256: str,
    program_vk_digest: str,
    public_output_sha256: str,
    group_size: int = GROUP_SIZE,
    backend_kind: str = "sp1-cuda-v6.9",
    tarball_path: Path | None = None,
) -> dict:
    """Create a pinned contributor kit directory (and optional .tar.gz) with zero key material."""
    out = Path(output_dir).resolve()
    if out.exists() and any(out.iterdir()):
        raise CollabError(f"kit output directory must be new or empty: {out}")
    for name in REQUIRED_KIT_BINARIES:
        if name not in binaries:
            raise CollabError(f"missing required contributor binary: {name}")
    for name in REQUIRED_KIT_PUBLIC_INPUTS:
        if name not in public_inputs:
            raise CollabError(f"missing required public proving input: {name}")
    require_hex64(shard_index_sha256, "shard_index_sha256")
    require_hex64(run_manifest_sha256, "run_manifest_sha256")
    require_hex64(program_vk_digest, "program_vk_digest")
    require_hex64(public_output_sha256, "public_output_sha256")

    (out / "bin").mkdir(parents=True, exist_ok=True)
    (out / "inputs").mkdir(parents=True, exist_ok=True)
    (out / "collab").mkdir(parents=True, exist_ok=True)

    pinned_bins: dict[str, dict] = {}
    for name, src in sorted(binaries.items()):
        assert_no_key_material_in_path(name)
        src_p = Path(src).resolve()
        if src_p.is_symlink() or not src_p.is_file():
            raise CollabError(f"binary must be a regular file: {src_p}")
        dst = out / "bin" / name
        shutil.copyfile(src_p, dst)
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        pinned_bins[name] = {
            "relpath": f"bin/{name}",
            "bytes": dst.stat().st_size,
            "sha256": sha256_file(dst),
        }

    pinned_inputs: dict[str, dict] = {}
    for name, src in sorted(public_inputs.items()):
        assert_no_key_material_in_path(name)
        src_p = Path(src).resolve()
        if src_p.is_symlink() or not src_p.is_file():
            raise CollabError(f"public input must be a regular file: {src_p}")
        dst = out / "inputs" / name
        shutil.copyfile(src_p, dst)
        pinned_inputs[name] = {
            "relpath": f"inputs/{name}",
            "bytes": dst.stat().st_size,
            "sha256": sha256_file(dst),
        }

    if pinned_inputs["run.json"]["sha256"] != run_manifest_sha256:
        raise CollabError("packaged run.json sha256 does not match run_manifest_sha256")

    # Copy pure-Python contributor runtime scripts into the kit.
    pkg_dir = Path(__file__).resolve().parent
    pinned_scripts: dict[str, dict] = {}
    for script_name in ("__init__.py", "schema.py", "kit.py", "contributor.py"):
        src_p = pkg_dir / script_name
        if src_p.is_file():
            dst = out / "collab" / script_name
            shutil.copyfile(src_p, dst)
            pinned_scripts[script_name] = {
                "relpath": f"collab/{script_name}",
                "bytes": dst.stat().st_size,
                "sha256": sha256_file(dst),
            }

    manifest = {
        "schema": KIT_SCHEMA,
        "network": network,
        "backend_kind": backend_kind,
        "group_size": group_size,
        "wallet_or_keys_required": False,
        "trust_model": (
            "Contributor is untrusted. Coordinator accepts a group root only after checking "
            "the cuda_reduction_verified receipt and independently running "
            "replay-reduction-cpu --check-inputs on the coordinator host."
        ),
        "pins": {
            "shard_index_sha256": shard_index_sha256,
            "run_manifest_sha256": run_manifest_sha256,
            "program_vk_digest": program_vk_digest,
            "public_output_sha256": public_output_sha256,
        },
        "binaries": pinned_bins,
        "public_inputs": pinned_inputs,
        "scripts": pinned_scripts,
    }
    assert_no_key_material_in_obj(manifest)
    manifest["manifest_sha256"] = sha256_bytes(canonical_json(manifest).encode("utf-8"))
    (out / "kit-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Self-verify hygiene & pins before returning.
    verify_kit(out)

    if tarball_path is not None:
        tb = Path(tarball_path).resolve()
        tb.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tb, "w:gz") as tar:
            for item in sorted(out.rglob("*")):
                if item.is_file():
                    tar.add(item, arcname=item.relative_to(out).as_posix())
        manifest["tarball_sha256"] = sha256_file(tb)
    return manifest


def verify_kit(kit_dir: Path, expected_manifest_sha256: str | None = None) -> dict:
    """Verify every binary/input SHA-256 pin and enforce zero wallet/key material in `kit_dir`."""
    root = Path(kit_dir).resolve()
    assert_kit_directory_clean(root)
    manifest_path = root / "kit-manifest.json"
    if not manifest_path.is_file():
        raise CollabError(f"missing kit-manifest.json in {root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != KIT_SCHEMA:
        raise CollabError(f"unexpected kit schema: {manifest.get('schema')!r}")
    if manifest.get("wallet_or_keys_required") is not False:
        raise CollabError("contributor kit must declare wallet_or_keys_required=false")
    assert_no_key_material_in_obj(manifest)

    recorded_hash = require_hex64(manifest.get("manifest_sha256"), "manifest_sha256")
    body = {k: v for k, v in manifest.items() if k not in ("manifest_sha256", "tarball_sha256")}
    computed_hash = sha256_bytes(canonical_json(body).encode("utf-8"))
    if computed_hash != recorded_hash:
        raise CollabError(f"kit manifest_sha256 mismatch: got {computed_hash}, recorded {recorded_hash}")
    if expected_manifest_sha256 is not None and recorded_hash != expected_manifest_sha256:
        raise CollabError("kit manifest_sha256 differs from coordinator pin")

    for section in ("binaries", "public_inputs", "scripts"):
        entries = manifest.get(section, {})
        if not isinstance(entries, dict):
            raise CollabError(f"invalid kit section: {section}")
        for name, meta in entries.items():
            assert_no_key_material_in_path(name)
            rel = meta["relpath"]
            assert_no_key_material_in_path(rel)
            target = (root / rel).resolve()
            if root not in target.parents:
                raise CollabError(f"kit entry escapes kit root: {rel}")
            verify_pinned_file(target, meta["sha256"], f"{section}.{name}")
            if target.stat().st_size != meta["bytes"]:
                raise CollabError(f"byte length mismatch for {rel}")

    for name in REQUIRED_KIT_BINARIES:
        if name not in manifest.get("binaries", {}):
            raise CollabError(f"kit missing required binary {name}")
    for name in REQUIRED_KIT_PUBLIC_INPUTS:
        if name not in manifest.get("public_inputs", {}):
            raise CollabError(f"kit missing required public input {name}")
    return manifest


def extract_group_slice(archive_path: Path, work_order: dict, output_slice_path: Path) -> str:
    """Extract the contiguous byte slice for one group from `proof.bin` and verify every shard SHA-256."""
    src = Path(archive_path)
    if not src.is_file():
        raise CollabError(f"missing Core archive: {src}")
    if src.stat().st_size != work_order["archive_size_bytes"]:
        raise CollabError(
            f"archive size mismatch: got {src.stat().st_size}, expected {work_order['archive_size_bytes']}"
        )
    start = int(work_order["archive_byte_start"])
    length = int(work_order["slice_bytes"])
    with src.open("rb") as fh:
        fh.seek(start)
        data = fh.read(length)
    if len(data) != length:
        raise CollabError(f"short read from archive for group {work_order['group_id']}")
    for shard in work_order["shards"]:
        s_off = int(shard["slice_offset"])
        s_len = int(shard["length"])
        chunk = data[s_off : s_off + s_len]
        if len(chunk) != s_len:
            raise CollabError(f"truncated shard {shard['global_ordinal']}")
        got = sha256_bytes(chunk)
        if got != shard["sha256"]:
            raise CollabError(
                f"shard {shard['global_ordinal']} sha256 mismatch: got {got}, expected {shard['sha256']}"
            )
    dst = Path(output_slice_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return sha256_bytes(data)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Package or verify a Cashu collaborative proving contributor kit.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser("verify", help="Verify a contributor kit directory.")
    p_verify.add_argument("kit_dir", type=Path)
    p_verify.add_argument("--manifest-sha256", help="Optional expected manifest_sha256.")

    p_order = sub.add_parser("work-order", help="Emit a standalone one-group work order JSON (and optional shard slice).")
    p_order.add_argument("--shard-index", type=Path, required=True)
    p_order.add_argument("--run-manifest-sha256", required=True)
    p_order.add_argument("--group", type=int, required=True, help="0-based group index.")
    p_order.add_argument("--network", default="regtest")
    p_order.add_argument("--group-size", type=int, default=GROUP_SIZE)
    p_order.add_argument("--archive", type=Path, help="Optional proof.bin to extract shards-NNNNNN.bin slice.")
    p_order.add_argument("--out-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.cmd == "verify":
        manifest = verify_kit(args.kit_dir, args.manifest_sha256)
        print(json.dumps({"valid": True, "manifest_sha256": manifest["manifest_sha256"], "network": manifest["network"]}))
        return 0

    index_data, index_sha = load_shard_index(args.shard_index)
    orders = groups_from_shard_index(
        index_data,
        index_sha,
        run_manifest_sha256=args.run_manifest_sha256,
        network=args.network,
        group_size=args.group_size,
    )
    if not 0 <= args.group < len(orders):
        raise CollabError(f"group {args.group} out of range [0, {len(orders) - 1}]")
    order = orders[args.group]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.archive is not None:
        slice_path = out_dir / f"shards-{order['group_id']}.bin"
        order["slice_sha256"] = extract_group_slice(args.archive, order, slice_path)
    order_path = out_dir / f"work-order-{order['group_id']}.json"
    order_path.write_text(json.dumps(order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"group_id": order["group_id"], "work_order": str(order_path), "group_shards": order["group_shards"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
