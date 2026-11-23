"""Transactions, Taproot/P2MR commitments, BIP341 digests and bech32m.

BIP341 signature messages come from BIPSpace/Keyless-CHECKSIG/reference.py,
which is checked against the official bitcoin/bips wallet test vectors.
"""
from __future__ import annotations

import hashlib
import importlib.util
import struct
from dataclasses import dataclass, field, replace
from pathlib import Path

from secp import G, N, lift_x, point_add, point_mul, tagged, xonly, has_even_y

_REF = Path(__file__).resolve().parents[2] / "BIPSpace" / "Keyless-CHECKSIG" / "reference.py"
_spec = importlib.util.spec_from_file_location("keyless_reference", _REF)
ref = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ref)

# BIP341's suggested unspendable internal key (no known discrete log).
NUMS = bytes.fromhex("50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0")


def dsha256(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


cs = ref.compact_size


def push(data: bytes) -> bytes:
    if len(data) < 76:
        return bytes([len(data)]) + data
    if len(data) <= 255:
        return b"\x4c" + bytes([len(data)]) + data
    return b"\x4d" + struct.pack("<H", len(data)) + data


@dataclass(frozen=True)
class TxIn:
    txid: str                 # display (big-endian) hex
    vout: int
    sequence: int = 0xFFFFFFFD
    witness: tuple = ()

    def outpoint(self) -> bytes:
        return bytes.fromhex(self.txid)[::-1] + struct.pack("<I", self.vout)


@dataclass(frozen=True)
class TxOut:
    value: int
    script: bytes

    def ser(self) -> bytes:
        return struct.pack("<q", self.value) + cs(len(self.script)) + self.script


@dataclass(frozen=True)
class Tx:
    vin: tuple
    vout: tuple
    version: int = 2
    locktime: int = 0

    def ser(self, witness: bool = True) -> bytes:
        has_w = witness and any(i.witness for i in self.vin)
        out = struct.pack("<i", self.version) + (b"\x00\x01" if has_w else b"")
        out += cs(len(self.vin)) + b"".join(i.outpoint() + b"\x00" + struct.pack("<I", i.sequence)
                                           for i in self.vin)
        out += cs(len(self.vout)) + b"".join(o.ser() for o in self.vout)
        if has_w:
            for i in self.vin:
                out += cs(len(i.witness)) + b"".join(cs(len(w)) + w for w in i.witness)
        return out + struct.pack("<I", self.locktime)

    def hex(self) -> str:
        return self.ser().hex()

    @property
    def txid(self) -> str:
        return dsha256(self.ser(False))[::-1].hex()

    @property
    def weight(self) -> int:
        return 3 * len(self.ser(False)) + len(self.ser(True))

    @property
    def vsize(self) -> int:
        return (self.weight + 3) // 4

    def with_witness(self, idx: int, witness: list) -> "Tx":
        vin = list(self.vin)
        vin[idx] = replace(vin[idx], witness=tuple(witness))
        return replace(self, vin=tuple(vin))


@dataclass(frozen=True)
class Prevout:
    value: int
    script: bytes


def ref_tx(tx: Tx, prevouts: list[Prevout]) -> "ref.Tx":
    inputs = tuple(ref.Input(bytes.fromhex(i.txid)[::-1], i.vout, p.value, p.script, i.sequence)
                   for i, p in zip(tx.vin, prevouts))
    outputs = tuple(ref.Output(o.value, o.script) for o in tx.vout)
    return ref.Tx(inputs, outputs, tx.version, tx.locktime)


def sighash_keypath(tx: Tx, idx: int, prevouts: list[Prevout]) -> bytes:
    return ref.sighash(ref_tx(tx, prevouts), idx, ext_flag=0)


def sighash_scriptpath(tx: Tx, idx: int, prevouts: list[Prevout], leaf_script: bytes,
                       key_version: int = 0) -> bytes:
    return ref.sighash(ref_tx(tx, prevouts), idx, ext_flag=1, leaf=ref.tapleaf(leaf_script),
                       key_version=key_version)


def sigmsg_scriptpath(tx: Tx, idx: int, prevouts: list[Prevout], leaf_script: bytes,
                      key_version: int = 2) -> bytes:
    return ref.sigmsg(ref_tx(tx, prevouts), idx, ext_flag=1, leaf=ref.tapleaf(leaf_script),
                      key_version=key_version)


# --- Taproot ------------------------------------------------------------------

def taproot_output(internal_x: bytes, leaves: list[bytes]) -> dict:
    """One- or two-leaf tree. Returns output key, scriptPubKey, control blocks."""
    hashes = [ref.tapleaf(s) for s in leaves]
    if len(hashes) == 1:
        root = hashes[0]
        siblings = [b""]
    elif len(hashes) == 2:
        root = ref.tapbranch(hashes[0], hashes[1])
        siblings = [hashes[1], hashes[0]]
    else:
        raise ValueError("one or two leaves supported")
    tweak = int.from_bytes(tagged("TapTweak", internal_x + root), "big")
    if tweak >= N:
        raise ValueError("tweak out of range")
    Q = point_add(lift_x(int.from_bytes(internal_x, "big")), point_mul(G, tweak))
    parity = 0 if has_even_y(Q) else 1
    controls = [bytes([0xC0 | parity]) + internal_x + sib for sib in siblings]
    return {"output_key": xonly(Q), "spk": b"\x51\x20" + xonly(Q), "controls": controls,
            "root": root, "tweak": tweak}


def keypath_seckey(d: int, merkle_root: bytes = b"") -> int:
    """Secret for a key-path spend of tr(d) with an optional script tree."""
    Pt = point_mul(G, d)
    if not has_even_y(Pt):
        d = N - d
    tweak = int.from_bytes(tagged("TapTweak", xonly(point_mul(G, d)) + merkle_root), "big")
    return (d + tweak) % N


def p2mr_spk(leaf: bytes, sibling_leaf: bytes) -> bytes:
    return ref.p2mr(leaf, sibling_leaf)


def p2mr_control(sibling_leaf: bytes) -> bytes:
    return b"\xc0" + ref.tapleaf(sibling_leaf)


# --- bech32m (BIP350) -------------------------------------------------------

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def _convertbits(data, frombits, tobits):
    acc = bits = 0
    out = []
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            out.append((acc >> bits) & ((1 << tobits) - 1))
    if bits:
        out.append((acc << (tobits - bits)) & ((1 << tobits) - 1))
    return out


def segwit_address(hrp: str, version: int, program: bytes) -> str:
    const = 1 if version == 0 else 0x2BC830A3
    data = [version] + _convertbits(program, 8, 5)
    hrp_exp = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    pm = _polymod(hrp_exp + data + [0] * 6) ^ const
    checksum = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_CHARSET[d] for d in data + checksum)


def spk_address(hrp: str, spk: bytes) -> str:
    version = 0 if spk[0] == 0 else spk[0] - 0x50
    return segwit_address(hrp, version, spk[2:])
