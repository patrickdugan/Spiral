"""Regtest holder tooling for the issuance-funded, single-outpoint profile."""

from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation
import hashlib
import re

from .adapters import CoreRPCError
from .cashu import compressed_point
from .domain import MAX_SATS, Refused, digest, hash32, positive

LEGACY_PLAN_SCHEMA = "proof-grove/protected-reserve-plan/v1"
LEGACY_BUNDLE_SCHEMA = "proof-grove/protected-reserve-bundle/v1"
PLAN_SCHEMA = "proof-grove/protected-reserve-plan/v2"
BUNDLE_SCHEMA = "proof-grove/protected-reserve-bundle/v2"
V3_PLAN_SCHEMA = "proof-grove/protected-reserve-plan/v3"
V3_BUNDLE_SCHEMA = "proof-grove/protected-reserve-bundle/v3"
SUCCESSOR_PLAN_SCHEMA = "proof-grove/protected-successor-plan/v1"
SUCCESSOR_BUNDLE_SCHEMA = "proof-grove/protected-successor-bundle/v1"
_BUNDLE_SCHEMAS = {
    LEGACY_PLAN_SCHEMA: LEGACY_BUNDLE_SCHEMA,
    PLAN_SCHEMA: BUNDLE_SCHEMA,
    V3_PLAN_SCHEMA: V3_BUNDLE_SCHEMA,
    SUCCESSOR_PLAN_SCHEMA: SUCCESSOR_BUNDLE_SCHEMA,
}
_ISSUANCE_TERM_SCHEMAS = {
    PLAN_SCHEMA: "proof-grove/protected-issuance-terms/v2",
    V3_PLAN_SCHEMA: "proof-grove/protected-issuance-terms/v3",
    SUCCESSOR_PLAN_SCHEMA: "proof-grove/protected-successor-terms/v1",
}
GENESIS = "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206"
COOPERATIVE_SEQUENCE = 0xFFFFFFFD
HEX = re.compile(r"(?:[0-9a-f]{2})+")
PLAN_FIELDS = (
    "holder_pubkey", "mint_pubkey", "claim_commitment", "reserve_sats", "payout_address",
    "fee_sats", "delay_blocks", "min_confirmations",
)


def issuance_batch_commitment(intent_id: str, outputs: list) -> str:
    """Commit to the Cashu intent and the ordered, validated blinded outputs."""
    return digest({"schema": "proof-grove/protected-issuance-batch/v1",
                   "intent_id": intent_id, "outputs": outputs})


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


def _witness_script(holder: str, mint: str, delay: int, issuance_hash: str | None = None) -> bytes:
    prefix = b""
    if issuance_hash is not None:
        # SIZE 32 EQUALVERIFY SHA256 <issuance_hash> EQUALVERIFY.
        prefix = b"\x82\x01\x20\x88\xa8\x20" + bytes.fromhex(issuance_hash) + b"\x88"
    # <holder> CHECKSIGVERIFY IF <mint> CHECKSIG ELSE <delay> CSV ENDIF
    return (prefix + b"\x21" + bytes.fromhex(holder) + b"\xad\x63\x21" + bytes.fromhex(mint)
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
               fee_sats, delay_blocks, min_confirmations, *, schema) -> dict:
    if not isinstance(schema, str) or schema not in _BUNDLE_SCHEMAS:
        raise Refused("protected_invalid_plan")
    if not compressed_point(holder_pubkey) or not compressed_point(mint_pubkey) or holder_pubkey == mint_pubkey:
        raise Refused("protected_distinct_public_keys_required")
    hash32(claim_commitment, "claim_commitment")
    positive(reserve_sats, "reserve_sats")
    positive(fee_sats, "fee_sats")
    positive(delay_blocks, "delay_blocks", 65535)
    positive(min_confirmations, "min_confirmations", 1000)
    if fee_sats >= reserve_sats:
        raise Refused("protected_fee_consumes_reserve")
    payout_script = _address_script(core, payout_address)
    terms = {
        "network": "regtest", "genesis": GENESIS, "holder_pubkey": holder_pubkey, "mint_pubkey": mint_pubkey,
        "claim_commitment": claim_commitment, "reserve_sats": reserve_sats, "fee_sats": fee_sats,
        "delay_blocks": delay_blocks, "min_confirmations": min_confirmations, "payout_address": payout_address,
        "payout_script": payout_script,
    }
    commitment = {}
    policy = f"and_v(v:pk({holder_pubkey}),or_i(pk({mint_pubkey}),older({delay_blocks})))"
    if schema in _ISSUANCE_TERM_SCHEMAS:
        preimage = digest({"schema": _ISSUANCE_TERM_SCHEMAS[schema]} | terms)
        issuance_hash = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
        commitment = {"issuance_preimage": preimage, "issuance_hash": issuance_hash}
        policy = f"and_v(v:sha256({issuance_hash}),{policy})"
    witness = _witness_script(holder_pubkey, mint_pubkey, delay_blocks, commitment.get("issuance_hash"))
    funding_script = "0020" + hashlib.sha256(witness).hexdigest()
    expr = f"wsh({policy})"
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
    if payout_script == funding_script:
        raise Refused("protected_payout_reuses_reserve")
    return {
        "schema": schema, **terms, "descriptor": descriptor, "funding_address": addresses[0],
        "funding_script": funding_script, "witness_script": witness.hex(),
        "payout_sats": reserve_sats - fee_sats, "change_sats": 0,
    } | commitment


def plan(core, *, schema=PLAN_SCHEMA, **terms) -> dict:
    before = _chain(core)
    body = _plan_body(core, **terms, schema=schema)
    _stable_tip(core, before)
    return body | {"plan_id": digest(body)}


def _validate_plan(core, saved: dict, plan_id: str) -> dict:
    hash32(plan_id, "plan_id")
    if not isinstance(saved, dict) or any(key not in saved for key in PLAN_FIELDS):
        raise Refused("protected_invalid_plan")
    if (saved != plan(core, schema=saved.get("schema"), **{key: saved[key] for key in PLAN_FIELDS})
            or saved["plan_id"] != plan_id):
        raise Refused("protected_plan_mismatch")
    return saved


def _funding(core, saved: dict, outpoint: dict, before: dict, *, active_funding_block: str | None = None) -> dict:
    if not isinstance(outpoint, dict) or set(outpoint) != {"txid", "vout", "block"}:
        raise Refused("protected_invalid_outpoint")
    txid = hash32(outpoint["txid"], "funding_txid")
    pinned_block = hash32(outpoint["block"], "funding_block")
    block = pinned_block if active_funding_block is None else hash32(active_funding_block, "active_funding_block")
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
    try:
        tx = core.rpc("getrawtransaction", [txid, True, block])
    except CoreRPCError as error:
        if active_funding_block is None or error.rpc_code != -5:
            raise
        _stable_tip(core, before)
        raise Refused("protected_funding_mismatch") from None
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
    observation = {
        "state": state, "tip": before["bestblockhash"], "height": before["blocks"],
        "funding_height": height, "confirmations": confirmations,
        "eligible_in_next_block": state == "unspent" and confirmations >= saved["delay_blocks"],
        "holder_only_earliest_height": height + saved["delay_blocks"],
    }
    if active_funding_block is not None:
        observation.update(pinned_funding_block=pinned_block, active_funding_block=block)
    return observation


def attach(core, saved: dict, plan_id: str, outpoint: dict) -> dict:
    saved = _validate_plan(core, saved, plan_id)
    observation = _funding(core, saved, outpoint, _chain(core))
    if observation["state"] != "unspent":
        raise Refused("protected_reserve_unavailable")
    return _bound_bundle(saved, outpoint)


def _bound_bundle(saved, outpoint):
    schema = _BUNDLE_SCHEMAS[saved["schema"]]
    body = {"schema": schema, "plan": saved, "funding": outpoint}
    return body | {"bundle_id": digest(body)}


def status(core, bundle: dict, bundle_id: str) -> dict:
    return _observe(core, bundle, bundle_id)


def holder_status(core, bundle: dict, bundle_id: str, *, active_funding_block: str | None = None) -> dict:
    """Observe the pinned outpoint for local holder recovery, even after it is re-mined."""
    return _observe(core, bundle, bundle_id, active_funding_block=active_funding_block)


def _observe(core, bundle: dict, bundle_id: str, *, active_funding_block: str | None = None) -> dict:
    hash32(bundle_id, "bundle_id")
    if not isinstance(bundle, dict) or set(bundle) != {"schema", "plan", "funding", "bundle_id"}:
        raise Refused("protected_invalid_bundle")
    body = {key: value for key, value in bundle.items() if key != "bundle_id"}
    if (bundle["schema"] not in _BUNDLE_SCHEMAS.values()
            or bundle["bundle_id"] != bundle_id or digest(body) != bundle_id):
        raise Refused("protected_bundle_mismatch")
    saved = bundle["plan"]
    if not isinstance(saved, dict):
        raise Refused("protected_invalid_plan")
    _validate_plan(core, saved, saved.get("plan_id"))
    expected_schema = _BUNDLE_SCHEMAS[saved["schema"]]
    if bundle["schema"] != expected_schema:
        raise Refused("protected_bundle_mismatch")
    return _funding(core, saved, bundle["funding"], _chain(core), active_funding_block=active_funding_block)


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


def _route_status(core, bundle, bundle_id, route, active_funding_block):
    if active_funding_block is None:
        return status(core, bundle, bundle_id)
    if route != "holder":
        raise Refused("protected_holder_reobservation_only")
    return holder_status(core, bundle, bundle_id, active_funding_block=active_funding_block)


def _with_psbt_input_record(psbt: str, key: bytes, value: bytes) -> str:
    """Insert one small field into the input map of a Core-created, one-input PSBT."""
    try:
        raw = base64.b64decode(psbt, validate=True)
    except (ValueError, TypeError):
        raise Refused("protected_psbt_input_mismatch") from None
    if not raw.startswith(b"psbt\xff") or not 0 < len(key) < 253 or len(value) >= 253:
        raise Refused("protected_psbt_input_mismatch")

    def compact_size(offset):
        if offset >= len(raw):
            raise Refused("protected_psbt_input_mismatch")
        prefix = raw[offset]
        number_bytes = {253: 2, 254: 4, 255: 8}.get(prefix, 0)
        end = offset + 1 + number_bytes
        if end > len(raw):
            raise Refused("protected_psbt_input_mismatch")
        return (int.from_bytes(raw[offset + 1:end], "little") if number_bytes else prefix), end

    def map_end(offset):
        while offset < len(raw):
            keylen, offset = compact_size(offset)
            if keylen == 0:
                return offset
            valuelen, offset = compact_size(offset + keylen)
            offset += valuelen
        raise Refused("protected_psbt_input_mismatch")

    separator = map_end(map_end(5)) - 1
    record = bytes([len(key)]) + key + bytes([len(value)]) + value
    return base64.b64encode(raw[:separator] + record + raw[separator:]).decode("ascii")


def _funded_psbt(core, bundle, sequence, destinations, fee_sats):
    saved, funding = bundle["plan"], bundle["funding"]
    requested = [{"txid": funding["txid"], "vout": funding["vout"], "sequence": sequence}]
    outputs = [{address: format(Decimal(sats) / 100_000_000, ".8f")} for address, sats in destinations]
    transaction = core.rpc("createpsbt", [requested, outputs, 0, False])
    enriched = core.rpc("utxoupdatepsbt", [transaction, [saved["descriptor"]]])
    if saved["schema"] in _ISSUANCE_TERM_SCHEMAS:
        # BIP174 PSBT_IN_SHA256 supplies the public commitment preimage to both signers.
        key = b"\x0b" + bytes.fromhex(saved["issuance_hash"])
        enriched = _with_psbt_input_record(enriched, key, bytes.fromhex(saved["issuance_preimage"]))
    decoded = core.rpc("decodepsbt", [enriched])
    entries = decoded.get("inputs", [])
    if len(entries) != 1:
        raise Refused("protected_psbt_input_mismatch")
    prevout = entries[0].get("witness_utxo", {})
    if (_sats(prevout.get("amount")) != saved["reserve_sats"]
            or prevout.get("scriptPubKey", {}).get("hex") != saved["funding_script"]
            or entries[0].get("witness_script", {}).get("hex") != saved["witness_script"]
            or _sats(decoded.get("fee")) != fee_sats):
        raise Refused("protected_psbt_input_mismatch")
    return enriched, decoded["tx"]


def unsigned_psbt(core, bundle: dict, bundle_id: str, route: str, *, active_funding_block: str | None = None) -> dict:
    observed = _route_status(core, bundle, bundle_id, route, active_funding_block)
    if observed["state"] != "unspent":
        raise Refused("protected_reserve_unavailable")
    saved = bundle["plan"]
    sequence = _sequence(route, saved)
    enriched, tx = _funded_psbt(core, bundle, sequence, [(saved["payout_address"], saved["payout_sats"])], saved["fee_sats"])
    _match_transaction(tx, bundle, sequence)
    after = _route_status(core, bundle, bundle_id, route, active_funding_block)
    if after["tip"] != observed["tip"] or after["state"] != "unspent":
        raise Refused("chain_changed_retry")
    return {"bundle_id": bundle_id, "route": route, "psbt": enriched, "txid": tx["txid"],
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
    if saved["schema"] in _ISSUANCE_TERM_SCHEMAS:
        if len(witness) < 2 or witness[-2] != saved["issuance_preimage"]:
            raise Refused("protected_witness_commitment_mismatch")
        witness = witness[:-2] + witness[-1:]
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


def check_signed(core, bundle: dict, bundle_id: str, route: str, raw: str, *, active_funding_block: str | None = None) -> dict:
    observed = _route_status(core, bundle, bundle_id, route, active_funding_block)
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
    after = _route_status(core, bundle, bundle_id, route, active_funding_block)
    if after["tip"] != observed["tip"] or after["state"] != "unspent":
        raise Refused("chain_changed_retry")
    return {
        "bundle_id": bundle_id, "route": route, "mempool_eligible": outcome.get("allowed") is True,
        "reject_reason": outcome.get("reject-reason"), "txid": tx["txid"], "wtxid": tx["hash"],
        "payout_sats": saved["payout_sats"], "fee_sats": saved["fee_sats"], "change_sats": 0,
        "observation": after,
    }
