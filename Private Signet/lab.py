#!/usr/bin/env python3
"""Isolated, locally signed Bitcoin Core custom Signet laboratory.

Infrastructure harness: a bootstrap node generates a disposable signer key,
a miner node holds it and signs blocks through Bitcoin Core's official
contrib/signet/miner, and an observer node validates them independently.
It does not implement Keyless-CHECKSIG, OP_CAT, P2MR, BitVM or any new
consensus rule; experiment harnesses import its helpers.

Commands: init, status, agree, mine, fund-demo, probe, stop, destroy.
"""
from __future__ import annotations

import argparse
import hashlib
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
LEGACY_DATA = ROOT / "legacy"
DATADIRS = {"bootstrap": BOOTSTRAP, "miner": MINER_DATA, "observer": OBSERVER_DATA,
            "legacy": LEGACY_DATA}

# Distinct data directories and non-default ports keep the lab away from any
# other regtest/Testnet4/Signet process. SPIRAL_SIGNET_PORT_BASE moves all six.
_BASE = int(os.environ.get("SPIRAL_SIGNET_PORT_BASE", "39432"))
PORTS = {
    "bootstrap": (_BASE, _BASE + 1),
    "miner": (_BASE + 10, _BASE + 11),
    "observer": (_BASE + 20, _BASE + 21),
    "legacy": (_BASE + 30, _BASE + 31),
}
# Extra daemon arguments for miner and observer, e.g. "-keylessresearch=1"
# with a patched build. BITCOIND_LEGACY (optional) adds a third node on a
# different (stock) binary that follows the miner with the old rules.
NODE_ARGS = shlex.split(os.environ.get("SPIRAL_SIGNET_BITCOIND_ARGS", ""))
BOOTSTRAP_CHALLENGE = "51"   # OP_TRUE: a throwaway signet used only to mint the signer key


def binary(name: str, var: str, *, required: bool = True) -> str | None:
    value = os.environ.get(var, name)
    found = shutil.which(value)
    if not found and required:
        raise RuntimeError(f"Missing {value}; configure {var} or PATH")
    return found


def run(args: list[str], *, timeout: int = 180, stdin: str | None = None) -> str:
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout, input=stdin)
    if p.returncode:
        raise RuntimeError(f"{shlex.join(args)}\n{p.stderr.strip()}\n{p.stdout.strip()}")
    return p.stdout.strip()


def base_cli(node: str, challenge: str) -> list[str]:
    return [binary("bitcoin-cli", "BITCOIN_CLI"), f"-datadir={DATADIRS[node]}", "-signet",
            f"-signetchallenge={challenge}", f"-rpcport={PORTS[node][0]}"]


def node_challenge(node: str, challenge: str | None) -> str:
    if node == "bootstrap":
        return BOOTSTRAP_CHALLENGE
    return challenge or read_state()["challenge"]


def cli(node: str, *args: str, wallet: str | None = None, challenge: str | None = None,
        wait: bool = False, stdin: str | None = None) -> str:
    cmd = base_cli(node, node_challenge(node, challenge))
    if wait:
        cmd += ["-rpcwait", "-rpcwaittimeout=60"]
    if wallet:
        cmd += [f"-rpcwallet={wallet}"]
    if stdin is not None:
        cmd += ["-stdin"]
    return run(cmd + list(args), timeout=120, stdin=stdin)


def rpc(node: str, *args: str, wallet: str | None = None, challenge: str | None = None) -> object:
    out = cli(node, *args, wallet=wallet, challenge=challenge)
    # bitcoin-cli prints nothing for a null result (e.g. gettxout on a spent coin).
    return None if out == "" else json.loads(out)


def spawn(node: str, challenge: str) -> list[str]:
    datadir = DATADIRS[node]
    rpcport, p2pport = PORTS[node]
    datadir.mkdir(parents=True, exist_ok=True, mode=0o700)
    exe = binary("bitcoind", "BITCOIND_LEGACY") if node == "legacy" else binary("bitcoind", "BITCOIND")
    cmd = [exe, f"-datadir={datadir}", "-signet",
           f"-signetchallenge={challenge}", f"-rpcport={rpcport}", f"-port={p2pport}",
           "-server=1", "-daemon", "-dnsseed=0", "-fixedseeds=0", "-fallbackfee=0.00001",
           "-rpcbind=127.0.0.1", "-rpcallowip=127.0.0.1"]
    if node == "bootstrap":
        cmd += ["-listen=0", "-connect=0"]
    elif node == "miner":
        cmd += ["-listen=1", "-bind=127.0.0.1", "-connect=0"] + NODE_ARGS
    elif node == "observer":
        cmd += ["-listen=1", "-bind=127.0.0.1", f"-connect=127.0.0.1:{PORTS['miner'][1]}"] + NODE_ARGS
    else:   # legacy: old rules, follows the miner only
        cmd += ["-listen=0", f"-connect=127.0.0.1:{PORTS['miner'][1]}", "-disablewallet=1"]
    run(cmd)
    # -rpcwait does not wait for the cookie file itself: a call made before
    # the daemon writes it fails at once with "Could not locate RPC credentials".
    deadline = time.time() + 60
    while not list(datadir.glob("*/.cookie")):
        if time.time() > deadline:
            raise RuntimeError(f"{node} wrote no RPC cookie under {datadir} within 60 s")
        time.sleep(0.2)
    cli(node, "getblockchaininfo", challenge=challenge, wait=True)
    return cmd


def read_state() -> dict:
    if not STATE.is_file():
        raise RuntimeError(f"No initialized Signet at {ROOT}; run: lab.py init")
    return json.loads(STATE.read_text(encoding="utf-8"))


def safe_json_write(path: Path, value: object, secret: bool = False) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # O_EXCL protects private descriptor exports from accidental overwrite.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if secret else 0o644)
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


def strip_checksum(desc: str) -> str:
    return desc.split("#", 1)[0]


def challenge_key_descriptor(export: dict, hdkeypath: str) -> str:
    """Private pk() descriptor for the exact key behind the challenge.

    The challenge is a bare `<pubkey> OP_CHECKSIG` script. A descriptor wallet
    signs only scripts its descriptors produce, and the wpkh()/tr() ranges
    the bootstrap wallet exports never produce bare P2PK. Without this pk()
    import, walletprocesspsbt returns the block PSBT unsigned. The key path
    comes from getaddressinfo's hdkeypath, e.g. m/84h/1h/0h/0/0.
    """
    m = re.fullmatch(r"m/84h/(\d+)h/(\d+)h/([01])/(\d+)", hdkeypath)
    if not m:
        raise ValueError(f"Unexpected BIP84 key path {hdkeypath!r}")
    branch, index = m.group(3), m.group(4)
    for item in export["descriptors"]:
        body = strip_checksum(item["desc"])
        if body.startswith("wpkh(") and body.endswith(f"/{branch}/*)") and "/84h/" in body:
            key = body[len("wpkh("):-1]
            return "pk(" + key[:-1] + index + ")"
    raise RuntimeError("No ranged BIP84 wpkh() descriptor in the signer export")


def init() -> None:
    if STATE.exists():
        raise RuntimeError(f"Already initialized: {STATE}. Use status, stop or destroy")
    if any(p.exists() for p in DATADIRS.values()):
        raise RuntimeError(f"Existing lab data in {ROOT}; inspect manually or run destroy")
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ROOT, 0o700)
    binary("bitcoind", "BITCOIND")
    binary("bitcoin-cli", "BITCOIN_CLI")
    print(f"Creating isolated seed wallet under {BOOTSTRAP}")
    spawn("bootstrap", BOOTSTRAP_CHALLENGE)
    try:
        cli("bootstrap", "createwallet", "seed_signer")
        address = cli("bootstrap", "getnewaddress", "", "bech32", wallet="seed_signer")
        info = rpc("bootstrap", "getaddressinfo", address, wallet="seed_signer")
        challenge = challenge_from_pubkey(info["pubkey"])
        exported = rpc("bootstrap", "listdescriptors", "true", wallet="seed_signer")
        safe_json_write(ROOT / "PRIVATE-descriptor-backup.json", exported, secret=True)
        requests = descriptors_for_import(exported)
        pk_desc = challenge_key_descriptor(exported, info["hdkeypath"])
        checksum = rpc("bootstrap", "getdescriptorinfo", pk_desc)["checksum"]
        requests.append({"desc": f"{pk_desc}#{checksum}", "timestamp": "now"})
    finally:
        try:
            cli("bootstrap", "stop")
        except RuntimeError as exc:
            print(f"Bootstrap stop warning: {exc}", file=sys.stderr)
    # Provisional state: lets stop/destroy reach the nodes if init fails later.
    safe_json_write(STATE, {"schema": "spiral-private-signet/2", "status": "initializing",
                            "challenge": challenge})
    print("Starting authorized custom Signet signer and observer on loopback")
    miner_cmd = spawn("miner", challenge)
    cli("miner", "createwallet", "signer", "false", "true", challenge=challenge)
    results = rpc("miner", "importdescriptors", json.dumps(requests), wallet="signer",
                  challenge=challenge)
    if not all(entry.get("success") for entry in results):
        raise RuntimeError(f"Signer descriptor import failed: {results}")
    cli("miner", "createwallet", "funds", challenge=challenge)
    reward = cli("miner", "getnewaddress", "", "bech32", wallet="funds", challenge=challenge)
    observer_cmd = spawn("observer", challenge)
    legacy_cmd = spawn("legacy", challenge) if os.environ.get("BITCOIND_LEGACY") else None
    genesis_a = cli("miner", "getblockhash", "0", challenge=challenge)
    genesis_b = cli("observer", "getblockhash", "0", challenge=challenge)
    if genesis_a != genesis_b:
        raise RuntimeError("Different genesis hashes; check challenge and binaries")
    network = rpc("miner", "getnetworkinfo", challenge=challenge)
    public = {
        "schema": "spiral-private-signet/2",
        "challenge": challenge,
        "genesis_hash": genesis_a,
        "reward_address": reward,
        "signer_address": address,
        "core_version": network["version"],
        "core_subversion": network["subversion"],
        "bitcoind_sha256": sha256_file(binary("bitcoind", "BITCOIND")),
        "ports": PORTS,
        "commands": {"miner": redact(miner_cmd), "observer": redact(observer_cmd),
                     **({"legacy": redact(legacy_cmd)} if legacy_cmd else {})},
        "nodes": ["miner", "observer"] + (["legacy"] if legacy_cmd else []),
        "node_args": NODE_ARGS,
        "scope": ("localhost-only; miner/observer args " + (" ".join(NODE_ARGS) or "(none)") +
                  ("; legacy node on " + os.environ["BITCOIND_LEGACY"] if legacy_cmd else "")),
    }
    tmp = STATE.with_suffix(".tmp")
    safe_json_write(tmp, public)
    os.replace(tmp, STATE)
    print(json.dumps(public, indent=2))
    print("Signer private descriptors are in PRIVATE-descriptor-backup.json, outside the repository.")


def redact(cmd: list[str]) -> list[str]:
    return [c if "-datadir=" not in c else "-datadir=<lab>/" + Path(c.split("=", 1)[1]).name for c in cmd]


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wait_synced(timeout: float = 120.0) -> dict:
    """Wait until every other node's tip equals the miner's tip."""
    end = time.time() + timeout
    while True:
        tips = {n: cli(n, "getbestblockhash") for n in nodes()}
        if len(set(tips.values())) == 1:
            return {"tip": tips["miner"], "height": rpc("miner", "getblockcount")}
        if time.time() > end:
            raise RuntimeError(f"Nodes did not reach the miner tip: {tips}")
        time.sleep(0.5)


def mine(blocks: int) -> dict:
    state = read_state()
    if not 1 <= blocks <= 1000:
        raise ValueError("Block count must be 1..1000")
    script = os.environ.get("SIGNET_MINER")
    if not script or not Path(script).is_file():
        raise RuntimeError("Set SIGNET_MINER=/absolute/path/to/bitcoin/contrib/signet/miner")
    utility = binary("bitcoin-util", "BITCOIN_UTIL", required=False)
    cli_cmd = base_cli("miner", state["challenge"]) + ["-rpcwallet=signer"]
    cmd = [sys.executable, str(Path(script).resolve()), "--cli=" + shlex.join(cli_cmd), "generate",
           f"--address={state['reward_address']}", "--min-nbits", f"--max-blocks={blocks}"]
    if utility:
        cmd.append("--grind-cmd=" + shlex.join([utility, "grind"]))
    before = {"height": rpc("miner", "getblockcount"), "tip": cli("miner", "getbestblockhash")}
    print(f"Mining {blocks} signed custom-Signet blocks "
          f"({'bitcoin-util grind' if utility else 'miner built-in grinding'})", flush=True)
    start = time.time()
    process = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    entry = {"kind": "mining", "blocks_requested": blocks,
             "elapsed_seconds": round(time.time() - start, 3),
             "returncode": process.returncode, "grinder": "bitcoin-util" if utility else "miner-python",
             "miner_sha256": sha256_file(script),
             "stdout": process.stdout[-20000:], "stderr": process.stderr[-20000:],
             "before": before,
             "height": rpc("miner", "getblockcount"), "tip": cli("miner", "getbestblockhash")}
    if process.returncode == 0:
        entry["observer"] = wait_synced()
        # The miner backdates its first block by 1000 minutes and spaces blocks
        # 10 minutes apart. A descriptor wallet skips blocks timestamped before
        # its birth time, so without a rescan the reward wallet misses those
        # coinbases (seen: 101 blocks mined, 24 coinbases credited).
        entry["funds_rescan"] = rpc("miner", "rescanblockchain", str(before["height"] + 1),
                                    wallet="funds")
        entry["funds_balances"] = rpc("miner", "getbalances", wallet="funds")["mine"]
    path = receipt(entry)
    print(json.dumps({"receipt": str(path), "height": entry["height"], "tip": entry["tip"],
                      "returncode": process.returncode, "seconds": entry["elapsed_seconds"]}, indent=2))
    if process.returncode:
        raise RuntimeError(f"Signet miner failed; inspect {path}")
    return entry


def mine_with(tx_hexes: list[str]) -> dict:
    """Signed block containing the miner's template plus `tx_hexes`.

    Uses contrib/signet/miner genpsbt / solvepsbt and the signer wallet, so the
    block carries a valid Signet solution even for transactions the mempool
    refuses (non-standard spends). Returns {"hex", "hash", "template_height"}
    without submitting it anywhere.
    """
    state = read_state()
    script = os.environ.get("SIGNET_MINER")
    if not script or not Path(script).is_file():
        raise RuntimeError("Set SIGNET_MINER=/absolute/path/to/bitcoin/contrib/signet/miner")
    tmpl = rpc("miner", "getblocktemplate", json.dumps({"rules": ["signet", "segwit"]}))
    tmpl["transactions"] = list(tmpl["transactions"]) + [{"data": h} for h in tx_hexes]
    # genpsbt resolves the reward address with getaddressinfo, which needs the
    # wallet that owns it when several wallets are loaded.
    miner_cli = shlex.join(base_cli("miner", state["challenge"]) + ["-rpcwallet=funds"])
    base = [sys.executable, str(Path(script).resolve()), "--cli=" + miner_cli]
    psbt = run(base + ["genpsbt", f"--address={state['reward_address']}"], stdin=json.dumps(tmpl))
    signed = rpc("miner", "walletprocesspsbt", psbt, wallet="signer")
    utility = binary("bitcoin-util", "BITCOIN_UTIL", required=False)
    solve = base + ["solvepsbt"] + (["--grind-cmd=" + shlex.join([utility, "grind"])] if utility else [])
    block_hex = run(solve, stdin=signed["psbt"], timeout=600)
    header = bytes.fromhex(block_hex[:160])
    return {"hex": block_hex, "hash": hashlib.sha256(hashlib.sha256(header).digest()).digest()[::-1].hex(),
            "template_height": tmpl["height"], "signed_complete": signed.get("complete")}


def submit_block(block: dict, to: list[str]) -> dict:
    """submitblock on each node; returns per-node verdict and resulting tip."""
    out = {}
    for n in to:
        # bitcoin-cli prints nothing on success and the bare reason string
        # (e.g. "block-script-verify-flag-failed (...)") on rejection.
        try:
            r = cli(n, "submitblock", block["hex"])
        except RuntimeError as exc:
            r = "rpc-error: " + str(exc).splitlines()[-1]
        out[n] = {"result": "accepted" if r == "" else r, "tip": cli(n, "getbestblockhash")}
    return out


def agree() -> dict:
    """Every node: same genesis, height, every block hash and chainwork."""
    state = read_state()
    sync = wait_synced()
    names = nodes()
    info = {n: rpc(n, "getblockchaininfo") for n in names}
    height = info["miner"]["blocks"]
    mismatches = []
    hashes = []
    for h in range(height + 1):
        row = {n: cli(n, "getblockhash", str(h)) for n in names}
        hashes.append(row["miner"])
        if len(set(row.values())) != 1:
            mismatches.append({"height": h, **row})
    report = {
        "kind": "agreement",
        "challenge": state["challenge"],
        "genesis": {n: cli(n, "getblockhash", "0") for n in names},
        "height": {n: info[n]["blocks"] for n in names},
        "bestblockhash": {n: info[n]["bestblockhash"] for n in names},
        "chainwork": {n: info[n]["chainwork"] for n in names},
        "tip_header": rpc("miner", "getblockheader", info["miner"]["bestblockhash"]),
        "block_hashes": hashes,
        "hash_mismatches": mismatches,
        "observer_peers": len(rpc("observer", "getpeerinfo")),
        "versions": {n: rpc(n, "getnetworkinfo")["subversion"] for n in names},
    }
    report["agree"] = (len(set(report["genesis"].values())) == 1
                       and report["genesis"]["miner"] == state["genesis_hash"]
                       and len(set(report["height"].values())) == 1
                       and len(set(report["chainwork"].values())) == 1
                       and not mismatches)
    path = receipt(report)
    print(json.dumps({"receipt": str(path), "agree": report["agree"], "height": report["height"],
                      "chainwork": report["chainwork"]["miner"], "tip": sync["tip"]}, indent=2))
    if not report["agree"]:
        raise RuntimeError(f"Nodes disagree; inspect {path}")
    return report


def fund_demo(amount: str) -> dict:
    """Fresh wallet, wallet-signed payment, broadcast, mined, UTXO on both nodes."""
    read_state()
    name = "demo-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    cli("miner", "createwallet", name)
    address = cli("miner", "getnewaddress", "", "bech32m", wallet=name)
    txid = cli("miner", "sendtoaddress", address, amount, wallet="funds")
    raw = rpc("miner", "gettransaction", txid, "true", "true", wallet="funds")
    mempool_entry = rpc("miner", "getmempoolentry", txid)
    mined = mine(1)
    vout = next(o["n"] for o in raw["decoded"]["vout"]
                if o["scriptPubKey"].get("address") == address)
    utxo = {n: rpc(n, "gettxout", txid, str(vout), "false") for n in ("miner", "observer")}
    block = rpc("miner", "getrawtransaction", txid, "1", mined["tip"])["blockhash"]
    entry = {"kind": "wallet-transaction", "wallet": name, "address": address,
             "amount": amount, "txid": txid, "raw_tx": raw["hex"], "vout": vout,
             "weight": raw["decoded"]["weight"], "fee_btc": raw.get("fee"),
             "mempool_entry": mempool_entry, "block": block, "height": mined["height"],
             "utxo": utxo, "wallet_balance": rpc("miner", "getbalances", wallet=name)}
    entry["confirmed_on_both"] = all(u is not None and u["confirmations"] >= 1 for u in utxo.values())
    path = receipt(entry)
    print(json.dumps({"receipt": str(path), "txid": txid, "block": block,
                      "confirmed_on_both": entry["confirmed_on_both"]}, indent=2))
    if not entry["confirmed_on_both"]:
        raise RuntimeError(f"UTXO not visible on both nodes; inspect {path}")
    return entry


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


def nodes() -> list[str]:
    return read_state().get("nodes", ["miner", "observer"])


def stop() -> None:
    read_state()
    for node in reversed(nodes()):
        try:
            print(f"{node}: {cli(node, 'stop')}")
        except Exception as exc:
            print(f"{node}: {exc}", file=sys.stderr)


def destroy() -> None:
    """Stop both nodes and delete the lab home (disposable keys and chain)."""
    if not ROOT.exists():
        return
    if not (ROOT / "PRIVATE-descriptor-backup.json").exists() and not STATE.exists():
        raise RuntimeError(f"{ROOT} does not look like a lab home; refusing to delete it")
    if STATE.exists():
        stop()
    for _ in range(120):   # wait for both daemons to release their pid files
        if not list(ROOT.glob("*/**/bitcoind.pid")):
            break
        time.sleep(0.5)
    shutil.rmtree(ROOT)
    print(f"removed {ROOT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "status", "agree", "stop", "destroy"):
        command.add_parser(name)
    p_mine = command.add_parser("mine")
    p_mine.add_argument("--blocks", type=int, default=1)
    p_fund = command.add_parser("fund-demo")
    p_fund.add_argument("--amount", default="1.0")
    p_probe = command.add_parser("probe")
    p_probe.add_argument("--txhex-file", type=Path, required=True)
    p_probe.add_argument("--broadcast", action="store_true",
                         help="Explicitly broadcast only on isolated miner node")
    args = parser.parse_args()
    {"init": init, "status": status, "agree": agree, "stop": stop, "destroy": destroy,
     "mine": lambda: mine(args.blocks), "fund-demo": lambda: fund_demo(args.amount),
     "probe": lambda: probe(args.txhex_file, args.broadcast)}[args.command]()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
