"""Settle a shared-capital batch from a MuSig2 key-path pool on isolated regtest.

Two signer wallets hold one key each. The pool output is
tr(musig(A, B)/0/*): a 2-of-2 aggregate key that spends with one Schnorr
signature. A batch of invoices plus pool change is signed through Core's
two-round MuSig2 PSBT flow (nonces, then partial signatures) and mined.
The same batch is then spent from a P2WSH 2-of-2 multisig and from a
single-key P2TR output so the settlement weight of each custody form is
measured on the same Core build.
"""
import argparse
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core_regtest import OwnedRegtest

POOL_SAT = 100_000
INVOICES = (1_400, 1_400)
FEE_SAT = 400


def btc(sat):
    return f"{sat // 100_000_000}.{sat % 100_000_000:08d}"


def sats(value):
    return int(Decimal(str(value)) * 100_000_000)


def account_keys(rpc, wallet, script_type):
    """Return a wallet's (private, public) root extended key.

    listdescriptors exposes the root key followed by a hardened path, which a
    musig() expression cannot carry, so the experiment derives from the root.
    Core's getdescriptorinfo supplies the public form.
    """
    rows = rpc("listdescriptors", [True], wallet=wallet)["descriptors"]
    (row,) = [r for r in rows if not r["internal"] and r["desc"].startswith(script_type + "(")]
    body = row["desc"].split("(", 1)[1].split("#")[0]
    root = body.split("/", 1)[0]
    if root.startswith("["):
        root = root.split("]", 1)[1]
    public = rpc("getdescriptorinfo", [f"pk({root})"])["descriptor"]
    return root, public.split("(", 1)[1].split(")", 1)[0]


def strip(desc):
    return desc.split("#")[0]


def with_checksum(rpc, desc):
    # getdescriptorinfo returns the public form; keep the private keys and add the checksum.
    return desc + "#" + rpc("getdescriptorinfo", [desc])["checksum"]


def import_active(rpc, wallet, desc):
    result = rpc("importdescriptors", [[{"desc": with_checksum(rpc, desc), "active": True,
                                          "range": [0, 20], "timestamp": "now",
                                          "internal": False}]], wallet=wallet)
    if not all(row["success"] for row in result):
        raise RuntimeError(f"import failed for {wallet}: {result}")


def fund(rpc, address, miner):
    txid = rpc("sendtoaddress", [address, btc(POOL_SAT)], wallet="faucet")
    rpc("generatetoaddress", [1, miner])
    tx = rpc("getrawtransaction", [txid, True])
    (vout,) = [o["n"] for o in tx["vout"] if o["scriptPubKey"].get("address") == address]
    return txid, vout


def batch_psbt(rpc, source, recipients, change_address):
    outputs = [{addr: btc(sat)} for addr, sat in zip(recipients, INVOICES)]
    change = POOL_SAT - sum(INVOICES) - FEE_SAT
    outputs.append({change_address: btc(change)})
    return rpc("createpsbt", [[{"txid": source[0], "vout": source[1]}], outputs, 0, False]), change


def settle(rpc, psbt, signers):
    """Run every signer once per round until the PSBT finalizes; return rounds used."""
    rounds = 0
    for _ in range(3):
        rounds += 1
        parts = [rpc("walletprocesspsbt", [psbt, True, "DEFAULT", True, False], wallet=w)["psbt"]
                 for w in signers]
        psbt = rpc("combinepsbt", [parts])
        final = rpc("finalizepsbt", [psbt])
        if final["complete"]:
            return final["hex"], rounds
    raise RuntimeError("PSBT did not finalize after three signing rounds")


def mine_and_measure(rpc, raw, miner, label):
    verdict = rpc("testmempoolaccept", [[raw]])[0]
    if not verdict["allowed"]:
        raise RuntimeError(f"{label}: {verdict}")
    txid = rpc("sendrawtransaction", [raw])
    block = rpc("generatetoaddress", [1, miner])[0]
    tx = rpc("getrawtransaction", [txid, True, block])
    witness = tx["vin"][0]["txinwitness"]
    return {"txid": txid, "blockhash": block, "vsize": tx["vsize"], "weight": tx["weight"],
            "fee_sat": sats(verdict["fees"]["base"]), "witness_items": len(witness),
            "witness_bytes": sum(len(item) // 2 for item in witness),
            "outputs": len(tx["vout"])}


def case(binary):
    with tempfile.TemporaryDirectory() as tmp:
        node = OwnedRegtest(binary, Path(tmp))
        try:
            node.start()
            rpc = node.rpc
            for name in ("faucet", "key-a", "key-b", "recipient", "single"):
                rpc("createwallet", [name, False, False, "", False, True, True])
            for name in ("pool-a", "pool-b", "msig-a", "msig-b"):
                rpc("createwallet", [name, False, True, "", False, True, True])
            miner = rpc("getnewaddress", wallet="faucet")
            rpc("generatetoaddress", [101, miner])

            tr_a, tr_a_pub = account_keys(rpc, "key-a", "tr")
            tr_b, tr_b_pub = account_keys(rpc, "key-b", "tr")
            import_active(rpc, "pool-a", f"tr(musig({tr_a},{tr_b_pub})/0/*)")
            import_active(rpc, "pool-b", f"tr(musig({tr_a_pub},{tr_b})/0/*)")
            pool_address = rpc("getnewaddress", ["", "bech32m"], wallet="pool-a")
            twin = rpc("getnewaddress", ["", "bech32m"], wallet="pool-b")
            if pool_address != twin:
                raise AssertionError("MuSig2 signers derived different pool addresses")
            change_address = rpc("getnewaddress", ["", "bech32m"], wallet="pool-a")
            rpc("getnewaddress", ["", "bech32m"], wallet="pool-b")
            pool_desc = rpc("getaddressinfo", [pool_address], wallet="pool-a")["desc"]

            wk_a, wk_a_pub = account_keys(rpc, "key-a", "wpkh")
            wk_b, wk_b_pub = account_keys(rpc, "key-b", "wpkh")
            import_active(rpc, "msig-a", f"wsh(multi(2,{wk_a}/0/*,{wk_b_pub}/0/*))")
            import_active(rpc, "msig-b", f"wsh(multi(2,{wk_a_pub}/0/*,{wk_b}/0/*))")
            msig_address = rpc("getnewaddress", ["", "bech32"], wallet="msig-a")
            if msig_address != rpc("getnewaddress", ["", "bech32"], wallet="msig-b"):
                raise AssertionError("multisig signers derived different addresses")
            msig_change = rpc("getnewaddress", ["", "bech32"], wallet="msig-a")
            rpc("getnewaddress", ["", "bech32"], wallet="msig-b")

            single_address = rpc("getnewaddress", ["", "bech32m"], wallet="single")
            single_change = rpc("getnewaddress", ["", "bech32m"], wallet="single")

            results = {}
            for label, address, change_to, signers in (
                ("musig2_keypath", pool_address, change_address, ["pool-a", "pool-b"]),
                ("p2wsh_2of2", msig_address, msig_change, ["msig-a", "msig-b"]),
                ("p2tr_single_key", single_address, single_change, ["single"]),
            ):
                source = fund(rpc, address, miner)
                recipients = [rpc("getnewaddress", ["", "bech32m"], wallet="recipient")
                              for _ in INVOICES]
                psbt, change = batch_psbt(rpc, source, recipients, change_to)
                raw, rounds = settle(rpc, psbt, signers)
                row = mine_and_measure(rpc, raw, miner, label)
                row.update(source=f"{source[0]}:{source[1]}", signing_rounds=rounds,
                           change_sat=change, invoices_sat=list(INVOICES))
                change_spendable = any(u["address"] == change_to and sats(u["amount"]) == change
                                       for u in rpc("listunspent", [1], wallet=signers[0]))
                row["change_back_in_pool"] = change_spendable
                results[label] = row

            musig = results["musig2_keypath"]
            if musig["witness_items"] != 1 or musig["witness_bytes"] != 64:
                raise AssertionError("MuSig2 key-path spend must carry one 64-byte signature")
            if not musig["change_back_in_pool"]:
                raise AssertionError("pool change is not spendable by the MuSig2 signers")
            return {
                "scope": "isolated regtest, Bitcoin Core native MuSig2 PSBT signing",
                "core_version": rpc("getnetworkinfo")["subversion"],
                "pool_descriptor": strip(pool_desc),
                "pool_sat": POOL_SAT,
                "fee_sat_per_settlement": FEE_SAT,
                "settlements": results,
                "musig2_vs_p2wsh_vbytes_saved": results["p2wsh_2of2"]["vsize"] - musig["vsize"],
                "musig2_vs_single_key_vbytes": musig["vsize"] - results["p2tr_single_key"]["vsize"],
            }
        finally:
            node.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitcoind", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    result = case(parser.parse_args().bitcoind)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args = parser.parse_args()
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
