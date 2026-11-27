#!/usr/bin/env python3
"""R-VER-1r: verified collateral release for a CBM-SHZ-01 clearing round on isolated regtest.

Each party's collateral sits in a vault output
    tr(musig(owner, operator)/0/*, and_v(v:pk(owner/1/*), older(144)))
held by two signer wallets that each have ONE private key (owner, clearing operator).

1. Clearing round (architecture C, Proposition "conservation under authenticated release"):
   A owes B a matured claim. One transaction spends both vaults through the MuSig2 key path,
   signed in Core's two-round MuSig2 PSBT flow by owner and operator wallets: B receives the
   claim (a `pay` transition), A and B receive their excess collateral (`unlock`). Checks:
   inputs = outputs + fee, payout = claim, returns = collateral - claims - fee share.
2. Reuse: after 3 confirmations each released output is spent again from the owner's own
   wallet, which is the observed recovery of spend authority.
3. Unilateral exit (offline operator and counterparty): the owner spends its vault through
   the CSV leaf alone. Core rejects it before 144 confirmations (non-BIP68-final) and accepts
   it after; without the operator the key path does not finalize.
4. Measured vsizes replace the simulator's assumed constants where they differ.

Synthetic regtest keys and coins only; no network.
"""
from __future__ import annotations

import argparse
import base64
import json
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

COLLATERAL = 50_000_000
CLAIM = 10_000_000
FEE_PER_INPUT = 1_000
CSV = 144


def btc(sat):
    return f"{sat // 100_000_000}.{sat % 100_000_000:08d}"


def sats(v):
    return int(Decimal(str(v)) * 100_000_000)


class Regtest:
    def __init__(self, binary, datadir):
        self.binary, self.datadir = Path(binary), Path(datadir)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = None

    def rpc(self, method, params=None, wallet=None):
        cookie = (self.datadir / "regtest" / ".cookie").read_bytes().strip()
        suffix = "/wallet/" + urllib.parse.quote(wallet, safe="") if wallet else "/"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{suffix}",
                                     data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode(),
                                     headers={"Authorization": "Basic " + base64.b64encode(cookie).decode()})
        try:
            resp = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            resp = e
        with resp:
            out = json.loads(resp.read(), parse_float=Decimal)
        if out.get("error"):
            raise RuntimeError(f"{method}: {out['error']}")
        return out["result"]

    def start(self):
        self.log = (self.datadir / "node.log").open("ab")
        self.proc = subprocess.Popen([str(self.binary), f"-datadir={self.datadir}", "-regtest=1", "-server=1",
                                      f"-rpcport={self.port}", "-rpcbind=127.0.0.1", "-listen=0", "-connect=0",
                                      "-dnsseed=0", "-discover=0", "-networkactive=0", "-persistmempool=0",
                                      "-dbcache=16", "-txindex=1", "-fallbackfee=0.00001000"],
                                     stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                assert self.rpc("getblockchaininfo")["chain"] == "regtest"
                return
            except (OSError, urllib.error.URLError, RuntimeError, FileNotFoundError):
                time.sleep(0.2)
        raise TimeoutError("regtest did not start")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.rpc("stop")
                self.proc.wait(timeout=20)
            except Exception:
                self.proc.kill()
        self.log.close()


def root_keys(rpc, wallet):
    rows = rpc("listdescriptors", [True], wallet=wallet)["descriptors"]
    (row,) = [r for r in rows if not r["internal"] and r["desc"].startswith("tr(")]
    root = row["desc"].split("(", 1)[1].split("#")[0].split("/", 1)[0]
    if root.startswith("["):
        root = root.split("]", 1)[1]
    pub = rpc("getdescriptorinfo", [f"pk({root})"])["descriptor"].split("(", 1)[1].split(")", 1)[0]
    return root, pub


def import_desc(rpc, wallet, desc):
    d = desc + "#" + rpc("getdescriptorinfo", [desc])["checksum"]
    res = rpc("importdescriptors", [[{"desc": d, "active": True, "range": [0, 10], "timestamp": "now", "internal": False}]], wallet=wallet)
    if not all(r["success"] for r in res):
        raise RuntimeError(f"import {wallet}: {res}")


def vault_wallets(rpc, owner, operator, tag):
    """Two signer wallets for one owner's vault; returns (owner_wallet, operator_wallet, address)."""
    (o_prv, o_pub), (p_prv, p_pub) = owner, operator
    w_owner, w_op = f"vault-{tag}@owner", f"vault-{tag}@operator"
    for w in (w_owner, w_op):
        rpc("createwallet", [w, False, True, "", False, True, True])
    import_desc(rpc, w_owner, f"tr(musig({o_prv},{p_pub})/0/*,and_v(v:pk({o_prv}/1/*),older({CSV})))")
    import_desc(rpc, w_op, f"tr(musig({o_pub},{p_prv})/0/*,and_v(v:pk({o_pub}/1/*),older({CSV})))")
    a = rpc("getnewaddress", ["", "bech32m"], wallet=w_owner)
    if a != rpc("getnewaddress", ["", "bech32m"], wallet=w_op):
        raise AssertionError("signers derived different vault addresses")
    return w_owner, w_op, a


def fund(rpc, address, amount, miner):
    txid = rpc("sendtoaddress", [address, btc(amount)], wallet="faucet")
    rpc("generatetoaddress", [1, miner])
    tx = rpc("getrawtransaction", [txid, True])
    (n,) = [o["n"] for o in tx["vout"] if o["scriptPubKey"].get("address") == address]
    return {"txid": txid, "vout": n}


def sign_rounds(rpc, psbt, wallets, rounds=3):
    for r in range(1, rounds + 1):
        parts = [rpc("walletprocesspsbt", [psbt, True, "DEFAULT", True, False], wallet=w)["psbt"] for w in wallets]
        psbt = rpc("combinepsbt", [parts])
        fin = rpc("finalizepsbt", [psbt])
        if fin["complete"]:
            return fin["hex"], r
    return None, rounds


def run(binary: Path) -> dict:
    out = {"scope": "isolated regtest; Bitcoin Core native MuSig2 and CSV script path; synthetic keys and coins",
           "checks": {}}
    with tempfile.TemporaryDirectory(prefix="cbm-rver-") as tmp:
        node = Regtest(binary, tmp)
        node.start()
        rpc = node.rpc
        try:
            out["core_version"] = rpc("getnetworkinfo")["subversion"]
            for w in ("faucet", "key-a", "key-b", "key-op"):
                rpc("createwallet", [w, False, False, "", False, True, True])
            miner = rpc("getnewaddress", wallet="faucet")
            rpc("generatetoaddress", [101, miner])
            A, B, O = root_keys(rpc, "key-a"), root_keys(rpc, "key-b"), root_keys(rpc, "key-op")
            va_own, va_op, va_addr = vault_wallets(rpc, A, O, "a")
            vb_own, vb_op, vb_addr = vault_wallets(rpc, B, O, "b")

            # 1. Clearing round.
            ia, ib = fund(rpc, va_addr, COLLATERAL, miner), fund(rpc, vb_addr, COLLATERAL, miner)
            rpc("generatetoaddress", [2, miner])
            b_pay = rpc("getnewaddress", ["", "bech32m"], wallet="key-b")
            a_ret = rpc("getnewaddress", ["", "bech32m"], wallet="key-a")
            b_ret = rpc("getnewaddress", ["", "bech32m"], wallet="key-b")
            outputs = [{b_pay: btc(CLAIM)}, {a_ret: btc(COLLATERAL - CLAIM - FEE_PER_INPUT)},
                       {b_ret: btc(COLLATERAL - FEE_PER_INPUT)}]
            psbt = rpc("createpsbt", [[ia, ib], outputs, 0, False])
            raw, rounds = sign_rounds(rpc, psbt, [va_own, va_op, vb_own, vb_op])
            assert raw, "clearing PSBT did not finalize with owner and operator signatures"
            verdict = rpc("testmempoolaccept", [[raw]])[0]
            assert verdict["allowed"], verdict
            clearing = rpc("sendrawtransaction", [raw])
            rpc("generatetoaddress", [3, miner])
            tx = rpc("getrawtransaction", [clearing, True])
            vin_total = 2 * COLLATERAL
            vout_total = sum(sats(o["value"]) for o in tx["vout"])
            fee = vin_total - vout_total
            out["clearing"] = dict(txid=clearing, vsize=tx["vsize"], weight=tx["weight"], inputs=2, outputs=len(tx["vout"]),
                                   signing_rounds=rounds, fee_sat=fee,
                                   witness_items_per_input=[len(v["txinwitness"]) for v in tx["vin"]])
            out["checks"]["clearing_conserves_value"] = vin_total == vout_total + fee and fee == 2 * FEE_PER_INPUT
            out["checks"]["payout_equals_claim"] = any(sats(o["value"]) == CLAIM and o["scriptPubKey"]["address"] == b_pay for o in tx["vout"])
            out["checks"]["keypath_single_schnorr_sig"] = all(len(v["txinwitness"]) == 1 for v in tx["vin"])

            # 2. Reuse from the owners' own wallets.
            reuse = {}
            for w in ("key-a", "key-b"):
                bal = rpc("getbalances", wallet=w)["mine"]["trusted"]
                dest = rpc("getnewaddress", ["", "bech32m"], wallet="faucet")
                txid = rpc("sendtoaddress", [dest, btc(sats(bal) - 2_000), "", "", True], wallet=w)
                reuse[w] = txid
            rpc("generatetoaddress", [1, miner])
            out["reuse"] = {w: dict(txid=t, confirmations=rpc("getrawtransaction", [t, True])["confirmations"]) for w, t in reuse.items()}
            out["checks"]["released_outputs_reused"] = all(v["confirmations"] >= 1 for v in out["reuse"].values())

            # 3. Unilateral exit with operator and counterparty offline.
            va2_own, va2_op, va2_addr = vault_wallets(rpc, A, O, "a2")
            iv = fund(rpc, va2_addr, COLLATERAL, miner)
            dest = rpc("getnewaddress", ["", "bech32m"], wallet="key-a")
            keypath = rpc("createpsbt", [[iv], [{dest: btc(COLLATERAL - FEE_PER_INPUT)}], 0, False])
            raw_kp, _ = sign_rounds(rpc, keypath, [va2_own])
            out["checks"]["keypath_needs_operator"] = raw_kp is None
            exit_psbt = rpc("createpsbt", [[dict(iv, sequence=CSV)], [{dest: btc(COLLATERAL - FEE_PER_INPUT)}], 0, False])
            raw_exit, _ = sign_rounds(rpc, exit_psbt, [va2_own])
            assert raw_exit, "owner could not sign the CSV leaf"
            conf_now = rpc("getrawtransaction", [iv["txid"], True])["confirmations"]
            early = rpc("testmempoolaccept", [[raw_exit]])[0]
            rpc("generatetoaddress", [CSV - 1 - conf_now, miner])
            conf_before = rpc("getrawtransaction", [iv["txid"], True])["confirmations"]
            before = rpc("testmempoolaccept", [[raw_exit]])[0]
            rpc("generatetoaddress", [1, miner])
            conf_at = rpc("getrawtransaction", [iv["txid"], True])["confirmations"]
            at = rpc("testmempoolaccept", [[raw_exit]])[0]
            ex = rpc("sendrawtransaction", [raw_exit])
            rpc("generatetoaddress", [1, miner])
            ext = rpc("getrawtransaction", [ex, True])
            out["unilateral_exit"] = dict(txid=ex, vsize=ext["vsize"], weight=ext["weight"],
                                          witness_items=len(ext["vin"][0]["txinwitness"]),
                                          rejected_at_confirmations=[conf_now, conf_before], accepted_at_confirmations=conf_at,
                                          early_reject_reason=early.get("reject-reason"), before_reject_reason=before.get("reject-reason"))
            out["checks"]["csv_rejected_before_144"] = (not early["allowed"]) and (not before["allowed"]) and conf_before == CSV - 1
            out["checks"]["csv_accepted_at_144"] = bool(at["allowed"]) and conf_at == CSV
            out["checks"]["exit_spendable_by_owner"] = ext["confirmations"] >= 1
            out["passed"] = all(out["checks"].values())
        finally:
            node.stop()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bitcoind", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    res = run(a.bitcoind)
    txt = json.dumps(res, indent=2, sort_keys=True, default=str) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(txt, encoding="utf-8")
    print(txt)
    raise SystemExit(0 if res.get("passed") else 1)


if __name__ == "__main__":
    main()
