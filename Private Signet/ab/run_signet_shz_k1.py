#!/usr/bin/env python3
"""SHZ-K1 on a PATCHED custom Signet (Keyless + Signet + CSFS patches).

Nodes (lab.py init, same environment as run_signet_keyless.py with
SPIRAL_SIGNET_CSFS=1): patched miner and observer with -keylessresearch=1,
and a stock Core legacy node following the miner.

Steps, on SatsHedgeZero trade 1 (run_shz_k1_regtest.fixture):
  fund      two K1 outputs from the lab wallet in one transaction
  transfer  the oracle attests $125,000; Alice has assigned her long
            position to Carol (Bob not involved); the settlement pays
            Carol 1,075 and Bob 550 sats. Refused by the mempool
            (non-standard), mined by the block signer, accepted by all nodes.
  double    Alice's second assignment (to another buyer) in a signed block:
            rejected everywhere because the coin is spent.
  split     on the second K1 output, a settlement that shaves 1 sat off the
            long payout with a fresh TXCOMMIT witness, in a signed block:
            both patched nodes reject it, the legacy node accepts and forks,
            and the fork is invalidated on the legacy node afterwards.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("lab", HERE.parent / "lab.py")
lab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lab)

from run_shz_k1_regtest import SETTLE_PRICE, fixture  # noqa: E402
from txlib import spk_address  # noqa: E402


def main() -> None:
    state = lab.read_state()
    names = lab.nodes()
    if "legacy" not in names or "-keylessresearch=1" not in state.get("node_args", []):
        raise SystemExit("needs a lab initialised with the patched build, -keylessresearch=1 and BITCOIND_LEGACY")
    p, oracle, spec, k1 = fixture()
    addr = spk_address("tb", k1.spk)
    amount = f"{k1.funding_sats / 1e8:.8f}"
    # sendmany refuses a duplicate address; fund the second output separately.
    funding_txid = lab.cli("miner", "sendtoaddress", addr, amount, wallet="funds")
    second_txid = lab.cli("miner", "sendtoaddress", addr, amount, wallet="funds")
    # Run straight after run_signet_keyless.py (whose last block was rejected,
    # so the tip did not move), the next block omitted both transactions, on
    # the CI runner and locally: getblocktemplate reuses its cached template
    # while the tip is unchanged and the mempool changed under 5 s ago. Mine
    # until the wallet sees both confirmed; look each up in its own block.
    fund_attempts = []
    for _ in range(4):
        fund_block = lab.mine(1)
        fund_attempts.append(fund_block["tip"])
        info = {t: lab.rpc("miner", "gettransaction", t, wallet="funds") for t in (funding_txid, second_txid)}
        if all(i.get("blockhash") for i in info.values()):
            break
    else:
        raise SystemExit(f"funding not confirmed after {len(fund_attempts)} blocks: "
                         + json.dumps({"mempool": lab.rpc("miner", "getrawmempool"), "blocks": fund_attempts,
                                       "wallet": {t: i.get("confirmations") for t, i in info.items()}}))
    raws = [lab.rpc("miner", "getrawtransaction", t, "1", info[t]["blockhash"]) for t in (funding_txid, second_txid)]
    vouts = [next(o["n"] for o in r["vout"] if o["scriptPubKey"]["hex"] == k1.spk.hex()) for r in raws]

    x = p.x
    att = oracle.attest(SETTLE_PRICE)
    i125 = k1.leaf_for_price(SETTLE_PRICE)
    own = {"long": (x("alice"), k1.assign(p.alice, x("alice"))), "short": (x("bob"), k1.assign(p.bob, x("bob")))}
    to_carol = {**own, "long": (x("carol"), k1.assign(p.alice, x("carol")))}
    to_second = {**own, "long": (x("mallory"), k1.assign(p.alice, x("mallory")))}

    report = {"kind": "signet-shz-k1", "challenge": state["challenge"], "node_args": state["node_args"],
              "versions": {n: lab.rpc(n, "getnetworkinfo")["subversion"] for n in names},
              "contract": k1.summary() | {"long_margin_sats": spec.long_margin_sats,
                                          "short_margin_sats": spec.short_margin_sats,
                                          "entry_price_usd": spec.entry_price_usd},
              "oracle": oracle.announcement(), "settle_price_usd": SETTLE_PRICE,
              "funding": {"address": addr, "txids": [funding_txid, second_txid], "vouts": vouts,
                          "blocks": [info[t]["blockhash"] for t in (funding_txid, second_txid)],
                          "blocks_mined": fund_attempts}}

    # Transfer: Carol is paid the long side, without Bob.
    settle = k1.spend(funding_txid, vouts[0], i125, to_carol, att)
    report["transfer_mempool"] = {n: lab.rpc(n, "testmempoolaccept", json.dumps([settle.hex()]))[0]
                                  for n in ("miner", "legacy")}
    blk = lab.mine_with([settle.hex()])
    t = {"txid": settle.txid, "weight": settle.weight, "vsize": settle.vsize,
         "outputs": [o.value for o in settle.vout], "block": blk["hash"], "signed": blk["signed_complete"],
         "submit": lab.submit_block(blk, ["miner"])}
    t["synced"] = lab.wait_synced()
    t["utxos"] = {n: [lab.rpc(n, "gettxout", settle.txid, str(i), "false") for i in (0, 1)] for n in names}
    t["accepted_by_all"] = all(u is not None for us in t["utxos"].values() for u in us)
    report["transfer"] = t

    # Double sale: the second assignment cannot settle once the first did.
    dbl = k1.spend(funding_txid, vouts[0], i125, to_second, att)
    blk2 = lab.mine_with([dbl.hex()])
    d = {"txid": dbl.txid, "block": blk2["hash"], "verdicts": lab.submit_block(blk2, names)}
    d["rejected_everywhere"] = all(v["result"] != "accepted" and v["tip"] != blk2["hash"] for v in d["verdicts"].values())
    report["double_sale"] = d

    # Split: 1-sat shave with a fresh witness, in a correctly signed block.
    shave = k1.spend(second_txid, vouts[1], i125, own, att, amounts={"long": 1_074, "short": 551})
    tip_before = lab.cli("miner", "getbestblockhash")
    blk3 = lab.mine_with([shave.hex()])
    verdicts = lab.submit_block(blk3, names)
    tips = {n: next((tp for tp in lab.rpc(n, "getchaintips") if tp["hash"] == blk3["hash"]), None) for n in names}
    s = {"txid": shave.txid, "outputs": [o.value for o in shave.vout], "block": blk3["hash"],
         "signed": blk3["signed_complete"], "tip_before": tip_before, "verdicts": verdicts, "chaintips": tips,
         "legacy_forked": verdicts["legacy"]["tip"] == blk3["hash"],
         "patched_rejected": all((tips[n] is None or tips[n]["status"] == "invalid") and verdicts[n]["tip"] != blk3["hash"]
                                 for n in ("miner", "observer"))}
    if s["legacy_forked"]:
        lab.rpc("legacy", "invalidateblock", blk3["hash"])
    s["legacy_restored_to"] = lab.cli("legacy", "getbestblockhash")
    report["split"] = s
    report["agreement"] = lab.agree()["agree"]
    path = lab.receipt(report)
    ok = (t["accepted_by_all"] and d["rejected_everywhere"] and s["legacy_forked"] and s["patched_rejected"]
          and report["agreement"])
    print(json.dumps({"receipt": str(path), "ok": ok, "transfer_txid": settle.txid, "transfer_block": blk["hash"],
                      "transfer_vsize": settle.vsize, "transfer_mempool": {n: v.get("reject-reason") for n, v in report["transfer_mempool"].items()},
                      "double_sale": {n: v["result"][:60] for n, v in d["verdicts"].items()},
                      "split_block": blk3["hash"], "split": {n: (tips[n] or {}).get("status") for n in names},
                      "agreement": report["agreement"]}, indent=2))
    if not ok:
        raise SystemExit("SHZ-K1 Signet expectations not met")


if __name__ == "__main__":
    main()
