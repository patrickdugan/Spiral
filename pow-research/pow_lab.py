"""Offline, bounded proof-of-work research. Standard library; Python 3.10+."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

VERSION = "spiral-pow-lab-v1"
FAMILIES = ("hashcash", "cunningham1", "cunningham2", "bitwin", "sat", "ecdlp")
MAX_PRIME = (1 << 24) - 1
MAX_WIRE = 65536


def integer(x: Any, low: int, high: int) -> bool:
    return type(x) is int and low <= x <= high


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class Challenge:
    family: str
    parent: str
    payload: str
    beacon: str
    epoch: int = 0
    bits: int = 10
    length: int = 3
    variables: int = 10
    clauses: int = 43
    version: str = VERSION

    def __post_init__(self) -> None:
        if self.version != VERSION or self.family not in FAMILIES:
            raise ValueError("unsupported challenge")
        for field in (self.parent, self.payload, self.beacon):
            if type(field) is not str or len(field) != 64 or any(
                    c not in "0123456789abcdef" for c in field):
                raise ValueError("context fields must be lowercase 32-byte hex")
        for value, low, high in ((self.epoch, 0, 2**32-1), (self.bits, 4, 16),
                                 (self.length, 2, 6), (self.variables, 3, 16),
                                 (self.clauses, 1, 128)):
            if not integer(value, low, high):
                raise ValueError("parameter outside research bounds")

    @property
    def id(self) -> str:
        return digest(asdict(self))


def fixture(family: str, seed: int = 0, **kw: Any) -> Challenge:
    if not integer(seed, 0, 2**32-1):
        raise ValueError("invalid seed")
    return Challenge(family, digest(["parent", seed]), digest(["payload", seed]),
                     digest(["beacon", seed]), **kw)


def ticket(cid: str, nonce: int, work: Counter) -> bytes:
    work["sha256"] += 2
    data = b"spiral/pow/ticket/v1\x00" + bytes.fromhex(cid) + nonce.to_bytes(4, "big")
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def origin(raw: bytes, bits: int) -> int:
    # Deliberately small range: collisions and precomputation are measurable.
    return 2 * (1 + int.from_bytes(raw, "big") % (2**(bits-1) - 1))


def chain_terms(center: int, family: str, length: int) -> list[int]:
    if not integer(center, 2, 2**16) or center % 2:
        raise ValueError("invalid origin")
    if not integer(length, 2, 6):
        raise ValueError("invalid length")
    if family == "bitwin":
        # Length counts individual primes, including odd-length prefixes.
        return [(center << (i//2)) + (-1 if i % 2 == 0 else 1)
                for i in range(length)]
    if family not in ("cunningham1", "cunningham2"):
        raise ValueError("invalid prime family")
    sign = -1 if family == "cunningham1" else 1
    return [(center << i) + sign for i in range(length)]


def prime(n: int, work: Counter) -> bool:
    if not integer(n, 2, MAX_PRIME):
        return False
    for d in range(2, math.isqrt(n) + 1):
        work["trial_divisions"] += 1
        if n % d == 0:
            return False
    return True


def modpow(a: int, b: int, n: int, work: Counter) -> int:
    work["modular_exponentiations"] += 1
    return pow(a, b, n)


def certify(n: int, work: Counter) -> dict:
    """Full-factorization Lucas/Pratt certificate; generation is toy-bounded."""
    if not prime(n, work):
        raise ValueError("composite or out of bounds")
    if n == 2:
        return {"n": 2, "a": 0, "f": []}
    factors, rest, d = [], n - 1, 2
    while d*d <= rest:
        exponent = 0
        while True:
            work["trial_divisions"] += 1
            if rest % d:
                break
            exponent += 1
            rest //= d
        if exponent:
            factors.append([d, exponent, certify(d, work)])
        d += 1
    if rest > 1:
        factors.append([rest, 1, certify(rest, work)])
    for a in range(2, n):
        if modpow(a, n-1, n, work) == 1 and all(
            math.gcd(modpow(a, (n-1)//q, n, work)-1, n) == 1
            for q, _, _ in factors
        ):
            return {"n": n, "a": a, "f": factors}
    raise AssertionError("prime must have a Lucas witness")


def check_certificate(cert: Any, n: int, work: Counter, depth: int = 0) -> bool:
    work["certificate_nodes"] += 1
    if depth > 24 or work["certificate_nodes"] > 2048:
        return False
    if not integer(n, 2, MAX_PRIME) or type(cert) is not dict:
        return False
    if set(cert) != {"n", "a", "f"} or type(cert["n"]) is not int or cert["n"] != n:
        return False
    a, factors = cert["a"], cert["f"]
    if type(factors) is not list or len(factors) > 24:
        return False
    if n == 2:
        return type(a) is int and a == 0 and factors == []
    if not integer(a, 2, n-1) or not factors:
        return False
    product, previous = 1, 1
    for item in factors:
        if type(item) is not list or len(item) != 3:
            return False
        q, exponent, child = item
        if not integer(q, previous+1, n-1) or not integer(exponent, 1, 24):
            return False
        if not check_certificate(child, q, work, depth+1):
            return False
        product *= q**exponent
        if product > n-1:
            return False
        previous = q
    if product != n-1 or modpow(a, n-1, n, work) != 1:
        return False
    return all(math.gcd(modpow(a, (n-1)//q, n, work)-1, n) == 1
               for q, _, _ in factors)


def sat_instance(c: Challenge, work: Counter) -> list[list[int]]:
    """Unplanted formula; generation is fixed by context, never by a witness."""
    result = []
    for i in range(c.clauses):
        work["sha256"] += 1
        raw = hashlib.sha256(bytes.fromhex(c.id) + b"/sat/" + i.to_bytes(2, "big")).digest()
        pool, clause = list(range(1, c.variables+1)), []
        for j in range(3):
            variable = pool.pop(int.from_bytes(raw[2*j:2*j+2], "big") % len(pool))
            clause.append(variable if raw[8+j] & 1 else -variable)
        result.append(clause)
    return result


def satisfies(formula: list[list[int]], assignment: int, work: Counter) -> bool:
    for clause in formula:
        work["clause_checks"] += 1
        if not any(bool(assignment & (1 << (abs(x)-1))) == (x > 0) for x in clause):
            return False
    return True


# Entire toy curve has 199 points, including infinity. Checked exhaustively in tests.
FIELD, ORDER, BASE = 211, 199, (3, 33)
Point = tuple[int, int] | None


def ec_add(p: Point, q: Point, work: Counter) -> Point:
    work["ec_additions"] += 1
    if p is None:
        return q
    if q is None:
        return p
    x, y = p
    u, v = q
    if x == u and (y + v) % FIELD == 0:
        return None
    numerator, denominator = (3*x*x, 2*y) if p == q else (v-y, u-x)
    slope = numerator * pow(denominator, -1, FIELD) % FIELD
    rx = (slope*slope-x-u) % FIELD
    return rx, (slope*(x-rx)-y) % FIELD


def ec_mul(k: int, p: Point, work: Counter) -> Point:
    out = None
    while k:
        if k & 1:
            out = ec_add(out, p, work)
        p = ec_add(p, p, work)
        k >>= 1
    return out


def ec_target(c: Challenge, work: Counter) -> Point:
    # Small try-and-increment fixture, explicitly not RFC 9380 hash-to-curve.
    x0 = int(c.id, 16) % FIELD
    for i in range(FIELD):
        x = (x0+i) % FIELD
        rhs = (x*x*x+7) % FIELD
        y = modpow(rhs, (FIELD+1)//4, FIELD, work)
        if y*y % FIELD == rhs:
            return x, y if int(c.id[-1], 16) % 2 else (-y) % FIELD
    raise AssertionError("curve has points")


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def verify(c: Challenge, raw: bytes, work: Counter | None = None) -> bool:
    """Verify against caller-supplied context and parameters; fail closed on wire data."""
    work = Counter() if work is None else work
    if type(raw) is not bytes or len(raw) > MAX_WIRE:
        return False
    try:
        proof = json.loads(raw, object_pairs_hook=unique_pairs)
        if canonical(proof) != raw or type(proof) is not dict:
            return False
        if set(proof) != {"challenge", "nonce", "solution", "certificates"}:
            return False
        if proof["challenge"] != c.id or not integer(proof["nonce"], 0, 2**32-1):
            return False
        nonce, solution, certs = proof["nonce"], proof["solution"], proof["certificates"]
        if c.family == "hashcash":
            hashed = ticket(c.id, nonce, work)
            return certs == [] and solution == hashed.hex() and int.from_bytes(
                hashed, "big") < 2**(256-c.bits)
        if c.family == "sat":
            return nonce == 0 and certs == [] and integer(solution, 0, 2**c.variables-1) and satisfies(
                sat_instance(c, work), solution, work)
        if c.family == "ecdlp":
            return nonce == 0 and certs == [] and integer(solution, 1, ORDER-1) and ec_mul(
                solution, BASE, work) == ec_target(c, work)
        terms = chain_terms(origin(ticket(c.id, nonce, work), c.bits), c.family, c.length)
        if type(solution) is not list or len(solution) != c.length or any(
                type(x) is not int for x in solution) or solution != terms:
            return False
        return type(certs) is list and len(certs) == c.length and all(
            check_certificate(cert, n, work) for cert, n in zip(certs, terms))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False


def solve(c: Challenge, budget: int = 4096) -> tuple[bytes | None, dict]:
    if not integer(budget, 1, 65536):
        raise ValueError("budget outside 1..65536")
    search, generation, certification = Counter(), Counter(), Counter()
    cid = c.id
    formula = sat_instance(c, generation) if c.family == "sat" else []
    target = ec_target(c, generation) if c.family == "ecdlp" else None
    limit = min(budget, 2**c.variables if c.family == "sat" else ORDER if c.family == "ecdlp" else budget)
    point, wire, tested = None, None, 0
    for attempt in range(limit):
        tested += 1
        nonce, certificates = attempt, []
        if c.family == "sat":
            solution, nonce = attempt, 0
            good = satisfies(formula, solution, search)
        elif c.family == "ecdlp":
            solution, nonce = attempt, 0
            good = point == target
            if not good:
                point = ec_add(point, BASE, search)
        else:
            hashed = ticket(cid, nonce, search)
            if c.family == "hashcash":
                solution = hashed.hex()
                good = int.from_bytes(hashed, "big") < 2**(256-c.bits)
            else:
                solution = chain_terms(origin(hashed, c.bits), c.family, c.length)
                good = all(prime(p, search) for p in solution)
                if good:
                    certificates = [certify(p, certification) for p in solution]
        if good:
            wire = canonical({"challenge": cid, "nonce": nonce,
                              "solution": solution, "certificates": certificates})
            break
    exhausted = c.family == "sat" and tested == 2**c.variables and wire is None
    stats = {"family": c.family, "challenge": asdict(c), "challenge_id": cid,
             "status": "solved" if wire else "exhaustive_unsat" if exhausted else "budget_exhausted",
             "candidates_tested": tested, "budget": budget,
             "generation_work": dict(generation), "search_work": dict(search),
             "certificate_work": dict(certification), "proof_bytes": len(wire) if wire else 0}
    return wire, stats


def artifact_id(family: str, terms: list[int]) -> str:
    """Research registry key for an exact ordered chain; excludes certificates."""
    return digest(["spiral/prime-artifact/v1", family, terms])


def overlap(a: list[int], b: list[int]) -> list[int]:
    return sorted(set(a) & set(b))


def shortcut_share(initial_share: float, speedup: float) -> float:
    if not math.isfinite(initial_share) or not 0 <= initial_share <= 1:
        raise ValueError("invalid share")
    if not math.isfinite(speedup) or speedup <= 0:
        raise ValueError("invalid speedup")
    return initial_share*speedup / (1-initial_share+initial_share*speedup)


def run(seeds: int = 8, budget: int = 4096) -> dict:
    if not integer(seeds, 1, 64):
        raise ValueError("seeds outside 1..64")
    rows, seen = [], set()
    for family in FAMILIES:
        for seed in range(seeds):
            c = fixture(family, seed)
            wire, row = solve(c, budget)
            checks = Counter()
            row.update(seed=seed, proof_sha256=None, verified=False,
                       exact_artifact_repeat=None)
            if wire is not None:
                row["verified"] = verify(c, wire, checks)
                if not row["verified"]:
                    raise AssertionError("solver emitted invalid witness")
                row["proof_sha256"] = hashlib.sha256(wire).hexdigest()
                if family.startswith("cunningham") or family == "bitwin":
                    key = artifact_id(family, json.loads(wire)["solution"])
                    row["exact_artifact_repeat"] = key in seen
                    seen.add(key)
            row["verification_work"] = dict(checks)
            rows.append(row)
    return {"schema": VERSION, "evidence_class": "bounded_synthetic",
            "seeds": seeds, "budget_per_instance": budget,
            "units": "typed operation counters; no cross-family cost equivalence",
            "energy_joules": None, "economic_security_usd": None,
            "context_digest_cost_counted": False,
            "shortcut_scenario": {"initial_share": 0.1, "speedup": 10,
                                  "effective_share": shortcut_share(0.1, 10)},
            "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--budget", type=int, default=4096)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.seeds, args.budget)
    except ValueError as error:
        parser.error(str(error))
    text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
