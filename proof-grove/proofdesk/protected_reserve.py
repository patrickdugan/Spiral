"""Regtest holder tooling for the issuance-funded, single-outpoint profile."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import re

from .adapters import CoreRPCError
from .cashu import compressed_point
from .domain import MAX_SATS, Refused, digest, hash32, positive

PLAN_SCHEMA = "proof-grove/protected-reserve-plan/v1"
BUNDLE_SCHEMA = "proof-grove/protected-reserve-bundle/v1"
GENESIS = "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206"
COOPERATIVE_SEQUENCE = 0xFFFFFFFD
HEX = re.compile(r"(?:[0-9a-f]{2})+")
PLAN_FIELDS = (
    "holder_pubkey", "mint_pubkey", "claim_commitment", "reserve_sats", "payout_address",
    "fee_sats", "delay_blocks", "min_confirmations",
)


def _chain(core) -> dict:
    info = core.rpc("getblockchaininfo", [])
    if (not isinstance(info, dict) or info.get("chain") != "regtest"
            or info.get("initialblockdownload") is not False
            or type(info.get("blocks")) is not int or info["blocks"] < 0):
        raise Refused("protected_regtest_required")
    hash32(info.get("bestblockhash"), "bestblockhash")
    if core.rpc("getblockhash", [0]) != GENESIS:
        raise Refused("protected_wrong_genesis")
    return info


def _stable_tip(core, prior: dict) -> None:
    if _chain(core)["bestblockhash"] != prior["bestblockhash"]:
        raise Refused("chain_changed_retry")


def _script_number(value: int) -> bytes:
    if value <= 16:
        return bytes([0x50 + value])
    payload = value.to_bytes((value.bit_length() + 8) // 8, "little")
    return bytes([len(payload)]) + payload


def _witness_script(holder: str, mint: str, delay: int) -> bytes:
    # <holder> CHECKSIGVERIFY IF <mint> CHECKSIG ELSE <delay> CSV ENDIF
    return (b"\x21" + bytes.fromhex(holder) + b"\xad\x63\x21" + bytes.fromhex(mint)
            + b"\xac\x67" + _script_number(delay) + b"\xb2\x68")


def _address_script(core, address: str) -> str:
    if not isinstance(address, str) or not 14 <= len(address) <= 90:
        raise Refused("protected_invalid_address")
    result = core.rpc("validateaddress", [address])
    script = result.get("scriptPubKey") if isinstance(result, dict) and result.get("isvalid") is True else None
    if not isinstance(script, str) or not HEX.fullmatch(script):
        raise Refused("protected_invalid_address")
    return script


def _sats(value) -> int:
    try:
        scaled = Decimal(str(value)) * 100_000_000
        if scaled.is_finite() and 0 <= scaled <= MAX_SATS and scaled == scaled.to_integral_value():
            return int(scaled)
    except (InvalidOperation, ValueError, TypeError):
        pass
    raise Refused("protected_invalid_amount")


def _plan_body(core, holder_pubkey, mint_pubkey, claim_commitment, reserve_sats, payout_address,
               fee_sats, delay_blocks, min_confirmations) -> dict:
    if not compressed_point(holder_pubkey) or not compressed_point(mint_pubkey) or holder_pubkey == mint_pubkey:
        raise Refused("protected_distinct_public_keys_required")
    hash32(claim_commitment, "claim_commitment")
    positive(reserve_sats, "reserve_sats")
    positive(fee_sats, "fee_sats")
    positive(delay_blocks, "delay_blocks", 65535)
    positive(min_confirmations, "min_confirmations", 1000)
    if fee_sats >= reserve_sats:
        raise Refused("protected_fee_consumes_reserve")
    witness = _witness_script(holder_pubkey, mint_pubkey, delay_blocks)
    funding_script = "0020" + hashlib.sha256(witness).hexdigest()
    expr = f"wsh(and_v(v:pk({holder_pubkey}),or_i(pk({mint_pubkey}),older({delay_blocks}))))"
    try:
        info = core.rpc("getdescriptorinfo", [expr])
    except CoreRPCError as error:
        if error.rpc_code == -5:
            raise Refused("protected_invalid_descriptor") from None
        raise
    if info.get("issolvable") is not True or info.get("hasprivatekeys") is not False:
        raise Refused("protected_invalid_descriptor")
    descriptor = info.get("descriptor")
    if not isinstance(descriptor, str):
        raise Refused("protected_invalid_descriptor")
    addresses = core.rpc("deriveaddresses", [descriptor])
    if (not isinstance(addresses, list) or len(addresses) != 1
            or _address_script(core, addresses[0]) != funding_script):
        raise Refused("protected_descriptor_script_mismatch")
    payout_script = _address_script(core, payout_address)
    if payout_script == funding_script:
        raise Refused("protected_payout_reuses_reserve")
    return {
        "schema": PLAN_SCHEMA, "network": "regtest", "genesis": GENESIS,
        "holder_pubkey": holder_pubkey, "mint_pubkey": mint_pubkey, "claim_commitment": claim_commitment,
        "reserve_sats": reserve_sats, "fee_sats": fee_sats, "delay_blocks": delay_blocks,
        "min_confirmations": min_confirmations, "descriptor": descriptor, "funding_address": addresses[0],
        "funding_script": funding_script, "witness_script": witness.hex(), "payout_address": payout_address,
        "payout_script": payout_script, "payout_sats": reserve_sats - fee_sats, "change_sats": 0,
    }


def plan(core, **terms) -> dict:
    before = _chain(core)
    body = _plan_body(core, **terms)
    _stable_tip(core, before)
    return body | {"plan_id": digest(body)}


def _validate_plan(core, saved: dict, plan_id: str) -> dict:
    hash32(plan_id, "plan_id")
    if not isinstance(saved, dict) or any(key not in saved for key in PLAN_FIELDS):
        raise Refused("protected_invalid_plan")
    if saved != plan(core, **{key: saved[key] for key in PLAN_FIELDS}) or saved["plan_id"] != plan_id:
        raise Refused("protected_plan_mismatch")
    return saved


def _funding(core, saved: dict, outpoint: dict, before: dict) -> dict:
    if not isinstance(outpoint, dict) or set(outpoint) != {"txid", "vout", "block"}:
        raise Refused("protected_invalid_outpoint")
    txid = hash32(outpoint["txid"], "funding_txid")
    block = hash32(outpoint["block"], "funding_block")
    vout = outpoint["vout"]
    if type(vout) is not int or not 0 <= vout < 2**32:
        raise Refused("protected_invalid_outpoint")
    header = core.rpc("getblockheader", [block])
    height = header.get("height")
    if (type(height) is not int or not 1 <= height <= before["blocks"]
            or core.rpc("getblockhash", [height]) != block):
        raise Refused("protected_funding_reorged")
    confirmations = before["blocks"] - height + 1
    if confirmations < saved["min_confirmations"]:
        raise Refused("protected_funding_unconfirmed")
    tx = core.rpc("getrawtransaction", [txid, True, block])
    if (tx.get("txid") != txid or tx.get("blockhash") != block or tx.get("in_active_chain") is False
            or any("coinbase" in item for item in tx.get("vin", []))):
        raise Refused("protected_funding_mismatch")
    outputs = tx.get("vout", [])
    if (vout >= len(outputs) or outputs[vout].get("n") != vout
            or _sats(outputs[vout].get("value")) != saved["reserve_sats"]
            or outputs[vout].get("scriptPubKey", {}).get("hex") != saved["funding_script"]):
        raise Refused("protected_funding_mismatch")
    confirmed = core.rpc("gettxout", [txid, vout, False])
    live = core.rpc("gettxout", [txid, vout, True])
    _stable_tip(core, before)
    for available in (confirmed, live):
        if available is not None and (
                available.get("bestblock") != before["bestblockhash"]
                or available.get("confirmations") != confirmations
                or _sats(available.get("value")) != saved["reserve_sats"]
                or available.get("scriptPubKey", {}).get("hex") != saved["funding_script"]):
            raise Refused("protected_funding_mismatch")
    if confirmed is None and live is not None:
        raise Refused("chain_changed_retry")
    state = "consumed" if confirmed is None else "pending-spend" if live is None else "unspent"
    return {
        "state": state, "tip": before["bestblockhash"], "height": before["blocks"],
        "funding_height": height, "confirmations": confirmations,
        "eligible_in_next_block": state == "unspent" and confirmations >= saved["delay_blocks"],
        "holder_only_earliest_height": height + saved["delay_blocks"],
    }


def attach(core, saved: dict, plan_id: str, outpoint: dict) -> dict:
    saved = _validate_plan(core, saved, plan_id)
    observation = _funding(core, saved, outpoint, _chain(core))
    if observation["state"] != "unspent":
        raise Refused("protected_reserve_unavailable")
    body = {"schema": BUNDLE_SCHEMA, "plan": saved, "funding": outpoint}
    return body | {"bundle_id": digest(body)}


def status(core, bundle: dict, bundle_id: str) -> dict:
    hash32(bundle_id, "bundle_id")
    if not isinstance(bundle, dict) or set(bundle) != {"schema", "plan", "funding", "bundle_id"}:
        raise Refused("protected_invalid_bundle")
    body = {key: value for key, value in bundle.items() if key != "bundle_id"}
    if bundle["schema"] != BUNDLE_SCHEMA or bundle["bundle_id"] != bundle_id or digest(body) != bundle_id:
        raise Refused("protected_bundle_mismatch")
    saved = bundle["plan"]
    if not isinstance(saved, dict):
        raise Refused("protected_invalid_plan")
    _validate_plan(core, saved, saved.get("plan_id"))
    return _funding(core, saved, bundle["funding"], _chain(core))


def _sequence(route: str, saved: dict) -> int:
    if route == "holder":
        return saved["delay_blocks"]
    if route == "cooperative":
        return COOPERATIVE_SEQUENCE
    raise Refused("protected_invalid_route")


def _match_transaction(tx: dict, bundle: dict, sequence: int) -> dict:
    saved, funding = bundle["plan"], bundle["funding"]
    inputs, outputs = tx.get("vin"), tx.get("vout")
    if (tx.get("version") != 2 or tx.get("locktime") != 0
            or not isinstance(inputs, list) or len(inputs) != 1
            or not isinstance(outputs, list) or len(outputs) != 1):
        raise Refused("protected_payout_mismatch")
    source, payout = inputs[0], outputs[0]
    if (source.get("txid") != funding["txid"] or source.get("vout") != funding["vout"]
            or source.get("sequence") != sequence or source.get("scriptSig", {}).get("hex") != ""
            or payout.get("n") != 0 or _sats(payout.get("value")) != saved["payout_sats"]
            or payout.get("scriptPubKey", {}).get("hex") != saved["payout_script"]):
        raise Refused("protected_payout_mismatch")
    return source


def unsigned_psbt(core, bundle: dict, bundle_id: str, route: str) -> dict:
    observed = status(core, bundle, bundle_id)
    if observed["state"] != "unspent":
        raise Refused("protected_reserve_unavailable")
    saved, funding = bundle["plan"], bundle["funding"]
    sequence = _sequence(route, saved)
    requested = [{"txid": funding["txid"], "vout": funding["vout"], "sequence": sequence}]
    value = format(Decimal(saved["payout_sats"]) / 100_000_000, ".8f")
    transaction = core.rpc("createpsbt", [requested, [{saved["payout_address"]: value}], 0, False])
    enriched = core.rpc("utxoupdatepsbt", [transaction, [saved["descriptor"]]])
    decoded = core.rpc("decodepsbt", [enriched])
    _match_transaction(decoded["tx"], bundle, sequence)
    entries = decoded.get("inputs", [])
    if len(entries) != 1:
        raise Refused("protected_psbt_input_mismatch")
    prevout = entries[0].get("witness_utxo", {})
    if (_sats(prevout.get("amount")) != saved["reserve_sats"]
            or prevout.get("scriptPubKey", {}).get("hex") != saved["funding_script"]
            or entries[0].get("witness_script", {}).get("hex") != saved["witness_script"]
            or _sats(decoded.get("fee")) != saved["fee_sats"]):
        raise Refused("protected_psbt_input_mismatch")
    after = status(core, bundle, bundle_id)
    if after["tip"] != observed["tip"] or after["state"] != "unspent":
        raise Refused("chain_changed_retry")
    return {"bundle_id": bundle_id, "route": route, "psbt": enriched, "txid": decoded["tx"]["txid"],
            "observation": after}


def spending_observation(core, bundle: dict, bundle_id: str) -> dict:
    observed = status(core, bundle, bundle_id)
    if observed["state"] == "unspent":
        return observed | {"spender": None}
    funding = bundle["funding"]
    outpoint = {key: funding[key] for key in ("txid", "vout")}
    spent = core.rpc("gettxspendingprevout", [[outpoint], {"mempool_only": False, "return_spending_tx": True}])[0]
    if any(spent.get(key) != value for key, value in outpoint.items()) or not spent.get("spendingtxid"):
        raise Refused("chain_changed_retry")
    txid = hash32(spent["spendingtxid"], "spending_txid")
    block = spent.get("blockhash")
    if (block is not None) != (observed["state"] == "consumed"):
        raise Refused("chain_changed_retry")
    if block:
        height = core.rpc("getblockheader", [block]).get("height")
        if type(height) is not int or height > observed["height"] or core.rpc("getblockhash", [height]) != block:
            raise Refused("chain_changed_retry")
    tx = core.rpc("decoderawtransaction", [spent["spendingtx"]])
    if (tx.get("txid") != txid or not any(
            vin.get("txid") == funding["txid"] and vin.get("vout") == funding["vout"] for vin in tx.get("vin", []))):
        raise Refused("chain_changed_retry")
    route = "other"
    for candidate in ("cooperative", "holder"):
        try:
            source = _match_transaction(tx, bundle, _sequence(candidate, bundle["plan"]))
            _check_witness(source, bundle["plan"], candidate)
        except Refused:
            continue
        route = candidate
        break
    if status(core, bundle, bundle_id) != observed:
        raise Refused("chain_changed_retry")
    return observed | {"spender": {"txid": txid, "wtxid": tx["hash"], "block": block, "route": route}}


def _check_witness(source, saved, route):
    witness = source.get("txinwitness", [])
    if route == "holder" and len(witness) == 3 and witness[0] == "":
        signatures = witness[1:2]
    elif route == "cooperative" and len(witness) == 4 and witness[1] == "01":
        signatures = (witness[0], witness[2])
    else:
        raise Refused("protected_witness_branch_mismatch")
    if witness[-1] != saved["witness_script"] or any(not all_signature(sig) for sig in signatures):
        raise Refused("protected_witness_authorization_mismatch")


def all_signature(signature):
    return (isinstance(signature, str) and 18 <= len(signature) <= 146
            and HEX.fullmatch(signature) is not None and signature.endswith("01"))


def check_signed(core, bundle: dict, bundle_id: str, route: str, raw: str) -> dict:
    observed = status(core, bundle, bundle_id)
    if observed["state"] != "unspent":
        raise Refused("protected_reserve_unavailable")
    if not isinstance(raw, str) or not 20 <= len(raw) <= 16000 or not HEX.fullmatch(raw):
        raise Refused("protected_invalid_transaction")
    saved = bundle["plan"]
    sequence = _sequence(route, saved)
    tx = core.rpc("decoderawtransaction", [raw])
    source = _match_transaction(tx, bundle, sequence)
    _check_witness(source, saved, route)
    outcome = core.rpc("testmempoolaccept", [[raw]])[0]
    if outcome.get("txid") != tx.get("txid") or outcome.get("wtxid") != tx.get("hash"):
        raise Refused("protected_payout_mismatch")
    after = status(core, bundle, bundle_id)
    if after["tip"] != observed["tip"] or after["state"] != "unspent":
        raise Refused("chain_changed_retry")
    return {
        "bundle_id": bundle_id, "route": route, "mempool_eligible": outcome.get("allowed") is True,
        "reject_reason": outcome.get("reject-reason"), "txid": tx["txid"], "wtxid": tx["hash"],
        "payout_sats": saved["payout_sats"], "fee_sats": saved["fee_sats"], "change_sats": 0,
        "observation": after,
    }
