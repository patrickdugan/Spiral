"""Local holder commands for the protected reserve profile."""

import json
from pathlib import Path

from . import protected_reserve, protected_rollover
from .adapters import CoreClient
from .domain import Refused
from .verifier import read_bounded


def configure(commands):
    plan = commands.add_parser("protected-plan", help="Pin protected reserve terms and derive the regtest funding address")
    plan.add_argument("--config", required=True)
    plan.add_argument("--profile", choices=("v2", "v3"), default="v2",
                      help="Use v3 to commit to the ordered blinded issuance batch")
    for key in ("holder-pubkey", "mint-pubkey", "claim-commitment", "payout-address", "output"):
        plan.add_argument("--" + key, required=True)
    for key in ("reserve-sats", "fee-sats", "delay-blocks"):
        plan.add_argument("--" + key, required=True, type=int)
    plan.add_argument("--min-confirmations", default=2, type=int)

    attach = commands.add_parser("protected-attach", help="Verify funding and save the exact coin and plan")
    attach.add_argument("--config", required=True)
    for key in ("plan", "plan-id", "txid", "block", "output"):
        attach.add_argument("--" + key, required=True)
    attach.add_argument("--vout", required=True, type=int)

    for action, help_text in (
        ("status", "Observe the protected outpoint and maturity"),
        ("psbt", "Export a checked external-signer PSBT"),
        ("check", "Check a fully signed redemption against the saved plan and Core policy"),
    ):
        parser = commands.add_parser("protected-" + action, help=help_text)
        for key in ("config", "bundle", "bundle-id"):
            parser.add_argument("--" + key, required=True)
        parser.add_argument("--active-funding-block", help="Reobserve the same outpoint in this active block for local holder recovery")
        if action != "status":
            parser.add_argument("--route", choices=("holder", "cooperative"), required=True)
        if action == "psbt":
            parser.add_argument("--output", required=True)
        if action == "check":
            parser.add_argument("--tx-file", required=True, help="File containing the signed transaction hex")

    for action, help_text in (
        ("plan", "Pin an exact two-recipient protected reserve split"),
        ("psbt", "Export a holder-only split PSBT"),
        ("check", "Check a signed split against its plan and Core policy"),
        ("confirm", "Attach both successors after the split confirms"),
    ):
        parser = commands.add_parser("protected-rollover-" + action, help=help_text)
        for key in ("config", "bundle", "bundle-id"):
            parser.add_argument("--" + key, required=True)
        if action == "plan":
            parser.add_argument("--recipient", action="append", required=True, help="Recipient terms JSON, supplied twice in output order")
            parser.add_argument("--split-fee-sats", type=int, required=True)
        else:
            parser.add_argument("--rollover", required=True)
            parser.add_argument("--rollover-id", required=True)
        if action == "check":
            parser.add_argument("--tx-file", required=True)
        else:
            parser.add_argument("--output", required=True)
        if action == "confirm":
            parser.add_argument("--txid", required=True)
            parser.add_argument("--block", required=True)


def _load(path):
    value = json.loads(read_bounded(path, 32768))
    if not isinstance(value, dict):
        raise Refused("protected_invalid_document")
    return value


def _write(path, content):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.write("\n")


def _rollover(core, args, bundle):
    if args.command == "protected-rollover-plan":
        result = protected_rollover.plan(core, bundle, args.bundle_id,
                                         [_load(path) for path in args.recipient], args.split_fee_sats)
        _write(args.output, json.dumps(result, indent=2))
        return {"rollover_id": result["rollover_id"]}
    inputs = (core, bundle, args.bundle_id, _load(args.rollover), args.rollover_id)
    if args.command == "protected-rollover-psbt":
        result = protected_rollover.unsigned_psbt(*inputs)
        _write(args.output, result.pop("psbt"))
        return result
    if args.command == "protected-rollover-check":
        raw = read_bounded(args.tx_file, 16002).decode("ascii").strip()
        return protected_rollover.check_signed(*inputs, raw)
    if args.command == "protected-rollover-confirm":
        result = protected_rollover.confirm(*inputs, args.txid, args.block)
        _write(args.output, json.dumps(result, indent=2))
        return {"receipt_id": result["receipt_id"], "successors": [child["bundle_id"] for child in result["successors"]]}
    raise Refused("protected_invalid_command")


def run(args):
    core = CoreClient.from_config(_load(args.config)["core"])
    if args.command == "protected-plan":
        terms = {key: getattr(args, key) for key in protected_reserve.PLAN_FIELDS}
        schema = protected_reserve.V3_PLAN_SCHEMA if args.profile == "v3" else protected_reserve.PLAN_SCHEMA
        result = protected_reserve.plan(core, schema=schema, **terms)
        _write(args.output, json.dumps(result, indent=2))
        return {key: result[key] for key in ("plan_id", "funding_address", "reserve_sats")}
    if args.command == "protected-attach":
        outpoint = {"txid": args.txid, "vout": args.vout, "block": args.block}
        result = protected_reserve.attach(core, _load(args.plan), args.plan_id, outpoint)
        _write(args.output, json.dumps(result, indent=2))
        return {"bundle_id": result["bundle_id"], "funding": result["funding"]}
    bundle = _load(args.bundle)
    if args.command.startswith("protected-rollover-"):
        return _rollover(core, args, bundle)
    evidence = {"active_funding_block": args.active_funding_block}
    if args.command == "protected-status":
        return protected_reserve.holder_status(core, bundle, args.bundle_id, **evidence)
    if args.command == "protected-psbt":
        result = protected_reserve.unsigned_psbt(core, bundle, args.bundle_id, args.route, **evidence)
        _write(args.output, result.pop("psbt"))
        return result
    if args.command == "protected-check":
        tx = read_bounded(args.tx_file, 16002).decode("ascii").strip()
        return protected_reserve.check_signed(core, bundle, args.bundle_id, args.route, tx, **evidence)
    raise Refused("protected_invalid_command")
