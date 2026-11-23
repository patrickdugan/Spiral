#!/usr/bin/env python3
"""Isolated, locally signed Bitcoin Core custom Signet laboratory.

This is an infrastructure harness. It does not implement Keyless-CHECKSIG,
OP_CAT, P2MR, BitVM, or any new consensus rule.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("SPIRAL_SIGNET_HOME", "~/.local/share/spiral-private-signet")).expanduser().resolve()
STATE = ROOT / "state.json"
BOOTSTRAP = ROOT / "bootstrap"
MINER_DATA = ROOT / "miner"
OBSERVER_DATA = ROOT / "observer"
RECEIPTS = ROOT / "receipts"

# Change these together if a port is occupied. Distinct Core data directories
# and non-default ports avoid touching existing regtest/Testnet4 processes.
PORTS = {
    "bootstrap": (39432, 39433),
    "miner": (39442, 39443),
    "observer": (39452, 39453),
}


def binary(name: str, var: str) -> str:
    value = os.environ.get(var, name)
    found = shutil.which(value)
    if not found:
        raise RuntimeError(f"Missing {value}; configure {var} or PATH")
    return found


def run(args: list[str], *, quiet: bool = False, timeout: int = 180) -> str:
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{shlex.join(args)}\n{p.stderr.strip()}\n{p.stdout.strip()}")
    if not quiet and p.stderr.strip():
        print(p.stderr.strip(), file=sys.stderr)
    return p.stdout.strip()


def cli(node: str, *args: str, wallet: str | None = None,
        challenge: str | None = None, wait: bool = False) -> str:
    if node == "bootstrap":
        datadir, rpcport, chal = BOOTSTRAP, PORTS[node][0], "51"
    else:
        datadir, rpcport = (MINER_DATA if node == "miner" else OBSERVER_DATA), PORTS[node][0]
        chal = challenge or read_state()["challenge"]
    cmd = [binary("bitcoin-cli", "BITCOIN_CLI"), f"-datadir={datadir}", "-signet",
           f"-signetchallenge={chal}", f"-rpcport={rpcport}"]
    if wait:
        cmd += ["-rpcwait", "-rpcwaittimeout=45"]
    if wallet:
        cmd += [f"-rpcwallet={wallet}"]
    return run(cmd + list(args), quiet=True, timeout=70)


def rpc(node: str, *args: str, wallet: str | None = None) -> object:
    return json.loads(cli(node, *args, wallet=wallet))


def spawn(node: str, challenge: str) -> None:
    datadir = {"bootstrap": BOOTSTRAP, "miner": MINER_DATA, "observer": OBSERVER_DATA}[node]
    rpcport, p2pport = PORTS[node]
    datadir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cmd = [binary("bitcoind", "BITCOIND"), f"-datadir={datadir}", "-signet",
           f"-signetchallenge={challenge}", f"-rpcport={rpcport}", f"-port={p2pport}",
           "-server=1", "-daemon", "-dnsseed=0", "-fallbackfee=0.00001"]
    if node == "bootstrap":
        cmd += ["-listen=0", "-connect=0"]
    elif node == "miner":
        cmd += ["-listen=1", "-bind=127.0.0.1", "-connect=0"]
    else:
        cmd += ["-listen=1", "-bind=127.0.0.1",
                f"-connect=127.0.0.1:{PORTS['miner'][1]}"]
    run(cmd, quiet=True)
    cli(node, "getblockchaininfo", challenge=challenge, wait=True)


def read_state() -> dict:
    if not STATE.is_file():
        raise RuntimeError(f"No initialized Signet at {ROOT}; run: lab.py init")
    return json.loads(STATE.read_text(encoding="utf-8"))


def safe_json_write(path: Path, value: object, secret: bool = False) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # O_EXCL protects private descriptor exports from accidental overwrite.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600 if secret else 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")


def challenge_from_pubkey(pubkey: str) -> str:
    if not re.fullmatch(r"(02|03)[0-9a-fA-F]{64}", pubkey):
        raise ValueError("Expected a 33-byte compressed secp256k1 public key")
    return "21" + pubkey.lower() + "ac"   # PUSH33 <pubkey> OP_CHECKSIG


def descriptors_for_import(export: dict) -> list[dict]:
    requests = []
    for item in export["descriptors"]:
        desc = item["desc"]
        req = {"desc": desc, "timestamp": "now", "active": False}
        if "*" in desc:
            req["range"] = item.get("range", [0, 1000])
        requests.append(req)
    if not requests:
        raise RuntimeError("No wallet descriptors to import")
    return requests


def init() -> None:
    if STATE.exists():
        raise RuntimeError(f"Already initialized: {STATE}. Use status or stop")
    if any(p.exists() for p in (BOOTSTRAP, MINER_DATA, OBSERVER_DATA)):
        raise RuntimeError(f"Existing lab data in {ROOT}; inspect manually before retrying")
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ROOT, 0o700)
    binary("bitcoind", "BITCOIND")
    binary("bitcoin-cli", "BITCOIN_CLI")
    print(f"Creating isolated seed wallet under {BOOTSTRAP}")
    spawn("bootstrap", "51")  # Isolated temporary Signet; only for key generation.
    try:
        cli("bootstrap", "createwallet", "seed_signer")
        address = cli("bootstrap", "getnewaddress", "", "bech32", wallet="seed_signer")
        info = rpc("bootstrap", "getaddressinfo", address, wallet="seed_signer")
        challenge = challenge_from_pubkey(info["pubkey"])
        exported = rpc("bootstrap", "listdescriptors", "true", wallet="seed_signer")
        safe_json_write(ROOT / "PRIVATE-descriptor-backup.json", exported, secret=True)
        requests = descriptors_for_import(exported)
    finally:
        try:
            cli("bootstrap", "stop")
        except RuntimeError as exc:
            print(f"Bootstrap stop warning: {exc}", file=sys.stderr)
    print("Starting authorized custom Signet signer and observer on loopback")
    spawn("miner", challenge)
    cli("miner", "createwallet", "signer", "false", "true")
    results = rpc("miner", "importdescriptors", json.dumps(requests), wallet="signer")
    if not all(entry.get("success") for entry in results):
        raise RuntimeError(f"Signer descriptor import failed: {results}")
    cli("miner", "createwallet", "funds")
    reward = cli("miner", "getnewaddress", wallet="funds")
    spawn("observer", challenge)
    genesis_a = cli("miner", "getblockhash", "0")
    genesis_b = cli("observer", "getblockhash", "0")
    if genesis_a != genesis_b:
        raise RuntimeError("Different genesis hashes; check challenge and binaries")
    public = {
        "schema": "spiral-private-signet/1",
        "challenge": challenge,
        "genesis_hash": genesis_a,
        "reward_address": reward,
        "signer_address": address,
        "core_version": rpc("miner", "getnetworkinfo")["version"],
        "ports": PORTS,
        "scope": "localhost-only; experimental consensus patch not installed",
    }
    safe_json_write(STATE, public)
    print(json.dumps(public, indent=2))
    print("Signer private descriptors are in PRIVATE-descriptor-backup.json, outside the repository.")
    print("Next: SIGNET_MINER=/path/to/bitcoin/contrib/signet/miner python3 lab.py mine --blocks 101")


def mine(blocks: int) -> None:
    state = read_state()
    if not 1 <= blocks <= 1000:
        raise ValueError("Block count must be 1..1000")
    script = os.environ.get("SIGNET_MINER")
    if not script or not Path(script).is_file():
        raise RuntimeError("Set SIGNET_MINER=/absolute/path/to/bitcoin/contrib/signet/miner")
    utility = binary("bitcoin-util", "BITCOIN_UTIL")
    client = binary("bitcoin-cli", "BITCOIN_CLI")
    cmd = [
        sys.executable, str(Path(script).resolve()),
        "--cli=" + shlex.join([client, f"-datadir={MINER_DATA}",
                               f"-signetchallenge={state['challenge']}",
                               f"-rpcport={PORTS['miner'][0]}", "-rpcwallet=signer"]),
        "generate",
        "--grind-cmd=" + shlex.join([utility, "grind"]),
        f"--address={state['reward_address']}",
        "--min-nbits",
        f"--max-blocks={blocks}",
    ]
    print(f"Mining {blocks} signed custom-Signet blocks", flush=True)
    # Signet miner output and any rejection are kept as receipts.
    start = time.time()
    process = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    entry = {"kind": "mining", "blocks_requested": blocks,
             "elapsed_seconds": round(time.time() - start, 3),
             "returncode": process.returncode,
             "stdout": process.stdout, "stderr": process.stderr,
             "height": rpc("miner", "getblockcount"),
             "tip": cli("miner", "getbestblockhash")}
    path = receipt(entry)
    print(json.dumps({"receipt": str(path), "height": entry["height"],
                      "tip": entry["tip"], "returncode": process.returncode}, indent=2))
    if process.returncode:
        raise RuntimeError(f"Signet miner failed; inspect {path}")


def status() -> None:
    state = read_state()
    report = {"challenge": state["challenge"], "genesis_hash": state["genesis_hash"]}
    for node in ("miner", "observer"):
        try:
            report[node] = {"chain": rpc(node, "getblockchaininfo"),
                            "network": rpc(node, "getnetworkinfo")}
        except Exception as exc:
            report[node] = {"error": str(exc)}
    print(json.dumps(report, indent=2))


def receipt(entry: dict) -> Path:
    RECEIPTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    dt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = RECEIPTS / f"{dt}-{entry['kind']}.json"
    safe_json_write(path, entry)
    return path


def validate_txhex(value: str) -> str:
    txhex = "".join(value.split()).lower()
    if len(txhex) < 20 or len(txhex) % 2 or not re.fullmatch(r"[0-9a-f]+", txhex):
        raise ValueError("Expected a complete, even-length raw transaction hex string")
    return txhex


def probe(path: Path, broadcast: bool) -> None:
    read_state()
    txhex = validate_txhex(path.read_text(encoding="utf-8"))
    entry = {"kind": "probe", "source_file": str(path), "raw_hex_length": len(txhex),
             "broadcast": broadcast, "observations": {}}
    for node in ("miner", "observer"):
        try:
            data = {"version": rpc(node, "getnetworkinfo")["version"],
                    "height": rpc(node, "getblockcount"),
                    "mempool_test": rpc(node, "testmempoolaccept", json.dumps([txhex]))}
            if broadcast and node == "miner":
                data["broadcast_txid"] = cli(node, "sendrawtransaction", txhex)
            entry["observations"][node] = data
        except Exception as exc:
            entry["observations"][node] = {"error": str(exc)}
    output = receipt(entry)
    print(json.dumps({"receipt": str(output), "observations": entry["observations"]}, indent=2))


def stop() -> None:
    read_state()
    for node in ("observer", "miner"):
        try:
            print(f"{node}: {cli(node, 'stop')}")
        except Exception as exc:
            print(f"{node}: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("init")
    command.add_parser("status")
    command.add_parser("stop")
    p_mine = command.add_parser("mine")
    p_mine.add_argument("--blocks", type=int, default=1)
    p_probe = command.add_parser("probe")
    p_probe.add_argument("--txhex-file", type=Path, required=True)
    p_probe.add_argument("--broadcast", action="store_true",
                         help="Explicitly broadcast only on isolated miner node")
    args = parser.parse_args()
    if args.command == "init":
        init()
    elif args.command == "mine":
        mine(args.blocks)
    elif args.command == "status":
        status()
    elif args.command == "probe":
        probe(args.txhex_file, args.broadcast)
    elif args.command == "stop":
        stop()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
