"""Bind the forecast's pricing rules to inspected source and executed config."""
import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

revision = "8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a"
source = Path("../bark-runtime-source")
identity_path = Path("audit/peer_review/regtest/evidence/runtime-identity.json")
identity = json.loads(identity_path.read_text(encoding="utf-8"))
config = tomllib.loads(identity["configurations"]["captaind.toml"]["redacted_text"])
table = [{"expiry_blocks_threshold": t, "ppm": p} for t, p in [(0, 0), (97, 1000), (199, 4000), (2161, 8000)]]
assert config["fees"]["board"] == {"min_fee_sat": 330, "base_fee_sat": 100, "ppm": 1000}
assert config["fees"]["lightning_receive"] == {"base_fee_sat": 100, "ppm": 2000}
assert config["fees"]["refresh"] == {"base_fee_sat": 150, "ppm_expiry_table": table}
assert config["fees"]["lightning_send"] == {"min_fee_sat": 10, "base_fee_sat": 75, "ppm_expiry_table": table}
assert config["ln_max_fee_ppm"] == 900000
assert config["max_vtxo_exit_depth"] == 100
assert config["min_board_amount"] == "20000 sat"
files = []
for path in ["lib/src/fees.rs", "lib/src/arkoor/package.rs", "lib/src/arkoor/mod.rs",
             "server/src/round/mod.rs", "server/src/ln/mod.rs", "server/src/arkoor.rs"]:
    blob = subprocess.check_output(["git", "-C", str(source), "rev-parse", f"{revision}:{path}"], text=True).strip()
    raw = subprocess.check_output(["git", "-C", str(source), "cat-file", "blob", blob])
    files.append({"path": path, "git_blob": blob, "sha256": hashlib.sha256(raw).hexdigest(),
                  "url": f"https://gitlab.com/ark-bitcoin/bark/-/blob/{revision}/{path}"})
result = {"evidence_class": "source_and_executed_configuration", "revision": revision, "files": files,
          "runtime_identity_sha256": hashlib.sha256(identity_path.read_bytes()).hexdigest(),
          "fees": config["fees"], "ln_max_fee_ppm": config["ln_max_fee_ppm"],
          "max_vtxo_exit_depth": config["max_vtxo_exit_depth"], "min_board_amount": config["min_board_amount"],
          "interpretation": "Pricing arithmetic and limits are source/configuration facts. Receipt backing, refresh scheduling, batching, and constant future miner fees remain forecast policies."}
Path("audit/peer_review/capital/fee-source.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
print("Pinned fee rules and policy limits match archived execution configuration.")
