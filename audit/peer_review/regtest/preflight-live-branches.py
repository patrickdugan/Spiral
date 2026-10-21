"""Read-only readiness snapshot for unobserved live paths; never changes nodes."""
import hashlib
import json
import time
from pathlib import Path
from bootstrap import core
from fund import cln
from attest import save

chain_before = core("getbestblockhash")
info = cln("server", "getinfo")
plugins = cln("server", "plugin", "list")
chain_after = core("getbestblockhash")
if chain_before != chain_after:
    raise RuntimeError("chain changed during preflight")
active = [p["name"] for p in plugins["plugins"] if p["active"]]
hold_active = any(Path(name).name == "hold" for name in active)
result = {"evidence_class": "read_only_regtest_readiness", "captured_unix_ns": time.time_ns(),
          "chain": "regtest", "best_block_hash": chain_after, "cln_version": info["version"],
          "cln_height": info["blockheight"], "active_plugins": active, "hold_plugin_active": hold_active,
          "inbound_receive_ready": hold_active,
          "source_requirement": "Bark 8f5d8c4 server/src/ln/cln/hold.rs uses a hold-invoice plugin; contrib/docker/cln.Dockerfile builds BoltzExchange/hold v0.3.3.",
          "interpretation": "This checks a required plugin, not successful receipt. No live inbound/failure/exit/reorg result is inferred.",
          "runtime_identity_sha256": hashlib.sha256((Path(__file__).parent / "evidence/runtime-identity.json").read_bytes()).hexdigest()}
save("live-branch-preflight.json", result)
print(json.dumps({"height": result["cln_height"], "hold_plugin_active": hold_active}))
