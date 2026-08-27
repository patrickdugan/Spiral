"""Small entry point for the bonding and Sybil mechanics only."""

from __future__ import annotations

import json

from .proof_experiments import experiment_bonding, experiment_sybil


def main() -> int:
    print(json.dumps({"bonding": experiment_bonding(), "sybil": experiment_sybil()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

