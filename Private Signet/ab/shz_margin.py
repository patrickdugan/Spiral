"""SatsHedgeZero contract semantics, ported from the Rust prototype.

Source: patrickdugan/SatsHedgeZero @ 5ca390e
- crates/shz-margin/src/lib.rs: InverseContractSpec, payout_at_price,
  liquidation prices, compress_cet_ranges (dyadic prefix CETs),
  decompose_price_bits.
- crates/shz-dlc/src/lib.rs: oracle_digit_message.

Integer arithmetic matches the Rust u128 code exactly; test_shz.py checks the
Rust crate's own test vectors.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

SATS_PER_BTC = 100_000_000
BPS = 10_000


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def _round_half_even(num: int, den: int) -> int:
    q, r = divmod(num, den)
    if 2 * r > den or (2 * r == den and q & 1):
        return q + 1
    return q


@dataclass(frozen=True)
class Payout:
    long_sats: int
    short_sats: int

    @property
    def total(self) -> int:
        return self.long_sats + self.short_sats


@dataclass(frozen=True)
class InverseContractSpec:
    """Inverse BTC/USD contract: `usd_notional` USD at `entry_price_usd`,
    margins in sats, zero protocol fee (SHZ v0)."""
    usd_notional: int
    entry_price_usd: int
    long_margin_sats: int
    short_margin_sats: int

    @staticmethod
    def margin_for_leverage_bps(usd_notional: int, entry_price_usd: int, leverage_bps: int) -> int:
        if min(usd_notional, entry_price_usd, leverage_bps) <= 0:
            raise ValueError("notional, price and leverage must be > 0")
        return _ceil_div(usd_notional * SATS_PER_BTC * BPS, entry_price_usd * leverage_bps)

    @classmethod
    def from_leverages_v0(cls, usd_notional: int, entry_price_usd: int,
                          long_leverage_bps: int, short_leverage_bps: int) -> "InverseContractSpec":
        m = cls.margin_for_leverage_bps
        return cls(usd_notional, entry_price_usd,
                   m(usd_notional, entry_price_usd, long_leverage_bps),
                   m(usd_notional, entry_price_usd, short_leverage_bps))

    @property
    def total_collateral_sats(self) -> int:
        return self.long_margin_sats + self.short_margin_sats

    def is_covered_synthetic_usd_short(self) -> bool:
        return self.short_margin_sats * self.entry_price_usd >= self.usd_notional * SATS_PER_BTC

    def unclamped_long_pnl_sats(self, price: int) -> int:
        if price == 0:
            return -self.total_collateral_sats
        q = self.usd_notional * SATS_PER_BTC
        p0 = self.entry_price_usd
        mag = _round_half_even(q * abs(price - p0), p0 * price)
        return mag if price >= p0 else -mag

    def payout_at_price(self, price: int) -> Payout:
        total = self.total_collateral_sats
        if price == 0:
            return Payout(0, total)
        long = min(max(self.long_margin_sats + self.unclamped_long_pnl_sats(price), 0), total)
        return Payout(long, total - long)

    def long_liquidation_price_usd(self) -> int:
        q = self.usd_notional * SATS_PER_BTC
        p0 = self.entry_price_usd
        return (p0 * q) // (q + self.long_margin_sats * p0)

    def short_liquidation_price_usd(self) -> int | None:
        if self.is_covered_synthetic_usd_short():
            return None
        q = self.usd_notional * SATS_PER_BTC
        p0 = self.entry_price_usd
        return _ceil_div(p0 * q, q - self.short_margin_sats * p0)


@dataclass(frozen=True)
class CetRange:
    prefix_bits: tuple[int, ...]
    min_price_usd: int
    max_price_usd: int
    payout: Payout

    def matches_price(self, price: int, num_bits: int) -> bool:
        p = min(price, (1 << num_bits) - 1)
        return self.min_price_usd <= p <= self.max_price_usd


def compress_cet_ranges(spec: InverseContractSpec, num_bits: int, max_error_sats: int) -> list[CetRange]:
    """Dyadic prefix partition of [0, 2^num_bits - 1]; same recursion, leaf
    rule and representative payout as the Rust `compress_dyadic_node`."""
    if not 4 <= num_bits <= 30:
        raise ValueError("num_bits must be 4..30")
    out: list[CetRange] = []
    total = spec.total_collateral_sats

    def node(lo: int, hi: int, prefix: list[int]) -> None:
        low, high = spec.payout_at_price(lo), spec.payout_at_price(hi)
        spread = max(high.long_sats - low.long_sats, 0)
        if prefix and (lo == hi or len(prefix) == num_bits or _ceil_div(spread, 2) <= max_error_sats):
            rep = (low.long_sats + high.long_sats) // 2
            out.append(CetRange(tuple(prefix), lo, hi, Payout(rep, total - rep)))
            return
        mid = lo + ((hi - lo) >> 1)
        node(lo, mid, prefix + [0])
        node(mid + 1, hi, prefix + [1])

    node(0, (1 << num_bits) - 1, [])
    return out


@dataclass(frozen=True)
class BookTrade:
    spec: InverseContractSpec
    long_party: str
    short_party: str


@dataclass(frozen=True)
class BookRange:
    prefix_bits: tuple[int, ...]
    min_price_usd: int
    max_price_usd: int
    payouts: dict          # party -> netted sats

    def matches_price(self, price: int, num_bits: int) -> bool:
        p = min(price, (1 << num_bits) - 1)
        return self.min_price_usd <= p <= self.max_price_usd


def book_payout_at_price(trades: list[BookTrade], price: int) -> dict:
    out: dict = {}
    for t in trades:
        p = t.spec.payout_at_price(price)
        out[t.long_party] = out.get(t.long_party, 0) + p.long_sats
        out[t.short_party] = out.get(t.short_party, 0) + p.short_sats
    return out


def compress_book_ranges(trades: list[BookTrade], num_bits: int, max_error_sats: int) -> list[BookRange]:
    """Dyadic prefix partition for several trades settling on ONE oracle
    event, paying each party its NETTED total. Each trade keeps SHZ's own
    representative (midpoint of its endpoint long payouts, short = total -
    long), so every range conserves every trade's collateral. A party's
    error is at most the sum of ceil(spread/2) over its trades; a node
    becomes a leaf when that bound is <= max_error_sats for every party
    (same root split and depth rules as compress_cet_ranges)."""
    if not 4 <= num_bits <= 30:
        raise ValueError("num_bits must be 4..30")
    out: list[BookRange] = []

    def node(lo: int, hi: int, prefix: list[int]) -> None:
        err: dict = {}
        net: dict = {}
        for t in trades:
            a, b = t.spec.payout_at_price(lo), t.spec.payout_at_price(hi)
            half = _ceil_div(max(b.long_sats - a.long_sats, 0), 2)
            rep = (a.long_sats + b.long_sats) // 2
            for party, amt in ((t.long_party, rep), (t.short_party, t.spec.total_collateral_sats - rep)):
                err[party] = err.get(party, 0) + half
                net[party] = net.get(party, 0) + amt
        if prefix and (lo == hi or len(prefix) == num_bits or max(err.values()) <= max_error_sats):
            out.append(BookRange(tuple(prefix), lo, hi, net))
            return
        mid = lo + ((hi - lo) >> 1)
        node(lo, mid, prefix + [0])
        node(mid + 1, hi, prefix + [1])

    node(0, (1 << num_bits) - 1, [])
    return out


def decompose_price_bits(price: int, num_bits: int) -> list[int]:
    p = min(price, (1 << num_bits) - 1)
    return [(p >> s) & 1 for s in range(num_bits - 1, -1, -1)]


def lookup_cet_for_price(cets: list[CetRange], price: int, num_bits: int) -> CetRange | None:
    for c in cets:
        if c.matches_price(price, num_bits):
            return c
    return None


def tagged_hash(tag: bytes, payload: bytes) -> bytes:
    t = hashlib.sha256(tag).digest()
    return hashlib.sha256(t + t + payload).digest()


def oracle_digit_message(event_id: str, digit_idx: int, bit_value: int) -> bytes:
    """shz-dlc: tagged_hash("SatsHedgeZero/DLC/DigitOutcome/v0",
    u32le(len) || event_id || digit_idx || bit_value). 32 bytes, so it fits
    the lab's 32-byte CSFS restriction unchanged."""
    e = event_id.encode()
    return tagged_hash(b"SatsHedgeZero/DLC/DigitOutcome/v0",
                       struct.pack("<I", len(e)) + e + bytes([digit_idx, bit_value]))
