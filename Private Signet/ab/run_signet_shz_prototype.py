#!/usr/bin/env python3
"""Dry run of the SatsHedgeZero prototype on the private custom Signet.

Runs SHZ's own live flow (`shz testnet4-live`, patrickdugan/SatsHedgeZero
bins/shz-cli, chain set by SHZ_CHAIN) against the lab miner node instead of
public Testnet4: three NUMS P2TR DLC fundings in one wallet transaction, the
pre-signed 3-input / 4-output collated clearing transaction, SHZ's two 1-sat
shave probes against the mempool, then broadcast. This script then mines one
signed block and checks both transactions and every clearing output on all
lab nodes.

  python run_signet_shz_prototype.py --shz /path/to/shz
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("lab", HERE.parent / "lab.py")
lab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lab)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shz", type=Path, required=True, help="SatsHedgeZero `shz` binary (bins/shz-cli)")
    ap.add_argument("--wallet", default="shz")
    args = ap.parse_args()
    state = lab.read_state()
    names = lab.nodes()

    lab.cli("miner", "createwallet", args.wallet)
    addr = lab.cli("miner", "getnewaddress", "", "bech32m", wallet=args.wallet)
    lab.cli("miner", "sendtoaddress", addr, "0.00100000", wallet="funds")
    wallet_block = lab.mine(1)

    env = dict(os.environ, SHZ_CHAIN="signet", SHZ_BITCOIN_CLI_DIRECT="1",
               SHZ_WSL_BITCOIN_CLI=lab.binary("bitcoin-cli", "BITCOIN_CLI"),
               SHZ_WSL_BITCOIN_DATADIR=str(lab.MINER_DATA),
               SHZ_BITCOIN_CLI_EXTRA_ARGS=f"-signetchallenge={state['challenge']} -rpcport={lab.PORTS['miner'][0]}")
    proc = subprocess.run([str(args.shz), "testnet4-live", args.wallet], env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    if proc.returncode:
        raise SystemExit(f"shz testnet4-live failed ({proc.returncode}):\n{proc.stderr[-4000:]}")
    shz = json.loads(proc.stdout)
    fund, clear = shz["funding_txid"], shz["atomic_clearing_txid"]

    block = lab.mine(1)
    synced = lab.wait_synced()
    tip = block["tip"]
    confirmed = {n: {t: (lab.rpc(n, "getrawtransaction", t, "1", tip) or {}).get("confirmations")
                     for t in (fund, clear)} for n in names}
    clear_raw = lab.rpc("miner", "getrawtransaction", clear, "1", tip)
    outputs = [{"n": o["n"], "sats": round(o["value"] * 1e8), "address": o["scriptPubKey"].get("address"),
                "unspent_on": [n for n in names if lab.rpc(n, "gettxout", clear, str(o["n"]), "false")]}
               for o in clear_raw["vout"]]
    report = {"kind": "signet-shz-prototype", "challenge": state["challenge"],
              "versions": {n: lab.rpc(n, "getnetworkinfo")["subversion"] for n in names},
              "shz_binary_sha256": lab.sha256_file(str(args.shz)),
              "wallet_funding_block": wallet_block["tip"], "settlement_block": tip, "synced": synced,
              "funding_txid": fund, "clearing_txid": clear, "clearing_vsize": shz["atomic_clearing_vsize"],
              "confirmations": confirmed, "clearing_outputs": outputs,
              "probes": [{k: p[k] for k in ("probe_id", "core_accepted", "core_reject_reason")}
                         for p in shz["adversarial_probes_live_testnet4"]],
              "shz_receipt": shz}
    report["agreement"] = lab.agree()["agree"]
    path = lab.receipt(report)
    ok = (all(c == 1 for per in confirmed.values() for c in per.values())
          and all(set(o["unspent_on"]) == set(names) for o in outputs)
          and all(not p["core_accepted"] for p in report["probes"]) and report["agreement"])
    print(json.dumps({"receipt": str(path), "ok": ok, "funding_txid": fund, "clearing_txid": clear,
                      "clearing_vsize": report["clearing_vsize"], "settlement_block": tip,
                      "outputs": [(o["sats"], len(o["unspent_on"])) for o in outputs],
                      "probes": {p["probe_id"]: p["core_reject_reason"] for p in report["probes"]},
                      "agreement": report["agreement"]}, indent=2))
    if not ok:
        raise SystemExit("SHZ prototype Signet dry run expectations not met")


if __name__ == "__main__":
    main()
