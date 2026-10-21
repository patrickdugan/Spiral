"""Capture source evidence, not runtime attestations. Inputs are read-only checkouts/snapshots."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

bark, references = map(Path, sys.argv[1:3])
revision = "683964f59fcb3dde1dcecd6eab23b2a9dd2eee6f"
assert subprocess.check_output(["git", "-C", str(bark), "rev-parse", "HEAD"], text=True).strip() == revision
files = []
for path in ["server/src/database/ln/model.rs", "server/schema.sql", "server/src/ln/cln/xpay.rs",
             "server/src/watchman/policy.rs", "server/src/watchman/config.rs", "server/src/watchman/frontier.rs",
             "server-log/src/msgs/lightning.rs", "server-log/src/msgs/watchman.rs",
             "contrib/docker/docker-compose.yml", "contrib/docker/cln.Dockerfile"]:
    content = subprocess.check_output(["git", "-C", str(bark), "show", f"{revision}:{path}"])
    blob = subprocess.check_output(["git", "-C", str(bark), "rev-parse", f"{revision}:{path}"], text=True).strip()
    files.append({"component": "bark", "path": path, "revision": revision, "git_blob": blob,
                  "sha256": hashlib.sha256(content).hexdigest(), "url": f"https://gitlab.com/ark-bitcoin/bark/-/blob/{revision}/{path}"})
for component, commit, name, repo_path, repository in [
    ("cln", "8684c68dffb04ab606e526b64d7d60390d1fe7ed", "listpays.json", "doc/schemas/listpays.json", "ElementsProject/lightning"),
    ("cln", "8684c68dffb04ab606e526b64d7d60390d1fe7ed", "listpeerchannels.json", "doc/schemas/listpeerchannels.json", "ElementsProject/lightning"),
    ("bitcoin", "d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3", "blockchain.cpp", "src/rpc/blockchain.cpp", "bitcoin/bitcoin"),
    ("bitcoin", "d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3", "rawtransaction.cpp", "src/rpc/rawtransaction.cpp", "bitcoin/bitcoin"),
]:
    # Hash the exact saved connector text, canonicalized to LF with one final newline.
    content = ((references / name).read_text(encoding="utf-8").rstrip("\n") + "\n").encode()
    files.append({"component": component, "path": repo_path, "revision": commit,
                  "sha256_normalized_text": hashlib.sha256(content).hexdigest(), "url": f"https://github.com/{repository}/blob/{commit}/{repo_path}"})
result = {"evidence_class": "source_inspection", "inspection_date": "2026-10-21",
          "spiral_base": "23155003010310c3a5c41b9ab8f3db910e69bc3e", "files": files,
          "runtime": {"status": "not_executed", "genesis_hash": None, "best_block_hash": None,
                      "binary_digests": None, "container_digests": None, "effective_configuration": None,
                      "initial_state_snapshots": None}}
destination = Path(__file__).parent / "capital" / "source-pins.json"
destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
