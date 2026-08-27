"""Command-line entry point for the complete bounded experiment suite."""

from __future__ import annotations

import argparse
import json

from .proof_experiments import run_proof_suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/experiments")
    parser.add_argument("--seeds", type=int, default=24)
    args = parser.parse_args()
    summary = run_proof_suite(args.output, args.seeds)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

