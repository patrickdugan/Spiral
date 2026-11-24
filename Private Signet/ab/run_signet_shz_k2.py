#!/usr/bin/env python3
"""SHZ-K2 on a PATCHED custom Signet (Keyless + Signet + CSFS patches) with a
stock legacy node. Fixture: run_shz_k2_regtest.fixture (FROST 3-of-5).

  fund      K2 trade 1 (alice/bob), the netted 3-trade book (alice/bob/carol)
            and a second K2 trade 1 (carol/mallory) for the refund
  transfer  alice's long moves to carol on-chain, signed only by alice
  double    alice's second sale (same coin to mallory) in a signed block:
            rejected everywhere, the coin is spent
  split     alice settling the transferred coin as if she still owned it, in
            a signed block: invalid on both patched nodes, active on the
            legacy node, then invalidated there
  settle    the new coin settles at $125,000 (FROST quorum 2,4,5): carol
            1,075 / bob 550
  book      the book settles in one transaction: alice 1,475 / bob 1,250 /
            carol 825
  refund    144 fast-timestamp blocks, then the keyless refund pays the
            margins to the third coin's owners
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

from run_shz_k2_regtest import PRICE, SETTLE_FEE, TRADE1, TRANSFER_FEE, TRIANGLE, fixture  # noqa: E402
from shz_k2 import Coin  # noqa: E402
from txlib import spk_address  # noqa: E402


def confirm(txids: list[str], tries: int = 4) -> dict:
    """Mine until the funds wallet sees every txid confirmed (getblocktemplate
    may reuse a cached template for up to 5 s while the tip is unchanged)."""
    mined = []
    for _ in range(tries):
        mined.append(lab.mine(1)["tip"])
        info = {t: lab.rpc("miner", "gettransaction", t, wallet="funds") for t in txids}
        if all(i.get("blockhash") for i in info.values()):
            return {"blocks": {t: i["blockhash"] for t, i in info.items()}, "mined": mined}
    raise SystemExit(f"not confirmed after {tries} blocks: {txids}")


def utxos(txid: str, count: int, names: list[str]) -> dict:
    return {n: [lab.rpc(n, "gettxout", txid, str(i), "false") for i in range(count)] for n in names}


def main() -> None:
    state = lab.read_state()
    names = lab.nodes()
    if "legacy" not in names or "-keylessresearch=1" not in state.get("node_args", []):
        raise SystemExit("needs a lab initialised with the patched build, -keylessresearch=1 and BITCOIND_LEGACY")
    p, oracle, k2, bk = fixture()
    x = p.x
    A, B, C, M = x("alice"), x("bob"), x("carol"), x("mallory")
    v_single = TRADE1.total_collateral_sats + SETTLE_FEE + 2 * TRANSFER_FEE
    v_book = sum(t.spec.total_collateral_sats for t in TRIANGLE) + SETTLE_FEE + 2 * TRANSFER_FEE
    spks = {"single": k2.spk([A, B]), "book": bk.spk([A, B, C]), "refund": k2.spk([C, M])}
    values = {"single": v_single, "book": v_book, "refund": v_single}
    outputs = {spk_address("tb", spks[k]): f"{values[k] / 1e8:.8f}" for k in spks}
    fund_txid = lab.cli("miner", "sendmany", "", json.dumps(outputs), wallet="funds")
    fund = confirm([fund_txid])
    raw = lab.rpc("miner", "getrawtransaction", fund_txid, "1", fund["blocks"][fund_txid])
    vout = {k: next(o["n"] for o in raw["vout"] if o["scriptPubKey"]["hex"] == spks[k].hex()) for k in spks}
    c0 = Coin(fund_txid, vout["single"], v_single, [A, B])
    cb = Coin(fund_txid, vout["book"], v_book, [A, B, C])
    cr = Coin(fund_txid, vout["refund"], v_single, [C, M])
    report = {"kind": "signet-shz-k2", "challenge": state["challenge"], "node_args": state["node_args"],
              "versions": {n: lab.rpc(n, "getnetworkinfo")["subversion"] for n in names},
              "oracle": oracle.announcement(), "single": k2.summary(), "book": bk.summary(),
              "funding": {"txid": fund_txid, "vouts": vout, "values": values, **fund,
                          "addresses": {k: spk_address("tb", s) for k, s in spks.items()}}}

    # Transfer: alice -> carol, on-chain, no Bob.
    to_carol, c1 = k2.transfer(c0, "long", C, p.alice)
    report["transfer_mempool"] = {n: lab.rpc(n, "testmempoolaccept", json.dumps([to_carol.hex()]))[0]
                                  for n in ("miner", "legacy")}
    blk = lab.mine_with([to_carol.hex()])
    t = {"txid": to_carol.txid, "vsize": to_carol.vsize, "value": c1.value, "block": blk["hash"],
         "submit": lab.submit_block(blk, ["miner"])}
    t["synced"] = lab.wait_synced()
    t["utxos"] = utxos(to_carol.txid, 1, names)
    t["accepted_by_all"] = all(u is not None for us in t["utxos"].values() for u in us)
    report["transfer"] = t

    # Second sale of the same coin.
    dbl = k2.transfer(c0, "long", M, p.alice)[0]
    blk2 = lab.mine_with([dbl.hex()])
    d = {"txid": dbl.txid, "block": blk2["hash"], "verdicts": lab.submit_block(blk2, names)}
    d["rejected_everywhere"] = all(v["result"] != "accepted" and v["tip"] != blk2["hash"] for v in d["verdicts"].values())
    report["double_sale"] = d

    # Split: the former owner settles the transferred coin to herself.
    att = oracle.attest(PRICE, [2, 4, 5])
    i125 = k2.index("cet", price=PRICE)
    stale = k2.payout(c1, i125, att, claimed_keys=[A, B])
    blk3 = lab.mine_with([stale.hex()])
    verdicts = lab.submit_block(blk3, names)
    tips = {n: next((tp for tp in lab.rpc(n, "getchaintips") if tp["hash"] == blk3["hash"]), None) for n in names}
    s = {"txid": stale.txid, "block": blk3["hash"], "verdicts": verdicts, "chaintips": tips,
         "legacy_forked": verdicts["legacy"]["tip"] == blk3["hash"],
         "patched_rejected": all((tips[n] is None or tips[n]["status"] == "invalid") and verdicts[n]["tip"] != blk3["hash"]
                                 for n in ("miner", "observer"))}
    if s["legacy_forked"]:
        lab.rpc("legacy", "invalidateblock", blk3["hash"])
    s["legacy_restored_to"] = lab.cli("legacy", "getbestblockhash")
    report["split"] = s

    # Settle the transferred coin and the book.
    for key, contract, coin, label in (("settle", k2, c1, "carol/bob"), ("book", bk, cb, "alice/bob/carol")):
        i = contract.index("cet", price=PRICE)
        tx = contract.payout(coin, i, att)
        b = lab.mine_with([tx.hex()])
        r = {"txid": tx.txid, "vsize": tx.vsize, "payees": label, "outputs": [o.value for o in tx.vout],
             "block": b["hash"], "submit": lab.submit_block(b, ["miner"])}
        r["synced"] = lab.wait_synced()
        r["utxos"] = utxos(tx.txid, len(tx.vout), names)
        r["accepted_by_all"] = all(u is not None for us in r["utxos"].values() for u in us)
        report[key] = r

    # Refund after the CSV delay, reached with fast timestamps.
    early = k2.payout(cr, k2.index("refund"), [])
    report["refund_early_mempool"] = lab.rpc("miner", "testmempoolaccept", json.dumps([early.hex()]))[0]
    report["csv_blocks"] = {k: lab.mine(k2.refund_csv, fast=True)[k] for k in ("height", "tip")}
    refund = k2.payout(cr, k2.index("refund"), [])
    b = lab.mine_with([refund.hex()])
    r = {"txid": refund.txid, "vsize": refund.vsize, "outputs": [o.value for o in refund.vout], "block": b["hash"],
         "submit": lab.submit_block(b, ["miner"])}
    r["synced"] = lab.wait_synced()
    r["utxos"] = utxos(refund.txid, len(refund.vout), names)
    r["accepted_by_all"] = all(u is not None for us in r["utxos"].values() for u in us)
    report["refund"] = r
    report["agreement"] = lab.agree()["agree"]
    path = lab.receipt(report)
    ok = (t["accepted_by_all"] and d["rejected_everywhere"] and s["legacy_forked"] and s["patched_rejected"]
          and report["settle"]["accepted_by_all"] and report["book"]["accepted_by_all"]
          and report["refund"]["accepted_by_all"] and not report["refund_early_mempool"].get("allowed")
          and report["agreement"])
    print(json.dumps({"receipt": str(path), "ok": ok,
                      "transfer": (to_carol.txid, blk["hash"], to_carol.vsize),
                      "transfer_mempool": {n: v.get("reject-reason") for n, v in report["transfer_mempool"].items()},
                      "double_sale": {n: v["result"][:60] for n, v in d["verdicts"].items()},
                      "split": {n: (tips[n] or {}).get("status") for n in names},
                      "settle": (report["settle"]["txid"], report["settle"]["outputs"]),
                      "book": (report["book"]["txid"], report["book"]["outputs"], report["book"]["vsize"]),
                      "refund_early": report["refund_early_mempool"].get("reject-reason"),
                      "refund": (refund.txid, r["outputs"]), "agreement": report["agreement"]}, indent=2))
    if not ok:
        raise SystemExit("SHZ-K2 Signet expectations not met")


if __name__ == "__main__":
    main()
