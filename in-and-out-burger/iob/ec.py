"""secp256k1 public-key arithmetic, enough to tweak a key: parse, serialize, add, multiply.

Standard library only. The desk only ever multiplies by public scalars (tweaks); the payer's
`payout-key` tool adds a tweak to a private key with plain modular addition.
"""
from __future__ import annotations

import hashlib

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)

Point = tuple  # (x, y), or None for the point at infinity


def on_curve(pt: Point) -> bool:
    if pt is None:
        return False
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - x * x * x - 7) % P == 0


def add(a: Point, b: Point) -> Point:
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0]:
        if (a[1] + b[1]) % P == 0:
            return None
        lam = 3 * a[0] * a[0] * pow(2 * a[1], -1, P) % P
    else:
        lam = (b[1] - a[1]) * pow(b[0] - a[0], -1, P) % P
    x = (lam * lam - a[0] - b[0]) % P
    return x, (lam * (a[0] - x) - a[1]) % P


def mul(k: int, pt: Point = G) -> Point:
    out = None
    k %= N
    while k:
        if k & 1:
            out = add(out, pt)
        pt = add(pt, pt)
        k >>= 1
    return out


def parse(b: bytes) -> Point:
    """A 33-byte compressed or 65-byte uncompressed SEC1 key. Raises ValueError off the curve."""
    if len(b) == 33 and b[0] in (2, 3):
        x = int.from_bytes(b[1:], "big")
        if x >= P:
            raise ValueError("x not below the field prime")
        y = pow((x * x * x + 7) % P, (P + 1) // 4, P)
        if (y * y - x * x * x - 7) % P:
            raise ValueError("x is not on secp256k1")
        if y & 1 != b[0] & 1:
            y = P - y
        return x, y
    if len(b) == 65 and b[0] == 4:
        pt = (int.from_bytes(b[1:33], "big"), int.from_bytes(b[33:], "big"))
        if not on_curve(pt):
            raise ValueError("point is not on secp256k1")
        return pt
    raise ValueError(f"not a SEC1 public key ({len(b)} bytes)")


def serialize(pt: Point, compressed: bool = True) -> bytes:
    x, y = pt
    if compressed:
        return bytes([2 + (y & 1)]) + x.to_bytes(32, "big")
    return b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")


def tagged_hash(tag: str, msg: bytes) -> bytes:
    """BIP340 tagged hash."""
    t = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(t + t + msg).digest()
