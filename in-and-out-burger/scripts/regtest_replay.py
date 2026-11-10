#!/usr/bin/env python3
"""Replay the M16 mainnet order end to end on a private regtest node.

The in-payment is the one the nova-bitvm3 M16 mainnet run proves (a652ab0c...0045:0, 940,000
sats, block 975,067). The burger pays the sender's script back on a throwaway regtest chain, so
no real sats move. Steps:

1. start bitcoind -regtest in a temporary datadir, mine 101 blocks to a `burger` wallet (the float);
2. serve the order: statement cross-checked with kan-payment-gate `inspect`, menu policy, txid,
   output, sender from the witness (bound by the sender proof), price, journal, payout;
3. mine a block and check, from the chain, that the sender's script holds exactly the payout and
   that the payout carries the IOBP link to the in-payment;
4. serve the same order again (refused: already_served);
5. refusals for a forged witness, a wrong in-address and a raised chainwork floor;
6. the proof layer through the real gate: guest A's real final proof offered for the M16
   statement (refused), and the order with no proof and no --allow-unproven (refused).

Run inside WSL (the gate and bitcoind are Linux binaries):
    python3 scripts/regtest_replay.py --out results/regtest-replay.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from iob import btc, desk, menu as menu_mod, statement  # noqa: E402
from iob.ledger import Ledger  # noqa: E402
from iob.rpc import RPC, RPCError  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "m16-mainnet")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read(name, mode="rb"):
    with open(os.path.join(FIX, name), mode) as f:
        return f.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bitcoin-bin", default="/root/opt/bitcoin-31.1/bin")
    ap.add_argument("--menu", default=os.path.join(ROOT, "menus", "m16-mainnet-replay.json"))
    ap.add_argument("--guest-a-proof", default="/root/kan-gate/fixtures/guest-a-wrap-blake3-v2.bin")
    ap.add_argument("--proof", help="M16 final proof (BLAKE3 wrap v2) of the mainnet statement: serve it proven")
    ap.add_argument("--out")
    a = ap.parse_args()

    m = menu_mod.load(a.menu)
    real = desk.Order(
        statement=read("statement.bin"),
        tx_hex=read("payment-tx.hex", "r").strip(),
        sender_proof=json.loads(read("sender-proof.json", "r")),
        proof_path=a.proof,
    )
    unproven = a.proof is None
    log: list = []

    def step(name, res, expect_status, expect_reason=None):
        ok = res.get("status") == expect_status and (expect_reason is None or res.get("reason") == expect_reason)
        log.append({"step": name, "ok": ok, "result": res})
        print(f"[{'ok' if ok else 'FAIL'}] {name}: {res.get('status')} {res.get('reason', '')}".rstrip(), flush=True)
        return res

    tmp = tempfile.mkdtemp(prefix="iob-regtest-")
    rpcport = free_port()
    proc = subprocess.Popen(
        [os.path.join(a.bitcoin_bin, "bitcoind"), "-regtest", f"-datadir={tmp}", f"-rpcport={rpcport}",
         f"-port={free_port()}", "-listen=0", "-dnsseed=0", "-fallbackfee=0.0001", "-printtoconsole=0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        cookie = os.path.join(tmp, "regtest", ".cookie")
        node = None
        for _ in range(120):
            if os.path.exists(cookie):
                try:
                    node = RPC(f"http://127.0.0.1:{rpcport}", cookie=cookie, timeout=600)
                    node.call("getblockchaininfo")
                    break
                except (RPCError, OSError):
                    node = None
            time.sleep(0.5)
        if node is None:
            raise SystemExit("bitcoind did not come up")
        node.call("createwallet", "burger")
        w = node.wallet("burger")
        node.call("generatetoaddress", 101, w.call("getnewaddress"))
        float_before = w.call("getbalance")

        ledger_path = os.path.join(tmp, "served.jsonl")
        payer = desk.CorePayer(w, m.out_network, m.fee_rate_sat_vb)

        res = step("serve the M16 mainnet payment order", desk.serve(m, real, Ledger(ledger_path), payer, allow_unproven=unproven), "served")
        if res.get("proof") != ("absent" if unproven else "verified"):
            log.append({"step": "proof state", "ok": False, "result": res.get("proof")})
        txid = res.get("payout", {}).get("txid")
        spk = bytes.fromhex(res["sender"]["script_pubkey"]) if "sender" in res else b""
        node.call("generatetoaddress", 1, w.call("getnewaddress"))

        if txid:
            wtx = w.call("gettransaction", txid)
            paid = btc.parse_tx(bytes.fromhex(wtx["hex"]))
            st = statement.parse(real.statement)
            link = desk.link_data(st.payment)
            pays = [o.value for o in paid.outputs if o.script_pubkey == spk]
            has_link = any(o.script_pubkey == b"\x6a" + btc.push(link) for o in paid.outputs)
            scan = node.call("scantxoutset", "start", [f"raw({spk.hex()})"])
            chain = {
                "payout_txid": txid,
                "confirmations": wtx["confirmations"],
                "outputs_to_sender_sats": pays,
                "link_output": has_link,
                "sender_utxo_total_btc": str(scan["total_amount"]),
                "fee_sats": round(-wtx["fee"] * 1e8),
                "vsize": None,
            }
            dec = node.call("decoderawtransaction", wtx["hex"])
            chain["vsize"] = dec["vsize"]
            ok = (wtx["confirmations"] == 1 and pays == [res["payout"]["sats"]] and has_link
                  and round(float(scan["total_amount"]) * 1e8) == res["payout"]["sats"])
            log.append({"step": "payout confirmed on regtest, sender script holds exactly the payout", "ok": ok, "result": chain})
            print(f"[{'ok' if ok else 'FAIL'}] payout on chain: {chain}", flush=True)

        step("serve the same order again", desk.serve(m, real, Ledger(ledger_path), payer, allow_unproven=unproven), "refused", "already_served")

        tx = bytearray(bytes.fromhex(real.tx_hex))
        tx[-40] ^= 1
        step("forged witness (same txid)", desk.serve(m, dataclasses.replace(real, tx_hex=tx.hex()), Ledger(None), None, allow_unproven=unproven), "refused", "sender_proof_witness")

        d = json.load(open(a.menu, encoding="utf-8"))
        d["in"]["address"] = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        step("menu pre-programmed with another address", desk.serve(menu_mod.from_dict(d), real, Ledger(None), None, allow_unproven=unproven), "refused", "script_not_registered")
        d = json.load(open(a.menu, encoding="utf-8"))
        d["in"]["min_tip_chainwork"] = "0x156c4c3c54ad473bac5daf262"
        step("chainwork floor one above the proven tip", desk.serve(menu_mod.from_dict(d), real, Ledger(None), None, allow_unproven=unproven), "refused", "chainwork_below_floor")

        step("no proof, no --allow-unproven", desk.serve(m, dataclasses.replace(real, proof_path=None), Ledger(None), None), "refused", "proof_required")
        if os.path.exists(a.guest_a_proof):
            res = desk.serve(m, dataclasses.replace(real, proof_path=a.guest_a_proof), Ledger(None), None)
            step("guest A's real final proof offered for the M16 statement (kan-payment-gate check)", res, "refused", "proof_wrong_program")
        else:
            log.append({"step": "guest A proof check", "ok": None, "result": f"missing {a.guest_a_proof}"})

        float_after = w.call("getbalance")
        summary = {
            "bitcoind": node.call("getnetworkinfo")["subversion"],
            "gate": list(m.gate_argv),
            "float_btc_before": str(float_before),
            "float_btc_after_one_block_more": str(float_after),
            "passed": sum(1 for s in log if s["ok"]),
            "failed": sum(1 for s in log if s["ok"] is False),
            "steps": log,
        }
        if a.out:
            os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=1, sort_keys=True, default=str)
                f.write("\n")
        print(f"{summary['passed']} passed, {summary['failed']} failed")
        return 0 if summary["failed"] == 0 else 1
    finally:
        try:
            RPC(f"http://127.0.0.1:{rpcport}", cookie=os.path.join(tmp, "regtest", ".cookie")).call("stop")
            proc.wait(timeout=60)
        except Exception:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
