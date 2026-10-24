"""Compare two runtime arms' ledgers run by run (design 8.6, soundness step 4).

Runs are matched by run id under <runs-root>/<experiment>/<arm>/. For each pair
the decision projection (``runtime_control.replay.decision_projection``) must
be equal: what the control plane proposed, decided, leased and recorded,
without the runtime record, native call ids and names, timestamps, sequence
numbers, ledger-position ids, state hashes, and the proxy's prompt records.

Usage: python scripts/compare_arm_ledgers.py --runs-root <dir> --experiment <id> --arms R1 R2
Prints one JSON object.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime_control.replay import compare_projections  # noqa: E402


def compare(runs_root: Path, experiment: str, left: str, right: str) -> dict:
    base = runs_root / experiment
    a = {p.name for p in (base / left).iterdir() if (p / "ledger.jsonl").exists()} if (base / left).is_dir() else set()
    b = {p.name for p in (base / right).iterdir() if (p / "ledger.jsonl").exists()} if (base / right).is_dir() else set()
    pairs = sorted(a & b)
    differing = {}
    for run_id in pairs:
        result = compare_projections(base / left / run_id, base / right / run_id)
        if not result["equal"]:
            differing[run_id] = result
    return {"arms": [left, right], "compared": len(pairs), "equal": len(pairs) - len(differing), "differing": differing, "unpaired": sorted(a ^ b)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--arms", nargs=2, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(compare(Path(args.runs_root), args.experiment, *args.arms), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
