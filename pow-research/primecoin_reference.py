"""Source-derived *bounded* Primecoin scoring oracle; not native consensus.

Pinned upstream prime.cpp/prime.h: 8acbee471c69a39bdb04ac2a941edb7112fb5dfa.
Important: tests of small origins bypass upstream's 255-bit header floor.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

UPSTREAM_COMMIT = "8acbee471c69a39bdb04ac2a941edb7112fb5dfa"
UPSTREAM_PRIME_CPP_BLOB = "5cd7669c0cbca70ad851d4ce27052bc059defc21"
UPSTREAM_PRIME_H_BLOB = "b3d9766289a1d27f738a38181047792a1eba50c1"
FRAC_BITS = 24
FRAC_UNIT = 1 << FRAC_BITS
FRAC_MASK = FRAC_UNIT - 1
MAX_ORIGIN_BITS = 2000
HEADER_FLOOR = 1 << 255
MAX_TARGET_LENGTH = 99


def uint(value: int, limit: int) -> bool:
    return type(value) is int and 0 <= value <= limit


def target_parts(bits: int) -> tuple[int, int]:
    if not uint(bits, (1 << 32) - 1):
        raise ValueError("target must be uint32")
    return bits >> FRAC_BITS, bits & FRAC_MASK


def encode_target(length: int, fraction: int = 0) -> int:
    if not uint(length, 255) or not uint(fraction, FRAC_MASK):
        raise ValueError("invalid target component")
    return (length << FRAC_BITS) | fraction


def target_fractional_difficulty(bits: int) -> int:
    _, fraction = target_parts(bits)
    # Integer truncation, as in Primecoin's uint64 implementation.
    return (1 << (FRAC_BITS + 32)) // (FRAC_UNIT - fraction)


def fractional_failure(n: int, residue: int) -> int:
    if type(n) is not int or n < 3 or n % 2 == 0 or not uint(residue, n - 1):
        raise ValueError("expect odd n >= 3 and residue in [0,n)")
    fraction = ((n - residue) << FRAC_BITS) // n
    if fraction >= FRAC_UNIT:
        raise ValueError("upstream fractional assertion failure")
    return fraction


def fermat(n: int) -> tuple[bool, int]:
    if type(n) is not int or n < 3 or n % 2 == 0:
        raise ValueError("only odd n >=3 supported in the bounded oracle")
    residue = pow(2, n - 1, n)
    return (True, 0) if residue == 1 else (False, fractional_failure(n, residue))


def ell(n: int, first_kind: bool) -> tuple[bool, int]:
    """Euler-Lagrange-Lifchitz continuation, matching prime.cpp:115-143."""
    if type(n) is not int or n < 3 or n % 2 == 0 or type(first_kind) is not bool:
        raise ValueError("invalid ELL input")
    residue = pow(2, (n - 1) // 2, n)
    case = n % 8
    if first_kind:
        if case not in (3, 7):
            return False, 0  # upstream logs invalid case and returns false
        passed = residue == (1 if case == 7 else n - 1)
    else:
        if case not in (1, 5):
            return False, 0
        passed = residue == (1 if case == 1 else n - 1)
    if passed:
        return True, 0
    return False, fractional_failure(n, residue * residue % n)


def cunningham_length(origin: int, first_kind: bool, fermat_only: bool = False,
                      max_steps: int = 120) -> int:
    """Bits in upstream 8.24 chain-length format; bounded if no failure found."""
    if type(origin) is not int or origin < 4 or origin % 2 or type(first_kind) is not bool or type(fermat_only) is not bool:
        raise ValueError("expect even chain origin >=4 and boolean mode")
    if not uint(max_steps, 120) or max_steps < 1:
        raise ValueError("invalid step cap")
    n = origin - 1 if first_kind else origin + 1
    passed, fraction = fermat(n)
    if not passed:
        return fraction
    length = 0
    for _ in range(max_steps):
        length += 1
        n = n * 2 + (1 if first_kind else -1)
        passed, fraction = fermat(n) if fermat_only else ell(n, first_kind)
        if not passed:
            return encode_target(length, fraction)
    raise ValueError("chain exceeds bounded oracle step cap")


def bi_twin_length(first_bits: int, second_bits: int) -> int:
    a, _ = target_parts(first_bits)
    b, _ = target_parts(second_bits)
    # prime.cpp:350-353: the shorter side's fraction, twice the shorter length,
    # with one extra terminal prime if first-kind chain is longer.
    return second_bits + encode_target(b + 1) if a > b else first_bits + encode_target(a)


@dataclass(frozen=True)
class Scores:
    cunningham1: int
    cunningham2: int
    bitwin: int

    def best(self) -> tuple[str, int]:
        # Upstream's strict > tie precedence is first-kind, second-kind, bi-twin.
        family, score = "cunningham1", self.cunningham1
        if self.cunningham2 > score:
            family, score = "cunningham2", self.cunningham2
        if self.bitwin > score:
            family, score = "bitwin", self.bitwin
        return family, score


def scores(origin: int, fermat_only: bool = False) -> Scores:
    first = cunningham_length(origin, True, fermat_only)
    second = cunningham_length(origin, False, fermat_only)
    return Scores(first, second, bi_twin_length(first, second))


def check_header_bounds(header_hash: int, multiplier: int, bits: int) -> str | None:
    if not uint(header_hash, (1 << 256) - 1) or not uint(multiplier, (1 << MAX_ORIGIN_BITS) - 1):
        return "noncanonical_header_or_multiplier"
    length, _ = target_parts(bits)
    if not 6 <= length <= MAX_TARGET_LENGTH:
        return "target_length"
    if header_hash < HEADER_FLOOR:
        return "header_hash_below_limit"
    origin = header_hash * multiplier
    if origin < HEADER_FLOOR:
        return "origin_too_small"
    if origin > (1 << MAX_ORIGIN_BITS) - 1:
        return "origin_too_large"
    return None


def acceptance_preview(header_hash: int, multiplier: int, bits: int,
                       *, small_origin_fixture: bool = False) -> dict:
    """Independent Python approximation of prime.cpp:385-477.

    Small fixtures admit target length 2..99 and arbitrary positive header hashes,
    so the experiment is useful without claiming real-block validation.
    """
    if type(small_origin_fixture) is not bool:
        raise ValueError("fixture flag must be bool")
    if small_origin_fixture:
        target_len, _ = target_parts(bits)
        if not 2 <= target_len <= MAX_TARGET_LENGTH or not uint(header_hash, (1 << 256) - 1) or not uint(multiplier, (1 << MAX_ORIGIN_BITS) - 1):
            return {"accepted": False, "reason": "fixture_header_bounds"}
        if header_hash * multiplier < 4 or (header_hash * multiplier) % 2:
            return {"accepted": False, "reason": "fixture_origin"}
    else:
        error = check_header_bounds(header_hash, multiplier, bits)
        if error:
            return {"accepted": False, "reason": error}
    origin = header_hash * multiplier
    main = scores(origin)
    family, best = main.best()
    result = {"accepted": False, "origin": origin, "scores": asdict(main),
              "best_family": family, "best_bits": best}
    if best < bits:
        result["reason"] = "below_target"
        return result
    fermat_scores = scores(origin, True)
    if main != fermat_scores:
        result["reason"] = "fermat_cross_check_mismatch"
        result["fermat_scores"] = asdict(fermat_scores)
        return result
    if multiplier % 2 == 0 and origin % 4 == 0:
        half = scores(origin // 2)
        if half.best()[1] >= bits and half.best()[1] > best:
            result["reason"] = "non_normalized_multiplier"
            result["half_best_bits"] = half.best()[1]
            return result
    result["accepted"] = True
    result["reason"] = "accepted_in_bounded_oracle"
    return result
