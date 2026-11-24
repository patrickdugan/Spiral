"""Cooperative protected settlement through the claim's existing Bitcoin outpoint."""
from __future__ import annotations

import base64
import re

from . import protected_reserve as reserve
from .adapters import CoreRPCError
from .domain import Refused, hash32


def _with_holder_signature(psbt, pubkey, signature):
    # Core produced this BIP-174 v0 PSBT. Add just the holder's partial
    # signature to its input map; upstream wallet RPC never sees caller metadata.
    raw = base64.b64decode(psbt, validate=True)
    if not raw.startswith(b"psbt\xff"):
        raise Refused("protected_psbt_input_mismatch")

    def compact_size(offset):
        prefix = raw[offset]
        number_bytes = {253: 2, 254: 4, 255: 8}.get(prefix, 0)
        end = offset + 1 + number_bytes
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
    sig = bytes.fromhex(signature)
    record = b"\x22\x02" + bytes.fromhex(pubkey) + bytes([len(sig)]) + sig
    return base64.b64encode(raw[:separator] + record + raw[separator:]).decode("ascii")


class ProtectedMelt:
    def __init__(self, cashu, core, mint_wallet):
        if cashu.ledger.namespace != "regtest":
            raise Refused("protected_regtest_required")
        if not isinstance(mint_wallet, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", mint_wallet):
            raise Refused("protected_invalid_mint_wallet")
        self.cashu, self.core = cashu, core
        self.wallet_path = "/wallet/" + mint_wallet

    def _registered(self, intent_id, bundle_id):
        hash32(bundle_id, "bundle_id")
        row = self.cashu.ledger.db.execute(
            "SELECT p.bundle_id FROM cashu_protected_reserves p JOIN cashu_issuance i ON i.intent_id=p.intent_id "
            "WHERE p.intent_id=? AND i.state='signatures_received' AND i.result IS NOT NULL", (intent_id,)
        ).fetchone()
        if row is None or row[0] != bundle_id:
            raise Refused("protected_melt_issuance_required")

    def _status(self, bundle, bundle_id):
        try:
            result = reserve.spending_observation(self.core, bundle, bundle_id)
        except Refused as error:
            if error.code not in ("protected_funding_reorged", "protected_funding_unconfirmed"):
                raise
            return {"bundle_id": bundle_id, "state": "funding-unavailable", "reason": error.code, "spender": None}
        return result | {"bundle_id": bundle_id}

    def status(self, intent_id, bundle, bundle_id):
        self._registered(intent_id, bundle_id)
        return self._status(bundle, bundle_id)

    def _require_index(self):
        result = self.core.rpc("getindexinfo", ["txospenderindex"])
        if result.get("txospenderindex", {}).get("synced") is not True:
            raise Refused("protected_melt_spender_index_required")

    def prepare(self, intent_id, bundle, bundle_id):
        self._registered(intent_id, bundle_id)
        self._require_index()
        return reserve.unsigned_psbt(self.core, bundle, bundle_id, "cooperative")

    def _holder_signature(self, bundle, psbt):
        if not isinstance(psbt, str) or not 20 <= len(psbt) <= 16_384:
            raise Refused("protected_invalid_psbt")
        try:
            base64.b64decode(psbt, validate=True)
            decoded = self.core.rpc("decodepsbt", [psbt])
        except (ValueError, CoreRPCError):
            raise Refused("protected_invalid_psbt") from None
        reserve._match_transaction(decoded["tx"], bundle, reserve.COOPERATIVE_SEQUENCE)
        saved = bundle["plan"]
        entries = decoded.get("inputs", [])
        if len(entries) != 1:
            raise Refused("protected_psbt_input_mismatch")
        entry = entries[0]
        prevout = entry.get("witness_utxo", {})
        if (reserve._sats(prevout.get("amount")) != saved["reserve_sats"]
                or prevout.get("scriptPubKey", {}).get("hex") != saved["funding_script"]
                or entry.get("witness_script", {}).get("hex") != saved["witness_script"]
                or reserve._sats(decoded.get("fee")) != saved["fee_sats"]):
            raise Refused("protected_psbt_input_mismatch")
        partials = entry.get("partial_signatures", {})
        holder = saved["holder_pubkey"]
        if set(partials) != {holder} or not reserve.all_signature(partials[holder]):
            raise Refused("protected_melt_holder_signature_required")
        return decoded["tx"]["txid"], partials[holder]

    @staticmethod
    def _result(observed, expected):
        spender = observed["spender"]
        own_payout = bool(spender and spender["txid"] == expected and spender["route"] == "cooperative")
        return observed | {"cooperative_payout_observed": own_payout, "expected_cooperative_txid": expected}

    def settle(self, intent_id, bundle, bundle_id, psbt):
        self._registered(intent_id, bundle_id)
        observed = self._status(bundle, bundle_id)
        expected, signature = self._holder_signature(bundle, psbt)
        if observed["state"] != "unspent":
            return self._result(observed, expected)
        self._require_index()
        try:
            canonical = reserve.unsigned_psbt(self.core, bundle, bundle_id, "cooperative")
            if canonical["txid"] != expected:
                raise Refused("protected_payout_mismatch")
            partial = _with_holder_signature(canonical["psbt"], bundle["plan"]["holder_pubkey"], signature)
            reserve._chain(self.core)
            signed = self.core._call("walletprocesspsbt", [partial, True, "ALL", False, True], self.wallet_path)
            if signed.get("complete") is not True or not isinstance(signed.get("hex"), str):
                raise Refused("protected_melt_cosign_refused")
            review = reserve.check_signed(self.core, bundle, bundle_id, "cooperative", signed["hex"])
            if review["txid"] != expected or not review["mempool_eligible"]:
                raise Refused("protected_melt_not_accepted")
            if self.core._call("sendrawtransaction", [signed["hex"]]) != expected:
                raise Refused("protected_payout_mismatch")
        except Refused as error:
            if error.code not in ("chain_changed_retry", "protected_reserve_unavailable", "protected_melt_not_accepted",
                                  "core_rpc_error", "upstream_unavailable"):
                raise
            current = self._status(bundle, bundle_id)
            if current["state"] == "unspent":
                raise
            return self._result(current, expected)
        return self._result(self._status(bundle, bundle_id), expected)
