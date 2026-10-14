"""Run exact leak-topology checks; no models or agents are contacted."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from spiral_ln.evaluation_leak_topology import verify


def _encode(value):
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return str(value)
    if isinstance(value, (tuple, set, frozenset)):
        return list(value)
    raise TypeError(f"cannot encode {type(value)!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"schema_version": "0.1",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(), **verify()}
    root = Path(__file__).resolve().parents[1]
    sources = ("scripts/verify_evaluation_leak_topology.py",
               "src/spiral_ln/evaluation_leak_topology.py",
               "src/spiral_ln/evaluation_feedback_lattice.py",
               "src/spiral_ln/evaluation_game_feedback.py",
               "src/spiral_ln/evaluation_game_testbed.py")
    report["source_sha256"] = {name: sha256((root/name).read_bytes()).hexdigest() for name in sources}
    report = json.loads(json.dumps(report, default=_encode))
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    else:
        print(rendered, end="")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
