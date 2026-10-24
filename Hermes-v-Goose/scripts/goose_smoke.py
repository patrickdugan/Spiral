"""Run goose once through the control plane against the demo ledger, and audit it.

Starts the control module, the tool gateway and the model proxy (scripted) on
loopback, runs goose in the chosen tier and drive, and writes ``report.json``
in the run directory. goose is isolated from the user's setup (own
GOOSE_PATH_ROOT, keyring off, telemetry off, default extensions off) and every
non-loopback request it makes fails. No model weights are loaded.

    python scripts\\goose_smoke.py --run-dir results\\goose-smoke --tier hooks --drive acp
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime_control.adapters.goose import DRIVES, TIERS, find_goose, run_goose_controlled  # noqa: E402
from runtime_control.demo import DemoLedgerEnvironment, demo_engine_spec  # noqa: E402


PLAN = [
    {"tool": "ledger_pay", "arguments": {"amount": 10, "to": "alice"}},
    {"tool": "ledger_pay", "arguments": {"amount": 5, "to": "mallory"}},
    {"content": "Done: alice was paid; the payment to mallory was refused."},
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--goose", type=Path, default=find_goose())
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--tier", choices=TIERS, default="hooks")
    parser.add_argument("--drive", choices=DRIVES, default="run")
    args = parser.parse_args()
    if args.goose is None:
        parser.error("no goose binary found; pass --goose or set GOOSE_BIN")
    report = run_goose_controlled(
        goose_bin=args.goose,
        run_dir=args.run_dir.resolve(),
        environment=DemoLedgerEnvironment(),
        engines=[demo_engine_spec()],
        plan=PLAN,
        task="Pay alice 10 units.",
        tier=args.tier,
        drive=args.drive,
    )
    summary = {key: report[key] for key in ("exitCode", "drive", "advertisedTools", "decisions", "coverage", "view", "truth", "gatewayCalls", "ledger")}
    print(json.dumps(summary, indent=2))
    return 0 if report["exitCode"] == 0 and report["ledger"][0] else 1


if __name__ == "__main__":
    raise SystemExit(main())
