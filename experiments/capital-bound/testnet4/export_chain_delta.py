"""Export contiguous public Core blocks in Bitcoin's loadblock file format."""
import argparse
import base64
import gzip
import hashlib
import json
import struct
import urllib.request
from pathlib import Path

GENESIS = "00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043"
MAGIC = bytes.fromhex("1c163f28")
MAX_RAW_BYTES = 384 * 1024**2
MAX_RPC_BYTES = 128 * 1024**2
MAX_DELTA_BLOCKS = 10_000


def rpc_client(datadir):
    cookie = (datadir / "testnet4" / ".cookie").read_bytes().strip()
    auth = base64.b64encode(cookie).decode("ascii")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(method, params):
        if not params:
            return []
        payload = [{"jsonrpc": "2.0", "method": method, "params": args, "id": i}
                   for i, args in enumerate(params)]
        request = urllib.request.Request(
            "http://127.0.0.1:48332/",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
        )
        with opener.open(request, timeout=40) as response:
            raw = response.read(MAX_RPC_BYTES + 1)
        if len(raw) > MAX_RPC_BYTES:
            raise ValueError("Oversized Core response")
        entries = json.loads(raw)
        if any(entry.get("error") for entry in entries):
            raise ValueError(f"Bitcoin Core rejected {method}")
        indexed = {entry["id"]: entry["result"] for entry in entries}
        return [indexed[i] for i in range(len(params))]

    return call


def hash_header(block):
    first = hashlib.sha256(block[:80]).digest()
    return hashlib.sha256(first).digest()[::-1].hex()


def file_digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def export(args):
    call = rpc_client(args.datadir)
    chain, = call("getblockchaininfo", [[]])
    if chain["chain"] != "testnet4" or call("getblockhash", [[0]]) != [GENESIS]:
        raise ValueError("Testnet4 genesis mismatch")
    if chain["initialblockdownload"] or chain["blocks"] != chain["headers"]:
        raise ValueError("The source must have processed all known headers")
    tip_height = chain["blocks"]
    if not 0 < tip_height - args.base_height <= MAX_DELTA_BLOCKS:
        raise ValueError("The requested block range exceeds the campaign limit")
    if args.base_height + 1 < chain.get("pruneheight", 0):
        raise ValueError("The first requested block has been pruned")
    if call("getblockhash", [[args.base_height]]) != [args.base_hash]:
        raise ValueError("The source and destination lack the specified common ancestor")

    args.out.mkdir()
    pending = args.out / "testnet4-blocks.dat.gz.pending"
    archive = args.out / "testnet4-blocks.dat.gz"
    raw_size = 0
    raw_hash = hashlib.sha256()
    prev = args.base_hash
    with gzip.open(pending, "wb", compresslevel=1) as stream:
        for start in range(args.base_height + 1, tip_height + 1, 12):
            heights = range(start, min(start + 12, tip_height + 1))
            hashes = call("getblockhash", [[height] for height in heights])
            encoded = call("getblock", [[block_hash, 0] for block_hash in hashes])
            for raw, block_hash in zip(encoded, hashes, strict=True):
                block = bytes.fromhex(raw)
                if not 81 <= len(block) <= 4_000_000:
                    raise ValueError("Unexpected Bitcoin block size")
                if hash_header(block) != block_hash or block[4:36][::-1].hex() != prev:
                    raise ValueError("The market tip changed during block export")
                record = MAGIC + struct.pack("<I", len(block)) + block
                raw_size += len(record)
                if raw_size > MAX_RAW_BYTES:
                    raise ValueError("The requested public data exceeds the export limit")
                stream.write(record)
                raw_hash.update(record)
                prev = block_hash
    if prev != chain["bestblockhash"] or call("getblockhash", [[tip_height]]) != [prev]:
        raise ValueError("The source tip changed during block export")
    pending.rename(archive)
    manifest = {
        "network": "testnet4", "genesis": GENESIS, "base_height": args.base_height,
        "base_hash": args.base_hash, "tip_height": tip_height, "tip_hash": prev,
        "tip_chainwork": chain["chainwork"], "blocks": tip_height - args.base_height,
        "size_bytes": raw_size, "sha256": raw_hash.hexdigest(), "gzip_sha256": file_digest(archive),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datadir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-height", type=int, required=True)
    parser.add_argument("--base-hash", required=True)
    export(parser.parse_args())
