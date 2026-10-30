"""Replay the retained deterministic campaign and verify source provenance."""
import hashlib
import json
from pathlib import Path

import pow_lab


def main() -> None:
    root = Path(__file__).resolve().parent
    receipt = json.loads((root / "evidence/baseline.json").read_text(encoding="utf-8"))
    for name, expected in receipt["source_sha256"].items():
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"Source hash mismatch: {name}")
    report = pow_lab.run(receipt["seeds"], receipt["budget_per_instance"])
    actual = hashlib.sha256(pow_lab.canonical(report)).hexdigest()
    if actual != receipt["report_sha256"]:
        raise SystemExit("Campaign digest mismatch")
    solved = sum(row["verified"] for row in report["rows"])
    if solved != receipt["verified_witnesses"]:
        raise SystemExit("Witness count mismatch")
    print(f"Verified {len(report['rows'])} instances, {solved} witnesses; {actual}")


if __name__ == "__main__":
    main()
