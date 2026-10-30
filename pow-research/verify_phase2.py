"""Reproduce the isolated upstream-semantics/occupancy and reorg model receipt."""
import hashlib
import json
from pathlib import Path

from pow_lab import canonical
from reuse_campaign import report


def main() -> None:
    root = Path(__file__).resolve().parent
    receipt = json.loads((root / "evidence/phase2.json").read_text(encoding="utf-8"))
    for filename, expected in receipt["source_sha256"].items():
        actual = hashlib.sha256((root / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"source hash mismatch: {filename}")
    observed = hashlib.sha256(canonical(report())).hexdigest()
    if observed != receipt["report_sha256"]:
        raise SystemExit("replay mismatch")
    if receipt["upstream_native_validation"] is not False:
        raise SystemExit("invalid evidence scope")
    print(f"Verified bounded source-derived phase 2: {observed}")


if __name__ == "__main__":
    main()
