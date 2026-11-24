"""Keep the local supervisor awake and enforce the paid cap on one exact VM."""
import ctypes
import json
from pathlib import Path
import re
import runpy
import sys
import time


def run():
    state, key, ready = map(Path, sys.argv[1:4])
    name = sys.argv[4]
    maximum = int(sys.argv[5])
    if not re.fullmatch("ark-mnr04-a100-[a-f0-9]{10}", name) or not 60 <= maximum <= 8 * 3600:
        raise ValueError("invalid overnight lease identity")
    helpers = runpy.run_path(str(Path(__file__).with_name("hyperstack-shinigami-pilot.py")))
    client = helpers["Pilot"].__new__(helpers["Pilot"])
    client.credential = key.read_text(encoding="utf-8-sig").strip()
    client.http = helpers["urllib"].request.build_opener(helpers["NoRedirect"]())
    if not ctypes.windll.kernel32.SetThreadExecutionState(0x80000001):
        raise RuntimeError("could not keep the local cleanup watchdog awake")
    try:
        ready.touch()
        startup_end = time.monotonic() + 300
        while time.monotonic() < startup_end:
            try:
                snapshot = json.loads(state.read_text(encoding="utf-8"))
                if snapshot["name"] != name or snapshot.get("cleanup") == "vm_deleted":
                    return
                if snapshot.get("requested_at"):
                    client.name = name
                    deadline = int(snapshot["requested_at"]) + maximum - 115
                    break
            except (OSError, ValueError):
                pass
            time.sleep(5)
        else:
            return
        while time.time() < deadline:
            try:
                snapshot = json.loads(state.read_text(encoding="utf-8"))
                if snapshot["name"] == name and snapshot.get("cleanup") == "vm_deleted":
                    return
            except (OSError, ValueError):
                pass
            time.sleep(min(15, max(1, deadline-time.time())))
        confirmation_end = time.monotonic() + 120
        while time.monotonic() < confirmation_end:
            try:
                # The provider can allocate the instance even if the submitting
                # process exits before recording the POST response.
                candidates = [row for row in client.inventory() if row["name"] == name]
                if not candidates:
                    return
                if len(candidates) != 1:
                    raise ValueError("more than one VM matched the overnight lease")
                client.vm_id = int(candidates[0]["id"])
                machine = client.vm(missing_ok=True)
                if not machine or machine["status"] == "DELETED":
                    return
                if machine["status"] != "DELETING":
                    client.api("DELETE", f"core/virtual-machines/{client.vm_id}", missing_ok=True)
            except (OSError, RuntimeError):
                pass
            time.sleep(3)
        raise RuntimeError("unable to confirm the lease cutoff deletion")
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == "__main__":
    run()
