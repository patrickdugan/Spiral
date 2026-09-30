"""Run exact synthetic evaluation-game checks; no models or agents are contacted."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from fractions import Fraction as Q
from hashlib import sha256
from pathlib import Path

from spiral_ln.evaluation_game_testbed import verify
from spiral_ln.evaluation_game_confirmation import (
    adaptation_fixture, run_confirmation_fixture, optimal_allocation, zero_sum_certificate,
)


def _encode(value):
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"cannot encode {type(value)!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"schema_version": "1.1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              **verify()}
    report["confirmation"] = run_confirmation_fixture()
    report["adaptation"] = adaptation_fixture()
    report["primal_dual_certificate"] = zero_sum_certificate(
        ((Q(1), Q(-1)), (Q(-1), Q(1))), (Q(1, 2), Q(1, 2)), (Q(1, 2), Q(1, 2)))
    report["allocation"] = optimal_allocation((Q(1, 4),)*4, (Q(1),)*4, (2,)*4, 96)
    report["checks"].update(
        heldout_interaction_confirmed=report["confirmation"]["fixture_interaction_supported"],
        feasible_primal_dual_equal=report["primal_dual_certificate"]["optimality_certified"],
        balanced_allocation_optimal=report["allocation"]["counts"] == (12, 12, 12, 12))
    report["all_passed"] = all(report["checks"].values())
    root = Path(__file__).resolve().parents[1]
    sources = ("scripts/verify_evaluation_game_testbed.py", "src/spiral_ln/evaluation_game_testbed.py",
               "src/spiral_ln/evaluation_game_confirmation.py")
    report["source_sha256"] = {name: sha256((root/name).read_bytes()).hexdigest() for name in sources}
    rendered = json.dumps(report, indent=2, default=_encode) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    else:
        print(rendered, end="")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
