#!/usr/bin/env python3
"""Arm A on the private Signet: a vanilla adaptor-signature DLC, funded from
the lab wallet, settled with the oracle's attestation, mined by the signed
Signet miner and checked on both nodes. Stock Bitcoin Core consensus.

Run after `lab.py init` and `lab.py mine --blocks 101`, with the same
SPIRAL_SIGNET_HOME / SIGNET_MINER / BITCOIN_CLI environment.
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

import secp  # noqa: E402
from arms import FUNDING_SATS, OUTCOMES, PAYOUT_SATS, ArmA, Parties  # noqa: E402
from txlib import spk_address  # noqa: E402


def main() -> None:
    state = lab.read_state()
    p = Parties.fixture("signet-dlc-v1")
    arm = ArmA(p)
    address = spk_address("tb", arm.funding_spk)
    announcement = {"oracle_P": p.oracle.P.hex(), "oracle_R": p.oracle.R.hex(),
                    "outcomes": {m: secp.xonly(p.oracle.attestation_point(m)).hex() for m in OUTCOMES}}
    funding_txid = lab.cli("miner", "sendtoaddress", address, f"{FUNDING_SATS / 1e8:.8f}", wallet="funds")
    funding = lab.rpc("miner", "getrawtransaction", funding_txid, "1")
    vout = next(o["n"] for o in funding["vout"] if o["scriptPubKey"]["hex"] == arm.funding_spk.hex())
    fund_mined = lab.mine(1)
    # Setup is complete only when every CET pre-signature is exchanged; in a
    # real DLC this precedes broadcasting the funding transaction.
    pre = arm.presign_all(funding_txid, vout)
    outcome = "ALICE_WINS"
    attestation = p.oracle.attest(outcome)
    cet = arm.settle(pre, outcome, attestation)
    mempool = lab.rpc("miner", "testmempoolaccept", json.dumps([cet.hex()]))
    observer_mempool = lab.rpc("observer", "testmempoolaccept", json.dumps([cet.hex()]))
    sent = lab.cli("miner", "sendrawtransaction", cet.hex())
    settle_mined = lab.mine(1)
    block = lab.rpc("miner", "getrawtransaction", sent, "1", settle_mined["tip"])["blockhash"]
    utxo = {n: lab.rpc(n, "gettxout", sent, "0", "false") for n in ("miner", "observer")}
    spent = {n: lab.rpc(n, "gettxout", funding_txid, str(vout), "false") for n in ("miner", "observer")}
    entry = {
        "kind": "signet-vanilla-dlc", "challenge": state["challenge"], "genesis": state["genesis_hash"],
        "arm": arm.name, "announcement": announcement, "funding_address": address,
        "funding_txid": funding_txid, "funding_vout": vout, "funding_raw": funding["hex"],
        "funding_block": fund_mined["tip"], "outcome": outcome,
        "attestation": attestation.to_bytes(32, "big").hex(),
        "cet_txid": cet.txid, "cet_raw": cet.hex(), "cet_weight": cet.weight, "cet_vsize": cet.vsize,
        "cet_witness_bytes": sum(len(w) for w in cet.vin[0].witness),
        "payout_sats": PAYOUT_SATS, "fee_sats": FUNDING_SATS - PAYOUT_SATS,
        "testmempoolaccept": {"miner": mempool, "observer": observer_mempool},
        "settlement_block": block, "settlement_height": settle_mined["height"],
        "payout_utxo": utxo, "funding_spent_on_both": all(v is None for v in spent.values()),
    }
    entry["confirmed_on_both"] = all(u is not None and u["confirmations"] >= 1 for u in utxo.values())
    path = lab.receipt(entry)
    print(json.dumps({"receipt": str(path), "funding": funding_txid, "cet": cet.txid,
                      "settlement_block": block, "confirmed_on_both": entry["confirmed_on_both"],
                      "mempool": mempool[0].get("allowed")}, indent=2))
    if not entry["confirmed_on_both"] or not entry["funding_spent_on_both"]:
        raise SystemExit("settlement not confirmed on both nodes")


if __name__ == "__main__":
    main()
