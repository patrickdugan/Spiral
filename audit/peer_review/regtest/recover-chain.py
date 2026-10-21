"""One-time recovery of the task chain index after the recorded disk-full stop.
Rebuilds Core's index from existing block files; never resets wallets or databases.
"""
from bootstrap import RUNTIME, IMAGES, docker, core, start, wait_core
from attest import save
import json

before = core("getblockchaininfo")
db = docker("exec", "spiral-postgres", "psql", "-h", "127.0.0.1", "-p", "15432", "-U", "postgres", "-d", "spiral_capital", "-Atc",
            "SELECT json_agg(t) FROM (SELECT height,hash FROM captaind_block ORDER BY height DESC LIMIT 3) t").stdout
save("disk-full-chain-interruption.json", {"event": "disk-full-interruption", "core_before_reindex": before,
    "captaind_saved_tip": json.loads(db), "explanation": "Core restarted at 101; Bark retained 113. No completed Bark payment existed yet.",
    "capital_lifecycle_complete": False})
docker("stop", "spiral-bitcoin")
docker("rename", "spiral-bitcoin", "spiral-bitcoin-before-reindex")
start("spiral-bitcoin", IMAGES["bitcoin"], "bitcoind", ["-regtest", "-server", "-listen=0", "-dnsseed=0", "-discover=0", "-txindex=1",
    "-rpcbind=127.0.0.1", "-rpcallowip=127.0.0.1", "-rpcport=18483", "-rpcuser=spiral", "-rpcpassword=owned-regtest-only",
    "-fallbackfee=0.00001", "-dbcache=64", "-par=1", "-datadir=/data", "-printtoconsole", "-reindex"], [(RUNTIME / "bitcoin", "/data")])
print(json.dumps(wait_core()))
