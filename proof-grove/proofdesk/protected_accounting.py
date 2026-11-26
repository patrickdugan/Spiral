"""Reconcile a pinned protected Cashu journal with a read-only Bitcoin Core observer."""

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .adapters import CoreClient
from .domain import digest, hash32, positive, Refused
from .protected_registry import discover
from .protected_reserve import GENESIS, SUCCESSOR_BUNDLE_SCHEMA, V3_BUNDLE_SCHEMA, _chain, _stable_tip, spending_observation
from .protected_rollover import verify_confirmed
from .verifier import read_bounded


CATALOG_SCHEMA = "proof-grove/protected-reserve-catalog/v1"
REGISTRY_CATALOG_SCHEMA = "proof-grove/protected-reserve-catalog/v2"
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


def journal_entry(bundle, action, evidence):
    coin = outpoint(bundle["funding"])
    record = evidence | {"bundle_id": bundle["bundle_id"]}
    return ({"funding_txid": coin[0], "funding_vout": coin[1], "amount_sats": bundle["plan"]["reserve_sats"],
             "action": action, "evidence_sha256": digest(record)}, record)


def rollover_entries(parent, plan, receipt):
    """Encode one admitted split as five events under the existing Nova key."""
    amount = parent["plan"]["reserve_sats"]
    entries = [journal_entry(parent, {"kind": "redeem", "input": bound_claim(outpoint(parent["funding"])),
                                     "reserve_before_sats": amount},
                             {"kind": "observed-regtest-rollover", "plan": plan, "receipt": receipt})]
    for child in receipt["successors"]:
        coin = outpoint(child["funding"])
        intent = digest({"schema": "proof-grove/protected-rollover-intent/v1",
                         "receipt_id": receipt["receipt_id"], "funding_txid": coin[0], "funding_vout": coin[1]})
        binding = {"receipt_id": receipt["receipt_id"], "funding": child["funding"]}
        entries.append(journal_entry(child, {"kind": "register", "intent": intent},
                                     {"kind": "observed-rollover-successor", **binding}))
        entries.append(journal_entry(child, {"kind": "issue", "intent": intent, "claim": bound_claim(coin)},
                                     {"kind": "admitted-rollover-successor", **binding}))
    return entries


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


def audit(core, catalog, journal, records, *, registry=None, live_receipt=None):
    """Check completeness relative to the supplied independent catalog and journal pins."""
    mint = catalog["mint"]
    profile = digest({"schema": "proof-grove/protected-accounting-mint/v3", "mint_url": mint})
    events, bundles = journal["events"], catalog["bundles"]
    if (catalog.get("schema") not in (CATALOG_SCHEMA, REGISTRY_CATALOG_SCHEMA) or catalog.get("genesis") != GENESIS
            or journal.get("schema") != JOURNAL_SCHEMA or journal.get("genesis") != GENESIS
            or journal["mint_profile_sha256"] != profile or not isinstance(mint, str) or not mint
            or not all(isinstance(items, list) for items in (bundles, events, records))
            or not 1 <= len(bundles) <= len(events) <= MAX_EVENTS or len(records) != len(events)):
        raise Refused("protected_accounting_invalid_catalog")
    uses_registry = catalog["schema"] == REGISTRY_CATALOG_SCHEMA
    if uses_registry != (registry is not None):
        raise Refused("protected_accounting_registry_profile_mismatch")
    if live_receipt is not None and not uses_registry:
        raise Refused("protected_accounting_live_issuance_requires_registry")
    if uses_registry and catalog.get("registry_sha256") != digest(registry):
        raise Refused("protected_accounting_registry_root_mismatch")
    by_coin = {}
    for bundle in bundles:
        coin = outpoint(bundle["funding"])
        if coin in by_coin or bundle.get("schema") not in (V3_BUNDLE_SCHEMA, SUCCESSOR_BUNDLE_SCHEMA):
            raise Refused("protected_accounting_duplicate_or_unsupported_reserve")
        by_coin[coin] = bundle

    tip = _chain(core)
    if (hash32(catalog["tip_hash"], "tip_hash") != tip["bestblockhash"]
            or positive(catalog["tip_height"], "tip_height", 2**31 - 1) != tip["blocks"]):
        raise Refused("protected_accounting_stale_catalog")
    registry_result = {}
    if registry is not None:
        registered, enrollment = discover(core, registry, mint, tip, max_reserves=MAX_EVENTS)
        if registered - by_coin.keys():
            raise Refused("protected_accounting_registered_reserve_omitted")
        if by_coin.keys() - registered:
            raise Refused("protected_accounting_unregistered_reserve")
        registry_result = {"registry": enrollment | {"root_sha256": digest(registry)}}

    # A confirmed rollover authorizes exactly four successive child events.
    intents, phases = {}, {}
    expected_successors = deque()
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
        if expected_successors:
            if (event, record) != expected_successors.popleft():
                raise Refused("protected_accounting_rollover_group_mismatch")
            intent = action["intent"]
            if kind == "register":
                if last is not None or intent in intents:
                    raise Refused("protected_accounting_registration_mismatch")
                intents[intent] = coin
            elif not last or last[0] != "register" or intents.get(intent) != coin:
                raise Refused("protected_accounting_rollover_group_mismatch")
        elif kind == "register" and last is None and bundle["schema"] == V3_BUNDLE_SCHEMA:
            funding = bundle["funding"] | {"sats": amount, "script": plan["funding_script"]}
            intent = hash32(action["intent"], "intent")
            if record.get("kind") != "observed-regtest-reserve" or record["funding"] != funding or intent in intents:
                raise Refused("protected_accounting_registration_mismatch")
            intents[intent] = coin
        elif kind == "issue" and last and last[0] == "register" and bundle["schema"] == V3_BUNDLE_SCHEMA:
            if intents.get(action["intent"]) != coin or action["claim"] != claim:
                raise Refused("protected_accounting_issuance_mismatch")
            check_issuance(record, bundle, mint, action["intent"], claim, amount)
        elif kind == "redeem" and last and last[0] == "issue":
            if action["input"] != claim or positive(action["reserve_before_sats"], "reserve_before_sats") != amount:
                raise Refused("protected_accounting_payout_mismatch")
            if record.get("kind") == "observed-regtest-rollover":
                receipt = record["receipt"]
                children = verify_confirmed(core, bundle, record["plan"], receipt, tip)
                if any(by_coin.get(outpoint(child["funding"])) != child for child in children):
                    raise Refused("protected_accounting_rollover_catalog_mismatch")
                parent_entry, *child_entries = rollover_entries(bundle, record["plan"], receipt)
                if (event, record) != parent_entry:
                    raise Refused("protected_accounting_rollover_group_mismatch")
                expected_successors.extend(child_entries)
            elif record.get("kind") != "observed-regtest-payout":
                raise Refused("protected_accounting_payout_mismatch")
        else:
            raise Refused("protected_accounting_invalid_transition")
        phases[coin] = kind, record
    if expected_successors:
        raise Refused("protected_accounting_rollover_group_mismatch")
    if phases.keys() != by_coin.keys():
        raise Refused("protected_accounting_catalog_omission")

    totals = {"declared_reserve_sats": 0, "outstanding_claims_sats": 0, "pending_issuance_sats": 0}
    for coin, bundle in by_coin.items():
        kind, record = phases[coin]
        if kind == "redeem" and record["kind"] == "observed-regtest-rollover":
            continue
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
    claim_result = {}
    if live_receipt is not None:
        bundle_id = hash32(live_receipt[0], "live_bundle_id")
        receipt_pin = hash32(live_receipt[1], "issuance_receipt_sha256")
        candidates = [coin for coin, bundle in by_coin.items() if bundle["bundle_id"] == bundle_id]
        if len(candidates) != 1:
            raise Refused("protected_accounting_issuance_bundle_not_registered")
        coin, = candidates
        kind, record = phases[coin]
        if kind != "issue" or record.get("kind") != "verified-cdk-protected-v3-batch":
            raise Refused("protected_accounting_issuance_not_live")
        if record.get("issuance_receipt_sha256") != receipt_pin:
            raise Refused("protected_accounting_issuance_receipt_mismatch")
        claim_result["live_issuance"] = {
            "bundle_id": bundle_id, "claim_id": bound_claim(coin), "funding_txid": coin[0], "funding_vout": coin[1],
            "amount_sats": record["amount_sats"], "issuance_receipt_sha256": receipt_pin, "mint": mint,
            "keysets_sha256": hash32(record["independent_verifier"].get("keysets_sha256"), "keysets_sha256"),
        }
    _stable_tip(core, tip)
    return totals | {"catalog_reserves": len(by_coin), "tip_hash": tip["bestblockhash"],
                     "tip_height": tip["blocks"]} | registry_result | claim_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("config", "catalog", "journal", "admission", "proof-dir", "nova-verifier"):
        parser.add_argument("--" + field, required=True, type=Path)
    for field in ("catalog-sha256", "journal-sha256", "nova-key-sha256"):
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--registry-sha256")
    parser.add_argument("--live-bundle-id")
    parser.add_argument("--issuance-receipt-sha256")
    args = parser.parse_args()
    if bool(args.registry) != bool(args.registry_sha256):
        parser.error("--registry and --registry-sha256 must be supplied together")
    if bool(args.live_bundle_id) != bool(args.issuance_receipt_sha256):
        parser.error("--live-bundle-id and --issuance-receipt-sha256 must be supplied together")
    live_receipt = (args.live_bundle_id, args.issuance_receipt_sha256) if args.live_bundle_id else None
    core = CoreClient.from_config(json.loads(read_bounded(args.config, 32768))["core"])
    catalog = pinned_json(args.catalog, args.catalog_sha256, 2 * 1024 * 1024)
    journal = pinned_json(args.journal, args.journal_sha256, 256 * 1024)
    records = json.loads(read_bounded(args.admission, 2 * 1024 * 1024))
    registry = pinned_json(args.registry, args.registry_sha256, 4096) if args.registry else None
    key_pin = hash32(args.nova_key_sha256, "nova_key_sha256")
    checked = subprocess.run([str(args.nova_verifier.resolve()), "verify-journal", str(args.proof_dir),
                              str(args.journal), args.journal_sha256], stdin=subprocess.DEVNULL,
                             capture_output=True, check=True, timeout=90)
    proof = json.loads(checked.stdout)
    if (proof.get("schema") != "proof-grove/cashu-nova-regtest-accounting/v1" or proof.get("mode") != "verify-journal"
            or proof.get("verified") is not True or proof.get("journal_sha256") != args.journal_sha256
            or proof.get("verifier_key_sha256") != key_pin or proof.get("steps") != len(journal["events"])):
        raise Refused("protected_accounting_nova_mismatch")
    result = audit(core, catalog, journal, records, registry=registry, live_receipt=live_receipt)
    if any(proof.get(field) != result[field] for field in ("declared_reserve_sats", "outstanding_claims_sats")):
        raise Refused("protected_accounting_nova_mismatch")
    print(json.dumps(result | {"schema": "proof-grove/protected-ledger-audit/v1",
                               "catalog_sha256": args.catalog_sha256, "journal_sha256": args.journal_sha256,
                               "nova": proof}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Refused as error:
        print(json.dumps({"error": error.code}), file=sys.stderr)
        raise SystemExit(1) from None
