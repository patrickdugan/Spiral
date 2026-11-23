"""secp256k1, BIP340 Schnorr and Schnorr adaptor signatures (stdlib only).

Disposable research keys only. Not constant time; never use with real funds.
"""
from __future__ import annotations

import hashlib

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def tagged(tag: str, data: bytes) -> bytes:
    t = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(t + t + data).digest()


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = 3 * x1 * x1 * pow(2 * y1, P - 2, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, P - 2, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return x3, (lam * (x1 - x3) - y1) % P


def point_add(a, b):
    return _add(a, b)


def point_mul(pt, k: int):
    k %= N
    acc, addend = None, pt
    while k:
        if k & 1:
            acc = _add(acc, addend)
        addend = _add(addend, addend)
        k >>= 1
    return acc


def neg(pt):
    return None if pt is None else (pt[0], (-pt[1]) % P)


def lift_x(x: int):
    if x >= P:
        raise ValueError("x out of range")
    c = (pow(x, 3, P) + 7) % P
    y = pow(c, (P + 1) // 4, P)
    if y * y % P != c:
        raise ValueError("not on curve")
    return x, y if y % 2 == 0 else P - y


def xonly(pt) -> bytes:
    return pt[0].to_bytes(32, "big")


def has_even_y(pt) -> bool:
    return pt[1] % 2 == 0


def seckey(label: str) -> int:
    """Deterministic disposable key from a public label (test fixtures only)."""
    return int.from_bytes(hashlib.sha256(b"spiral-private-signet/test-key/" + label.encode()).digest(), "big") % (N - 1) + 1


def pubkey_xonly(d: int) -> bytes:
    return xonly(point_mul(G, d))


def challenge(r_x: bytes, p_x: bytes, msg: bytes) -> int:
    return int.from_bytes(tagged("BIP0340/challenge", r_x + p_x + msg), "big") % N


def _even_secret(d: int) -> int:
    return d if has_even_y(point_mul(G, d)) else N - d


def sign(d: int, msg: bytes, aux: bytes = bytes(32)) -> bytes:
    """BIP340 signature (deterministic nonce derived per the BIP)."""
    d = _even_secret(d)
    px = pubkey_xonly(d)
    t = (d ^ int.from_bytes(tagged("BIP0340/aux", aux), "big")).to_bytes(32, "big")
    k = int.from_bytes(tagged("BIP0340/nonce", t + px + msg), "big") % N
    R = point_mul(G, k)
    if not has_even_y(R):
        k = N - k
        R = point_mul(G, k)
    e = challenge(xonly(R), px, msg)
    return xonly(R) + ((k + e * d) % N).to_bytes(32, "big")


def verify(px: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        Pt = lift_x(int.from_bytes(px, "big"))
    except ValueError:
        return False
    r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
    if r >= P or s >= N:
        return False
    e = challenge(sig[:32], px, msg)
    R = point_add(point_mul(G, s), neg(point_mul(Pt, e)))
    return R is not None and has_even_y(R) and R[0] == r


# --- adaptor signatures -----------------------------------------------------

def adaptor_presign(d: int, msg: bytes, T, label: str) -> tuple[bytes, int]:
    """Pre-signature encrypted to point T: (x(R+T), s') with s'G = R + eP.

    The nonce is retried until R+T has an even y, so decryption is always
    s = s' + t and the completed signature is a plain BIP340 signature.
    """
    d = _even_secret(d)
    px = pubkey_xonly(d)
    for ctr in range(256):
        k = int.from_bytes(tagged("spiral/adaptor-nonce", d.to_bytes(32, "big") + msg + xonly(T)
                                  + label.encode() + bytes([ctr])), "big") % N
        R = point_mul(G, k)
        RT = point_add(R, T)
        if RT is not None and has_even_y(RT):
            e = challenge(xonly(RT), px, msg)
            return xonly(RT), (k + e * d) % N
    raise RuntimeError("no adaptor nonce with even R+T")


def adaptor_verify(px: bytes, msg: bytes, T, presig: tuple[bytes, int]) -> bool:
    rt_x, s_pre = presig
    try:
        RT = lift_x(int.from_bytes(rt_x, "big"))
        Pt = lift_x(int.from_bytes(px, "big"))
    except ValueError:
        return False
    R = point_add(RT, neg(T))
    e = challenge(rt_x, px, msg)
    return point_mul(G, s_pre) == point_add(R, point_mul(Pt, e))


def adaptor_complete(presig: tuple[bytes, int], t: int) -> bytes:
    rt_x, s_pre = presig
    return rt_x + ((s_pre + t) % N).to_bytes(32, "big")


# --- DLC oracle -------------------------------------------------------------

class Oracle:
    """Single-nonce BIP340 oracle. Attestation for outcome m is s_m with
    s_m G = R + H(R||P||m) P; that point is the adaptor encryption key."""

    def __init__(self, label: str):
        self.d = _even_secret(seckey("oracle/" + label))
        self.k = seckey("oracle-nonce/" + label)
        if not has_even_y(point_mul(G, self.k)):
            self.k = N - self.k
        self.P = pubkey_xonly(self.d)
        self.R = xonly(point_mul(G, self.k))

    @staticmethod
    def message(outcome: str) -> bytes:
        return hashlib.sha256(b"spiral-dlc-outcome/" + outcome.encode()).digest()

    def attestation_point(self, outcome: str):
        e = challenge(self.R, self.P, self.message(outcome))
        return point_add(lift_x(int.from_bytes(self.R, "big")),
                         point_mul(lift_x(int.from_bytes(self.P, "big")), e))

    def attest(self, outcome: str) -> int:
        e = challenge(self.R, self.P, self.message(outcome))
        return (self.k + e * self.d) % N

    def hash_commitment(self, outcome: str) -> bytes:
        """SHA256 of the 32-byte attestation scalar, announced in advance for
        script-checkable settlement (the oracle can compute every s_m ahead)."""
        return hashlib.sha256(self.attest(outcome).to_bytes(32, "big")).digest()
