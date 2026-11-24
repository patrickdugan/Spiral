"""Enforce the one-hour budget for one named Hyperstack pilot."""
import json
from pathlib import Path
import re
import runpy
import sys
import time

state_path, credential_path = map(Path, sys.argv[1:3])
expected_name = sys.argv[3]
if not re.fullmatch(r"ark-mnr04-a100-[a-f0-9]{10}", expected_name):
    raise SystemExit("unexpected pilot namespace")
helper = runpy.run_path(str(Path(__file__).with_name("hyperstack-shinigami-pilot.py")))
client = helper["Pilot"].__new__(helper["Pilot"])
client.credential = credential_path.read_text(encoding="utf-8-sig").strip()
client.http = helper["urllib"].request.build_opener(helper["NoRedirect"]())

startup_cutoff = time.monotonic() + 3800
deadline = None
while deadline is None and time.monotonic() < startup_cutoff:
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        time.sleep(3)
        continue
    if state["name"] != expected_name or state.get("cleanup") == "vm_deleted":
        raise SystemExit(0)
    if state.get("requested_at") and state.get("vm_id"):
        deadline = int(state["requested_at"]) + 3510
        vm_id = int(state["vm_id"])
        break
    time.sleep(8)
if deadline is None:
    raise SystemExit(0)

while time.time() < deadline:
    try:
        state = json.loads(state_path.read_text())
        if state["name"] == expected_name and state.get("cleanup") == "vm_deleted":
            raise SystemExit(0)
    except (OSError, ValueError):
        pass
    time.sleep(max(1, min(10, deadline - time.time())))

client.name = expected_name
client.vm_id = vm_id
for _ in range(3):
    try:
        machine = client.vm(missing_ok=True)
        if machine is None or machine["status"] == "DELETED":
            break
        client.api("DELETE", f"core/virtual-machines/{vm_id}", missing_ok=True)
        print(json.dumps({"budget_watchdog_requested_deletion": vm_id}), flush=True)
        break
    except (OSError, TimeoutError):
        time.sleep(2)
else:
    raise SystemExit("billing watchdog could not confirm the VM deletion request")
