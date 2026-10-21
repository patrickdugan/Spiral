"""Export allowlisted, public runtime identity. Never copy wallet directories."""
from bootstrap import RUNTIME, IMAGES, docker, core
from pathlib import Path
import hashlib
import json
import re
import time

DEST = Path(__file__).parent / "evidence"


def save(name, value):
    DEST.mkdir(exist_ok=True)
    (DEST / name).write_text(json.dumps(value, indent=2) + "\n", newline="\n")


def main():
    identities = []
    for component, ref in IMAGES.items():
        image = json.loads(docker("image", "inspect", ref).stdout)[0]
        identities.append({"component": component, "reference": ref, "image_id": image["Id"],
                           "architecture": image["Architecture"], "os": image["Os"],
                           "repo_digests": image["RepoDigests"], "created": image["Created"]})
    containers = []
    for name in ["spiral-bitcoin", "spiral-cln-server", "spiral-cln-peer", "spiral-postgres", "spiral-captaind", "spiral-watchmand"]:
        r = docker("inspect", name, check=False)
        if r.returncode:
            continue
        data = json.loads(r.stdout)[0]
        containers.append({"name": name, "image_id": data["Image"], "running": data["State"]["Running"],
                           "started_at": data["State"]["StartedAt"], "oom_killed": data["State"]["OOMKilled"],
                           "memory_limit": data["HostConfig"]["Memory"], "network_mode": data["HostConfig"]["NetworkMode"],
                           "entrypoint": data["Config"]["Entrypoint"],
                           "command": [re.sub(r'(-rpcpassword=).*', r'\1<redacted-local-test-credential>', arg) for arg in data["Config"]["Cmd"]]})
    configs = {}
    for path in (RUNTIME / "config").glob("*.toml"):
        raw = path.read_text()
        configs[path.name] = {"sha256": hashlib.sha256(raw.encode()).hexdigest(),
                             "redacted_text": re.sub(r'(?m)^(rpc_pass|password) = .*$', r'\1 = "<local-test-credential-redacted>"', raw)}
    executables = []
    for container, binary in [("spiral-bitcoin", "bitcoind"), ("spiral-cln-server", "lightningd"),
                              ("spiral-captaind", "captaind"), ("spiral-watchmand", "watchmand"), ("spiral-bark", "bark")]:
        if not any(c["name"] == container and c["running"] for c in containers) and container != "spiral-bark":
            continue
        path = docker("exec", container, "/bin/sh", "-c", f"command -v {binary}").stdout.strip()
        version = docker("exec", container, path, "--version").stdout.strip().splitlines()[0]
        checksum = docker("exec", container, "sha256sum", path).stdout.split()[0]
        executables.append({"binary": binary, "container": container, "path": path, "version": version, "sha256": checksum})
    save("runtime-identity.json", {"evidence_class": "partial-regtest-execution", "captured_unix_ns": time.time_ns(),
                                 "genesis": core("getblockhash", "0"), "chain": core("getblockchaininfo"),
                                 "images": identities, "containers": containers, "configurations": configs, "executables": executables,
                                 "source_revisions": {"bark_reported_build_commit": "8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a",
                                     "bitcoin_v31_release_commit": "6574cb40869b96b9ffc79c19dc8f4e467d60f321",
                                     "cln_v26_06_7_release_commit": "8684c68dffb04ab606e526b64d7d60390d1fe7ed"},
                                 "transaction_lifecycle_verified": (DEST / 'reuse-proof.json').exists(),
                                 "reference_reducer_acceptance": False})
    print("Saved public runtime identity; reducer acceptance is a separate check.")


if __name__ == "__main__":
    main()
