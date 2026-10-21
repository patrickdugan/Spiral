"""Owned, loopback-only regtest. Runs under WSL with the task-local Docker daemon.

No signing material is written into the repository. Existing containers are
inspected/reused, never silently discarded. Run with the pinned Bark source path.
"""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

RUNTIME = Path("/var/tmp/spiral-capital-runtime")
DOCKER = [str(RUNTIME / "bin/docker"), "-H", f"unix://{RUNTIME}/docker.sock"]
IMAGES = {
    "captain": "secondark/captaind@sha256:9e1dff4d944ec3049bae08a45c6bb9d37ce66334a131a1faec42dfeac4d5f358",
    "bark": "secondark/bark@sha256:ebbcab48d5c45e83e3b9f4328213bf89151193b9dffca3785e3c35ff6b3fbc02",
    "bitcoin": "bitcoin/bitcoin@sha256:a1d05be6939b5c85132a761d2b795f5b8a2612ce53782263da4939778e461792",
    "cln": "elementsproject/lightningd@sha256:0421a5f0d1b2e1ad639edfa17d777816040e3850d91bae7f2d32186d9c1e6da4",
}

def docker(*args, check=True):
    return subprocess.run([*DOCKER, *map(str, args)], text=True, capture_output=True, check=check)

def start(name, image, entrypoint, arguments, mounts=()):
    # WSL's virtual ext4 free space can exceed physical Windows free space.
    if Path('/mnt/c').exists() and shutil.disk_usage('/mnt/c').free < 4 * 1024**3:
        raise RuntimeError('Windows host has less than 4 GiB free; refuse more container writes')
    inspected = docker("inspect", name, check=False)
    if inspected.returncode == 0:
        state = json.loads(inspected.stdout)[0]["State"]
        if not state["Running"]:
            raise RuntimeError(f"{name} exists but stopped: {state}. Inspect logs before restarting.")
        return
    args = ["run", "-d", "--name", name, "--network", "host", "--memory", "768m", "--cpus", "2"]
    for source, target in mounts:
        args += ["-v", f"{source}:{target}"]
    args += ["--entrypoint", entrypoint, image, *arguments]
    docker(*args)

def core(*args):
    r = docker("exec", "spiral-bitcoin", "bitcoin-cli", "-regtest", "-rpcport=18483", "-rpcuser=spiral", "-rpcpassword=owned-regtest-only", *args)
    try:
        return json.loads(r.stdout, parse_float=str)
    except json.JSONDecodeError:
        return r.stdout.strip()

def wait_core():
    for _ in range(30):
        try:
            return core("getblockchaininfo")
        except subprocess.CalledProcessError:
            time.sleep(1)
    raise RuntimeError("Core readiness timed out; inspect spiral-bitcoin logs")

def main():
    source = Path(sys.argv[1]).resolve()
    git = ["git", "-C", str(source)]
    if (source / ".git").is_file():
        gitdir = (source / ".git").read_text().strip().removeprefix("gitdir: ").replace("\\", "/")
        if len(gitdir) > 2 and gitdir[1:3] == ":/":
            gitdir = f"/mnt/{gitdir[0].lower()}/{gitdir[3:]}"
            git = ["git", f"--git-dir={gitdir}", f"--work-tree={source}"]
    pin = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    if pin != "8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a":
        raise RuntimeError("source checkout does not match executable build commit")
    for path in ["bitcoin", "cln-server", "cln-peer", "captain", "watchman", "postgres", "config", "evidence"]:
        (RUNTIME / path).mkdir(exist_ok=True)
    start("spiral-bitcoin", IMAGES["bitcoin"], "bitcoind", ["-regtest", "-server", "-listen=0", "-dnsseed=0", "-discover=0", "-txindex=1",
        "-rpcbind=127.0.0.1", "-rpcallowip=127.0.0.1", "-rpcport=18483", "-rpcuser=spiral", "-rpcpassword=owned-regtest-only",
        "-fallbackfee=0.00001", "-dbcache=64", "-par=1", "-datadir=/data", "-printtoconsole"], [(RUNTIME / "bitcoin", "/data")])
    info = wait_core()
    if info["chain"] != "regtest":
        raise RuntimeError("not regtest")
    if "miner" not in core("listwallets"):
        exists = any(w["name"] == "miner" for w in core("listwalletdir")["wallets"])
        core("loadwallet" if exists else "createwallet", "miner")
    for name, port, grpc in [("server", 11935, 11936), ("peer", 12935, 12936)]:
        start(f"spiral-cln-{name}", IMAGES["cln"], "lightningd", ["--network=regtest", "--lightning-dir=/data", "--log-level=info",
            f"--alias=spiral-{name}", f"--bind-addr=127.0.0.1:{port}", f"--grpc-port={grpc}", "--grpc-host=127.0.0.1",
            "--bitcoin-rpcconnect=127.0.0.1", "--bitcoin-rpcport=18483", "--bitcoin-rpcuser=spiral", "--bitcoin-rpcpassword=owned-regtest-only"],
            [(RUNTIME / f"cln-{name}", "/data")])
    config = (source / "server/captaind.default.toml").read_text()
    replacements = {
        'data_dir = "./bark-server"': 'data_dir = "/data/captain"',
        'public_address = "127.0.0.1:3535"': 'public_address = "127.0.0.1:13535"',
        'admin_address = "127.0.0.1:3536"': 'admin_address = "127.0.0.1:13536"',
        'integration_address = "127.0.0.1:3537"': 'integration_address = "127.0.0.1:13537"',
        'url = "http://127.0.0.1:18443"': 'url = "http://127.0.0.1:18483"',
        '#rpc_user = "admin"': 'rpc_user = "spiral"', '#rpc_pass = "super_secure"': 'rpc_pass = "owned-regtest-only"',
        '#user = "postgres"': 'user = "postgres"', '#password = "super_secure"': 'password = "owned-regtest-only"',
        'port = 5432': 'port = 15432', 'name = "bark-server-db"': 'name = "spiral_capital"',
    }
    for old, new in replacements.items():
        if old not in config:
            raise RuntimeError(f"source config changed: {old}")
        config = config.replace(old, new)
    settings = RUNTIME / 'config/fixture-settings.json'
    if settings.exists() and json.loads(settings.read_text()).get('disable_pool_issuance') is True:
        config = config.replace('vtxo_targets = [ "1000sat:10", "10000sat:10" ]', 'vtxo_targets = []')
    config += '''\n[[cln_array]]
uri = "https://localhost:11936"
priority = 1
server_cert_path = "/data/cln-server/regtest/ca.pem"
client_cert_path = "/data/cln-server/regtest/client.pem"
client_key_path = "/data/cln-server/regtest/client-key.pem"
'''
    (RUNTIME / "config/captaind.toml").write_text(config)
    # Use the pinned image's PostgreSQL, but bind only loopback at a distinct port.
    pg = RUNTIME / "config/postgres-start.sh"
    pg.write_text('''#!/bin/sh
set -eu
export PATH=/usr/lib/postgresql/16/bin:$PATH
mkdir -p /run/postgresql
chown postgres:postgres /run/postgresql /pgdata
chmod 700 /pgdata
if [ ! -f /pgdata/PG_VERSION ]; then
  su postgres -s /bin/sh -c 'initdb -D /pgdata --auth-local=trust --auth-host=trust'
fi
exec su postgres -s /bin/sh -c 'exec postgres -D /pgdata -h 127.0.0.1 -p 15432'
''')
    start("spiral-postgres", IMAGES["captain"], "/bin/sh", ["/config/postgres-start.sh"], [(RUNTIME / "postgres", "/pgdata"), (RUNTIME / "config", "/config")])
    (RUNTIME / "evidence/initial-chain.json").write_text(json.dumps({"info": info, "genesis": core("getblockhash", "0"), "source": pin}, indent=2))
    print(json.dumps({"core": info["chain"], "genesis": core("getblockhash", "0"), "source": pin, "next": "verify CLN/PG readiness and create captaind"}))

if __name__ == "__main__":
    main()
