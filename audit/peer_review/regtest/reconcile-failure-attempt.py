"""Read and reconcile the existing interrupted failure collector; never resends."""
import json
import time
from bootstrap import RUNTIME, docker
from attest import DEST, save
from fund import cln
from observe import snapshot, redact

intent = json.loads((DEST / "action-fault-pay-1000.json").read_text())
payment_hash = intent["payment_hash"]
processes = docker("top", "spiral-bark", "-eo", "pid,args").stdout
if "bark --datadir" in processes:
    raise RuntimeError("Original Bark command still active; inspect it rather than opening another wallet command")
sendpays = redact(cln("server", "-k", "listsendpays", f"payment_hash={payment_hash}"))
if not sendpays["payments"] or any(p["status"] != "failed" for p in sendpays["payments"]):
    raise RuntimeError("Existing Lightning attempt is not conclusively failed")
save("failure-sendpays.json", sendpays)
snapshot("failure-resolved")
events = [json.loads(line) for line in (RUNTIME / "cln-peer/spiral-fault-events.jsonl").read_text().splitlines()]
save("failure-hook-events.json", {"payment_hash": payment_hash, "events": [e for e in events if e["payment_hash"] == payment_hash]})
save("failure-collection-gap.json", {"evidence_class": "collector_gap", "captured_monotonic_ns": time.monotonic_ns(),
    "failed_command": "bark balance --no-sync while original send --wait was active", "observed_exit_status": 1,
    "raw_stderr_available": False, "interpretation": "Concurrent wallet access failed; wallet locking is a source-supported explanation, not a preserved error-string observation.",
    "original_send_exit_status_available": False, "original_send_process_terminal": True,
    "repeated_payment": False, "pending_snapshot_available": False,
    "resolution_evidence": ["failure-sendpays.json", "failure-resolved.json", "failure-hook-events.json"]})
plugins = cln("peer", "plugin", "list")["plugins"]
if any(p["name"] == "/data/spiral-hold-fail.py" for p in plugins):
    save("failure-plugin-stop.json", cln("peer", "plugin", "stop", "/data/spiral-hold-fail.py"))
print(json.dumps({"payment_hash": payment_hash, "failed_attempts": len(sendpays["payments"]), "resend": False}))
