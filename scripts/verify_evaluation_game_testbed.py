"""Run exact synthetic evaluation-game checks; no models or agents are contacted."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from spiral_ln.evaluation_game_testbed import verify


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
    report = {"schema_version": "1.0", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              **verify()}
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
