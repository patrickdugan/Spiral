"""Admit an exact signed, unbroadcast Cashu withdrawal to a candidate Nova journal."""

import hashlib

from .domain import Refused, digest, hash32
from .protected_accounting import MAX_EVENTS, audit, bound_claim, journal_entry, outpoint
from .protected_reserve import GENESIS, check_signed


SCHEMA = "proof-grove/protected-withdrawal-candidate/v1"
STATEMENT = "proof-grove/protected-withdrawal-authorization/v1"


def prepare(core, catalog, journal, records, bundle_id, raw):
    """Check the live confirmed prefix and return one provisional consumption event."""
    hash32(bundle_id, "bundle_id")
    totals = audit(core, catalog, journal, records)
    if len(journal["events"]) >= MAX_EVENTS:
        raise Refused("protected_withdrawal_journal_full")
    matches = [bundle for bundle in catalog["bundles"] if bundle["bundle_id"] == bundle_id]
    if len(matches) != 1:
        raise Refused("protected_withdrawal_bundle_not_in_catalog")
    bundle, = matches
    coin = outpoint(bundle["funding"])
    claim = bound_claim(coin)
    latest = next(event for event in reversed(journal["events"])
                  if outpoint(event, "funding_txid", "funding_vout") == coin)
    if latest["action"]["kind"] != "issue" or latest["action"]["claim"] != claim:
        raise Refused("protected_withdrawal_claim_not_live")

    checked = check_signed(core, bundle, bundle_id, "holder", raw)
    observation = checked["observation"]
    if (observation["tip"], observation["height"]) != (totals["tip_hash"], totals["tip_height"]):
        raise Refused("chain_changed_retry")
    if not checked["mempool_eligible"] or not observation["eligible_in_next_block"]:
        raise Refused("protected_withdrawal_not_eligible", checked["reject_reason"] or "not mature")

    plan = bundle["plan"]
    statement = {
        "schema": STATEMENT,
        "genesis": GENESIS,
        "anchor": {"hash": observation["tip"], "height": observation["height"]},
        "catalog_sha256": digest(catalog),
        "confirmed_journal_sha256": digest(journal),
        "claim_id": claim,
        "holder_pubkey": plan["holder_pubkey"],
        "reserve": bundle["funding"] | {"height": observation["funding_height"],
                                     "sats": plan["reserve_sats"], "script": plan["funding_script"]},
        "withdrawal": {
            "txid": checked["txid"], "wtxid": checked["wtxid"],
            "signed_tx_sha256": hashlib.sha256(bytes.fromhex(raw)).hexdigest(),
            "script": plan["payout_script"], "sats": checked["payout_sats"],
            "fee_sats": checked["fee_sats"], "change_sats": checked["change_sats"],
            "sequence": plan["delay_blocks"], "earliest_height": observation["holder_only_earliest_height"],
        },
    }
    event, record = journal_entry(bundle, {"kind": "redeem", "input": claim,
                                           "reserve_before_sats": plan["reserve_sats"]},
                                  {"kind": "authorized-regtest-withdrawal", "statement": statement})
    return {"schema": SCHEMA, "withdrawal_id": digest(record), "admission": record,
            "journal": journal | {"events": [*journal["events"], event]}}


def verify_candidate(core, catalog, journal, records, bundle_id, raw, candidate):
    """Readmit against the pinned live prefix, then check all bytes used by the prover."""
    expected = prepare(core, catalog, journal, records, bundle_id, raw)
    if digest(candidate) != digest(expected):
        raise Refused("protected_withdrawal_candidate_mismatch")
    return expected
