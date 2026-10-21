"""Read-only post-instrument pin check; never overwrites historical identity."""
import json
import time
from bootstrap import docker, core
from fund import cln
from attest import DEST, save

prior = json.loads((DEST / "runtime-identity.json").read_text())
expected = next(x["sha256"] for x in prior["executables"] if x["binary"] == "lightningd")
actual = docker("exec", "spiral-cln-peer", "sha256sum", "/usr/local/bin/lightningd").stdout.split()[0]
assert actual == expected
plugins = cln("peer", "plugin", "list")["plugins"]
assert not any(p["name"] == "/data/spiral-hold-fail.py" for p in plugins)
assert core("getblockhash", "0") == prior["genesis"]
save("failure-runtime-verification.json", {"captured_unix_ns": time.time_ns(),
    "lightningd_sha256": actual, "matches_prior_execution_pin": True, "fault_plugin_stopped": True,
    "receiver_packages": docker("exec", "spiral-cln-peer", "dpkg-query", "-W").stdout,
    "kernel_boot_id": docker("exec", "spiral-cln-peer", "cat", "/proc/sys/kernel/random/boot_id").stdout.strip(),
    "chain_tip": core("getbestblockhash"), "height": core("getblockcount"),
    "interpretation": "Container overlay includes the declared Python instrument dependencies; Lightning executable remains pinned."})
print(json.dumps({"binary_pin_matches": True, "fault_plugin_stopped": True}))
