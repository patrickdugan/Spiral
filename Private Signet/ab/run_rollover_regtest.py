#!/usr/bin/env python3
"""Block-consensus proof of post-confirmation DLC ownership exclusion on stock regtest.

Two independent stock Bitcoin Core validators receive identical raw blocks.
The OLD CET is first accepted in a candidate block, which is invalidated
to restore the original UTXO. After an Alice+Bob authorized re-funding to
Carol+Bob confirms, that same old CET is rejected in a newly constructed
candidate block. The buyer's new adaptor CET is accepted in another block.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from arms import ArmA, FUNDING_SATS, Parties, p2tr_key_spk  # noqa: E402
from nodes import Faucet, Node, build_block, coinbase_coin, submit_all  # noqa: E402
from rollover import RolledDLC, former_holder_attack, make_rollover  # noqa: E402
from txlib import TxOut  # noqa: E402


def tips(nodes):
    return {node.name: node.rpc("getbestblockhash") for node in nodes}


def candidate(nodes, tx, label: bytes):
    raw, block_hash = build_block(nodes[0], [tx], label)
    observations = submit_all(nodes, raw)
    return block_hash, observations


def assert_verdict(nodes, tx, label: bytes, accepted: bool, *, undo: bool = False):
    before = tips(nodes)
    block_hash, result = candidate(nodes, tx, label)
    verdict = {name: entry["result"] == "accepted" for name, entry in result.items()}
    if any(value != accepted for value in verdict.values()):
        raise RuntimeError(f"{label!r} unexpected block consensus verdict: {result}")
    if accepted:
        if any(node.rpc("getbestblockhash") != block_hash for node in nodes):
            raise RuntimeError(f"{label!r} accepted block not at matching tips")
        if undo:
            for node in nodes:
                node.rpc("invalidateblock", block_hash)
    if not accepted or undo:
        if tips(nodes) != before:
            raise RuntimeError(f"{label!r} altered chain despite rejected/invalidated block")
    return {"candidate_block": block_hash, "observations": result, "accepted": accepted,
            "undone": undo}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stock", type=Path, required=True, help="stock bitcoind")
    ap.add_argument("--output", type=Path, required=True, help="machine-readable evidence")
    args = ap.parse_args()
    if not args.stock.is_file():
        raise SystemExit(f"Missing binary: {args.stock}")
    home = Path(tempfile.mkdtemp(prefix="spiral-rollover-regtest-"))
    nodes = [Node("old-miner", args.stock, home / "miner"),
             Node("old-observer", args.stock, home / "observer")]
    try:
        for n in nodes:
            n.start()
        lead, follower = nodes
        faucet = Faucet("stock-rollover-faucet-v1")
        mined = lead.rpc("generatetoaddress", 110, faucet.address)
        for bh in mined:
            if follower.rpc("submitblock", lead.rpc("getblock", bh, 0)) is not None:
                raise RuntimeError("Observer rejected regtest funding-prefix block")
        if tips(nodes)["old-miner"] != tips(nodes)["old-observer"]:
            raise RuntimeError("Stock validators differ on base chain")
        p = Parties.fixture("stock-rollover-block-v1")
        original = ArmA(p)
        buyer = RolledDLC(p)
        coin = coinbase_coin(lead, mined[0])
        change = coin["value"] - FUNDING_SATS - 5_000
        fund = faucet.spend(coin, [TxOut(FUNDING_SATS, original.funding_spk),
                                  TxOut(change, faucet.spk)])
        funding_result = assert_verdict(nodes, fund, b"rollover-funding", True)
        attestation = p.oracle.attest("ALICE_WINS")
        old_pre = original.presign_all(fund.txid, 0)
        stale = original.settle(old_pre, "ALICE_WINS", attestation)
        transfer = make_rollover(original, p, fund.txid, 0, buyer)
        new_pre = buyer.presign_all(transfer.txid, 0)
        buyer_cet = buyer.settle(new_pre, "ALICE_WINS", attestation)
        wrong_keys = former_holder_attack(buyer, transfer.txid, 0)

        # Actual consensus acceptance of the old CET before transfer.
        old_before = assert_verdict(nodes, stale, b"old-valid-before", True, undo=True)
        transfer_result = assert_verdict(nodes, transfer, b"transfer-confirm", True)
        old_outs = {node.name: node.rpc("gettxout", fund.txid, 0, False) for node in nodes}
        successor_utxos = {node.name: node.rpc("gettxout", transfer.txid, 0, False)
                           for node in nodes}
        if any(x is not None for x in old_outs.values()):
            raise RuntimeError("Old UTXO not consumed by confirmed transfer")
        if not all(x and x["scriptPubKey"]["hex"] == buyer.funding_spk.hex()
                   and x["confirmations"] >= 1 for x in successor_utxos.values()):
            raise RuntimeError("Fresh buyer UTXO not independently validated")
        old_after = assert_verdict(nodes, stale, b"old-stale-after", False)
        old_key_attack = assert_verdict(nodes, wrong_keys, b"old-keys-on-buyer", False)
        payout_result = assert_verdict(nodes, buyer_cet, b"buyer-new-cet", True)
        payout_utxos = {node.name: node.rpc("gettxout", buyer_cet.txid, 0, False)
                        for node in nodes}
        if not all(x and x["scriptPubKey"]["hex"] == p2tr_key_spk(p.x("carol")).hex()
                   and x["confirmations"] >= 1 for x in payout_utxos.values()):
            raise RuntimeError("Buyer payout not confirmed on independent validators")
        if any(node.rpc("gettxout", transfer.txid, 0, False) is not None for node in nodes):
            raise RuntimeError("Successor DLC remains unspent after buyer CET")

        report = {
            "kind": "stock-regtest-ownership-rollover-consensus",
            "core_versions": {node.name: node.version() for node in nodes},
            "funding": funding_result,
            "funding_txid": fund.txid,
            "old_cet_txid": stale.txid,
            "old_cet_raw": stale.hex(),
            "old_cet_accepted_in_block_before": old_before,
            "rollover_txid": transfer.txid,
            "rollover_raw": transfer.hex(),
            "rollover": transfer_result,
            "rollover_fee_sats": FUNDING_SATS - buyer.funding_sats,
            "old_utxo_after": old_outs,
            "new_utxo_after": successor_utxos,
            "same_old_cet_rejected_in_block_after": old_after,
            "old_owner_keys_rejected_in_block_after": old_key_attack,
            "buyer_cet_txid": buyer_cet.txid,
            "buyer_cet_raw": buyer_cet.hex(),
            "buyer_payout": payout_result,
            "buyer_payout_utxo": payout_utxos,
            "old_signatures_still_cryptographically_valid": True,
            "buyer_exclusive_on_confirmed_chain": True,
            "limitation": (
                "On-chain cooperative rollover only. The seller can race "
                "before confirmation and a reorg may revive the old funding "
                "outpoint. Buyer payment is not atomically enforced."
            ),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": "PASS",
            "output": str(args.output),
            "original_cet": stale.txid,
            "old_cet_before": old_before["observations"],
            "old_cet_after": old_after["observations"],
            "buyer_cet": buyer_cet.txid,
            "payout_block": payout_result["candidate_block"],
        }, indent=2))
    finally:
        for node in nodes:
            node.stop()
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
