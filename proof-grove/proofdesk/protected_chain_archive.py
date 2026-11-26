"""Archive and replay the public regtest blocks behind a protected withdrawal checkpoint."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from .domain import Refused, hash32, positive
from .protected_reserve import GENESIS
from .verifier import read_bounded


MAX_BLOCKS = 4096
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def _header_hash(block):
    return hashlib.sha256(hashlib.sha256(block[:80]).digest()).digest()[::-1].hex()


def _block(line, previous):
    try:
        raw = bytes.fromhex(line.decode("ascii"))
    except (ValueError, UnicodeError):
        raise ValueError("invalid block encoding in regtest archive") from None
    if len(raw) < 81 or raw.hex().encode("ascii") != line or raw[4:36][::-1].hex() != previous:
        raise ValueError("regtest archive block does not extend its pinned predecessor")
    return _header_hash(raw)


def _regtest_tip(rpc):
    info = rpc("getblockchaininfo", [])
    if info["chain"] != "regtest" or rpc("getblockhash", [0]) != GENESIS:
        raise ValueError("block archives require a regtest node")
    return info


def capture(rpc, path, height, anchor):
    positive(height, "height", MAX_BLOCKS)
    hash32(anchor, "anchor")
    tip = _regtest_tip(rpc)
    if tip["blocks"] < height or rpc("getblockhash", [height]) != anchor:
        raise ValueError("the requested checkpoint is outside the active regtest chain")
    archive = bytearray()
    previous = GENESIS
    for index in range(1, height + 1):
        block_hash = rpc("getblockhash", [index])
        line = rpc("getblock", [block_hash, 0]).encode("ascii")
        if len(archive) + len(line) + 1 > MAX_ARCHIVE_BYTES:
            raise ValueError("regtest block archive exceeds its size limit")
        if _block(line, previous) != block_hash:
            raise ValueError("Bitcoin Core returned different block data")
        archive.extend(line + b"\n")
        previous = block_hash
    if previous != anchor or rpc("getblockhash", [height]) != anchor:
        raise ValueError("regtest checkpoint changed during capture")
    with path.open("xb") as stream:
        stream.write(archive)
    return {"schema": "proof-grove/protected-regtest-block-archive/v1", "network": "regtest",
            "genesis": GENESIS, "height": height, "anchor": anchor, "archive_sha256": hashlib.sha256(archive).hexdigest(),
            "archive_bytes": len(archive)}


def inspect_headers(archive, height, anchor):
    """Check the archived headers through an independently supplied checkpoint."""
    positive(height, "height", MAX_BLOCKS)
    hash32(anchor, "anchor")
    if not archive.endswith(b"\n"):
        raise ValueError("regtest archive does not have a complete final block")
    blocks = archive[:-1].split(b"\n")
    if len(blocks) != height:
        raise ValueError("regtest archive does not end at the pinned height")
    hashes = [GENESIS]
    for line in blocks:
        hashes.append(_block(line, hashes[-1]))
    if hashes[-1] != anchor:
        raise ValueError("regtest archive does not open the pinned checkpoint")
    return blocks, hashes


def replay(rpc, path, archive_sha256, height, anchor, *, before_final=None):
    hash32(archive_sha256, "archive_sha256")
    archive = read_bounded(path, MAX_ARCHIVE_BYTES)
    if hashlib.sha256(archive).hexdigest() != archive_sha256 or not archive.endswith(b"\n"):
        raise ValueError("regtest archive differs from the independent byte pin")
    blocks, hashes = inspect_headers(archive, height, anchor)

    tip = _regtest_tip(rpc)
    current = tip["blocks"]
    if not 0 <= current <= height or tip["bestblockhash"] != hashes[current]:
        raise ValueError("the destination regtest chain is not an archive prefix")
    if before_final is not None and current == height:
        raise ValueError("the final block has already been submitted")
    for index in range(current + 1, height + 1):
        if index == height and before_final is not None:
            before_final()
        result = rpc("submitblock", [blocks[index - 1].decode("ascii")])
        if result not in (None, "duplicate") or rpc("getblockhash", [index]) != hashes[index]:
            raise ValueError(f"Bitcoin Core refused block {index}: {result}")
    final = rpc("getblockchaininfo", [])
    if (final["blocks"], final["bestblockhash"]) != (height, anchor):
        raise ValueError("destination regtest tip differs from the pinned checkpoint")
    return {"schema": "proof-grove/protected-regtest-block-replay/v1", "network": "regtest",
            "height": height, "anchor": anchor, "archive_sha256": archive_sha256, "blocks_submitted": height - current}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("capture", "replay"))
    parser.add_argument("archive", type=Path)
    parser.add_argument("--bitcoin-cli", type=Path, required=True)
    parser.add_argument("--datadir", type=Path, required=True)
    parser.add_argument("--rpc-port", type=int)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--archive-sha256")
    args = parser.parse_args()
    if (args.operation == "replay") != bool(args.archive_sha256):
        parser.error("replay requires an independent --archive-sha256 pin")
    command = [str(args.bitcoin_cli.resolve()), "-regtest", f"-datadir={args.datadir.resolve()}", "-stdin"]
    if args.rpc_port is not None:
        command.append(f"-rpcport={args.rpc_port}")

    def rpc(method, params):
        stdin = "".join(f"{param}\n" for param in params)
        process = subprocess.run([*command, method], input=stdin, text=True, capture_output=True, timeout=30, check=True)
        raw = process.stdout.strip()
        if method in ("getblockchaininfo", "getblockhash"):
            return json.loads(raw) if method == "getblockchaininfo" else raw
        return raw or None

    try:
        if args.operation == "capture":
            result = capture(rpc, args.archive, args.height, args.anchor)
        else:
            result = replay(rpc, args.archive, args.archive_sha256, args.height, args.anchor)
    except (OSError, Refused, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"regtest archive refused: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
