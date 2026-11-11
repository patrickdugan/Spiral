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
   statement (refused), and the order with no proof and no --allow-unproven (refused);
7. the payout key: the order pays P + t*G (`payout_key.py`), not the script the payer spent, and
   the spent-key menu prices the same order to the old script; for a fresh key of each one-key
   type, Core derives the same address from p + t and spends the derived output;
8. with --proof only: the wrap tampered three ways (a bit flipped, the committed digest
   re-pointed at a statement claiming twice the value, the last byte cut) and the real wrap
   offered with a wrong statement (the value doubled; another real M16 statement). All refused.

Run inside WSL (the gate and bitcoind are Linux binaries):
    python3 scripts/regtest_replay.py --out results/regtest-replay.json
    python3 scripts/regtest_replay.py --proof m16-wrap-blake3-v2.bin --out results/regtest-replay-proven.json
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from iob import btc, desk, ec, menu as menu_mod, payout_key, sender, statement  # noqa: E402
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


# m13 wrap v2: SHA-256 of the guest's public values sits at this offset, one byte per
# little-endian u32 (a KoalaBear element), 32 elements. Found by searching the M16 wrap for the
# committed digest cae6068f...c869; it occurs once.
WRAP_DIGEST_OFFSET = 240
VALUE_OFFSET = statement.CHAIN_BYTES + 84  # PAY1 u64 value


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


SWEEP_TYPES = (("p2wpkh", True), ("p2sh-p2wpkh", True), ("p2pkh", True), ("p2pkh", False))
SWEEP_SATS = 50_000


def sweep_derived(node, burger, payer, txid_internal: bytes, vout: int) -> dict:
    """For a fresh key of each one-key type: the desk derives P' = P + t*G and pays it; the payer
    derives p + t (`payout_key.derive_private`, what `iob payout-key --wif-stdin` prints), imports
    it into a Core descriptor wallet, and spends every derived output back to the desk. Core
    computing the same address from p + t that the desk computed from P + t*G is an independent
    check of the tweak arithmetic."""
    keys, mismatch = [], []
    for key_type, compressed in SWEEP_TYPES:
        secret = int.from_bytes(os.urandom(32), "big") % (ec.N - 1) + 1
        pub = ec.serialize(ec.mul(secret), compressed)
        derived_pub, _ = payout_key.derive_pubkey(pub, txid_internal, vout)
        spk = payout_key.script_for(derived_pub, key_type)
        addr = btc.spk_to_address(spk, "regtest")
        wif = payout_key.wif_encode(payout_key.derive_private(secret, compressed, txid_internal, vout), "regtest", compressed)
        desc = payout_key.DESCRIPTOR[key_type].format(wif)
        info = node.call("getdescriptorinfo", desc)
        core_addr = node.call("deriveaddresses", info["descriptor"])[0]
        if core_addr != addr:
            mismatch.append(key_type)
        paid = payer.pay(spk, SWEEP_SATS, None)
        keys.append({"type": key_type, "compressed": compressed, "address": addr, "core_address": core_addr,
                     "funding_txid": paid["txid"], "desc": f"{desc}#{info['checksum']}"})
    node.call("generatetoaddress", 1, burger.call("getnewaddress"))

    node.call("createwallet", "payer", False, True)
    pw = node.wallet("payer")
    imported = pw.call("importdescriptors", [{"desc": k["desc"], "timestamp": 0} for k in keys])
    balance = pw.call("getbalance")
    back = burger.call("getnewaddress")
    sent = pw.call("sendall", [back])
    node.call("generatetoaddress", 1, burger.call("getnewaddress"))
    swept = pw.call("gettransaction", sent["txid"])
    dec = node.call("decoderawtransaction", swept["hex"])
    ok = (not mismatch and all(r.get("success") for r in imported)
          and round(float(balance) * 1e8) == SWEEP_SATS * len(keys)
          and swept["confirmations"] == 1 and len(dec["vin"]) == len(keys))
    for k in keys:
        del k["desc"]  # carries the private key; regtest only, but not needed in the record
    return {
        "status": "swept" if ok else "failed",
        "keys": keys,
        "address_mismatch": mismatch,
        "payer_wallet_balance_btc": str(balance),
        "sweep_txid": sent["txid"],
        "sweep_inputs": len(dec["vin"]),
        "sweep_confirmations": swept["confirmations"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bitcoin-bin", default="/root/opt/bitcoin-31.1/bin")
    ap.add_argument("--menu", default=os.path.join(ROOT, "menus", "m16-mainnet-replay.json"))
    ap.add_argument("--guest-a-proof", default="/root/kan-gate/fixtures/guest-a-wrap-blake3-v2.bin")
    ap.add_argument("--other-statement", default="/root/kan-gate/fixtures/m16-block170-statement.bin",
                    help="another real M16 statement, offered with the mainnet wrap (refused)")
    ap.add_argument("--proof", help="M16 final proof (BLAKE3 wrap v2) of the mainnet statement: serve it proven")
    ap.add_argument("--out")
    a = ap.parse_args()
    started = time.monotonic()

    m = menu_mod.load(a.menu)
    real = desk.Order(
        statement=read("statement.bin"),
        tx_hex=read("payment-tx.hex", "r").strip(),
        sender_proof=json.loads(read("sender-proof.json", "r")),
        proof_path=a.proof,
    )
    st = statement.parse(real.statement)
    unproven = a.proof is None
    log: list = []

    def step(name, run, expect_status, expect_reason=None):
        t = time.monotonic()
        res = run()
        dt = round(time.monotonic() - t, 3)
        ok = res.get("status") == expect_status and (expect_reason is None or res.get("reason") == expect_reason)
        log.append({"step": name, "ok": ok, "seconds": dt, "result": res})
        print(f"[{'ok' if ok else 'FAIL'}] {name}: {res.get('status')} {res.get('reason', '')} ({dt} s)".rstrip(), flush=True)
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

        res = step("serve the M16 mainnet payment order", lambda: desk.serve(m, real, Ledger(ledger_path), payer, allow_unproven=unproven), "served")
        want_proof = "absent" if unproven else "verified"
        log.append({"step": f"proof state is {want_proof}", "ok": res.get("proof") == want_proof, "result": res.get("proof")})
        txid = res.get("payout", {}).get("txid")
        spk = bytes.fromhex(res["sender"]["script_pubkey"]) if "sender" in res else b""
        node.call("generatetoaddress", 1, w.call("getnewaddress"))

        if txid:
            wtx = w.call("gettransaction", txid)
            paid = btc.parse_tx(bytes.fromhex(wtx["hex"]))
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
            spent = (res["sender"].get("derived_from") or {}).get("spent_script_pubkey")
            if m.payout_key == "derived":
                # The payout goes to P + t*G; the script the payer spent from receives nothing.
                old = node.call("scantxoutset", "start", [f"raw({spent})"]) if spent else None
                chain["derived_payout_address"] = res["sender"]["payout_address"]
                chain["spent_script_pubkey"] = spent
                chain["spent_script_utxo_total_btc"] = str(old["total_amount"]) if old else None
                ok = ok and bool(spent) and spent != spk.hex() and old is not None and old["total_amount"] == 0
            log.append({"step": "payout confirmed on regtest, payout script holds exactly the payout", "ok": ok, "result": chain})
            print(f"[{'ok' if ok else 'FAIL'}] payout on chain: {chain}", flush=True)

        step("serve the same order again", lambda: desk.serve(m, real, Ledger(ledger_path), payer, allow_unproven=unproven), "refused", "already_served")

        d0 = json.load(open(a.menu, encoding="utf-8"))
        d0["out"]["payout_key"] = "spent"
        res = step("menu with payout_key spent: the same order priced to the script the payer spent",
                   lambda: desk.serve(menu_mod.from_dict(d0), real, Ledger(None), None, allow_unproven=unproven), "accepted")
        spent_spk = sender.from_input(btc.parse_tx(bytes.fromhex(real.tx_hex)).inputs[0]).script_pubkey.hex()
        if res.get("sender", {}).get("script_pubkey") != spent_spk:
            log[-1]["ok"] = False

        step("derived keys of every one-key type: Core derives the same address from p + t, then spends it",
             lambda: sweep_derived(node, w, payer, st.payment.txid_internal, st.payment.vout), "swept")

        tx = bytearray(bytes.fromhex(real.tx_hex))
        tx[-40] ^= 1
        step("forged witness (same txid)", lambda: desk.serve(m, dataclasses.replace(real, tx_hex=tx.hex()), Ledger(None), None, allow_unproven=unproven), "refused", "sender_proof_witness")

        d = json.load(open(a.menu, encoding="utf-8"))
        d["in"]["address"] = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        step("menu pre-programmed with another address", lambda: desk.serve(menu_mod.from_dict(d), real, Ledger(None), None, allow_unproven=unproven), "refused", "script_not_registered")
        d2 = json.load(open(a.menu, encoding="utf-8"))
        d2["in"]["min_tip_chainwork"] = "0x156c4c3c54ad473bac5daf262"
        step("chainwork floor one above the proven tip", lambda: desk.serve(menu_mod.from_dict(d2), real, Ledger(None), None, allow_unproven=unproven), "refused", "chainwork_below_floor")

        step("no proof, no --allow-unproven", lambda: desk.serve(m, dataclasses.replace(real, proof_path=None), Ledger(None), None), "refused", "proof_required")
        if os.path.exists(a.guest_a_proof):
            step("guest A's real final proof offered for the M16 statement (kan-payment-gate check)",
                 lambda: desk.serve(m, dataclasses.replace(real, proof_path=a.guest_a_proof), Ledger(None), None), "refused", "proof_wrong_program")
        else:
            log.append({"step": "guest A proof check", "ok": None, "result": f"missing {a.guest_a_proof}"})

        proof_info = None
        if not unproven:
            wrap = open(a.proof, "rb").read()
            proof_info = {"path": a.proof, "bytes": len(wrap), "sha256": hashlib.sha256(wrap).hexdigest()}

            def tampered(name: str, data: bytes) -> str:
                p = os.path.join(tmp, name)
                with open(p, "wb") as f:
                    f.write(data)
                return p

            inflated = bytearray(real.statement)
            v = struct.unpack_from("<Q", inflated, VALUE_OFFSET)[0]
            struct.pack_into("<Q", inflated, VALUE_OFFSET, 2 * v)
            inflated = bytes(inflated)

            flipped = bytearray(wrap)
            flipped[len(wrap) // 2] ^= 1
            step("tampered wrap: one bit flipped at the middle byte",
                 lambda: desk.serve(m, dataclasses.replace(real, proof_path=tampered("flip.bin", flipped)), Ledger(None), None),
                 "refused", "proof_rejected")

            digest = wrap[WRAP_DIGEST_OFFSET:WRAP_DIGEST_OFFSET + 128]
            want = b"".join(struct.pack("<I", b) for b in bytes.fromhex(st.sha256))
            if digest != want:
                log.append({"step": "committed digest found at the wrap offset", "ok": False, "result": digest.hex()})
            repointed = bytearray(wrap)
            repointed[WRAP_DIGEST_OFFSET:WRAP_DIGEST_OFFSET + 128] = b"".join(struct.pack("<I", b) for b in hashlib.sha256(inflated).digest())
            step(f"tampered wrap: committed digest re-pointed at a statement claiming {2 * v:,} sats",
                 lambda: desk.serve(m, dataclasses.replace(real, statement=inflated, proof_path=tampered("repoint.bin", repointed)), Ledger(None), None),
                 "refused", "proof_rejected")

            step("tampered wrap: last byte cut",
                 lambda: desk.serve(m, dataclasses.replace(real, proof_path=tampered("cut.bin", wrap[:-1])), Ledger(None), None),
                 "refused", "proof_malformed")

            step(f"wrong statement: the real wrap with the value doubled to {2 * v:,} sats",
                 lambda: desk.serve(m, dataclasses.replace(real, statement=inflated), Ledger(None), None),
                 "refused", "statement_digest_mismatch")

            if os.path.exists(a.other_statement):
                other = open(a.other_statement, "rb").read()
                step(f"wrong statement: the real wrap with another real M16 statement (sha256 {hashlib.sha256(other).hexdigest()[:16]}...)",
                     lambda: desk.serve(m, dataclasses.replace(real, statement=other), Ledger(None), None),
                     "refused", "statement_digest_mismatch")
            else:
                log.append({"step": "other statement check", "ok": None, "result": f"missing {a.other_statement}"})

        float_after = w.call("getbalance")
        summary = {
            "bitcoind": node.call("getnetworkinfo")["subversion"],
            "gate": list(m.gate_argv),
            "gate_sha256": sha256_file(m.gate_argv[0]) if m.gate_argv and os.path.exists(m.gate_argv[0]) else None,
            "proof": proof_info,
            "statement_sha256": st.sha256,
            "float_btc_before": str(float_before),
            "float_btc_after_one_block_more": str(float_after),
            "passed": sum(1 for s in log if s["ok"]),
            "failed": sum(1 for s in log if s["ok"] is False),
            "seconds": round(time.monotonic() - started, 1),
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
