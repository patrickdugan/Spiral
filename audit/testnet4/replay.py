"""Read-only public-header audit; no wallet, RPC authentication, or node mutation.

Reads Bitcoin Core XOR-obfuscated blk records by seeking over transactions.
Anchors a historical branch to the last public UpdateTip entry. This is NOT a
consensus validator, a current chain query, or a live Lightning experiment.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import socket
import struct
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

MAGIC = bytes.fromhex("1c163f28")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(raw: bytes, key: bytes, offset: int) -> bytes:
    return bytes(value ^ key[(offset + index) % 8] for index, value in enumerate(raw))


def header_record(header: bytes) -> dict:
    digest = hashlib.sha256(hashlib.sha256(header).digest()).digest()
    bits = struct.unpack_from("<I", header, 72)[0]
    exponent, mantissa = bits >> 24, bits & 0x007fffff
    target = (mantissa << (8 * (exponent - 3))) if exponent >= 3 else (mantissa >> (8 * (3 - exponent)))
    return {
        "hash": digest[::-1].hex(), "previous": header[4:36][::-1].hex(),
        "timestamp": struct.unpack_from("<I", header, 68)[0], "bits": f"{bits:08x}",
        "pow_target_met": 0 < target < 2**256 and not bits & 0x00800000 and int.from_bytes(digest, "little") <= target,
        "header_hex": header.hex(),
    }


def read_headers(blocks: Path) -> tuple[dict, list]:
    key_path = blocks / "xor.dat"
    key = key_path.read_bytes() if key_path.exists() else bytes(8)
    if len(key) != 8:
        raise ValueError("expected Core's eight-byte disk-obfuscation key")
    headers, receipts = {}, []
    for path in sorted(blocks.glob("blk*.dat")):
        size, count, header_digest = path.stat().st_size, 0, hashlib.sha256()
        with path.open("rb") as stream:
            while stream.tell() + 8 <= size:
                offset = stream.tell()
                framing = decode(stream.read(8), key, offset)
                if framing == bytes(8):
                    break  # Core preallocation, not a block
                if framing[:4] != MAGIC:
                    # Raw zero tails can occur in preallocated obfuscated files.
                    stream.seek(offset)
                    if stream.read(min(4096, size - offset)) == bytes(min(4096, size - offset)):
                        break
                    raise ValueError(f"unexpected testnet4 framing: {path.name}:{offset}")
                length = struct.unpack_from("<I", framing, 4)[0]
                if not 81 <= length <= 4_000_000 or offset + 8 + length > size:
                    raise ValueError(f"truncated or invalid record: {path.name}:{offset}")
                header = decode(stream.read(80), key, offset + 8)
                record = header_record(header)
                if not record["pow_target_met"]:
                    raise ValueError("stored header does not meet its encoded target")
                record.update(file=path.name, offset=offset, serialized_block_bytes=length)
                headers[record["hash"]] = record
                header_digest.update(struct.pack("<Q", offset) + header)
                count += 1
                stream.seek(offset + 8 + length)
        receipts.append({"file": path.name, "bytes": size, "records": count,
                         "offset_and_decoded_headers_sha256": header_digest.hexdigest()})
    return headers, receipts


def summarize(values: list[int]) -> dict:
    ordered = sorted(values)
    return {"n": len(values), "min": min(values), "median": median(values),
            "p95_nearest_rank": ordered[max(0, (95 * len(values) + 99) // 100 - 1)],
            "max": max(values), "nonpositive": sum(v <= 0 for v in values)}


def replay_scenarios(chain: list[dict]) -> list[dict]:
    """Declared ordinal experiment: one demand per block, not wall-clock latency.

    Submission just after block b; synthetic funding inclusion at b+1; opening
    depth d activates b+d. A unit arrival consumes one of 10 directional units.
    Horizons 3, 6, 12 blocks are assumptions, never fitted chain observations.
    """
    results = []
    for horizon in (3, 6, 12):
        for depth in (0, 1, 3, 6):
            for inclusion_lag in (1, 3):
                # d=0 is the original instantaneous baseline, not a real zeroconf model.
                activation = 0 if depth == 0 else inclusion_lag + depth - 1
                attempts = horizon
                delivered = sum(1 for block in range(1, horizon + 1) if block >= activation)
                delivered = min(10, delivered)
                anchors = []
                for start in range(0, len(chain) - horizon, horizon):
                    anchors.append({"start_height": chain[start]["height"],
                                    "end_height": chain[start + horizon]["height"]})
                results.append({"horizon_blocks": horizon, "depth": depth,
                                "inclusion_lag_blocks": inclusion_lag,
                                "activation_offset": activation, "demand_count": attempts,
                                "delivered": delivered, "delivery_fraction": delivered / attempts,
                                "nonoverlapping_header_windows": len(anchors),
                                "first_window": anchors[0] if anchors else None,
                                "interpretation": "synthetic ordinal gate, identical across windows; not independent replications"})
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datadir", type=Path, default=Path("D:/BitcoinTestnet/testnet4"))
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results")
    parser.add_argument("--headers", type=int, default=512)
    args = parser.parse_args()
    if args.headers < 12:
        raise ValueError("at least 12 headers required")
    log_bytes = (args.datadir / "debug.log").read_bytes()
    tips = re.findall(rb"(\d{4}-\d{2}-\d{2}T\S+) UpdateTip: new best=([0-9a-f]{64}) height=(\d+)", log_bytes)
    if not tips:
        raise ValueError("no public UpdateTip anchor; refusing to invent chain tip")
    observed, tip_hash, tip_height = tips[-1]
    records, file_receipts = read_headers(args.datadir / "blocks")
    chain, cursor = [], tip_hash.decode()
    while cursor in records and len(chain) < args.headers:
        chain.append(dict(records[cursor], height=int(tip_height) - len(chain)))
        cursor = records[cursor]["previous"]
    chain.reverse()
    if len(chain) != args.headers:
        raise ValueError(f"only {len(chain)} linked headers available")
    assert all(b["previous"] == a["hash"] for a, b in zip(chain, chain[1:]))
    intervals = [b["timestamp"] - a["timestamp"] for a, b in zip(chain, chain[1:])]
    windows = {str(depth): summarize([chain[i+depth]["timestamp"] - chain[i]["timestamp"]
                                    for i in range(len(chain) - depth)]) for depth in (1, 3, 6, 12)}
    try:
        with socket.create_connection(("127.0.0.1", 48332), timeout=1.5):
            rpc_status = "TCP reachable; no RPC or authentication attempted"
    except OSError:
        rpc_status = "TCP unreachable at inspection; historical replay only"
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    with (out / "headers.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(chain[0]))
        writer.writeheader()
        writer.writerows(chain)
    summary = {
        "schema": "spiral-testnet4-header-replay-v1", "generated_utc": datetime.now(timezone.utc).isoformat(),
        "data_directory": str(args.datadir), "source_log_sha256": sha(log_bytes),
        "script_sha256": sha(Path(__file__).read_bytes()), "file_receipts": file_receipts,
        "scope": "historical testnet4 public-header replay, not live LN, no wallet access or transactions",
        "checks": ["testnet4 magic", "double-SHA256 header identity", "encoded proof-of-work target", "512 parent links anchored to last logged tip"],
        "unchecked": ["current active tip", "full difficulty/consensus rules", "transactions/merkle roots", "UTXO state", "actual funding inclusion", "LN protocol"],
        "rpc_status": rpc_status, "tip_log_observed_utc": observed.decode(),
        "tip_hash": tip_hash.decode(), "tip_height": int(tip_height),
        "first_height": chain[0]["height"], "header_count": len(chain),
        "headers_csv_sha256": sha((out / "headers.csv").read_bytes()),
        "header_time_intervals_seconds": summarize(intervals), "header_time_windows_seconds": windows,
        "clock_warning": "Miner timestamps are not observed arrival/inclusion times; negative differences are possible. No latency forecast or clamp-to-zero used.",
        "settlement_scenarios": replay_scenarios(chain),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("scope", "rpc_status", "tip_height", "first_height", "header_count", "header_time_intervals_seconds")}, indent=2))


if __name__ == "__main__":
    main()
