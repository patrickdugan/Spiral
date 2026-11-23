#!/usr/bin/env python3
"""K4 / C1 on a PATCHED custom Signet.

Nodes (from lab.py init with the environment below):
  miner     patched Core, -keylessresearch=1, holds the block-signing key
  observer  patched Core, -keylessresearch=1, independent validation
  legacy    stock Core, old rules, follows the miner

  BITCOIND=<patched bitcoind>  BITCOIN_CLI=<cli>
  SPIRAL_SIGNET_BITCOIND_ARGS=-keylessresearch=1  BITCOIND_LEGACY=<stock bitcoind>

Steps:
  K4  arm B settlement (ALICE_WINS paid to Carol, chosen at settlement) is
      refused by the mempool (non-standard), put into a block by the
      authorized signer through the official miner's genpsbt/solvepsbt, and
      accepted by all three nodes.
  C1  a forbidden arm B spend (stale witness, recipient changed to Mallory)
      in a correctly signed block: both patched nodes reject it, the stock
      node accepts it and forks; the fork is then invalidated on that node.
  K3  a bare TXCOMMIT output is taken by a thief under the new rules too.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("lab", HERE.parent / "lab.py")
lab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lab)

from arms import FUNDING_SATS, ArmB, ArmC, Parties, UnsafeUnconstrained  # noqa: E402
from txlib import spk_address  # noqa: E402


def vout_of(raw: dict, spk: bytes) -> int:
    return next(o["n"] for o in raw["vout"] if o["scriptPubKey"]["hex"] == spk.hex())


def main() -> None:
    state = lab.read_state()
    names = lab.nodes()
    if "legacy" not in names or "-keylessresearch=1" not in state.get("node_args", []):
        raise SystemExit("needs a lab initialised with the patched build, -keylessresearch=1 and BITCOIND_LEGACY")
    p = Parties.fixture("signet-keyless-v1")
    arm = ArmB(p)
    k3 = UnsafeUnconstrained()
    # Arm C needs the build with core/patch_core_csfs.py (SPIRAL_SIGNET_CSFS=1).
    arm_c = ArmC(p) if os.environ.get("SPIRAL_SIGNET_CSFS") == "1" else None
    amount = f"{FUNDING_SATS / 1e8:.8f}"
    outputs = {spk_address("tb", arm.funding_spk): amount}
    k3_addr = spk_address("tb", k3.funding_spk)
    if arm_c:
        outputs[spk_address("tb", arm_c.funding_spk)] = amount
    funding_txid = lab.cli("miner", "sendmany", "", json.dumps(outputs | {k3_addr: amount}), wallet="funds")
    second_txid = lab.cli("miner", "sendtoaddress", spk_address("tb", arm.funding_spk), amount, wallet="funds")
    fund_block = lab.mine(1)
    raw1 = lab.rpc("miner", "getrawtransaction", funding_txid, "1", fund_block["tip"])
    raw2 = lab.rpc("miner", "getrawtransaction", second_txid, "1", fund_block["tip"])
    b_vout, k3_vout = vout_of(raw1, arm.funding_spk), vout_of(raw1, k3.funding_spk)
    b2_vout = vout_of(raw2, arm.funding_spk)
    s_alice = p.oracle.attest("ALICE_WINS")
    report = {"kind": "signet-keyless-k4", "challenge": state["challenge"],
              "node_args": state["node_args"], "versions": {n: lab.rpc(n, "getnetworkinfo")["subversion"] for n in names},
              "funding": {"txid": funding_txid, "arm_b_vout": b_vout, "k3_vout": k3_vout,
                          "second_txid": second_txid, "second_arm_b_vout": b2_vout,
                          "block": fund_block["tip"], "arm_b_address": spk_address("tb", arm.funding_spk),
                          "k3_address": k3_addr},
              "arm_b_leaves": {m: l.hex() for m, l in arm.leaves.items()}}

    # K4: honest settlement selected for Carol.
    honest = arm.settlement(funding_txid, b_vout, "ALICE_WINS", "carol", s_alice)
    report["k4_mempool"] = {n: lab.rpc(n, "testmempoolaccept", json.dumps([honest.hex()]))[0]
                            for n in ("miner", "legacy")}
    block = lab.mine_with([honest.hex()])
    report["k4"] = {"txid": honest.txid, "weight": honest.weight, "block": block["hash"],
                    "signed": block["signed_complete"], "submit": lab.submit_block(block, ["miner"])}
    report["k4"]["synced"] = lab.wait_synced()
    report["k4"]["payout_utxo"] = {n: lab.rpc(n, "gettxout", honest.txid, "0", "false") for n in names}
    report["k4"]["accepted_by_all"] = all(u is not None for u in report["k4"]["payout_utxo"].values())

    # C1: forbidden spend in a correctly signed block.
    base = arm.settlement(second_txid, b2_vout, "ALICE_WINS", "alice", s_alice)
    theft = arm.settlement(second_txid, b2_vout, "ALICE_WINS", "mallory", s_alice, witness_for=base)
    tip_before = lab.cli("miner", "getbestblockhash")
    bad = lab.mine_with([theft.hex()])
    # The miner validates first. Core relays a new block to high-bandwidth
    # compact-block peers before script validation, so the other nodes may
    # already hold it ("duplicate" / "duplicate-invalid"); getchaintips shows
    # each node's verdict on the block either way.
    verdicts = lab.submit_block(bad, ["miner", "observer", "legacy"])
    tips = {n: next((t for t in lab.rpc(n, "getchaintips") if t["hash"] == bad["hash"]), None)
            for n in ("miner", "observer", "legacy")}
    report["c1"] = {"txid": theft.txid, "block": bad["hash"], "signed": bad["signed_complete"],
                    "verdicts": verdicts, "chaintips": tips, "tip_before": tip_before,
                    "legacy_forked": verdicts["legacy"]["tip"] == bad["hash"],
                    "patched_rejected": all(tips[n] is None or tips[n]["status"] == "invalid"
                                            for n in ("miner", "observer"))
                                        and all(verdicts[n]["tip"] != bad["hash"] for n in ("miner", "observer"))}
    if report["c1"]["legacy_forked"]:
        lab.rpc("legacy", "invalidateblock", bad["hash"])
    report["c1"]["legacy_restored_to"] = lab.cli("legacy", "getbestblockhash")

    # K3: a bare TXCOMMIT output is anyone-can-spend under the new rules too.
    steal = k3.steal(funding_txid, k3_vout, p.x("mallory"))
    k3_block = lab.mine_with([steal.hex()])
    report["k3"] = {"txid": steal.txid, "block": k3_block["hash"],
                    "submit": lab.submit_block(k3_block, ["miner"])}
    report["k3"]["synced"] = lab.wait_synced()
    report["k3"]["thief_utxo"] = {n: lab.rpc(n, "gettxout", steal.txid, "0", "false") for n in names}

    # Arm C: owner-assigned transfer and the double-sale race.
    if arm_c:
        c_vout = vout_of(raw1, arm_c.funding_spk)
        osig = arm_c.oracle_sig("ALICE_WINS", s_alice)
        to_carol = arm_c.settlement(funding_txid, c_vout, "ALICE_WINS", "carol", osig,
                                    arm_c.assign("ALICE_WINS", "carol"))
        to_second = arm_c.settlement(funding_txid, c_vout, "ALICE_WINS", "mallory", osig,
                                     arm_c.assign("ALICE_WINS", "mallory"))
        first = lab.mine_with([to_carol.hex()])
        c = {"leaf_bytes": len(arm_c.leaves["ALICE_WINS"]), "transfer_txid": to_carol.txid,
             "transfer_weight": to_carol.weight, "transfer_block": first["hash"],
             "mempool": lab.rpc("miner", "testmempoolaccept", json.dumps([to_carol.hex()]))[0],
             "transfer_submit": lab.submit_block(first, ["miner"])}
        c["synced"] = lab.wait_synced()
        c["carol_utxo"] = {n: lab.rpc(n, "gettxout", to_carol.txid, "0", "false") for n in names}
        second = lab.mine_with([to_second.hex()])
        c["double_sale_txid"] = to_second.txid
        c["double_sale_block"] = second["hash"]
        c["double_sale_verdicts"] = lab.submit_block(second, names)
        c["double_sale_rejected_everywhere"] = all(v["result"] != "accepted" and v["tip"] != second["hash"]
                                                    for v in c["double_sale_verdicts"].values())
        c["accepted_by_all"] = all(u is not None for u in c["carol_utxo"].values())
        report["armC"] = c
    report["agreement"] = lab.agree()["agree"]
    path = lab.receipt(report)
    if arm_c and not (report["armC"]["accepted_by_all"] and report["armC"]["double_sale_rejected_everywhere"]):
        raise SystemExit("arm C expectations not met: " + json.dumps(report["armC"]["double_sale_verdicts"]))
    ok = (report["k4"]["accepted_by_all"] and report["c1"]["patched_rejected"] and report["c1"]["legacy_forked"]
          and all(u is not None for u in report["k3"]["thief_utxo"].values()) and report["agreement"])
    print(json.dumps({"receipt": str(path), "k4_txid": honest.txid, "k4_block": block["hash"],
                      "c1_block": bad["hash"], "c1": {n: v["result"][:80] for n, v in verdicts.items()},
                      "k3_txid": steal.txid, "agreement": report["agreement"], "ok": ok,
                      "armC": ({k: report["armC"][k] for k in ("transfer_txid", "transfer_block",
                                                                "double_sale_rejected_everywhere")}
                               | {"double_sale": {n: v["result"][:70] for n, v in report["armC"]["double_sale_verdicts"].items()}})
                      if arm_c else None}, indent=2))
    if not ok:
        raise SystemExit("K4/C1 expectations not met")


if __name__ == "__main__":
    main()
