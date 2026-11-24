#!/usr/bin/env bash
set -euo pipefail
umask 077
case_root=/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat/outputs/ark-cashu-proofdesk/.runtime
bundle=/var/tmp/proofdesk-paired-bundle.ICs7BUPt/shinigami-cpu-pilot
runner="$bundle/benchmarks/shinigami/run.py"
test -f "$runner"
scratch=$(mktemp -d /var/tmp/cashu-pair-reverify.XXXXXX)
issuance="$case_root/cdk-e2e-1e97dc74f2"
payout="$case_root/regtest-stack-hvjk1b9v"
issue_proof="$issuance/verified-proofs/d4f6d30c2a8208bc620bbd5772ace5524226df0d05a9ae2a64a086a32584f977-0.json"
python3 "$runner" "$scratch/issuance" --threads 1 --max-seconds 40 \
  --regtest-case "$issuance/shinigami-case.json" --audit-proof "$issue_proof"
python3 "$runner" "$scratch/redemption" --threads 1 --max-seconds 40 \
  --redemption-case "$payout/redemption-case" --audit-proof "$payout/redemption-proof.json"
python3 - "$scratch" <<'PY'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
for name in ("issuance", "redemption"):
    report = json.loads((root / name / "report.json").read_bytes())
    assert report["status"] == "existing_proof_audited"
    assert report["phases"]["verify"]["exit_code"] == 0
    assert all(report["phases"][key]["exit_code"] == 1 for key in (
        "reject_changed_anchor_amount", "reject_changed_commitment"
    ))
    print(json.dumps({"case": name, "sha256": report["verifier_input_sha256"],
                      "verified": True, "negative_controls": 2}))
PY
