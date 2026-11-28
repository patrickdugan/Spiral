"""Schemas, binary pinning, shard-index group slicing, and key-material hygiene checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

KIT_SCHEMA = "proof-grove/cashu-collab-kit/v1"
WORK_ORDER_SCHEMA = "proof-grove/cashu-collab-work-order/v1"
SUBMISSION_SCHEMA = "proof-grove/cashu-collab-submission/v1"
TELEMETRY_SCHEMA = "proof-grove/cashu-collab-telemetry/v1"
SHARD_INDEX_SCHEMA = "nb3/sp1-core-shard-index/v1"
CPU_REDUCTION_MANIFEST_SCHEMA = "nb3-reduction-failure/v1"

GROUP_SIZE = 128
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
GROUP_ID_RE = re.compile(r"^[0-9]{6}$")

# Patterns that must never appear in a contributor kit or work order.
FORBIDDEN_KEY_PATH_TOKENS = (
    "wallet.dat",
    ".cookie",
    ".wif",
    ".priv",
    ".pem",
    ".sec",
    "private_key",
    "privkey",
    "mnemonic",
    "seed_phrase",
    "signing_key",
    "blinding_factor",
    "mint_secret",
    "holder_secret",
    "challenger_secret",
    "descriptor_priv",
)

FORBIDDEN_KEY_JSON_FIELDS = frozenset(
    {
        "private_key",
        "privkey",
        "wif",
        "mnemonic",
        "seed_phrase",
        "xprv",
        "tprv",
        "wallet_rpc",
        "rpc_cookie",
        "rpc_password",
        "holder_secret",
        "mint_secret",
        "challenger_secret",
        "blinding_secret",
        "issuance_preimage",
    }
)

REQUIRED_KIT_BINARIES = ("normalize-core-cuda", "replay-reduction-cuda")
REQUIRED_KIT_PUBLIC_INPUTS = ("core-vk.bin", "program-key.json", "run.json", "cashu-withdrawal.elf")


class CollabError(ValueError):
    """Raised on any pin mismatch, hygiene violation, or protocol error."""


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_hex64(value: Any, name: str) -> str:
    if not isinstance(value, str) or HEX64_RE.fullmatch(value) is None:
        raise CollabError(f"{name} must be a 64-char lowercase hex sha256 digest")
    return value


def format_group_id(group_index: int) -> str:
    if type(group_index) is not int or not 0 <= group_index < 1_000_000:
        raise CollabError(f"invalid group_index: {group_index!r}")
    return f"{group_index:06d}"


def verify_pinned_file(path: Path, expected_sha256: str, label: str) -> str:
    require_hex64(expected_sha256, f"{label}.sha256")
    p = Path(path)
    if p.is_symlink():
        raise CollabError(f"{label} must not be a symlink: {p}")
    if not p.is_file():
        raise CollabError(f"missing pinned file {label}: {p}")
    actual = sha256_file(p)
    if actual != expected_sha256:
        raise CollabError(
            f"sha256 pin mismatch for {label}: got {actual}, expected {expected_sha256}"
        )
    return actual


def assert_no_key_material_in_path(path_str: str) -> None:
    lowered = path_str.replace("\\", "/").lower()
    for token in FORBIDDEN_KEY_PATH_TOKENS:
        if token in lowered:
            raise CollabError(
                f"forbidden wallet/key material pattern '{token}' in contributor artifact path: {path_str}"
            )


def assert_no_key_material_in_obj(obj: Any, *, prefix: str = "") -> None:
    """Recursively reject any wallet, private key, or secret field in contributor payloads."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_lower = str(k).lower()
            if key_lower in FORBIDDEN_KEY_JSON_FIELDS:
                raise CollabError(f"forbidden wallet/key field '{prefix}{k}' in contributor payload")
            assert_no_key_material_in_obj(v, prefix=f"{prefix}{k}.")
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            assert_no_key_material_in_obj(item, prefix=f"{prefix}[{idx}].")
    elif isinstance(obj, str):
        if obj.startswith(("xprv", "tprv", "-----BEGIN ", "cU", "cV", "L", "K")) and len(obj) >= 51:
            # Reject PEM private key headers or extended private keys.
            if obj.startswith(("xprv", "tprv", "-----BEGIN ")):
                raise CollabError(f"forbidden key material value at '{prefix}'")


def assert_kit_directory_clean(kit_dir: Path) -> None:
    root = Path(kit_dir).resolve()
    if not root.is_dir():
        raise CollabError(f"kit directory does not exist: {root}")
    for entry in root.rglob("*"):
        if entry.is_symlink():
            raise CollabError(f"symlinks are forbidden in contributor kit: {entry.name}")
        rel = entry.relative_to(root).as_posix()
        assert_no_key_material_in_path(rel)


def load_shard_index(index_path: Path, expected_sha256: str | None = None) -> tuple[dict, str]:
    p = Path(index_path)
    raw = p.read_bytes()
    actual_sha = sha256_bytes(raw)
    if expected_sha256 is not None:
        require_hex64(expected_sha256, "shard_index_sha256")
        if actual_sha != expected_sha256:
            raise CollabError(
                f"shard-index.json sha256 mismatch: got {actual_sha}, expected {expected_sha256}"
            )
    data = json.loads(raw.decode("utf-8"))
    if data.get("schema") != SHARD_INDEX_SCHEMA:
        raise CollabError(f"unexpected shard index schema: {data.get('schema')!r}")
    shards = data.get("shards")
    if not isinstance(shards, list) or not shards:
        raise CollabError("shard index has no shards")
    require_hex64(data.get("archive_sha256"), "archive_sha256")
    require_hex64(data.get("program_vk_digest"), "program_vk_digest")
    require_hex64(data.get("public_output_sha256"), "public_output_sha256")
    return data, actual_sha


def groups_from_shard_index(
    index_data: dict,
    index_sha256: str,
    *,
    run_manifest_sha256: str,
    network: str = "regtest",
    group_size: int = GROUP_SIZE,
) -> list[dict]:
    """Split an authenticated `nb3/sp1-core-shard-index/v1` into independent one-group work orders."""
    if type(group_size) is not int or not 2 <= group_size <= 256:
        raise CollabError(f"invalid group_size: {group_size!r}")
    require_hex64(index_sha256, "index_sha256")
    require_hex64(run_manifest_sha256, "run_manifest_sha256")
    shards = index_data["shards"]
    total = len(shards)
    orders = []
    for g_idx, start in enumerate(range(0, total, group_size)):
        end = min(start + group_size, total)
        slice_shards = shards[start:end]
        base_offset = int(slice_shards[0]["offset"])
        last = slice_shards[-1]
        end_offset = int(last["offset"]) + int(last["length"])
        rel_shards = []
        for ordinal_in_group, entry in enumerate(slice_shards):
            rel_shards.append(
                {
                    "global_ordinal": start + ordinal_in_group + 1,
                    "archive_offset": int(entry["offset"]),
                    "slice_offset": int(entry["offset"]) - base_offset,
                    "length": int(entry["length"]),
                    "sha256": require_hex64(entry["sha256"], f"shard[{start + ordinal_in_group}].sha256"),
                }
            )
        group_id = format_group_id(g_idx)
        slice_digest = sha256_bytes(canonical_json(rel_shards).encode("utf-8"))
        order = {
            "schema": WORK_ORDER_SCHEMA,
            "network": network,
            "group_id": group_id,
            "group_index": g_idx,
            "group_size": group_size,
            "shard_start": start + 1,          # 1-based inclusive (matches SP1 Core index convention)
            "shard_end": end,                  # 1-based inclusive
            "group_shards": end - start,
            "total_shards": total,
            "archive_sha256": index_data["archive_sha256"],
            "archive_size_bytes": int(index_data["archive_size_bytes"]),
            "shard_index_sha256": index_sha256,
            "run_manifest_sha256": run_manifest_sha256,
            "program_vk_digest": index_data["program_vk_digest"],
            "public_output_sha256": index_data["public_output_sha256"],
            "archive_byte_start": base_offset,
            "archive_byte_end": end_offset,
            "slice_bytes": end_offset - base_offset,
            "shards_manifest_sha256": slice_digest,
            "shards": rel_shards,
            "wallet_or_keys_required": False,
        }
        assert_no_key_material_in_obj(order)
        orders.append(order)
    return orders
