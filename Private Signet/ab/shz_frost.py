"""t-of-n FROST digit oracle, ported from SatsHedgeZero crates/shz-oracle/src/frost.rs.

Same construction as the Rust code:
- keygen: a degree t-1 polynomial whose constant term is the (even-Y
  normalised) group secret; signer i holds f(i), checked against Feldman
  commitments a_m * G;
- announce: one Shamir-shared nonce polynomial per digit; the announced
  nonce is R_j = k_j(0) * G, negated when its Y is odd;
- sign: any t signers give z_i = lambda_i * (+-k_ij + e * x_i), each share
  checked against the signer's public commitments (identifiable abort);
  sum z_i is a plain BIP340 signature (R_j, s) under the group key.

Fewer than t shares do not interpolate the secret: their sum is not a valid
signature. Signing both bit values of one digit reuses R_j and reveals the
group key, which is what deters equivocation.

The Rust keygen is dealer-style from a seed (keygen_deterministic); so is
this port. Seeds are public test labels.
"""
from __future__ import annotations

import hashlib

import secp
from secp import G, N, has_even_y, point_add, point_mul, xonly
from shz_margin import decompose_price_bits, oracle_digit_message


def _scalar(label: str) -> int:
    return int.from_bytes(hashlib.sha256(b"spiral-shz-frost/" + label.encode()).digest(), "big") % (N - 1) + 1


def _poly_eval(coeffs: list[int], x: int) -> int:
    acc = 0
    for c in reversed(coeffs):
        acc = (acc * x + c) % N
    return acc


def lagrange_at_zero(i: int, ids: list[int]) -> int:
    num = den = 1
    for j in ids:
        if j != i:
            num = num * j % N
            den = den * (j - i) % N
    if den == 0:
        raise ValueError("duplicate signer id")
    return num * pow(den, -1, N) % N


class FrostOracle:
    """Drop-in for shz_k1.DigitOracle (P, R, msg, attest) backed by t-of-n shares."""

    def __init__(self, label: str, event_id: str, num_bits: int, t: int = 3, n: int = 5):
        if not 2 <= t <= n <= 255:
            raise ValueError("require 2 <= t <= n <= 255")
        self.event_id, self.num_bits, self.t, self.n = event_id, num_bits, t, n
        d = _scalar(f"{label}/group")
        d = d if has_even_y(point_mul(G, d)) else N - d
        coeffs = [d] + [_scalar(f"{label}/coeff/{m}") for m in range(1, t)]
        self.P = xonly(point_mul(G, d))
        self.feldman = [point_mul(G, c) for c in coeffs]
        self.share = {i: _poly_eval(coeffs, i) for i in range(1, n + 1)}
        self.Y = {i: point_mul(G, x) for i, x in self.share.items()}
        for i, Yi in self.Y.items():          # Feldman VSS check
            exp, pw = None, 1
            for c in self.feldman:
                exp = point_add(exp, point_mul(c, pw))
                pw = pw * i % N
            if exp != Yi:
                raise AssertionError("Feldman share check failed")
        self.R, self.negated, self.k, self.K = [], [], [], []
        for j in range(num_bits):
            poly = [_scalar(f"{label}/{event_id}/nonce/{j}/{m}") for m in range(t)]
            Rj = point_mul(G, poly[0])
            self.R.append(xonly(Rj))
            self.negated.append(not has_even_y(Rj))
            shares = {i: _poly_eval(poly, i) for i in range(1, n + 1)}
            self.k.append(shares)
            self.K.append({i: point_mul(G, s) for i, s in shares.items()})

    def msg(self, j: int, bit: int) -> bytes:
        return oracle_digit_message(self.event_id, j, bit)

    def partial(self, i: int, ids: list[int], j: int, bit: int) -> int:
        e = secp.challenge(self.R[j], self.P, self.msg(j, bit))
        lam = lagrange_at_zero(i, ids)
        k = self.k[j][i] if not self.negated[j] else N - self.k[j][i]
        z = lam * (k + e * self.share[i]) % N
        Kc = self.K[j][i] if not self.negated[j] else secp.neg(self.K[j][i])
        if point_mul(G, z) != point_mul(point_add(Kc, point_mul(self.Y[i], e)), lam):
            raise AssertionError(f"byzantine share from signer {i}")
        return z

    def sign_digit(self, j: int, bit: int, signers: list[int]) -> bytes:
        """Aggregate s for digit j; uses exactly the signers given (the Rust
        code takes the first t of a larger set and refuses fewer than t)."""
        z = sum(self.partial(i, signers, j, bit) for i in signers) % N
        return z.to_bytes(32, "big")

    def attest(self, price: int, signers: list[int] | None = None) -> list[bytes]:
        ids = list(signers or range(1, self.t + 1))
        if signers is None or len(ids) >= self.t:
            ids = ids[:self.t]
        return [self.sign_digit(j, bit, ids) for j, bit in enumerate(decompose_price_bits(price, self.num_bits))]

    def announcement(self) -> dict:
        return {"event_id": self.event_id, "oracle_pubkey_x": self.P.hex(),
                "digit_nonces_x": [r.hex() for r in self.R], "threshold": f"{self.t}-of-{self.n}",
                "feldman_commitments": [xonly(c).hex() for c in self.feldman]}
