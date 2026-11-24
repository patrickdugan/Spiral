"""Prevent Windows idle sleep while one named private transfer is running."""
import ctypes
import json
from pathlib import Path
import sys
import time

handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, int(sys.argv[1]))
state = Path(sys.argv[2])
if not handle:
    raise SystemExit("transfer process is no longer present")
if not ctypes.windll.kernel32.SetThreadExecutionState(0x80000001):
    ctypes.windll.kernel32.CloseHandle(handle)
    raise SystemExit("could not request temporary wakefulness")
try:
    deadline = time.monotonic() + 4 * 3600
    while time.monotonic() < deadline:
        if ctypes.windll.kernel32.WaitForSingleObject(handle, 15000) == 0:
            break
        try:
            status = json.loads(state.read_text())
            if status.get("vm_id") or status.get("cleanup"):
                break
        except (OSError, ValueError):
            pass
finally:
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    ctypes.windll.kernel32.CloseHandle(handle)
