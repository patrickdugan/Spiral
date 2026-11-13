"""Taproot script-path spending: BIP340 signatures, BIP341 trees, sighashes and transactions.

Standard library only, on top of `ec`. Enough to build and sign the BitVM3 claim graph: outputs
with a NUMS internal key and a few tapscript leaves, spent by script path with SIGHASH_DEFAULT,
plus spends of legacy P2PKH outputs for the payer's payment.
"""
from __future__ import annotations

import dataclasses
import hashlib
import struct

from . import btc, ec

# BIP341's provably unspendable internal key: lift_x(SHA256(G uncompressed)).
NUMS_X = bytes.fromhex("50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0")
LEAF_VERSION = 0xC0


# --- BIP340 ------------------------------------------------------------------------------------


def lift_x(x: int):
    if not 0 <= x < ec.P:
        return None
    y_sq = (pow(x, 3, ec.P) + 7) % ec.P
    y = pow(y_sq, (ec.P + 1) // 4, ec.P)
    if pow(y, 2, ec.P) != y_sq:
        return None
    return x, y if y % 2 == 0 else ec.P - y


def xonly(secret: int) -> bytes:
    return ec.mul(secret)[0].to_bytes(32, "big")


def schnorr_sign(msg: bytes, secret: int, aux: bytes = bytes(32)) -> bytes:
    """BIP340 Sign. aux defaults to zeros, which BIP340 permits; nonces stay unique per message."""
    assert len(msg) == 32 and 0 < secret < ec.N
    pt = ec.mul(secret)
    d = secret if pt[1] % 2 == 0 else ec.N - secret
    t = (d ^ int.from_bytes(ec.tagged_hash("BIP0340/aux", aux), "big")).to_bytes(32, "big")
    px = pt[0].to_bytes(32, "big")
    k0 = int.from_bytes(ec.tagged_hash("BIP0340/nonce", t + px + msg), "big") % ec.N
    assert k0 != 0
    r = ec.mul(k0)
    k = k0 if r[1] % 2 == 0 else ec.N - k0
    rx = r[0].to_bytes(32, "big")
    e = int.from_bytes(ec.tagged_hash("BIP0340/challenge", rx + px + msg), "big") % ec.N
    sig = rx + ((k + e * d) % ec.N).to_bytes(32, "big")
    assert schnorr_verify(msg, px, sig)
    return sig


def schnorr_verify(msg: bytes, pubkey_x: bytes, sig: bytes) -> bool:
    pt = lift_x(int.from_bytes(pubkey_x, "big"))
    if pt is None or len(sig) != 64:
        return False
    r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
    if r >= ec.P or s >= ec.N:
        return False
    e = int.from_bytes(ec.tagged_hash("BIP0340/challenge", sig[:32] + pubkey_x + msg), "big") % ec.N
    rr = ec.add(ec.mul(s), ec.mul(ec.N - e, pt))
    return rr is not None and rr[1] % 2 == 0 and rr[0] == r


# --- scripts -----------------------------------------------------------------------------------

OP_0, OP_RETURN, OP_IF, OP_ENDIF, OP_DROP, OP_DUP = 0x00, 0x6A, 0x63, 0x68, 0x75, 0x76
OP_EQUAL, OP_EQUALVERIFY, OP_SHA256, OP_HASH160 = 0x87, 0x88, 0xA8, 0xA9
OP_CHECKSIG, OP_CHECKSIGVERIFY, OP_CSV = 0xAC, 0xAD, 0xB2


def num(n: int) -> bytes:
    """A minimal script number push."""
    if n == 0:
        return bytes([OP_0])
    if 1 <= n <= 16:
        return bytes([0x50 + n])
    out = bytearray()
    v = abs(n)
    while v:
        out.append(v & 0xFF)
        v >>= 8
    if out[-1] & 0x80:
        out.append(0x80 if n < 0 else 0)
    elif n < 0:
        out[-1] |= 0x80
    return btc.push(bytes(out))


def op_return(data: bytes) -> bytes:
    return bytes([OP_RETURN]) + btc.push(data)


# --- BIP341 trees ------------------------------------------------------------------------------


def leaf_hash(script: bytes) -> bytes:
    return ec.tagged_hash("TapLeaf", bytes([LEAF_VERSION]) + btc.ser_compact(len(script)) + script)


def branch_hash(a: bytes, b: bytes) -> bytes:
    return ec.tagged_hash("TapBranch", min(a, b) + max(a, b))


@dataclasses.dataclass(frozen=True)
class TapOutput:
    """A P2TR output over a NUMS internal key and two leaves (a one-level tree)."""
    leaves: tuple  # (script_a, script_b)

    @property
    def merkle_root(self) -> bytes:
        return branch_hash(leaf_hash(self.leaves[0]), leaf_hash(self.leaves[1]))

    def _tweaked(self):
        p = lift_x(int.from_bytes(NUMS_X, "big"))
        t = int.from_bytes(ec.tagged_hash("TapTweak", NUMS_X + self.merkle_root), "big")
        assert t < ec.N
        return ec.add(p, ec.mul(t))

    @property
    def output_key(self) -> bytes:
        return self._tweaked()[0].to_bytes(32, "big")

    @property
    def script_pubkey(self) -> bytes:
        return btc.p2tr(self.output_key)

    def control_block(self, index: int) -> bytes:
        parity = self._tweaked()[1] & 1
        sibling = leaf_hash(self.leaves[1 - index])
        return bytes([LEAF_VERSION | parity]) + NUMS_X + sibling


# --- transactions ------------------------------------------------------------------------------


@dataclasses.dataclass
class In:
    txid: str  # display order
    vout: int
    sequence: int = 0xFFFFFFFD
    script_sig: bytes = b""
    witness: list = dataclasses.field(default_factory=list)

    def outpoint(self) -> bytes:
        return bytes.fromhex(self.txid)[::-1] + struct.pack("<I", self.vout)


@dataclasses.dataclass
class Out:
    value: int
    script_pubkey: bytes

    def ser(self) -> bytes:
        return struct.pack("<q", self.value) + btc.ser_compact(len(self.script_pubkey)) + self.script_pubkey


@dataclasses.dataclass
class Tx:
    ins: list
    outs: list
    version: int = 2
    locktime: int = 0

    def ser(self, witness: bool = True) -> bytes:
        seg = witness and any(i.witness for i in self.ins)
        b = struct.pack("<i", self.version) + (b"\x00\x01" if seg else b"")
        b += btc.ser_compact(len(self.ins))
        for i in self.ins:
            b += i.outpoint() + btc.ser_compact(len(i.script_sig)) + i.script_sig + struct.pack("<I", i.sequence)
        b += btc.ser_compact(len(self.outs)) + b"".join(o.ser() for o in self.outs)
        if seg:
            for i in self.ins:
                b += btc.ser_compact(len(i.witness)) + b"".join(btc.ser_compact(len(w)) + w for w in i.witness)
        return b + struct.pack("<I", self.locktime)

    def txid(self) -> str:
        return btc.sha256d(self.ser(witness=False))[::-1].hex()

    def vsize(self) -> int:
        base, total = len(self.ser(witness=False)), len(self.ser())
        return (base * 3 + total + 3) // 4

    def hex(self) -> str:
        return self.ser().hex()


def sighash_script_path(tx: Tx, index: int, spent: list, leaf_script: bytes) -> bytes:
    """BIP341 signature message, SIGHASH_DEFAULT, script path (ext_flag 1, key_version 0).
    `spent` is [(value, script_pubkey)] for every input."""
    sha = lambda b: hashlib.sha256(b).digest()
    msg = bytes([0x00, 0x00]) + struct.pack("<iI", tx.version, tx.locktime)
    msg += sha(b"".join(i.outpoint() for i in tx.ins))
    msg += sha(b"".join(struct.pack("<q", v) for v, _ in spent))
    msg += sha(b"".join(btc.ser_compact(len(s)) + s for _, s in spent))
    msg += sha(b"".join(struct.pack("<I", i.sequence) for i in tx.ins))
    msg += sha(b"".join(o.ser() for o in tx.outs))
    msg += bytes([2 * 1 + 0])  # spend_type: ext_flag 1, no annex
    msg += struct.pack("<I", index)
    msg += leaf_hash(leaf_script) + bytes([0x00]) + struct.pack("<i", -1)
    return ec.tagged_hash("TapSighash", msg)


def sighash_legacy_all(tx: Tx, index: int, script_code: bytes) -> bytes:
    """Legacy SIGHASH_ALL digest (for spending P2PKH)."""
    b = struct.pack("<i", tx.version) + btc.ser_compact(len(tx.ins))
    for k, i in enumerate(tx.ins):
        sc = script_code if k == index else b""
        b += i.outpoint() + btc.ser_compact(len(sc)) + sc + struct.pack("<I", i.sequence)
    b += btc.ser_compact(len(tx.outs)) + b"".join(o.ser() for o in tx.outs) + struct.pack("<I", tx.locktime)
    return btc.sha256d(b + struct.pack("<I", 1))


def ecdsa_sign_der(msg32: bytes, secret: int) -> bytes:
    """ECDSA over secp256k1 with an RFC 6979 nonce, low-S, strict DER."""
    import hmac

    x = secret.to_bytes(32, "big")
    h = int.from_bytes(msg32, "big") % ec.N
    hb = h.to_bytes(32, "big")
    v, k = b"\x01" * 32, b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + x + hb, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + x + hb, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        nonce = int.from_bytes(v, "big")
        if 0 < nonce < ec.N:
            r = ec.mul(nonce)[0] % ec.N
            s = pow(nonce, -1, ec.N) * (h + r * secret) % ec.N
            if r and s:
                break
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()
    if s > ec.N // 2:
        s = ec.N - s

    def der_int(n: int) -> bytes:
        b = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
        if b[0] & 0x80:
            b = b"\x00" + b
        return b"\x02" + bytes([len(b)]) + b

    body = der_int(r) + der_int(s)
    return b"\x30" + bytes([len(body)]) + body


def sign_p2pkh(tx: Tx, index: int, secret: int) -> None:
    pub = ec.serialize(ec.mul(secret), compressed=True)
    script_code = btc.p2pkh(btc.hash160(pub))
    sig = ecdsa_sign_der(sighash_legacy_all(tx, index, script_code), secret) + b"\x01"
    tx.ins[index].script_sig = btc.push(sig) + btc.push(pub)
