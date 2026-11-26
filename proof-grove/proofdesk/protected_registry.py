"""Discover protected reserve enrollments from a pinned regtest registry coin."""

import re

from .domain import Refused, hash32, positive
from .protected_reserve import GENESIS, _sats, _stable_tip


SCHEMA = "proof-grove/protected-reserve-registry/v1"
MARKER = b"PGCR\x01"
MAX_MARKED_OUTPUTS = (75 - len(MARKER) - 32) // 4
REGISTRY_SCRIPT = re.compile(r"(?:0014[a-f0-9]{40}|(?:0020|5120)[a-f0-9]{64})")
FIELDS = {"schema", "genesis", "mint", "txid", "vout", "block", "height", "script", "sats"}


def registration_payload(txid, vouts):
    """Encode the data payload for a zero-value OP_RETURN output."""
    target = bytes.fromhex(hash32(txid, "reserve_txid"))
    if (not isinstance(vouts, (list, tuple)) or not 1 <= len(vouts) <= MAX_MARKED_OUTPUTS
            or any(type(index) is not int or not 0 <= index < 2**32 for index in vouts)
            or list(vouts) != sorted(set(vouts))):
        raise Refused("protected_registry_invalid_marker")
    return (MARKER + target + b"".join(index.to_bytes(4, "big") for index in vouts)).hex()


def _registration(script):
    try:
        raw = bytes.fromhex(script)
    except (TypeError, ValueError):
        raise Refused("protected_registry_invalid_marker") from None
    if (raw.hex() != script or len(raw) < 2 or raw[0] != 0x6a or raw[1] != len(raw) - 2
            or raw[1] > 75 or not raw[2:].startswith(MARKER)):
        raise Refused("protected_registry_invalid_marker")
    data = raw[2 + len(MARKER):]
    if len(data) < 36 or (len(data) - 32) % 4:
        raise Refused("protected_registry_invalid_marker")
    txid = data[:32].hex()
    vouts = [int.from_bytes(data[i:i + 4], "big") for i in range(32, len(data), 4)]
    registration_payload(txid, vouts)
    return {(txid, index) for index in vouts}


def _outputs(tx):
    if not isinstance(tx.get("vout"), list):
        raise Refused("protected_registry_invalid_transaction")
    outputs = {}
    for index, item in enumerate(tx["vout"]):
        script = item["scriptPubKey"]["hex"]
        if type(item["n"]) is not int or item["n"] != index or not isinstance(script, str):
            raise Refused("protected_registry_invalid_transaction")
        outputs[index] = script, _sats(item["value"])
    return outputs


def discover(core, root, mint, tip, *, max_reserves):
    """Walk confirmed spends from the independent root to the live registry head."""
    if (not isinstance(root, dict) or root.keys() != FIELDS or root["schema"] != SCHEMA
            or root["genesis"] != GENESIS or root["mint"] != mint
            or type(root["vout"]) is not int or not 0 <= root["vout"] < 2**32
            or not isinstance(root["script"], str) or REGISTRY_SCRIPT.fullmatch(root["script"]) is None):
        raise Refused("protected_registry_invalid_root")
    txid = hash32(root["txid"], "registry_txid")
    block = hash32(root["block"], "registry_block")
    height = positive(root["height"], "registry_height", tip["blocks"])
    registry_output = root["script"], positive(root["sats"], "registry_sats")
    if core.rpc("getblockhash", [height]) != block:
        raise Refused("protected_registry_root_inactive")
    entry = core.rpc("getrawtransaction", [txid, True, block])
    index = root["vout"]
    if (entry.get("txid") != txid or entry.get("in_active_chain") is not True
            or _outputs(entry).get(index) != registry_output):
        raise Refused("protected_registry_invalid_root")

    registered, seen = set(), {txid}
    registry_coins = {(txid, index)}
    for _ in range(max_reserves + 1):
        live = core.rpc("gettxout", [txid, index, False])
        if live is not None:
            if (live.get("bestblock") != tip["bestblockhash"]
                    or live.get("confirmations") != tip["blocks"] - height + 1
                    or (live["scriptPubKey"]["hex"], _sats(live["value"])) != registry_output):
                raise Refused("protected_registry_head_mismatch")
            _stable_tip(core, tip)
            return registered, {"head_txid": txid, "head_vout": index, "registered_reserves": len(registered)}
        point = {"txid": txid, "vout": index}
        spending = core.rpc("gettxspendingprevout", [[point], {"mempool_only": False, "return_spending_tx": True}])
        if (not isinstance(spending, list) or len(spending) != 1
                or any(spending[0].get(key) != value for key, value in point.items())
                or not spending[0].get("blockhash") or not spending[0].get("spendingtx")):
            raise Refused("protected_registry_confirmed_spend_unavailable")
        item = spending[0]
        block = hash32(item["blockhash"], "registry_spend_block")
        next_height = core.rpc("getblockheader", [block]).get("height")
        if (type(next_height) is not int or not height <= next_height <= tip["blocks"]
                or core.rpc("getblockhash", [next_height]) != block):
            raise Refused("chain_changed_retry")
        successor = hash32(item.get("spendingtxid"), "registry_spend_txid")
        tx = core.rpc("getrawtransaction", [successor, True, block])
        if (successor in seen or tx.get("txid") != successor or tx.get("in_active_chain") is not True
                or tx.get("hex") != item["spendingtx"] or not any(
                    vin.get("txid") == txid and vin.get("vout") == index for vin in tx.get("vin", []))):
            raise Refused("protected_registry_invalid_transition")
        outputs = _outputs(tx)
        continuation = [out for out, value in outputs.items() if value == registry_output]
        markers = [script for script, amount in outputs.values() if script.startswith("6a") and amount == 0]
        if len(continuation) != 1 or len(markers) != 1:
            raise Refused("protected_registry_invalid_transition")
        additions = _registration(markers[0])
        head = successor, continuation[0]
        registry_coins.add(head)
        if head in registered or additions & registry_coins:
            raise Refused("protected_registry_coin_reused_as_reserve")
        if additions & registered or len(registered) + len(additions) > max_reserves:
            raise Refused("protected_registry_repeated_or_oversized_enrollment")
        registered.update(additions)
        seen.add(successor)
        txid, index = head
        height = next_height
    raise Refused("protected_registry_repeated_or_oversized_enrollment")
