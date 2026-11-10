"""Bitcoin primitives the burger needs: hashes, transactions, Merkle branches, scripts and
addresses. Standard library only.

Byte order: txids, wtxids and block hashes are handled in internal order (as hashed) unless a
name says ``display``; display order is the reversed hex that explorers and Core print.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

M32 = 0xFFFFFFFF


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def sha256d(b: bytes) -> bytes:
    return sha256(sha256(b))


# --- RIPEMD-160 -------------------------------------------------------------------------------
# OpenSSL 3 moved RIPEMD-160 to its legacy provider, so hashlib may not have it. This is a
# plain implementation of the specification; tests check it against the published vectors.

_RL = [
    list(range(16)),
    [7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8],
    [3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12],
    [1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2],
    [4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13],
]
_RR = [
    [5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12],
    [6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2],
    [15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13],
    [8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14],
    [12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11],
]
_SL = [
    [11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8],
    [7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12],
    [11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5],
    [11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12],
    [9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6],
]
_SR = [
    [8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6],
    [9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11],
    [9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5],
    [15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8],
    [8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11],
]
_KL = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
_KR = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]


def _rol(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & M32


def _f(j: int, x: int, y: int, z: int) -> int:
    if j == 0:
        r = x ^ y ^ z
    elif j == 1:
        r = (x & y) | (~x & z)
    elif j == 2:
        r = (x | ~y) ^ z
    elif j == 3:
        r = (x & z) | (y & ~z)
    else:
        r = x ^ (y | ~z)
    return r & M32


def _ripemd_compress(h: tuple, block: bytes) -> tuple:
    x = struct.unpack("<16I", block)
    al, bl, cl, dl, el = h
    ar, br, cr, dr, er = h
    for j in range(5):
        for i in range(16):
            t = (_rol((al + _f(j, bl, cl, dl) + x[_RL[j][i]] + _KL[j]) & M32, _SL[j][i]) + el) & M32
            al, el, dl, cl, bl = el, dl, _rol(cl, 10), bl, t
            t = (_rol((ar + _f(4 - j, br, cr, dr) + x[_RR[j][i]] + _KR[j]) & M32, _SR[j][i]) + er) & M32
            ar, er, dr, cr, br = er, dr, _rol(cr, 10), br, t
    return (
        (h[1] + cl + dr) & M32,
        (h[2] + dl + er) & M32,
        (h[3] + el + ar) & M32,
        (h[4] + al + br) & M32,
        (h[0] + bl + cr) & M32,
    )


def ripemd160_pure(data: bytes) -> bytes:
    h = (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0)
    msg = data + b"\x80" + b"\x00" * ((55 - len(data)) % 64) + struct.pack("<Q", 8 * len(data))
    for i in range(0, len(msg), 64):
        h = _ripemd_compress(h, msg[i : i + 64])
    return struct.pack("<5I", *h)


def ripemd160(data: bytes) -> bytes:
    try:
        return hashlib.new("ripemd160", data).digest()
    except ValueError:
        return ripemd160_pure(data)


def hash160(b: bytes) -> bytes:
    return ripemd160(sha256(b))


# --- serialization ----------------------------------------------------------------------------


class ParseError(ValueError):
    pass


def ser_compact(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


class Reader:
    def __init__(self, b: bytes):
        self.b = b
        self.o = 0

    def take(self, n: int) -> bytes:
        if n < 0 or self.o + n > len(self.b):
            raise ParseError("truncated")
        v = self.b[self.o : self.o + n]
        self.o += n
        return v

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def compact(self) -> int:
        c = self.take(1)[0]
        if c < 0xFD:
            return c
        if c == 0xFD:
            v, lo = struct.unpack("<H", self.take(2))[0], 0xFD
        elif c == 0xFE:
            v, lo = struct.unpack("<I", self.take(4))[0], 0x10000
        else:
            v, lo = struct.unpack("<Q", self.take(8))[0], 0x100000000
        if v < lo:
            raise ParseError("non-canonical compact size")
        return v

    def peek(self, n: int) -> bytes:
        return self.b[self.o : self.o + n]

    def done(self) -> bool:
        return self.o == len(self.b)


@dataclass
class TxIn:
    prev_txid: bytes  # internal order
    prev_vout: int
    script_sig: bytes
    sequence: int
    witness: list = field(default_factory=list)


@dataclass
class TxOut:
    value: int
    script_pubkey: bytes


@dataclass
class Tx:
    version: int
    inputs: list
    outputs: list
    locktime: int

    @property
    def has_witness(self) -> bool:
        return any(i.witness for i in self.inputs)

    def stripped(self) -> bytes:
        out = [struct.pack("<i", self.version), ser_compact(len(self.inputs))]
        for i in self.inputs:
            out += [i.prev_txid, struct.pack("<I", i.prev_vout), ser_compact(len(i.script_sig)), i.script_sig, struct.pack("<I", i.sequence)]
        out.append(ser_compact(len(self.outputs)))
        for o in self.outputs:
            out += [struct.pack("<q", o.value), ser_compact(len(o.script_pubkey)), o.script_pubkey]
        out.append(struct.pack("<I", self.locktime))
        return b"".join(out)

    def serialize(self) -> bytes:
        if not self.has_witness:
            return self.stripped()
        s = self.stripped()
        body = s[4:-4]
        wit = []
        for i in self.inputs:
            wit.append(ser_compact(len(i.witness)))
            for item in i.witness:
                wit += [ser_compact(len(item)), item]
        return s[:4] + b"\x00\x01" + body + b"".join(wit) + s[-4:]

    def txid(self) -> bytes:
        return sha256d(self.stripped())

    def wtxid(self) -> bytes:
        return sha256d(self.serialize())


def parse_tx_from(r: Reader) -> Tx:
    version = struct.unpack("<i", r.take(4))[0]
    segwit = False
    if r.peek(2) == b"\x00\x01":
        r.take(2)
        segwit = True
    n_in = r.compact()
    if n_in == 0:
        raise ParseError("no inputs")
    inputs = []
    for _ in range(n_in):
        prev = r.take(32)
        vout = r.u32()
        ss = r.take(r.compact())
        seq = r.u32()
        inputs.append(TxIn(prev, vout, ss, seq))
    outputs = []
    for _ in range(r.compact()):
        value = struct.unpack("<q", r.take(8))[0]
        if value < 0:
            raise ParseError("negative output value")
        outputs.append(TxOut(value, r.take(r.compact())))
    if segwit:
        for i in inputs:
            i.witness = [r.take(r.compact()) for _ in range(r.compact())]
        if not any(i.witness for i in inputs):
            raise ParseError("superfluous witness record")
    locktime = r.u32()
    return Tx(version, inputs, outputs, locktime)


def parse_tx(raw: bytes) -> Tx:
    """Parse one complete transaction; refuse trailing bytes and non-canonical encodings."""
    r = Reader(raw)
    tx = parse_tx_from(r)
    if not r.done():
        raise ParseError("trailing bytes")
    if tx.serialize() != raw:
        raise ParseError("non-canonical serialization")
    return tx


def parse_block(raw: bytes) -> tuple[bytes, list]:
    """Return (80-byte header, [Tx]) for a full serialized block."""
    r = Reader(raw)
    header = r.take(80)
    txs = [parse_tx_from(r) for _ in range(r.compact())]
    if not r.done():
        raise ParseError("trailing bytes after block")
    return header, txs


# --- Merkle -----------------------------------------------------------------------------------


def merkle_branch(leaves: list, index: int) -> list:
    """Siblings from leaf to root, with Bitcoin's duplicate-the-last-node rule."""
    if not 0 <= index < len(leaves):
        raise IndexError("leaf index out of range")
    level, branch = list(leaves), []
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        branch.append(level[index ^ 1])
        level = [sha256d(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
        index //= 2
    return branch


def merkle_root(leaves: list) -> bytes:
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256d(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def root_from_branch(leaf: bytes, branch: list, index: int) -> bytes:
    if index < 0 or index >> len(branch):
        raise ParseError("index does not fit the branch depth")
    h = leaf
    for sib in branch:
        h = sha256d(sib + h) if index & 1 else sha256d(h + sib)
        index >>= 1
    return h


# --- scripts ----------------------------------------------------------------------------------


def parse_pushes(script: bytes):
    """The pushed items of a push-only script, or None if it contains any other opcode."""
    r, items = Reader(script), []
    try:
        while not r.done():
            op = r.take(1)[0]
            if op == 0:
                items.append(b"")
            elif op <= 0x4B:
                items.append(r.take(op))
            elif op == 0x4C:
                items.append(r.take(r.take(1)[0]))
            elif op == 0x4D:
                items.append(r.take(struct.unpack("<H", r.take(2))[0]))
            elif op == 0x4E:
                items.append(r.take(r.u32()))
            elif op == 0x4F:
                items.append(b"\x81")
            elif 0x51 <= op <= 0x60:
                items.append(bytes([op - 0x50]))
            else:
                return None
    except ParseError:
        return None
    return items


def push(data: bytes) -> bytes:
    n = len(data)
    if n <= 0x4B:
        return bytes([n]) + data
    if n <= 0xFF:
        return b"\x4c" + bytes([n]) + data
    return b"\x4d" + struct.pack("<H", n) + data


def is_der_signature(sig: bytes) -> bool:
    """Strict DER plus a sighash byte (Core's IsValidSignatureEncoding, BIP66)."""
    if len(sig) < 9 or len(sig) > 73 or sig[0] != 0x30 or sig[1] != len(sig) - 3:
        return False
    rlen = sig[3]
    if 5 + rlen >= len(sig):
        return False
    slen = sig[5 + rlen]
    if rlen + slen + 7 != len(sig):
        return False
    if sig[2] != 0x02 or rlen == 0 or sig[4] & 0x80:
        return False
    if rlen > 1 and sig[4] == 0 and not sig[5] & 0x80:
        return False
    if sig[rlen + 4] != 0x02 or slen == 0 or sig[rlen + 6] & 0x80:
        return False
    if slen > 1 and sig[rlen + 6] == 0 and not sig[rlen + 7] & 0x80:
        return False
    return True


def is_compressed_pubkey(b: bytes) -> bool:
    return len(b) == 33 and b[0] in (2, 3)


def is_pubkey(b: bytes) -> bool:
    return is_compressed_pubkey(b) or (len(b) == 65 and b[0] == 4)


def p2pkh(h: bytes) -> bytes:
    return b"\x76\xa9\x14" + h + b"\x88\xac"


def p2sh(h: bytes) -> bytes:
    return b"\xa9\x14" + h + b"\x87"


def p2wpkh(h: bytes) -> bytes:
    return b"\x00\x14" + h


def p2wsh(h: bytes) -> bytes:
    return b"\x00\x20" + h


def p2tr(xonly: bytes) -> bytes:
    return b"\x51\x20" + xonly


def script_kind(spk: bytes):
    if len(spk) == 25 and spk[:3] == b"\x76\xa9\x14" and spk[23:] == b"\x88\xac":
        return "p2pkh"
    if len(spk) == 23 and spk[:2] == b"\xa9\x14" and spk[22] == 0x87:
        return "p2sh"
    if len(spk) == 22 and spk[:2] == b"\x00\x14":
        return "p2wpkh"
    if len(spk) == 34 and spk[:2] == b"\x00\x20":
        return "p2wsh"
    if len(spk) == 34 and spk[:2] == b"\x51\x20":
        return "p2tr"
    return None


# Core's dust thresholds at the default 3 sat/vB dust relay fee.
DUST_SATS = {"p2pkh": 546, "p2sh": 540, "p2wpkh": 294, "p2wsh": 330, "p2tr": 330}


# --- addresses --------------------------------------------------------------------------------

NETWORKS = {
    "mainnet": {"hrp": "bc", "p2pkh": 0x00, "p2sh": 0x05},
    "testnet4": {"hrp": "tb", "p2pkh": 0x6F, "p2sh": 0xC4},
    "signet": {"hrp": "tb", "p2pkh": 0x6F, "p2sh": 0xC4},
    "regtest": {"hrp": "bcrt", "p2pkh": 0x6F, "p2sh": 0xC4},
}

_B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32M = 0x2BC830A3


def _polymod(values) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (top >> i) & 1 else 0
    return chk


def _hrp_expand(hrp: str) -> list:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convertbits(data, frombits: int, tobits: int, pad: bool):
    acc = bits = 0
    out, maxv = [], (1 << tobits) - 1
    for v in data:
        if v < 0 or v >> frombits:
            return None
        acc = (acc << frombits) | v
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            out.append((acc >> bits) & maxv)
    if pad:
        if bits:
            out.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return out


def segwit_encode(hrp: str, version: int, program: bytes) -> str:
    const = 1 if version == 0 else _BECH32M
    data = [version] + _convertbits(program, 8, 5, True)
    pm = _polymod(_hrp_expand(hrp) + data + [0] * 6) ^ const
    checksum = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_B32[d] for d in data + checksum)


def segwit_decode(hrp: str, addr: str):
    if addr.lower() != addr and addr.upper() != addr:
        return None
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr) or len(addr) > 90 or addr[:pos] != hrp:
        return None
    if any(c not in _B32 for c in addr[pos + 1 :]):
        return None
    data = [_B32.find(c) for c in addr[pos + 1 :]]
    const = _polymod(_hrp_expand(hrp) + data)
    if const not in (1, _BECH32M):
        return None
    data = data[:-6]
    if not data:
        return None
    version = data[0]
    prog = _convertbits(data[1:], 5, 8, False)
    if prog is None or version > 16 or not 2 <= len(prog) <= 40:
        return None
    if version == 0 and len(prog) not in (20, 32):
        return None
    if (version == 0) != (const == 1):
        return None
    return version, bytes(prog)


_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58check_encode(payload: bytes) -> str:
    raw = payload + sha256d(payload)[:4]
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def base58check_decode(s: str):
    n = 0
    for c in s:
        if c not in _B58:
            return None
        n = n * 58 + _B58.index(c)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    raw = b"\x00" * (len(s) - len(s.lstrip("1"))) + body
    if len(raw) < 5 or sha256d(raw[:-4])[:4] != raw[-4:]:
        return None
    return raw[:-4]


def address_to_spk(addr: str, network: str) -> bytes:
    net = NETWORKS[network]
    seg = segwit_decode(net["hrp"], addr)
    if seg:
        version, prog = seg
        return bytes([0x50 + version if version else 0, len(prog)]) + prog
    raw = base58check_decode(addr)
    if raw is not None and len(raw) == 21:
        if raw[0] == net["p2pkh"]:
            return p2pkh(raw[1:])
        if raw[0] == net["p2sh"]:
            return p2sh(raw[1:])
    raise ValueError(f"not a {network} address: {addr}")


def spk_to_address(spk: bytes, network: str):
    net, kind = NETWORKS[network], script_kind(spk)
    if kind == "p2pkh":
        return base58check_encode(bytes([net["p2pkh"]]) + spk[3:23])
    if kind == "p2sh":
        return base58check_encode(bytes([net["p2sh"]]) + spk[2:22])
    if kind in ("p2wpkh", "p2wsh"):
        return segwit_encode(net["hrp"], 0, spk[2:])
    if kind == "p2tr":
        return segwit_encode(net["hrp"], 1, spk[2:])
    return None
