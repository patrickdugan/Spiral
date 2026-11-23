"""Isolated regtest nodes, cookie-auth JSON-RPC and hand-built blocks."""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import secp
from txlib import Prevout, Tx, TxIn, TxOut, dsha256, keypath_seckey, sighash_keypath, spk_address


class RPCError(RuntimeError):
    pass


class RPC:
    def __init__(self, url: str, cookie: Path, timeout: float = 300):
        self.url, self.cookie, self.timeout = url, cookie, timeout

    def __call__(self, method: str, *params):
        auth = base64.b64encode(self.cookie.read_text().strip().encode()).decode()
        body = json.dumps({"jsonrpc": "1.0", "id": "ab", "method": method, "params": params}).encode()
        req = Request(self.url, body, {"Content-Type": "application/json", "Authorization": "Basic " + auth})
        try:
            with urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except HTTPError as e:
            data = json.loads(e.read())
        if data.get("error"):
            raise RPCError(f"{method}: {data['error']}")
        return data["result"]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Node:
    name: str
    binary: Path
    datadir: Path
    extra: list[str] = field(default_factory=list)
    proc: subprocess.Popen | None = None
    rpc: RPC | None = None
    cmdline: list[str] = field(default_factory=list)

    def start(self) -> "Node":
        self.datadir.mkdir(parents=True, exist_ok=True)
        port, p2p = free_port(), free_port()
        self.cmdline = [str(self.binary), "-regtest", f"-datadir={self.datadir}", f"-rpcport={port}",
                        f"-port={p2p}", "-listen=0", "-connect=0", "-dnsseed=0", "-server=1",
                        "-rpcbind=127.0.0.1", "-rpcallowip=127.0.0.1", "-printtoconsole=0",
                        "-disablewallet=1", *self.extra]
        self.proc = subprocess.Popen(self.cmdline, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cookie = self.datadir / "regtest" / ".cookie"
        end = time.time() + 90
        while time.time() < end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"{self.name} exited with {self.proc.returncode}")
            if cookie.exists():
                self.rpc = RPC(f"http://127.0.0.1:{port}", cookie)
                try:
                    self.rpc("getblockcount")
                    return self
                except (RPCError, OSError):
                    pass
            time.sleep(0.3)
        raise RuntimeError(f"{self.name} RPC never became ready")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.rpc("stop")
                self.proc.wait(60)
            except Exception:
                self.proc.kill()

    def version(self) -> str:
        return self.rpc("getnetworkinfo")["subversion"]


# --- regtest funding from a Python-held key ----------------------------------

class Faucet:
    """Coinbase outputs paid to a Python-held P2TR key, spent by key path."""

    def __init__(self, label: str = "ab-faucet"):
        self.d = secp.seckey(label)
        self.x = secp.pubkey_xonly(self.d)
        from txlib import taproot_output
        Pt = secp.point_mul(secp.G, self.d)
        # Key-only Taproot output: tweak by H_TapTweak(P) with empty root.
        tweak = int.from_bytes(secp.tagged("TapTweak", self.x), "big")
        Q = secp.point_add(secp.lift_x(int.from_bytes(self.x, "big")), secp.point_mul(secp.G, tweak))
        self.spk = b"\x51\x20" + secp.xonly(Q)
        self.address = spk_address("bcrt", self.spk)
        self.tweaked = keypath_seckey(self.d)

    def spend(self, coin: dict, outputs: list[TxOut]) -> Tx:
        tx = Tx((TxIn(coin["txid"], coin["vout"], 0xFFFFFFFD),), tuple(outputs))
        msg = sighash_keypath(tx, 0, [Prevout(coin["value"], self.spk)])
        return tx.with_witness(0, [secp.sign(self.tweaked, msg)])


def coinbase_coin(node: Node, block_hash: str) -> dict:
    cb = node.rpc("getblock", block_hash, 2)["tx"][0]
    return {"txid": cb["txid"], "vout": 0, "value": round(cb["vout"][0]["value"] * 1e8)}


# --- hand-built blocks ---------------------------------------------------------

def _merkle(hashes: list[bytes]) -> bytes:
    layer = list(hashes)
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [dsha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


def _scriptnum(n: int) -> bytes:
    out = bytearray()
    while n:
        out.append(n & 0xFF)
        n >>= 8
    if out and out[-1] & 0x80:
        out.append(0)
    return bytes([len(out)]) + bytes(out)


def build_block(tip_node: Node, txs: list[Tx], tag: bytes = b"ab") -> tuple[str, str]:
    """Regtest block on tip_node's tip with a BIP141 witness commitment.

    Zero-value coinbase (always <= subsidy + fees), BIP34 height, real PoW.
    Returns (block_hex, block_hash)."""
    tip = tip_node.rpc("getbestblockhash")
    head = tip_node.rpc("getblockheader", tip)
    height = head["height"] + 1
    wtxids = [bytes(32)] + [dsha256(t.ser(True)) for t in txs]
    commitment = dsha256(_merkle(wtxids) + bytes(32))
    coinbase = Tx((TxIn("00" * 32, 0xFFFFFFFF, 0xFFFFFFFF, (bytes(32),)),),
                  (TxOut(0, b"\x51"), TxOut(0, b"\x6a\x24\xaa\x21\xa9\xed" + commitment)))
    # The coinbase scriptSig must carry the BIP34 height; Tx has no scriptSig
    # field, so serialize it by hand.
    sig = _scriptnum(height) + bytes([len(tag)]) + tag
    cb_nowit = (struct.pack("<i", 2) + b"\x01" + bytes(32) + b"\xff\xff\xff\xff" +
                bytes([len(sig)]) + sig + b"\xff\xff\xff\xff" + b"\x02" +
                b"".join(o.ser() for o in coinbase.vout) + struct.pack("<I", 0))
    cb_wit = (cb_nowit[:4] + b"\x00\x01" + cb_nowit[4:-4] + b"\x01\x20" + bytes(32) + cb_nowit[-4:])
    txids = [dsha256(cb_nowit)] + [dsha256(t.ser(False)) for t in txs]
    bits = int(head["bits"], 16)
    target = (bits & 0x7FFFFF) << (8 * ((bits >> 24) - 3))
    when = max(head["mediantime"] + 1, head["time"] + 1)
    prefix = struct.pack("<i", 0x20000000) + bytes.fromhex(tip)[::-1] + _merkle(txids) + struct.pack("<II", when, bits)
    for nonce in range(1 << 32):
        header = prefix + struct.pack("<I", nonce)
        if int.from_bytes(dsha256(header), "little") <= target:
            break
    body = bytes([1 + len(txs)]) + cb_wit + b"".join(t.ser(True) for t in txs)
    return (header + body).hex(), dsha256(header)[::-1].hex()


def submit_all(nodes: list[Node], block_hex: str) -> dict:
    out = {}
    for n in nodes:
        t0 = time.perf_counter()
        try:
            r = n.rpc("submitblock", block_hex)
        except RPCError as e:
            r = "rpc-error: " + str(e)
        out[n.name] = {"result": "accepted" if r is None else r,
                       "ms": round((time.perf_counter() - t0) * 1000, 2)}
    return out
