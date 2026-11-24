"""Combine the archived Cairo payout statement with a pinned Core regtest chain."""

import hashlib

from .domain import Refused, hash32
from .protected_reserve import GENESIS, HEX, _chain, _sats, _stable_tip


def _bitcoin_hash(raw):
    return hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex()


def _word_pair(low, high):
    if not 0 <= low < 2**128 or not 0 <= high < 2**128:
        raise Refused("exact_melt_invalid_hash_words")
    return (low | high << 128).to_bytes(32, "big")


def _wire_hash(low, high):
    return _word_pair(low, high)[::-1].hex()


def _script(words, full_words):
    if (len(words) != full_words + 3 or words[0] != full_words
            or not 0 <= words[-1] < 31 or words[-2] >= 1 << (8 * words[-1])
            or any(word >= 2**248 for word in words[1:-2])):
        raise Refused("exact_melt_invalid_script_words")
    script = b"".join(word.to_bytes(31, "big") for word in words[1:-2])
    return (script + words[-2].to_bytes(words[-1], "big")).hex()


def _mined(core, height, txid):
    block = hash32(core.rpc("getblockhash", [height]), "exact_melt_block")
    tx = core.rpc("getrawtransaction", [txid, True, block])
    if (tx.get("txid") != txid or tx.get("blockhash") != block
            or tx.get("in_active_chain") is not True
            or not isinstance(tx.get("hex"), str) or not HEX.fullmatch(tx["hex"])):
        raise Refused("exact_melt_transaction_not_active")
    proof = core.rpc("gettxoutproof", [[txid], block])
    if not isinstance(proof, str) or len(proof) <= 160 or not HEX.fullmatch(proof):
        raise Refused("exact_melt_invalid_inclusion")
    header = bytes.fromhex(proof[:160])
    if _bitcoin_hash(header) != block or core.rpc("verifytxoutproof", [proof]) != [txid]:
        raise Refused("exact_melt_invalid_inclusion")
    return tx, {"txid": txid, "block": block, "height": height, "txoutproof": proof,
                "raw_transaction": tx["hex"]}


def _match_output(outputs, index, sats, script):
    if (not 0 <= index < len(outputs) or outputs[index].get("n") != index
            or _sats(outputs[index].get("value")) != sats
            or outputs[index].get("scriptPubKey", {}).get("hex") != script):
        raise Refused("exact_melt_output_mismatch")


def observe(core, receipt, expected, anchor_height, anchor_hash):
    """Check the exact verified statement against an independently pinned active checkpoint."""
    marker = int.from_bytes(b"PROOFDESK_CSV_REDEEM_V1", "big")
    if len(expected) != 24 or expected[3] != marker or receipt["network"] != "regtest":
        raise Refused("exact_melt_invalid_statement")
    words = expected[3:]
    funding_txid = _wire_hash(*words[1:3])
    vout, reserve_sats = words[3:5]
    funding_script = _script(words[5:9], 1)
    funding_height, payout_height = words[9:11]
    melt_commitment = _word_pair(*words[11:13]).hex()
    payout_script = _script(words[13:16], 0)
    payout_sats = words[16]
    payout_txid = _wire_hash(*words[17:19])
    payout_wtxid = _wire_hash(*words[19:21])
    delay = receipt["relative_delay_blocks"]
    fee_sats = reserve_sats - payout_sats
    if (f"{funding_txid}:{vout}" != receipt["funding_outpoint"]
            or payout_txid != receipt["confirmed_spend"] or payout_wtxid != receipt["confirmed_spend_wtxid"]
            or melt_commitment != receipt["wallet_melt_commitment"]
            or (reserve_sats, payout_sats, fee_sats) != (
                receipt["reserve_sats"], receipt["payout_sats"], receipt["payout_fee_sats"])
            or not 0 < delay <= 65535 or payout_height - funding_height < delay):
        raise Refused("exact_melt_receipt_mismatch")

    before = _chain(core)
    hash32(anchor_hash, "exact_melt_chain_anchor")
    if (type(anchor_height) is not int or not 0 < funding_height < payout_height <= anchor_height <= before["blocks"]
            or core.rpc("getblockhash", [anchor_height]) != anchor_hash):
        raise Refused("exact_melt_chain_anchor_mismatch")

    funding, funding_evidence = _mined(core, funding_height, funding_txid)
    _match_output(funding.get("vout", []), vout, reserve_sats, funding_script)
    payout, payout_evidence = _mined(core, payout_height, payout_txid)
    inputs, outputs = payout.get("vin", []), payout.get("vout", [])
    if (payout.get("hash") != payout_wtxid or _bitcoin_hash(bytes.fromhex(payout["hex"])) != payout_wtxid
            or payout.get("version") != 2 or payout.get("locktime") != 0
            or len(inputs) != 1 or len(outputs) != 1 or inputs[0].get("txid") != funding_txid
            or inputs[0].get("vout") != vout or inputs[0].get("sequence") != delay):
        raise Refused("exact_melt_payout_mismatch")
    _match_output(outputs, 0, payout_sats, payout_script)
    _stable_tip(core, before)
    return {
        "schema": "proof-grove/exact-melt-chain-observation/v1",
        "evidence_level": "independent-bitcoin-core-regtest",
        "network": "regtest", "genesis": GENESIS, "statement_sha256": receipt["statement_sha256"],
        "wallet_melt_commitment": melt_commitment,
        "anchor_height": anchor_height, "anchor_hash": anchor_hash,
        "observed_tip_height": before["blocks"], "observed_tip_hash": before["bestblockhash"],
        "funding": funding_evidence | {"outpoint_vout": vout, "amount_sats": reserve_sats, "script": funding_script},
        "payout": payout_evidence | {"wtxid": payout_wtxid, "amount_sats": payout_sats, "script": payout_script},
        "relative_delay_blocks": delay, "change_sats": 0, "fee_sats": fee_sats,
    }
