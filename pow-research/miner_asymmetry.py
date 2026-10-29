"""Finite stochastic security model for algorithmic-shortcut PoW asymmetry.

Offline mathematics only. Independent winner draws assume fixed hash/work rates,
no latency, no retarget feedback, and constant miner allocation.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from math import comb


def rate_share(attacker_fraction: Fraction, relative_speed: Fraction) -> Fraction:
    if not 0 <= attacker_fraction <= 1 or relative_speed <= 0:
        raise ValueError("invalid share or speedup")
    return attacker_fraction * relative_speed / (
        1 - attacker_fraction + attacker_fraction * relative_speed
    )


def majority_tail(p: Fraction, blocks: int) -> Fraction:
    """Exact probability of strictly more than half of N independent wins."""
    if not 1 <= blocks <= 1024:
        raise ValueError("block count outside 1..1024")
    q = 1 - p
    return sum(
        (Fraction(comb(blocks, k)) * p ** k * q ** (blocks-k)
         for k in range(blocks // 2 + 1, blocks + 1)),
        Fraction(0),
    )


def max_speedup_before_majority(alpha: Fraction) -> Fraction | None:
    """Critical speedup for rate share = 1/2 (strict dominance above)."""
    if not 0 <= alpha <= 1:
        raise ValueError("invalid share")
    if alpha == 0:
        return None
    if alpha == 1:
        return Fraction(0)
    return (1-alpha) / alpha


def scenario(numerator: int, denominator: int, speedup: int,
             blocks: int) -> dict:
    if not 0 <= numerator <= denominator or denominator <= 0 or speedup <= 0:
        raise ValueError("invalid scenario")
    alpha = Fraction(numerator, denominator)
    p = rate_share(alpha, Fraction(speedup))
    tail = majority_tail(p, blocks)
    threshold = max_speedup_before_majority(alpha)
    return {
        "baseline_share": str(alpha),
        "speedup": speedup,
        "effective_share": str(p),
        "blocks": blocks,
        "strict_majority_probability": str(tail),
        "strict_majority_probability_decimal": round(float(tail), 10),
        "critical_speedup": str(threshold) if threshold is not None else None,
        "assumptions": "fixed resources; independent block winners; no latency, strategy, or retarget feedback",
        "evidence_class": "exact_finite_model",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", type=int, default=21)
    parser.add_argument("--out")
    args = parser.parse_args()
    rows = [scenario(1, 10, s, args.blocks) for s in (1, 2, 5, 10, 20)]
    report = {"schema": "spiral-pow-asymmetry-v1", "rows": rows,
              "energy_joules": None, "dollar_attack_cost": None}
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.out:
        from pathlib import Path
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
