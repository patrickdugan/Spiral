#!/usr/bin/env python3
"""On-chain DLC ownership rollover on an isolated, signed Bitcoin Core Signet.

Alice's original adaptor CET is confirmed valid *before* the transfer.
Alice and Bob cooperatively spend the old funding UTXO into Carol/Bob's
fresh Taproot contract. After confirmation, old CETs are rejected because
their input is spent; an Alice+Bob forgery cannot unlock Carol/Bob's leaf.
Carol/Bob's new adaptor CET settles to Carol under the same oracle outcome.

This illustrates a canonical UTXO transition, not off-chain transfer.
There is a pre-confirmation double-spend race and residual reorg risk.
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

from arms import ArmA, FUNDING_SATS, Parties, p2tr_key_spk  # noqa: E402
from rollover import RolledDLC, former_holder_attack, make_rollover  # noqa: E402
from txlib import spk_address  # noqa: E402


def mempool_result(tx, node: str):
    result = lab.rpc(node, "testmempoolaccept", json.dumps([tx.hex()]))
    if not isinstance(result, list) or len(result) != 1:
        raise RuntimeError(f"{node}: unexpected testmempoolaccept response: {result}")
    return result[0]


def observe_mempool(tx):
    return {node: mempool_result(tx, node) for node in ("miner", "observer")}


def all_allowed(response: dict) -> bool:
    return all(item.get("allowed") is True for item in response.values())


def all_rejected(response: dict) -> bool:
    return all(item.get("allowed") is False for item in response.values())


def outputs_on_both(txid: str, vout: int = 0) -> dict:
    return {node: lab.rpc(node, "gettxout", txid, str(vout), "false")
            for node in ("miner", "observer")}


def confirmed_output(outputs: dict, spk: bytes) -> bool:
    return all(u is not None and u["confirmations"] >= 1 and
               u["scriptPubKey"]["hex"] == spk.hex()
               for u in outputs.values())


def main():
    state = lab.read_state()
    p = Parties.fixture("signet-rollover-v1")
    original = ArmA(p)
    successor = RolledDLC(p, holder="carol", counterparty="bob")
    old_addr = spk_address("tb", original.funding_spk)

    funding_txid = lab.cli(
        "miner", "sendtoaddress", old_addr, f"{FUNDING_SATS / 1e8:.8f}", wallet="funds"
    )
    funding = lab.rpc("miner", "getrawtransaction", funding_txid, "1")
    old_vout = next(o["n"] for o in funding["vout"]
                    if o["scriptPubKey"]["hex"] == original.funding_spk.hex())
    # The original signed CET exists before any transfer. The new buyer's
    # adaptor CET can likewise be prepared before the on-chain transition.
    old_presigned = original.presign_all(funding_txid, old_vout)
    outcome = "ALICE_WINS"
    attestation = p.oracle.attest(outcome)
    stale_cet = original.settle(old_presigned, outcome, attestation)
    transfer = make_rollover(original, p, funding_txid, old_vout, successor)
    successor_presigned = successor.presign_all(transfer.txid, 0)
    buyer_cet = successor.settle(successor_presigned, outcome, attestation)
    former_keys = former_holder_attack(successor, transfer.txid, 0)

    funding_block = lab.mine(1)
    old_before = observe_mempool(stale_cet)
    if not all_allowed(old_before):
        raise RuntimeError(f"Original Alice CET was not valid before transfer: {old_before}")

    transfer_before = observe_mempool(transfer)
    if not all_allowed(transfer_before):
        raise RuntimeError(f"Signed rollover failed preflight: {transfer_before}")
    txid = lab.cli("miner", "sendrawtransaction", transfer.hex())
    if txid != transfer.txid:
        raise RuntimeError("Broadcast returned a different rollover transaction ID")
    transfer_block = lab.mine(1)
    old_funding = outputs_on_both(funding_txid, old_vout)
    new_funding = outputs_on_both(transfer.txid, 0)
    if any(v is not None for v in old_funding.values()):
        raise RuntimeError("Original DLC funding output is still unspent")
    if not confirmed_output(new_funding, successor.funding_spk):
        raise RuntimeError("Replacement Carol/Bob funding output not confirmed on both nodes")

    stale_after = observe_mempool(stale_cet)
    former_after = observe_mempool(former_keys)
    if not all_rejected(stale_after):
        raise RuntimeError(f"Superseded Alice CET remained acceptable: {stale_after}")
    if not all_rejected(former_after):
        raise RuntimeError(f"Alice/Bob unauthorized successor spend accepted: {former_after}")
    # Separately exercise real RPC broadcast rejection. A stale CET is a
    # consensus-invalid double spend at this tip, not merely a poor fee bid.
    try:
        stale_broadcast = lab.cli("miner", "sendrawtransaction", stale_cet.hex())
    except RuntimeError as exc:
        stale_broadcast = str(exc)[-1500:]
        stale_broadcast_rejected = True
    else:
        stale_broadcast_rejected = False
    if not stale_broadcast_rejected:
        raise RuntimeError(f"Unexpected old-CET broadcast success: {stale_broadcast}")

    buyer_preflight = observe_mempool(buyer_cet)
    if not all_allowed(buyer_preflight):
        raise RuntimeError(f"Carol CET refused: {buyer_preflight}")
    buyer_txid = lab.cli("miner", "sendrawtransaction", buyer_cet.hex())
    if buyer_txid != buyer_cet.txid:
        raise RuntimeError("Broadcast returned different successor CET transaction ID")
    settlement_block = lab.mine(1)

    old_funding_after = outputs_on_both(funding_txid, old_vout)
    new_funding_after = outputs_on_both(transfer.txid, 0)
    payout = outputs_on_both(buyer_txid)
    expected_payout_spk = p2tr_key_spk(p.x("carol"))
    successful = (
        all_allowed(old_before) and
        all_allowed(transfer_before) and
        all_rejected(stale_after) and
        all_rejected(former_after) and
        stale_broadcast_rejected and
        all_allowed(buyer_preflight) and
        all(v is None for v in old_funding_after.values()) and
        all(v is None for v in new_funding_after.values()) and
        confirmed_output(payout, expected_payout_spk) and
        all(u["value"] == successor.payout_sats / 1e8 for u in payout.values())
    )

    evidence = {
        "kind": "signet-dlc-ownership-rollover",
        "schema": "spiral-rollover/1",
        "status": "confirmed_on_chain" if successful else "failed",
        "network": "isolated-custom-signet-stock-core",
        "challenge": state["challenge"],
        "genesis": state["genesis_hash"],
        "old_owner": "alice",
        "new_owner": "carol",
        "counterparty": "bob",
        "oracle_outcome": outcome,
        "funding_txid": funding_txid,
        "funding_vout": old_vout,
        "funding_block": funding_block["tip"],
        "funding_sats": FUNDING_SATS,
        "old_cet_txid": stale_cet.txid,
        "old_cet_raw": stale_cet.hex(),
        "old_cet_allowed_before_rollover": old_before,
        "rollover_txid": transfer.txid,
        "rollover_raw": transfer.hex(),
        "rollover_weight": transfer.weight,
        "rollover_fee_sats": FUNDING_SATS - successor.funding_sats,
        "rollover_mempool": transfer_before,
        "rollover_block": transfer_block["tip"],
        "rollover_height": transfer_block["height"],
        "replacement_sats": successor.funding_sats,
        "replacement_script_pubkey": successor.funding_spk.hex(),
        "original_funding_spent": old_funding,
        "replacement_funding_utxo": new_funding,
        "old_cet_rejected_after_rollover": stale_after,
        "old_cet_broadcast_rejected": stale_broadcast_rejected,
        "old_cet_broadcast_error": stale_broadcast,
        "former_holder_keys_rejected": former_after,
        "buyer_cet_txid": buyer_txid,
        "buyer_cet_raw": buyer_cet.hex(),
        "buyer_cet_weight": buyer_cet.weight,
        "buyer_cet_vsize": buyer_cet.vsize,
        "buyer_cet_fee_sats": successor.settlement_fee_sats,
        "buyer_cet_mempool": buyer_preflight,
        "buyer_settlement_block": settlement_block["tip"],
        "buyer_settlement_height": settlement_block["height"],
        "buyer_payout_utxo": payout,
        "seller_and_original_funding_remain_spent": all(
            u is None for u in old_funding_after.values()
        ),
        "confirmed_new_owner_payout": successful,
        "security_boundary": (
            "The old funding outpoint is spent on the recorded chain. "
            "Rollover is cooperative and on-chain. An unconfirmed transfer can "
            "lose a double-spend race; a later reorganization can resurrect old "
            "rights. The buyer must wait for a chosen confirmation depth."
        ),
    }
    path = lab.receipt(evidence)
    print(json.dumps({
        "receipt": str(path),
        "funding": funding_txid,
        "rollover": transfer.txid,
        "old_cet_pre": all_allowed(old_before),
        "old_cet_post_rejected": all_rejected(stale_after),
        "alice_bob_attack_rejected": all_rejected(former_after),
        "carol_cet": buyer_txid,
        "buyer_confirmed_on_both": successful,
        "rollover_height": transfer_block["height"],
        "settlement_height": settlement_block["height"],
    }, indent=2))
    if not successful:
        raise SystemExit("Buyer payout or old-holder exclusion proof failed")


if __name__ == "__main__":
    main()
