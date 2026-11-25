"""Split a protected regtest coin into two independently recoverable outputs."""

from . import protected_reserve as reserve
from .domain import Refused, digest, hash32, positive


PLAN_SCHEMA = "proof-grove/protected-rollover-plan/v1"
RECEIPT_SCHEMA = "proof-grove/protected-rollover-receipt/v1"
RECIPIENT_FIELDS = {
    "holder_pubkey", "reserve_sats", "payout_address", "fee_sats", "delay_blocks", "min_confirmations",
}


def _observe(core, parent, bundle_id):
    observed = reserve.holder_status(core, parent, bundle_id)
    if parent["schema"] not in (reserve.V3_BUNDLE_SCHEMA, reserve.SUCCESSOR_BUNDLE_SCHEMA):
        raise Refused("protected_rollover_parent_profile")
    return observed


def _same_tip(core, observed):
    if reserve._chain(core)["bestblockhash"] != observed["tip"]:
        raise Refused("chain_changed_retry")


def _build_plan(core, parent, recipients, split_fee_sats):
    positive(split_fee_sats, "split_fee_sats")
    if (not isinstance(recipients, list) or len(recipients) != 2
            or any(not isinstance(terms, dict) or set(terms) != RECIPIENT_FIELDS for terms in recipients)):
        raise Refused("protected_rollover_recipients")
    parent_plan = parent["plan"]
    children = []
    for vout, terms in enumerate(recipients):
        claim = digest({"schema": "proof-grove/protected-successor-claim/v1",
                        "parent_bundle_id": parent["bundle_id"], "vout": vout, "recipient": terms})
        children.append(reserve.plan(core, schema=reserve.SUCCESSOR_PLAN_SCHEMA, **terms,
                                     mint_pubkey=parent_plan["mint_pubkey"], claim_commitment=claim))
    if (children[0]["holder_pubkey"] == children[1]["holder_pubkey"]
            or len({parent_plan["funding_script"], *(child["funding_script"] for child in children)}) != 3):
        raise Refused("protected_rollover_recipients")
    if sum(child["reserve_sats"] for child in children) + split_fee_sats != parent_plan["reserve_sats"]:
        raise Refused("protected_rollover_value_mismatch")
    body = {"schema": PLAN_SCHEMA, "parent_bundle_id": parent["bundle_id"], "parent_funding": parent["funding"],
            "split_fee_sats": split_fee_sats, "recipients": recipients, "children": children}
    return body | {"rollover_id": digest(body)}


def plan(core, parent, bundle_id, recipients, split_fee_sats):
    observed = _observe(core, parent, bundle_id)
    if observed["state"] != "unspent":
        raise Refused("protected_reserve_unavailable")
    result = _build_plan(core, parent, recipients, split_fee_sats)
    _same_tip(core, observed)
    return result


def _checked_plan(core, parent, bundle_id, saved, rollover_id):
    hash32(rollover_id, "rollover_id")
    observed = _observe(core, parent, bundle_id)
    if (not isinstance(saved, dict) or saved.get("rollover_id") != rollover_id
            or saved != _build_plan(core, parent, saved.get("recipients"), saved.get("split_fee_sats"))):
        raise Refused("protected_rollover_plan_mismatch")
    _same_tip(core, observed)
    return observed


def _match_transaction(tx, parent, children):
    inputs, outputs = tx.get("vin"), tx.get("vout")
    if (tx.get("version") != 2 or tx.get("locktime") != 0
            or not isinstance(inputs, list) or len(inputs) != 1
            or not isinstance(outputs, list) or len(outputs) != len(children)):
        raise Refused("protected_rollover_transaction_mismatch")
    source, funding = inputs[0], parent["funding"]
    if (source.get("txid") != funding["txid"] or source.get("vout") != funding["vout"]
            or source.get("sequence") != parent["plan"]["delay_blocks"]
            or source.get("scriptSig", {}).get("hex") != ""):
        raise Refused("protected_rollover_transaction_mismatch")
    for vout, (output, child) in enumerate(zip(outputs, children, strict=True)):
        if (output.get("n") != vout or reserve._sats(output.get("value")) != child["reserve_sats"]
                or output.get("scriptPubKey", {}).get("hex") != child["funding_script"]):
            raise Refused("protected_rollover_transaction_mismatch")
    return source


def unsigned_psbt(core, parent, bundle_id, saved, rollover_id):
    observed = _checked_plan(core, parent, bundle_id, saved, rollover_id)
    if observed["state"] != "unspent":
        raise Refused("protected_reserve_unavailable")
    destinations = [(child["funding_address"], child["reserve_sats"]) for child in saved["children"]]
    psbt, tx = reserve._funded_psbt(core, parent, parent["plan"]["delay_blocks"], destinations, saved["split_fee_sats"])
    _match_transaction(tx, parent, saved["children"])
    if _observe(core, parent, bundle_id) != observed:
        raise Refused("chain_changed_retry")
    return {"rollover_id": rollover_id, "txid": tx["txid"], "psbt": psbt, "observation": observed}


def check_signed(core, parent, bundle_id, saved, rollover_id, raw):
    observed = _checked_plan(core, parent, bundle_id, saved, rollover_id)
    if observed["state"] != "unspent":
        raise Refused("protected_reserve_unavailable")
    if not isinstance(raw, str) or not 20 <= len(raw) <= 16000 or not reserve.HEX.fullmatch(raw):
        raise Refused("protected_invalid_transaction")
    tx = core.rpc("decoderawtransaction", [raw])
    reserve._check_witness(_match_transaction(tx, parent, saved["children"]), parent["plan"], "holder")
    policy = core.rpc("testmempoolaccept", [[raw]])[0]
    if (policy.get("txid"), policy.get("wtxid")) != (tx["txid"], tx["hash"]):
        raise Refused("protected_rollover_transaction_mismatch")
    if _observe(core, parent, bundle_id) != observed:
        raise Refused("chain_changed_retry")
    return {"rollover_id": rollover_id, "txid": tx["txid"], "wtxid": tx["hash"],
            "mempool_eligible": policy.get("allowed") is True, "reject_reason": policy.get("reject-reason"),
            "split_fee_sats": saved["split_fee_sats"], "observation": observed}


def confirm(core, parent, bundle_id, saved, rollover_id, txid, block):
    hash32(txid, "rollover_txid")
    hash32(block, "rollover_block")
    observed = _checked_plan(core, parent, bundle_id, saved, rollover_id)
    if observed["state"] != "consumed":
        raise Refused("protected_rollover_unconfirmed")
    height = core.rpc("getblockheader", [block]).get("height")
    if (type(height) is not int or not observed["holder_only_earliest_height"] <= height <= observed["height"]
            or core.rpc("getblockhash", [height]) != block):
        raise Refused("protected_rollover_inactive_block")
    tx = core.rpc("getrawtransaction", [txid, True, block])
    if tx.get("txid") != txid or tx.get("blockhash") != block or tx.get("in_active_chain") is not True:
        raise Refused("protected_rollover_transaction_mismatch")
    reserve._check_witness(_match_transaction(tx, parent, saved["children"]), parent["plan"], "holder")
    successors = [reserve.attach(core, child, child["plan_id"], {"txid": txid, "vout": n, "block": block})
                  for n, child in enumerate(saved["children"])]
    if _observe(core, parent, bundle_id) != observed:
        raise Refused("chain_changed_retry")
    body = {"schema": RECEIPT_SCHEMA, "rollover_id": rollover_id, "parent_bundle_id": bundle_id,
            "parent_funding": parent["funding"], "txid": txid, "wtxid": tx["hash"], "block": block,
            "height": height, "tip": observed["tip"], "split_fee_sats": saved["split_fee_sats"],
            "successors": successors}
    return body | {"receipt_id": digest(body)}
