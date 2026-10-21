"""Run upstream watchmand against the same server keys and database."""
from bootstrap import RUNTIME, IMAGES, start
from launch import rpc
from pathlib import Path
import json
import sys

source = Path(sys.argv[1])
config = (source / "server/watchmand.default.toml").read_text()
address = json.loads(rpc("wallet").stdout)["rounds"]["address"]
for old, new in {
    'data_dir = "./bark-server-watchmand"': 'data_dir = "/data/captain"',
    'url = "http://127.0.0.1:18443"': 'url = "http://127.0.0.1:18483"',
    '#rpc_user = "admin"': 'rpc_user = "spiral"', '#rpc_pass = "super_secure"': 'rpc_pass = "owned-regtest-only"',
    '#user = "postgres"': 'user = "postgres"', '#password = "super_secure"': 'password = "owned-regtest-only"',
    'port = 5432': 'port = 15432', 'name = "bark-server-db"': 'name = "spiral_capital"',
}.items():
    if old not in config:
        raise RuntimeError(f"source configuration changed: {old}")
    config = config.replace(old, new)
config = f'admin_address = "127.0.0.1:13538"\nsweep_address = "{address}"\n' + config
(RUNTIME / "config/watchmand.toml").write_text(config)
start("spiral-watchmand", IMAGES["captain"], "watchmand", ["--config", "/data/config/watchmand.toml", "start"], [(RUNTIME, "/data")])
print("Watchmand launched with source-default 2h sweep cadence; manual triggers will be recorded separately.")
