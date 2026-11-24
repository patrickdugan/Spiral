import json
from pathlib import Path
import shutil
import subprocess

base = Path("/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat")
repo = base / "outputs/ark-cashu-proofdesk"
bundle = Path("/tmp/shinigami-dual-audit.Uj17i0hJ/shinigami-cpu-pilot")
historical = Path("/var/tmp/proof-grove-shinigami-20261123/tapleaf-independent-verifier.proof.json")
command = ["python3", "-B", str(repo / "tests/run-regtest-stack.py"), "--cdk",
           str(base / "work/integration-bin/cdk-mintd-0.18.3-x86_64"), "--node",
           "/opt/node/bin/node", "--shinigami-redemption-bundle", str(bundle), "--test-funded-refusal",
           "--shinigami-redemption-external", "45"]
messages = []
target = None
try:
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as run:
        for line in run.stdout:
            messages.append(line)
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("status") != "waiting_for_redemption_proof":
                continue
            assert run.poll() is None, "Core fixture stopped before the handoff"
            candidate = Path(event["proof_target"]).resolve()
            assert candidate.is_relative_to(repo / ".runtime")
            assert candidate.parent.name.startswith("regtest-stack-") and candidate.name == "redemption-proof.json"
            partial = candidate.with_suffix(".tmp")
            shutil.copyfile(historical, partial)
            partial.replace(candidate)
            target = candidate
        code = run.wait()
    assert target is not None and code != 0, "".join(messages)[-3000:]
    report = json.loads((target.parent / "redemption-proof-audit.json").read_text())
    assert report["status"] == "failed" and report["case"] == "fresh_cashu_redemption"
    assert report["error"].partition(":")[0] == "shinigami_program_mismatch", report
    payout = json.loads((target.parent / "funded-refusal-report.json").read_text())
    print(json.dumps({"live_core_rechecked": True, "payout_sat": payout["payout_sat"],
                      "different_program_proof": "refused", "audit_status": report["status"]}))
finally:
    if target is not None:
        target.unlink(missing_ok=True)
