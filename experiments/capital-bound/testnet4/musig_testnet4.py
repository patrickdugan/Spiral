#!/usr/bin/env python3
"""Fund and settle a MuSig2 key-path shared-capital pool on public Testnet4.

Stages, each journaled before any submission:
  setup   create the two signer wallets and the two pool views of
          tr(musig(A, B)/0/*); record the pool address.
  fund    sign a payment of POOL_SAT from the dedicated payer's one
          confirmed output to the pool, with payer change.
  settle  after CONFIRMATIONS, sign the invoice batch plus pool change
          from the pool output through Core's two-round MuSig2 PSBT flow.
  observe write Core Merkle receipts from the campaign node and the
          independent observer node.

Private keys stay inside the local Core wallets. The journal holds signed
bytes and stays in the private state directory; the evidence export omits them.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from core import Core, Gate, RPCError, btc, chain_tip, inclusion, sats

POOL_SAT = 100_000
INVOICES = (1_400, 1_400)
FEE_SAT = 400
CONFIRMATIONS = 2
WALLETS = {"key_a": "cbm-musig01-key-a", "key_b": "cbm-musig01-key-b",
           "pool_a": "cbm-musig01-pool-a", "pool_b": "cbm-musig01-pool-b"}
PAYER = "cbm-pilot01-payer"
RECIPIENT = "cbm-musig01-recipient"


class Journal:
    def __init__(self, path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def save(self):
        scratch = self.path.with_name("." + self.path.name + ".tmp")
        scratch.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        scratch.replace(self.path)


def root_keys(core, wallet):
    rows = core.rpc("listdescriptors", [True], wallet=wallet)["descriptors"]
    (row,) = [r for r in rows if not r["internal"] and r["desc"].startswith("tr(")]
    root = row["desc"].split("(", 1)[1].split("#")[0].split("/", 1)[0]
    if root.startswith("["):
        root = root.split("]", 1)[1]
    public = core.rpc("getdescriptorinfo", [f"pk({root})"])["descriptor"]
    return root, public.split("(", 1)[1].split(")", 1)[0]


def import_active(core, wallet, desc):
    full = desc + "#" + core.rpc("getdescriptorinfo", [desc])["checksum"]
    result = core.rpc("importdescriptors", [[{"desc": full, "active": True, "range": [0, 20],
                                               "timestamp": "now", "internal": False}]],
                      wallet=wallet)
    if not all(row["success"] for row in result):
        raise Gate(f"Descriptor import failed for {wallet}")


def setup(core, journal):
    if "pool_address" in journal.data:
        return {"pool_address": journal.data["pool_address"], "setup": "already_done"}
    loaded = core.rpc("listwallets")
    for name in (WALLETS["key_a"], WALLETS["key_b"], RECIPIENT):
        if name not in loaded:
            core.rpc("createwallet", [name, False, False, "", False, True, True])
    for key in ("pool_a", "pool_b"):
        if WALLETS[key] not in loaded:
            core.rpc("createwallet", [WALLETS[key], False, True, "", False, True, True])
    a_priv, a_pub = root_keys(core, WALLETS["key_a"])
    b_priv, b_pub = root_keys(core, WALLETS["key_b"])
    import_active(core, WALLETS["pool_a"], f"tr(musig({a_priv},{b_pub})/0/*)")
    import_active(core, WALLETS["pool_b"], f"tr(musig({a_pub},{b_priv})/0/*)")
    addresses = []
    for _ in range(2):
        mine = core.rpc("getnewaddress", ["", "bech32m"], wallet=WALLETS["pool_a"])
        twin = core.rpc("getnewaddress", ["", "bech32m"], wallet=WALLETS["pool_b"])
        if mine != twin:
            raise Gate("MuSig2 signers derived different pool addresses")
        addresses.append(mine)
    info = core.rpc("getaddressinfo", [addresses[0]], wallet=WALLETS["pool_a"])
    journal.data.update(pool_address=addresses[0], pool_change_address=addresses[1],
                        pool_descriptor_public=f"tr(musig({a_pub},{b_pub})/0/*)",
                        pool_scriptpubkey=info["scriptPubKey"])
    journal.save()
    return {"pool_address": addresses[0]}


def confirmed_output(core, txid, vout, sat):
    out = core.rpc("gettxout", [txid, vout, True])
    if not out or out["confirmations"] < CONFIRMATIONS or sats(out["value"]) != sat:
        raise Gate(f"{txid}:{vout} is not a confirmed unspent {sat}-sat output")
    return out


def sign_fund(core, journal):
    funds = [u for u in core.rpc("listunspent", [CONFIRMATIONS], wallet=PAYER)
             if u.get("safe") and u.get("spendable")]
    if len(funds) != 1:
        raise Gate("The payer must hold exactly one confirmed output before funding the pool")
    src = funds[0]
    total = sats(src["amount"])
    change_sat = total - POOL_SAT - FEE_SAT
    if change_sat < 600:
        raise Gate("Payer output is too small to fund the pool")
    change = core.rpc("getrawchangeaddress", ["bech32"], wallet=PAYER)
    raw = core.rpc("createrawtransaction", [[{"txid": src["txid"], "vout": src["vout"],
                                              "sequence": 0xFFFFFFFE}],
                                            [{journal.data["pool_address"]: btc(POOL_SAT)},
                                             {change: btc(change_sat)}], 0, False])
    signed = core.rpc("signrawtransactionwithwallet", [raw], wallet=PAYER)
    if not signed["complete"]:
        raise Gate("Payer could not sign the pool funding")
    decoded = core.rpc("decoderawtransaction", [signed["hex"]])
    (vout,) = [o["n"] for o in decoded["vout"]
               if o["scriptPubKey"]["hex"] == journal.data["pool_scriptpubkey"]]
    return {"raw": signed["hex"], "txid": decoded["txid"], "fee_sat": FEE_SAT,
            "source": f"{src['txid']}:{src['vout']}", "source_sat": total,
            "pool_vout": vout, "payer_change_sat": change_sat, "vsize": decoded["vsize"]}


def sign_settle(core, journal):
    fund = journal.data["fund"]
    confirmed_output(core, fund["txid"], fund["pool_vout"], POOL_SAT)
    recipients = [core.rpc("getnewaddress", ["", "bech32m"], wallet=RECIPIENT) for _ in INVOICES]
    change_sat = POOL_SAT - sum(INVOICES) - FEE_SAT
    outputs = [{a: btc(s)} for a, s in zip(recipients, INVOICES)]
    outputs.append({journal.data["pool_change_address"]: btc(change_sat)})
    psbt = core.rpc("createpsbt", [[{"txid": fund["txid"], "vout": fund["pool_vout"],
                                     "sequence": 0xFFFFFFFE}], outputs, 0, False])
    rounds = 0
    for _ in range(3):
        rounds += 1
        parts = [core.rpc("walletprocesspsbt", [psbt, True, "DEFAULT", True, False], wallet=w)["psbt"]
                 for w in (WALLETS["pool_a"], WALLETS["pool_b"])]
        psbt = core.rpc("combinepsbt", [parts])
        final = core.rpc("finalizepsbt", [psbt])
        if final["complete"]:
            break
    else:
        raise Gate("MuSig2 PSBT did not finalize")
    decoded = core.rpc("decoderawtransaction", [final["hex"]])
    witness = decoded["vin"][0]["txinwitness"]
    if len(witness) != 1 or len(witness[0]) != 128:
        raise Gate("MuSig2 key-path spend must carry one 64-byte signature")
    return {"raw": final["hex"], "txid": decoded["txid"], "fee_sat": FEE_SAT,
            "source": f"{fund['txid']}:{fund['pool_vout']}", "signing_rounds": rounds,
            "invoices_sat": list(INVOICES), "pool_change_sat": change_sat,
            "vsize": decoded["vsize"], "weight": decoded["weight"]}


def wallet_tx(core, txid):
    """Find a transaction through the campaign wallets; the pruned node has no txindex."""
    for wallet in (PAYER, WALLETS["pool_a"], RECIPIENT):
        try:
            return core.rpc("gettransaction", [txid], wallet=wallet)
        except RPCError as failure:
            if failure.code != -5:
                raise
    return None


def submit(core, journal, stage, args):
    entry = journal.data.get(stage)
    if entry is None:
        entry = (sign_fund if stage == "fund" else sign_settle)(core, journal)
        journal.data[stage] = entry
        journal.save()
    txid = entry["txid"]
    seen = wallet_tx(core, txid)
    if seen and (seen["confirmations"] > 0 or core.rpc("getrawmempool").count(txid)):
        return {"stage": stage, "txid": txid, "submission": "already_observed"}
    verdict = core.rpc("testmempoolaccept", [[entry["raw"]]])[0]
    if not verdict.get("allowed") or sats(verdict["fees"]["base"]) != entry["fee_sat"]:
        raise Gate(f"Core policy rejected the signed {stage} transaction")
    if not args.broadcast:
        return {"stage": stage, "txid": txid, "submission": "dry_run", "vsize": verdict["vsize"]}
    if entry.get("attempted_at") and not args.retry_same:
        raise Gate("Submission already attempted; observe, or pass --retry-same for identical bytes")
    entry["attempted_at"] = int(time.time())
    entry["attempt_height"] = chain_tip(core)["blocks"]
    journal.save()
    if core.rpc("sendrawtransaction", [entry["raw"]]) != txid:
        raise Gate("Core returned a different transaction ID")
    return {"stage": stage, "txid": txid, "submission": "accepted", "fee_sat": entry["fee_sat"]}


def observe(core, observer, journal, out):
    rows = {}
    for stage in ("fund", "settle"):
        entry = journal.data.get(stage)
        if not entry:
            continue
        tx = wallet_tx(core, entry["txid"]) or {}
        row = {k: v for k, v in entry.items() if k != "raw"}
        row["confirmations"] = tx.get("confirmations", 0)
        if tx.get("blockhash") and tx["confirmations"] > 0:
            row["receipt"] = inclusion(core, entry["txid"], tx["blockhash"])
            if observer is not None:
                chain_tip(observer)
                other = inclusion(observer, entry["txid"], tx["blockhash"])
                row["independent_inclusion"] = {k: v for k, v in other.items() if k != "merkle_proof"}
        rows[stage] = row
    evidence = {"network": "testnet4", "campaign": "musig01",
                "pool_descriptor_public": journal.data.get("pool_descriptor_public"),
                "pool_address": journal.data.get("pool_address"), "pool_sat": POOL_SAT,
                "confirmations_required": CONFIRMATIONS, "stages": rows}
    if out:
        out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--datadir", type=Path, required=True)
    p.add_argument("--observer-datadir", type=Path)
    p.add_argument("--observer-port", type=int)
    p.add_argument("command", choices=("setup", "fund", "settle", "observe"))
    p.add_argument("--broadcast", action="store_true")
    p.add_argument("--retry-same", action="store_true")
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)
    args.state.mkdir(parents=True, exist_ok=True)
    journal = Journal(args.state / "musig01.json")
    core = Core("testnet4", args.datadir.resolve())
    observer = (Core("testnet4", args.observer_datadir.resolve(), args.observer_port)
                if args.observer_datadir else None)
    try:
        chain_tip(core)
        if args.command == "setup":
            result = setup(core, journal)
        elif args.command in ("fund", "settle"):
            if "pool_address" not in journal.data:
                raise Gate("Run setup first")
            if args.command == "settle" and "fund" not in journal.data:
                raise Gate("Fund the pool first")
            result = submit(core, journal, args.command, args)
        else:
            result = observe(core, observer, journal, args.out)
    except Gate as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
