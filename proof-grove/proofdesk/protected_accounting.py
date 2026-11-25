"""Reconcile a pinned protected Cashu journal with a read-only Bitcoin Core observer."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from .adapters import CoreClient
from .domain import digest, hash32, positive, Refused
from .protected_reserve import GENESIS, V3_BUNDLE_SCHEMA, _chain, _stable_tip, spending_observation
from .verifier import read_bounded


CATALOG_SCHEMA = "proof-grove/protected-reserve-catalog/v1"
JOURNAL_SCHEMA = "proof-grove/cashu-nova-journal/v1"
MAX_EVENTS = 256


def pinned_json(path, pin, limit):
    raw = read_bounded(path, limit)
    if hashlib.sha256(raw).hexdigest() != hash32(pin, "artifact_sha256"):
        raise Refused("protected_accounting_pin_mismatch")
    return json.loads(raw)


def outpoint(value, txid="txid", vout="vout"):
    index = value[vout]
    if type(index) is not int or not 0 <= index < 2**32:
        raise Refused("protected_accounting_invalid_outpoint")
    return hash32(value[txid], txid), index


def bound_claim(key):
    txid, index = key
    return hashlib.sha256(b"proof-grove/protected-reserve/v1\0" + bytes.fromhex(GENESIS + txid)
                          + index.to_bytes(4, "big")).hexdigest()


def check_issuance(record, bundle, mint, intent, claim, amount):
    receipt = record["independent_verifier"]
    quote_tag, _, quote = record["intent_id"].partition(":")
    expected_intent = hashlib.sha256(b"proof-grove/protected-issuance-intent/v1\0"
                                     + bytes.fromhex(hash32(quote, "quote"))).hexdigest()
    if (quote_tag != "cashu" or expected_intent != intent or record.get("kind") != "verified-cdk-protected-v3-batch"
            or record.get("real_cdk_issuance") is not True or record["claim"] != claim
            or record["amount_sats"] != amount or record["issuance_batch_sha256"] != bundle["plan"]["claim_commitment"]
            or receipt["bundle_id"] != bundle["bundle_id"] or receipt["amount_sats"] != amount
            or receipt["mint"] != mint or any(receipt.get(flag) is not True for flag in (
                "batch_bound", "dleq_verified", "offline_keyset_audit"))):
        raise Refused("protected_accounting_issuance_mismatch")


def check_payout(core, plan, receipt, observation):
    spender = observation["spender"]
    if (observation["state"] != "consumed" or spender["route"] not in ("holder", "cooperative")
            or any(receipt[key] != spender[key] for key in ("txid", "wtxid", "block"))
            or receipt["sats"] != plan["payout_sats"] or receipt["script"] != plan["payout_script"]
            or receipt["fee_sats"] != plan["fee_sats"] or receipt["delay_blocks"] != plan["delay_blocks"]
            or receipt["height"] != core.rpc("getblockheader", [spender["block"]]).get("height")
            or (spender["route"] == "holder" and receipt["height"] < observation["holder_only_earliest_height"])):
        raise Refused("protected_accounting_payout_mismatch")


def audit(core, catalog, journal, records):
    """Check completeness relative to the supplied independent catalog and journal pins."""
    mint = catalog["mint"]
    profile = digest({"schema": "proof-grove/protected-accounting-mint/v3", "mint_url": mint})
    events, bundles = journal["events"], catalog["bundles"]
    if (catalog.get("schema") != CATALOG_SCHEMA or catalog.get("genesis") != GENESIS
            or journal.get("schema") != JOURNAL_SCHEMA or journal.get("genesis") != GENESIS
            or journal["mint_profile_sha256"] != profile or not isinstance(mint, str) or not mint
            or not all(isinstance(items, list) for items in (bundles, events, records))
            or not 1 <= len(bundles) <= len(events) <= MAX_EVENTS or len(records) != len(events)):
        raise Refused("protected_accounting_invalid_catalog")
    by_coin = {}
    for bundle in bundles:
        coin = outpoint(bundle["funding"])
        if coin in by_coin or bundle.get("schema") != V3_BUNDLE_SCHEMA:
            raise Refused("protected_accounting_duplicate_or_unsupported_reserve")
        by_coin[coin] = bundle

    # Each protected claim is a full outpoint. Native Nova split/swap steps have
    # their own scope and do not authorize fractional claims against these bundles.
    intents, phases = {}, {}
    for event, record in zip(events, records, strict=True):
        coin = outpoint(event, "funding_txid", "funding_vout")
        if coin not in by_coin or digest(record) != event["evidence_sha256"]:
            raise Refused("protected_accounting_event_not_in_catalog")
        bundle = by_coin[coin]
        plan = bundle["plan"]
        amount = positive(plan["reserve_sats"], "reserve_sats")
        if positive(event["amount_sats"], "amount_sats") != amount or record["bundle_id"] != bundle["bundle_id"]:
            raise Refused("protected_accounting_amount_or_bundle_mismatch")
        action, last = event["action"], phases.get(coin)
        kind = action["kind"]
        claim = bound_claim(coin)
        if kind == "register" and last is None:
            funding = bundle["funding"] | {"sats": amount, "script": plan["funding_script"]}
            intent = hash32(action["intent"], "intent")
            if record.get("kind") != "observed-regtest-reserve" or record["funding"] != funding or intent in intents:
                raise Refused("protected_accounting_registration_mismatch")
            intents[intent] = coin
        elif kind == "issue" and last and last[0] == "register":
            if intents.get(action["intent"]) != coin or action["claim"] != claim:
                raise Refused("protected_accounting_issuance_mismatch")
            check_issuance(record, bundle, mint, action["intent"], claim, amount)
        elif kind == "redeem" and last and last[0] == "issue":
            if (action["input"] != claim or positive(action["reserve_before_sats"], "reserve_before_sats") != amount
                    or record.get("kind") != "observed-regtest-payout"):
                raise Refused("protected_accounting_payout_mismatch")
        else:
            raise Refused("protected_accounting_invalid_transition")
        phases[coin] = kind, record
    if phases.keys() != by_coin.keys():
        raise Refused("protected_accounting_catalog_omission")

    tip = _chain(core)
    if (hash32(catalog["tip_hash"], "tip_hash") != tip["bestblockhash"]
            or positive(catalog["tip_height"], "tip_height", 2**31 - 1) != tip["blocks"]):
        raise Refused("protected_accounting_stale_catalog")
    totals = {"declared_reserve_sats": 0, "outstanding_claims_sats": 0, "pending_issuance_sats": 0}
    for coin, bundle in by_coin.items():
        kind, record = phases[coin]
        observation = spending_observation(core, bundle, bundle["bundle_id"])
        if observation["tip"] != tip["bestblockhash"]:
            raise Refused("chain_changed_retry")
        plan = bundle["plan"]
        if kind == "redeem":
            check_payout(core, plan, record["payout"], observation)
        else:
            if observation["state"] != "unspent":
                raise Refused("protected_accounting_reserve_unavailable")
            field = "outstanding_claims_sats" if kind == "issue" else "pending_issuance_sats"
            totals[field] += plan["reserve_sats"]
            totals["declared_reserve_sats"] += plan["reserve_sats"]
    _stable_tip(core, tip)
    return totals | {"catalog_reserves": len(by_coin), "tip_hash": tip["bestblockhash"], "tip_height": tip["blocks"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("config", "catalog", "journal", "admission", "proof-dir", "nova-verifier"):
        parser.add_argument("--" + field, required=True, type=Path)
    for field in ("catalog-sha256", "journal-sha256", "nova-key-sha256"):
        parser.add_argument("--" + field, required=True)
    args = parser.parse_args()
    core = CoreClient.from_config(json.loads(read_bounded(args.config, 32768))["core"])
    catalog = pinned_json(args.catalog, args.catalog_sha256, 2 * 1024 * 1024)
    journal = pinned_json(args.journal, args.journal_sha256, 256 * 1024)
    records = json.loads(read_bounded(args.admission, 2 * 1024 * 1024))
    key_pin = hash32(args.nova_key_sha256, "nova_key_sha256")
    checked = subprocess.run([str(args.nova_verifier.resolve()), "verify-journal", str(args.proof_dir),
                              str(args.journal), args.journal_sha256], stdin=subprocess.DEVNULL,
                             capture_output=True, check=True, timeout=90)
    proof = json.loads(checked.stdout)
    if (proof.get("schema") != "proof-grove/cashu-nova-regtest-accounting/v1" or proof.get("mode") != "verify-journal"
            or proof.get("verified") is not True or proof.get("journal_sha256") != args.journal_sha256
            or proof.get("verifier_key_sha256") != key_pin or proof.get("steps") != len(journal["events"])):
        raise Refused("protected_accounting_nova_mismatch")
    result = audit(core, catalog, journal, records)
    if any(proof.get(field) != result[field] for field in ("declared_reserve_sats", "outstanding_claims_sats")):
        raise Refused("protected_accounting_nova_mismatch")
    print(json.dumps(result | {"schema": "proof-grove/protected-ledger-audit/v1",
                               "catalog_sha256": args.catalog_sha256, "journal_sha256": args.journal_sha256,
                               "nova": proof}, indent=2))


if __name__ == "__main__":
    main()
