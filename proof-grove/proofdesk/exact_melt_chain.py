"""Audit the archived Cairo payout's exact witness and pinned Core regtest chain."""

from dataclasses import replace
import hashlib

from .domain import Refused, hash32
from .protected_chain_archive import MAX_BLOCKS
from .protected_payout_evidence import (
    CHAIN_SCHEMA, _hash256, _p2wsh_sighash_all, _raw, _transaction, _verify_inclusion, _verify_signature, capture,
)
from .protected_reserve import GENESIS, HEX, _chain, _sats, _stable_tip


WITNESS_CONTEXT_SCHEMA = "proof-grove/exact-melt-witness-context/v1"


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


def _opening(receipt, expected):
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

    return {"funding": {"txid": funding_txid, "height": funding_height, "outpoint_vout": vout,
                        "amount_sats": reserve_sats, "script": funding_script},
            "payout": {"txid": payout_txid, "height": payout_height, "wtxid": payout_wtxid,
                       "amount_sats": payout_sats, "script": payout_script},
            "wallet_melt_commitment": melt_commitment, "relative_delay_blocks": delay,
            "fee_sats": fee_sats, "change_sats": 0}


def audit_holder_transaction(arguments, receipt, expected, openssl):
    """Open the STARK's exact payout wtxid and independently check its holder signature."""
    opening = _opening(receipt, expected)
    prevout, paid = opening["funding"], opening["payout"]
    if len(arguments) < 18 or arguments[:15] != expected[4:19]:
        raise ValueError("Cairo transaction arguments differ from the public statement")
    tx = _transaction(_script(arguments[15:], arguments[15]))
    previous = bytes.fromhex(prevout["txid"])[::-1] + prevout["outpoint_vout"].to_bytes(4, "little")
    delay = opening["relative_delay_blocks"]
    sequence = delay.to_bytes(4, "little")
    reserve, amount, destination = prevout["amount_sats"], paid["amount_sats"], bytes.fromhex(paid["script"])
    if ((tx.txid, tx.wtxid) != (paid["txid"], paid["wtxid"])
            or tx.version != b"\x02\0\0\0" or tx.locktime != bytes(4)
            or tx.inputs != [(previous, b"", sequence)] or tx.outputs != [(amount, destination)]
            or len(tx.witnesses) != 1 or len(tx.witnesses[0]) != 3):
        raise ValueError("archived holder transaction does not open the Cairo payout")
    branch, signature, script = tx.witnesses[0]
    holder, mint = script[1:34], script[37:70]
    if (branch or len(signature) < 2 or signature[-1] != 1 or delay != 6
            or len(holder) != 33 or len(mint) != 33 or holder[0] not in (2, 3) or mint[0] not in (2, 3)
            or script != b"\x21" + holder + b"\xad\x63\x21" + mint + b"\xac\x67\x56\xb2\x68"
            or b"\x00\x20" + hashlib.sha256(script).digest() != bytes.fromhex(prevout["script"])):
        raise ValueError("archived holder witness differs from the pinned reserve script or delay")

    fields = dict(tx=tx, previous=previous, sequence=sequence, script=script, reserve=reserve)
    sighash = _p2wsh_sighash_all(**fields)
    der = signature[:-1]
    _verify_signature(openssl, holder, der, sighash)
    outputs = tx.output_bytes
    changed_fields = {
        "funding_txid": {"previous": bytes([previous[0] ^ 1]) + previous[1:]},
        "funding_vout": {"previous": previous[:-1] + bytes([previous[-1] ^ 1])},
        "sequence": {"sequence": (delay - 1).to_bytes(4, "little")},
        "reserve_script": {"script": script[:-1] + b"\x61"},
        "reserve_amount": {"reserve": reserve - 1},
        "payout_amount_and_fee": {"tx": replace(tx, output_bytes=(amount - 1).to_bytes(8, "little") + outputs[8:])},
        "beneficiary": {"tx": replace(tx, output_bytes=outputs[:-1] + bytes([outputs[-1] ^ 1]))},
    }
    changes = {name: (_p2wsh_sighash_all(**(fields | fields_changed)), der)
               for name, fields_changed in changed_fields.items()}
    changes["signature"] = (sighash, der[:-1] + bytes([der[-1] ^ 1]))
    for field, (message, candidate) in changes.items():
        try:
            _verify_signature(openssl, holder, candidate, message)
        except ValueError:
            continue
        raise ValueError(f"holder signature accepted a changed {field}")
    return {"schema": "proof-grove/exact-melt-holder-audit/v1", "statement_sha256": receipt["statement_sha256"],
            **opening, "holder_pubkey": holder.hex(), "bip143_sighash_all": sighash.hex(),
            "holder_signature_verified": True, "signature_mutations_rejected": list(changes)}


def observe(core, receipt, expected, anchor_height, anchor_hash):
    """Check the exact verified statement against an independently pinned active checkpoint."""
    opening = _opening(receipt, expected)
    prevout, paid = opening["funding"], opening["payout"]
    delay = opening["relative_delay_blocks"]
    before = _chain(core)
    hash32(anchor_hash, "exact_melt_chain_anchor")
    if (type(anchor_height) is not int or not 0 < prevout["height"] < paid["height"] <= anchor_height <= before["blocks"]
            or core.rpc("getblockhash", [anchor_height]) != anchor_hash):
        raise Refused("exact_melt_chain_anchor_mismatch")

    funding, funding_evidence = _mined(core, prevout["height"], prevout["txid"])
    _match_output(funding.get("vout", []), prevout["outpoint_vout"], prevout["amount_sats"], prevout["script"])
    payout, payout_evidence = _mined(core, paid["height"], paid["txid"])
    inputs, outputs = payout.get("vin", []), payout.get("vout", [])
    if (payout.get("hash") != paid["wtxid"] or _bitcoin_hash(bytes.fromhex(payout["hex"])) != paid["wtxid"]
            or payout.get("version") != 2 or payout.get("locktime") != 0
            or len(inputs) != 1 or len(outputs) != 1 or inputs[0].get("txid") != prevout["txid"]
            or inputs[0].get("vout") != prevout["outpoint_vout"] or inputs[0].get("sequence") != delay):
        raise Refused("exact_melt_payout_mismatch")
    _match_output(outputs, 0, paid["amount_sats"], paid["script"])
    _stable_tip(core, before)
    return {
        "schema": "proof-grove/exact-melt-chain-observation/v1",
        "evidence_level": "independent-bitcoin-core-regtest",
        "network": "regtest", "genesis": GENESIS, "statement_sha256": receipt["statement_sha256"],
        **opening,
        "anchor_height": anchor_height, "anchor_hash": anchor_hash,
        "observed_tip_height": before["blocks"], "observed_tip_hash": before["bestblockhash"],
        "funding": funding_evidence | prevout,
        "payout": payout_evidence | paid,
    }


def verify_witness_context(context, receipt, expected, anchor_height, anchor_hash):
    """Check raw transactions, regtest headers and the BIP141 witness commitment offline."""
    opening = _opening(receipt, expected)
    prevout, paid = opening["funding"], opening["payout"]
    if (context.get("schema"), context.get("network"), context.get("genesis"), context.get("statement_sha256"),
            context.get("anchor_height"), context.get("anchor_hash")) != (
            WITNESS_CONTEXT_SCHEMA, "regtest", GENESIS, receipt["statement_sha256"], anchor_height, anchor_hash):
        raise ValueError("exact Cashu chain context differs from the independent pins")
    hash32(anchor_hash, "exact_melt_chain_anchor")
    if type(anchor_height) is not int or not 0 < prevout["height"] < paid["height"] <= anchor_height <= MAX_BLOCKS:
        raise ValueError("invalid exact Cashu chain context heights")
    for name, field in opening.items():
        if name in ("funding", "payout"):
            if any(context[name].get(key) != value for key, value in field.items()):
                raise ValueError(f"exact Cashu {name} metadata differs from the pinned statement")
        elif context.get(name) != field:
            raise ValueError(f"exact Cashu {name} differs from the pinned statement")
    witness = context["bitcoin_chain_evidence"]
    raw_headers = witness["headers"]
    if witness.get("schema") != CHAIN_SCHEMA or not isinstance(raw_headers, list) or len(raw_headers) != anchor_height + 1:
        raise ValueError("invalid exact Cashu regtest header chain length")
    headers = [_raw(header, 80, 80) for header in raw_headers]
    hashes = [_hash256(header) for header in headers]
    if (hashes[0][::-1].hex() != GENESIS or hashes[-1][::-1].hex() != anchor_hash
            or any(header[4:36] != parent for header, parent in zip(headers[1:], hashes))):
        raise ValueError("exact Cashu headers do not connect regtest genesis to the pinned checkpoint")
    for entry in (context["funding"], context["payout"]):
        if hashes[entry["height"]][::-1].hex() != entry["block"]:
            raise ValueError("exact Cashu transaction block differs from its pinned header")
    funding = _transaction(context["funding"]["raw_transaction"])
    payout = _transaction(context["payout"]["raw_transaction"])
    vout = prevout["outpoint_vout"]
    if (funding.txid != prevout["txid"] or not 0 <= vout < len(funding.outputs)
            or funding.outputs[vout] != (prevout["amount_sats"], bytes.fromhex(prevout["script"]))):
        raise ValueError("exact Cashu funding transaction differs from the pinned reserve")
    previous = bytes.fromhex(prevout["txid"])[::-1] + vout.to_bytes(4, "little")
    sequence = opening["relative_delay_blocks"].to_bytes(4, "little")
    if ((payout.txid, payout.wtxid) != (paid["txid"], paid["wtxid"])
            or payout.version != b"\x02\0\0\0" or payout.locktime != bytes(4)
            or payout.inputs != [(previous, b"", sequence)]
            or payout.outputs != [(paid["amount_sats"], bytes.fromhex(paid["script"]))]):
        raise ValueError("exact Cashu payout bytes differ from the pinned withdrawal")
    _verify_inclusion(witness, headers[prevout["height"]:], funding, payout,
                      payout_index=paid["height"] - prevout["height"])
    return {"funding_txid": funding.txid, "payout_txid": payout.txid, "payout_wtxid": payout.wtxid,
            "anchor_height": anchor_height, "anchor_hash": anchor_hash, "witness_inclusion_verified": True}


def observe_witness_context(core, receipt, expected, anchor_height, anchor_hash):
    context = observe(core, receipt, expected, anchor_height, anchor_hash)
    if anchor_height > MAX_BLOCKS:
        raise ValueError("exact Cashu witness context exceeds the regtest archive height bound")
    funding, payout = context["funding"], context["payout"]
    evidence = capture(core.rpc, funding["height"], payout["height"], funding["block"], payout["block"])

    def headers(start, end):
        for height in range(start, end):
            block = core.rpc("getblockhash", [height])
            yield core.rpc("getblockheader", [block, False])

    evidence["headers"] = [*headers(0, funding["height"]), *evidence["headers"],
                           *headers(payout["height"] + 1, anchor_height + 1)]
    context.update(schema=WITNESS_CONTEXT_SCHEMA, bitcoin_chain_evidence=evidence)
    context["witness_verification"] = verify_witness_context(context, receipt, expected, anchor_height, anchor_hash)
    _stable_tip(core, {"blocks": context["observed_tip_height"], "bestblockhash": context["observed_tip_hash"]})
    return context
