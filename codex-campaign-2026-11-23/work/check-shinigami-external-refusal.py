import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

base = Path("/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat")
repo = base / "outputs/ark-cashu-proofdesk"
bundle = Path("/tmp/proofdesk-shinigami-pilot-26maqmjn/shinigami-cpu-pilot")
historical = Path("/var/tmp/proof-grove-shinigami-20261123/tapleaf-independent-verifier.proof.json")
assert historical.is_file() and bundle.is_dir()

command = ["python3", "-B", str(repo/"tests/run-regtest-stack.py"), "--cdk",
           str(base/"work/integration-bin/cdk-mintd-0.18.3-x86_64"), "--node",
           "/opt/node/bin/node", "--shinigami-bundle", str(bundle), "--shinigami-external", "30"]
messages = []
handoff = None
with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as run:
    for line in run.stdout:
        messages.append(line)
        if not line.startswith("{"):
            continue
        record = json.loads(line)
        if record.get("status") != "waiting_for_shinigami_proof":
            continue
        assert run.poll() is None, "Expected a live quote during handoff"
        handoff = record
        case = Path(record["case_file"]).resolve()
        expected = json.loads(case.read_text())["statement"]["vtxo"]
        target = Path(record["proof_target"]).resolve()
        assert case.parent.is_relative_to(repo / ".runtime")
        assert target == case.parent / "verified-proofs" / f"{expected['txid']}-{expected['vout']}.json"
        partial = target.with_suffix(".tmp")
        shutil.copyfile(historical, partial)
        partial.replace(target)
    code = run.wait()
assert handoff is not None and code != 0, "".join(messages)[-3000:]
assert "shinigami_payment_mismatch" in "".join(messages), "".join(messages)[-3000:]
runtime = Path(handoff["case_file"]).parent
with sqlite3.connect(runtime/"desk.sqlite") as db:
    assert db.execute("SELECT count(*) FROM claims").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 0
Path(handoff["proof_target"]).unlink()  # Remove the historical replay copied solely for this test.
print(json.dumps({"waiting_process_confirmed_alive": True,
                  "historical_proof_for_other_payment": "refused",
                  "fresh_payment_admitted": False, "mint_issuance_prepared": False}))
