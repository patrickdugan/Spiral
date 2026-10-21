"""One recorded 1,000-sat outgoing attempt, held then failed by owned receiver.

Never retries an uncertain monetary action. The plugin has its own 90-second
failure guard; the orchestration releases the hold in a finally block as well.
Historical reuse observations are immutable; this writes new branch labels.
"""
import hashlib
import json
import shutil
import re
import sys
import subprocess
import time
from pathlib import Path
from bootstrap import RUNTIME, DOCKER, core, docker
from launch import bark
from fund import cln
from attest import DEST, save
from observe import snapshot, redact
from pay import action


def control(payment_hash, release):
    path = RUNTIME / "cln-peer/spiral-fault-control.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"payment_hash": payment_hash, "release": release}))
    temporary.replace(path)


def fault_events():
    path = RUNTIME / "cln-peer/spiral-fault-events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "failure"
    amount = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    if not re.fullmatch(r"failure[a-z0-9-]*", label) or not 1 <= amount <= 10000:
        raise ValueError("bounded failure label and amount required")
    prefix = "fault" if label == "failure" else label
    intent_name = f"action-{prefix}-pay-{amount}.json"
    if (DEST / intent_name).exists():
        raise RuntimeError("Fault payment already attempted; inspect, never blindly repeat")
    if core("getblockchaininfo")["chain"] != "regtest":
        raise RuntimeError("owned regtest required")
    source = Path(__file__).with_name("hold-fail-plugin.py")
    installed = RUNTIME / "cln-peer/spiral-hold-fail.py"
    shutil.copyfile(source, installed); installed.chmod(0o755)
    interpreter = docker("exec", "spiral-cln-peer", "sha256sum", "/usr/bin/python3.11").stdout.split()[0]
    packages = docker("exec", "spiral-cln-peer", "dpkg-query", "-W", "python3", "python3.11", "libpython3.11-stdlib").stdout
    save(f"{label}-instrument.json", {"evidence_class": "owned_regtest_fault_instrument",
        "plugin_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "python_executable_sha256": interpreter,
        "kernel_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "python_packages": packages, "scope": "Dynamic receiver hook, 90-second fail guard, target hash only. No channel or consensus implementation change.",
        "container_overlay_change": "Python interpreter and standard library added to spiral-cln-peer; original CLN executable unchanged.",
        "corelightning_hook_reference": "https://docs.corelightning.org/reference/hook-htlc_accepted"})
    invoice = action(f"{prefix}-invoice-{amount}", lambda: cln("peer", "invoice", f"{amount * 1000}msat", f"spiral-{label}-{amount}", "owned regtest deliberate failure"))
    payment_hash = invoice["payment_hash"]
    control(payment_hash, False)
    action(f"{prefix}-plugin-start", lambda: cln("peer", "plugin", "start", "/data/spiral-hold-fail.py"))
    before = snapshot(f"{label}-before")
    process = None
    try:
        entry = {"state": "intent", "payment_hash": payment_hash, "amount_sat": amount,
                 "height": core("getblockcount"), "monotonic_start_ns": time.monotonic_ns()}
        save(intent_name, entry)
        process = subprocess.Popen([*DOCKER, "exec", "spiral-bark", "bark", "--datadir", "/data", "send", invoice["bolt11"], "--wait"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            if any(e["event"] == "receiver_hook_accepted" and e["payment_hash"] == payment_hash for e in fault_events()):
                break
            if process.poll() is not None:
                raise RuntimeError("Payment returned before the receiver hold was observed")
            time.sleep(.2)
        else:
            raise RuntimeError("Receiver hold not observed within 50 seconds")
        snapshot(f"{label}-in-flight", include_client=False)
        save(f"{label}-peer-in-flight.json", {"monotonic_ns": time.monotonic_ns(), "channels": cln("peer", "listpeerchannels")})
        control(payment_hash, True)
        stdout, stderr = process.communicate(timeout=120)
        entry.update(state="returned", exit_code=process.returncode, monotonic_end_ns=time.monotonic_ns(),
                     stdout=stdout, stderr=stderr)
        save(intent_name, entry)
        # A successful wait command may report a failed terminal payment via
        # movement status rather than a nonzero exit code. Observe actual state.
        bark("balance")
        after = snapshot(f"{label}-resolved")
        save(f"{label}-hook-events.json", {"payment_hash": payment_hash,
            "events": [e for e in fault_events() if e["payment_hash"] == payment_hash]})
        save(f"{label}-sendpays.json", redact(cln("server", "-k", "listsendpays", f"payment_hash={payment_hash}")))
        print(json.dumps({"payment_hash": payment_hash, "before_balance": before["bark_balance"],
                          "after_balance": after["bark_balance"], "exit_code": process.returncode}), flush=True)
    except Exception as exc:
        save(f"{label}-collector-error.json", {"type": type(exc).__name__, "message": str(exc),
            "stderr": getattr(exc, "stderr", None), "monotonic_ns": time.monotonic_ns(), "payment_hash": payment_hash})
        raise
    finally:
        control(payment_hash, True)
        if process is not None and process.poll() is None:
            # Do not kill an uncertain payment or start another. The receiver's
            # guard/release resolves it; preserve its state for inspection.
            print("Payment command still active: inspect existing attempt before any follow-up.", flush=True)
        else:
            save(f"{label}-plugin-stop.json", cln("peer", "plugin", "stop", "/data/spiral-hold-fail.py"))


if __name__ == "__main__":
    main()
