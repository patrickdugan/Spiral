#!/usr/bin/env python3
"""Testnet4 inputs for the M16 guest from a Bitcoin Core node (txindex not needed).

  fetch_testnet4.py --datadir C:\\BitcoinTestnet --out DIR headers [--tip HEIGHT]
  fetch_testnet4.py --datadir C:\\BitcoinTestnet --out DIR payment --txid TXID --vout N --tip HEIGHT

`headers` writes DIR/headers.bin (80-byte raw headers from genesis to the tip, nova-chain's input)
and DIR/core_ref.tsv (Core's hash, chainwork, bits, time and median time per height, for
`nova-chain native-check`). Run again with a higher --tip to extend both files in place; the
existing prefix is re-checked against the node first.

`payment` writes DIR/payment.bin, the M16 guest's payment input
(u32 n | headers B..T | u32 vout | u32 len | tx without witness | u32 depth | siblings | u32 index),
DIR/block.bin and DIR/payment.json. B is the block that confirmed TXID and T is --tip, which must
be a header in DIR/headers.bin.

Standard library only; JSON-RPC calls are batched.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import struct
import sys
import time

GENESIS = "00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043"


def sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


class Rpc:
    def __init__(self, datadir: str, port: int):
        cookie = open(os.path.join(datadir, "testnet4", ".cookie"), encoding="utf-8").read().strip()
        self.auth = "Basic " + base64.b64encode(cookie.encode()).decode()
        self.port = port
        self.conn = http.client.HTTPConnection("127.0.0.1", port, timeout=600)

    def _post(self, body):
        self.conn.request("POST", "/", json.dumps(body), {"Authorization": self.auth, "Content-Type": "application/json"})
        return json.loads(self.conn.getresponse().read())

    def __call__(self, method, *params):
        r = self._post({"jsonrpc": "1.0", "id": 0, "method": method, "params": list(params)})
        if r.get("error"):
            raise RuntimeError(f"{method}: {r['error']}")
        return r["result"]

    def batch(self, method, param_lists):
        out = []
        for k in range(0, len(param_lists), 1000):
            chunk = param_lists[k:k + 1000]
            rs = self._post([{"jsonrpc": "1.0", "id": k + j, "method": method, "params": p} for j, p in enumerate(chunk)])
            rs.sort(key=lambda r: r["id"])
            for r in rs:
                if r.get("error"):
                    raise RuntimeError(f"{method}: {r['error']}")
                out.append(r["result"])
        return out


def raw_header(m) -> bytes:
    return (struct.pack("<i", m["version"]) + bytes.fromhex(m.get("previousblockhash", "00" * 32))[::-1]
            + bytes.fromhex(m["merkleroot"])[::-1] + struct.pack("<III", m["time"], int(m["bits"], 16), m["nonce"]))


def read_headers(path: str) -> list[bytes]:
    if not os.path.exists(path):
        return []
    hb = open(path, "rb").read()
    assert len(hb) % 80 == 0
    return [hb[k:k + 80] for k in range(0, len(hb), 80)]


def cmd_headers(rpc: Rpc, a) -> None:
    info = rpc("getblockchaininfo")
    assert info["chain"] == "testnet4", info["chain"]
    tip = a.tip if a.tip is not None else info["blocks"]
    assert tip <= info["blocks"], f"node is at {info['blocks']}"
    hpath, tpath = f"{a.out}/headers.bin", f"{a.out}/core_ref.tsv"
    have = read_headers(hpath)
    t0 = time.time()
    hashes = rpc.batch("getblockhash", [[h] for h in range(tip + 1)])
    assert hashes[0] == GENESIS
    prev = b"\x00" * 32
    for h, raw in enumerate(have):
        assert raw[4:36] == prev and sha256d(raw)[::-1].hex() == hashes[h], f"existing header {h} differs from the node's chain"
        prev = sha256d(raw)
    start = len(have)
    assert start <= tip + 1, "headers.bin is already past the requested tip"
    metas = rpc.batch("getblockheader", [[hashes[h], True] for h in range(start, tip + 1)])
    mode = "ab" if start else "wb"
    with open(hpath, mode) as hb, open(tpath, "a" if start else "w", encoding="utf-8", newline="\n") as tsv:
        if not start:
            tsv.write("height\thash\tchainwork\tbits\ttime\tmediantime\n")
        for m in metas:
            raw = raw_header(m)
            assert sha256d(raw)[::-1].hex() == m["hash"] and raw[4:36] == prev, m["height"]
            prev = sha256d(raw)
            hb.write(raw)
            tsv.write(f"{m['height']}\t{m['hash']}\t{m['chainwork']}\t{m['bits']}\t{m['time']}\t{m['mediantime']}\n")
    print(f"headers {start}..{tip} appended ({time.time() - t0:.0f} s); tip hash {hashes[tip]}")


def varint(b: bytes, i: int):
    x = b[i]
    if x < 0xFD:
        return x, i + 1
    n = {0xFD: 2, 0xFE: 4, 0xFF: 8}[x]
    return int.from_bytes(b[i + 1:i + 1 + n], "little"), i + 1 + n


def ser_varint(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF:
        return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")


def parse_tx(b: bytes, i: int):
    """(serialization without witness, next offset)."""
    start = i
    ver = b[i:i + 4]; i += 4
    segwit = b[i] == 0 and b[i + 1] == 1
    if segwit:
        i += 2
    n_in, i = varint(b, i)
    ins = []
    for _ in range(n_in):
        j = i + 36
        ln, j = varint(b, j)
        j += ln + 4
        ins.append(b[i:j]); i = j
    n_out, i = varint(b, i)
    outs = []
    for _ in range(n_out):
        j = i + 8
        ln, j = varint(b, j)
        j += ln
        outs.append(b[i:j]); i = j
    if segwit:
        for _ in range(n_in):
            items, i = varint(b, i)
            for _ in range(items):
                ln, i = varint(b, i)
                i += ln
    lock = b[i:i + 4]; i += 4
    legacy = ver + ser_varint(n_in) + b"".join(ins) + ser_varint(n_out) + b"".join(outs) + lock
    if not segwit:
        assert legacy == b[start:i]
    return legacy, i


def merkle_branch(txids, index):
    level, branch = list(txids), []
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        branch.append(level[index ^ 1])
        level = [sha256d(level[k] + level[k + 1]) for k in range(0, len(level), 2)]
        index //= 2
    return branch, level[0]


def cmd_payment(rpc: Rpc, a) -> None:
    raws = read_headers(f"{a.out}/headers.bin")
    assert len(raws) > a.tip, f"headers.bin ends at {len(raws) - 1}, below --tip {a.tip}"
    tx_meta = rpc("getrawtransaction", a.txid, True)
    b_hash = tx_meta["blockhash"]
    b_height = rpc("getblockheader", b_hash)["height"]
    assert sha256d(raws[b_height])[::-1].hex() == b_hash, "payment block is not in headers.bin"
    assert b_height <= a.tip
    block = bytes.fromhex(rpc("getblock", b_hash, 0))
    assert block[:80] == raws[b_height]
    n_tx, i = varint(block, 80)
    txids, target = [], None
    for k in range(n_tx):
        legacy, i = parse_tx(block, i)
        txid = sha256d(legacy)
        txids.append(txid)
        if txid[::-1].hex() == a.txid:
            target = (k, legacy)
    assert i == len(block) and target is not None
    index, legacy = target
    branch, root = merkle_branch(txids, index)
    assert root == block[36:68]
    n = a.tip - b_height + 1
    out = struct.pack("<I", n) + b"".join(raws[b_height:a.tip + 1])
    out += struct.pack("<I", a.vout) + struct.pack("<I", len(legacy)) + legacy
    out += struct.pack("<I", len(branch)) + b"".join(branch) + struct.pack("<I", index)
    open(f"{a.out}/payment.bin", "wb").write(out)
    open(f"{a.out}/block.bin", "wb").write(block)
    meta = {
        "network": "testnet4",
        "txid": a.txid,
        "vout": a.vout,
        "block_height": b_height,
        "block_hash": b_hash,
        "tip_height": a.tip,
        "tip_hash": sha256d(raws[a.tip])[::-1].hex(),
        "confirmations": n,
        "tx_index": index,
        "merkle_depth": len(branch),
        "sha256": {f: hashlib.sha256(open(f"{a.out}/{f}", "rb").read()).hexdigest() for f in ("payment.bin", "block.bin")},
    }
    json.dump(meta, open(f"{a.out}/payment.json", "w", encoding="utf-8", newline="\n"), indent=1)
    print(json.dumps(meta, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", required=True)
    ap.add_argument("--port", type=int, default=48332)
    ap.add_argument("--out", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("headers")
    h.add_argument("--tip", type=int)
    p = sub.add_parser("payment")
    p.add_argument("--txid", required=True)
    p.add_argument("--vout", type=int, required=True)
    p.add_argument("--tip", type=int, required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rpc = Rpc(a.datadir, a.port)
    {"headers": cmd_headers, "payment": cmd_payment}[a.cmd](rpc, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
