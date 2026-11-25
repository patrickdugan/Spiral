"""Check V3 funding inclusion and holder authorization at a pinned pre-broadcast checkpoint."""

import argparse
import hashlib
import json
from pathlib import Path

from .domain import Refused, canonical, digest, hash32, positive
from .protected_accounting import bound_claim
from .protected_payout_evidence import (
    MAX_HEADERS, _leaves, _merkle_root, _pinned_headers, _raw, _transaction, _verify_holder_witness,
    _v3_amounts_and_script, _v3_plan,
)
from .protected_reserve import GENESIS
from .protected_withdrawal import STATEMENT
from .verifier import read_bounded


SCHEMA = "proof-grove/protected-withdrawal-bitcoin-evidence/v1"


def capture(rpc, bundle, admission, signed_tx):
    """Record the funding transaction and header prefix while the admitted tip remains active."""
    statement = admission["statement"]
    anchor = statement["anchor"]
    funding = statement["reserve"]
    if not 0 <= anchor["height"] - funding["height"] < MAX_HEADERS:
        raise ValueError("invalid protected withdrawal header interval")
    blocks = [rpc("getblockhash", [height]) for height in range(funding["height"], anchor["height"] + 1)]
    if (blocks[0], blocks[-1]) != (funding["block"], anchor["hash"]):
        raise ValueError("withdrawal funding or checkpoint left the active chain")
    headers = [rpc("getblockheader", [block, False]) for block in blocks]
    block = rpc("getblock", [funding["block"], 1])
    raw = rpc("getrawtransaction", [funding["txid"], False, funding["block"]])
    leaves = block["tx"]
    _leaves(leaves)
    if (block["hash"], block["height"], block["nTx"], rpc("getblockhash", [anchor["height"]])) != (
            funding["block"], funding["height"], len(leaves), anchor["hash"]):
        raise ValueError("withdrawal chain changed during capture")
    return {"schema": SCHEMA, "bundle": bundle, "admission": admission, "headers": headers,
            "funding_txids": leaves, "funding_tx": raw, "signed_tx": signed_tx}


def verify(evidence, bundle_id, withdrawal_id, anchor_height, anchor_hash, *, openssl="openssl"):
    """Verify a funding inclusion and the signed candidate under externally supplied pins."""
    hash32(withdrawal_id, "withdrawal_id")
    admission = evidence["admission"]
    statement = admission["statement"]
    if (evidence.get("schema") != SCHEMA or admission.get("bundle_id") != bundle_id
            or admission.get("kind") != "authorized-regtest-withdrawal"
            or digest(admission) != withdrawal_id or statement.get("schema") != STATEMENT
            or statement.get("genesis") != GENESIS
            or canonical(statement.get("anchor")) != canonical({"hash": anchor_hash, "height": anchor_height})):
        raise ValueError("withdrawal admission differs from the observer pins")

    bundle = evidence["bundle"]
    plan = _v3_plan(bundle, bundle_id)
    headers, funding_block, funding_height = _pinned_headers(evidence["headers"], anchor_height, anchor_hash, 1)
    delay = positive(plan["delay_blocks"], "delay_blocks", 65535)
    earliest = funding_height + delay
    if earliest > anchor_height + 1:
        raise ValueError("withdrawal CSV matures after the next block")
    reserve, amount, fee, destination, funding_script = _v3_amounts_and_script(plan, delay)
    funding = _transaction(evidence["funding_tx"])
    outpoint = bundle["funding"]
    vout = outpoint["vout"]
    txids = evidence["funding_txids"]
    leaves = _leaves(txids)
    if (outpoint["block"] != funding_block or funding.txid != outpoint["txid"] or funding.txid not in txids[1:]
            or _merkle_root(leaves) != headers[0][36:68] or type(vout) is not int or not 0 <= vout < len(funding.outputs)
            or funding.outputs[vout] != (reserve, funding_script)):
        raise ValueError("withdrawal funding output is outside the pinned header or has different terms")

    claim = bound_claim((funding.txid, vout))
    expected_funding = outpoint | {"height": funding_height, "sats": reserve, "script": funding_script.hex()}
    if (canonical(statement.get("reserve")) != canonical(expected_funding) or statement.get("claim_id") != claim
            or statement.get("holder_pubkey") != plan["holder_pubkey"]):
        raise ValueError("withdrawal admission differs from the funded claim")
    signed = evidence["signed_tx"]
    tx = _transaction(signed)
    expected_payout = {"txid": tx.txid, "wtxid": tx.wtxid, "signed_tx_sha256": hashlib.sha256(_raw(signed, 1024)).hexdigest(),
                       "script": destination.hex(), "sats": amount, "fee_sats": fee, "change_sats": 0,
                       "sequence": delay, "earliest_height": earliest}
    if canonical(statement.get("withdrawal")) != canonical(expected_payout) or tx.outputs != [(amount, destination)]:
        raise ValueError("signed withdrawal differs from the pinned beneficiary, values or transaction")
    previous = bytes.fromhex(funding.txid)[::-1] + vout.to_bytes(4, "little")
    _verify_holder_witness(tx, previous, plan, openssl)
    return {"schema": "proof-grove/protected-withdrawal-bitcoin-verification/v1", "network": "regtest",
            "bundle_id": bundle_id, "withdrawal_id": withdrawal_id, "claim_id": claim,
            "anchor": statement["anchor"], "reserve": expected_funding, "withdrawal": expected_payout,
            "holder_signature_verified": True, "funding_inclusion_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--withdrawal-id", required=True)
    parser.add_argument("--anchor-height", type=int, required=True)
    parser.add_argument("--anchor-hash", required=True)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args()
    try:
        evidence = json.loads(read_bounded(args.evidence, 256 * 1024))
        result = verify(evidence, args.bundle_id, args.withdrawal_id, args.anchor_height, args.anchor_hash, openssl=args.openssl)
    except (Refused, KeyError, TypeError, ValueError, OSError) as error:
        parser.exit(1, f"withdrawal evidence refused: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
