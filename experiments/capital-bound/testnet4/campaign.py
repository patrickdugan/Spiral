#!/usr/bin/env python3
"""Stage and observe a bounded native Bitcoin settlement campaign."""
import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from core import (
    ARRIVAL_SECONDS, ASSERTION_LIMIT, FEE_LIMIT, FUNDING_LIMIT, GENESIS,
    MIN_OUTPUT, PAYMENT_LIMIT, Core, Gate, RPCError, active_output, btc,
    chain_tip, inclusion, inspect, sats, spendable, wallet_names,
)

SOURCE = Path(__file__).resolve().parent
TXID = re.compile(r"[0-9a-f]{64}")
CAMPAIGN = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
DEADLINE = 3600
REGTEST_ROUNDS = (
    (("s", "t", 1_400), ("a", "t", 2_800)),
    (("s", "a", 1_800), ("s", "b", 1_800)),
    (("b", "t", 2_200), ("a", "s", 1_400)),
)


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stamp():
    return int(time.time())


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def atomic(path, data):
    scratch = path.with_name("." + path.name + ".tmp")
    scratch.write_text(data, encoding="utf-8", newline="\n")
    scratch.replace(path)


def output(path, value):
    atomic(path, json.dumps(value, sort_keys=True, indent=2) + "\n")


def funding_reference(value):
    txid, sep, number = value.partition(":")
    if not sep or not TXID.fullmatch(txid) or not re.fullmatch("[0-9]{1,10}", number):
        raise Gate("Funding must specify a lowercase txid and a numeric vout")
    vout = int(number)
    if vout >= 2**32:
        raise Gate("Funding vout exceeds the transaction limit")
    return txid, vout


def groups(profile):
    rounds = REGTEST_ROUNDS
    if profile == "canary":
        rounds = ((("s", "t", 1_400),), (("b", "t", 1_400),))
    invoices = []
    for round_num, rows in enumerate(rounds):
        round_invoices = [
            {"id": f"invoice-{round_num}-{i}", "from": origin, "to": target,
             "sat": sat, "arrival_seconds": round_num * 2, "deadline_seconds": DEADLINE}
            for i, (origin, target, sat) in enumerate(rows)
        ]
        if profile == "individual":
            invoices.extend([row] for row in round_invoices)
        else:
            invoices.append(round_invoices)
    return invoices


class Journal:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "campaign.sqlite3", isolation_level=None, timeout=25)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, data TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS drafts (position INTEGER PRIMARY KEY, data TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS attempts (position INTEGER PRIMARY KEY, "
                        "started INTEGER, height INTEGER, event_order INTEGER)")
        self.db.execute("CREATE TABLE IF NOT EXISTS event_order (seq INTEGER PRIMARY KEY)")
        self.db.execute("CREATE TABLE IF NOT EXISTS observations (seq INTEGER PRIMARY KEY, data TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS failures (seq INTEGER PRIMARY KEY, data TEXT)")

    @contextmanager
    def locked(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def data(self, table):
        return [json.loads(r[0]) for r in self.db.execute(f"SELECT data FROM {table} ORDER BY rowid")]

    def plan(self, args):
        row = self.db.execute("SELECT data FROM metadata WHERE key='plan'").fetchone()
        if not row:
            raise Gate("Create the campaign plan first")
        value = json.loads(row[0])
        if value["campaign"] != args.campaign or value["network"] != args.network:
            raise Gate("Campaign ID or network differs from the immutable plan")
        return value

    def next_event(self):
        return self.db.execute("INSERT INTO event_order DEFAULT VALUES").lastrowid

    def failure(self, command, error):
        self.db.execute("INSERT INTO failures(data) VALUES (?)",
                        (dump({"at": stamp(), "command": command, "error": str(error)}),))


def make_plan(args, core, journal):
    funding_txid, funding_vout = funding_reference(args.funding)
    ready = inspect(core, args.campaign, args.confirmations)
    if not ready["ready"]:
        raise Gate("; ".join(ready["blockers"]))
    payer, recipient = wallet_names(args.campaign)
    if ready.get("recipient_has_outputs"):
        raise Gate("A new campaign requires a fresh recipient wallet")
    funds = spendable(core, payer, args.confirmations)
    if len(funds) != 1 or (funds[0]["txid"], funds[0]["vout"]) != (funding_txid, funding_vout):
        raise Gate("Seed the dedicated payer with exactly the named eligible funding outpoint")
    fund = funds[0]
    if not active_output(core, fund, args.confirmations):
        raise Gate("The explicit funding outpoint must be spendable on the active chain")
    schedule = groups(args.profile)
    invoice_count = sum(len(group) for group in schedule)
    total_sat = sum(item["sat"] for group in schedule for item in group)
    if not (
        1 <= args.confirmations <= 12
        and (args.network != "testnet4" or args.confirmations >= 2)
        and 1 <= len(schedule) * args.fee_sat <= FEE_LIMIT
        and invoice_count <= PAYMENT_LIMIT
        and total_sat + len(schedule) * args.fee_sat + MIN_OUTPUT <= fund["sat"] <= FUNDING_LIMIT
        and all(0 <= item["arrival_seconds"] < ARRIVAL_SECONDS for group in schedule for item in group)
    ):
        raise Gate("Plan exceeds funding, fee, confirmation or payment limits")
    plan = {
        "schema_version": 1, "campaign": args.campaign, "network": args.network,
        "profile": args.profile, "started_at": stamp(), "initial_tip": ready["tip"],
        "initial_height": ready["height"], "funding": fund, "wallets": [payer, recipient],
        "confirmations": args.confirmations, "fee_sat": args.fee_sat, "groups": schedule,
        "ceilings": {"funding_sat": FUNDING_LIMIT, "fees_sat": FEE_LIMIT,
                     "payments": PAYMENT_LIMIT, "arrival_seconds": ARRIVAL_SECONDS,
                     "simultaneous_assertions": ASSERTION_LIMIT},
    }
    with journal.locked():
        if journal.data("metadata"):
            raise Gate("The campaign plan is already sealed")
        journal.db.execute("INSERT INTO metadata VALUES ('plan', ?)", (dump(plan),))
    return {"plan": plan, "plan_sha256": digest(plan)}


def validate_tx(decoded, source, payments, change_sat, change_script):
    vin = decoded["vin"]
    if len(vin) != 1 or (vin[0]["txid"], vin[0]["vout"]) != (source["txid"], source["vout"]):
        raise Gate("Signed transaction changed the selected funding input")
    if vin[0]["sequence"] != 0xFFFFFFFE:
        raise Gate("Unexpected signed input sequence")
    want = {p["script"]: p["sat"] for p in payments} | {change_script: change_sat}
    actual = {}
    change = None
    for row in decoded["vout"]:
        script = row["scriptPubKey"]["hex"]
        if script in actual:
            raise Gate("Duplicate output script in signed transaction")
        actual[script] = sats(row["value"])
        if script == change_script:
            change = {"txid": decoded["txid"], "vout": row["n"], "sat": change_sat}
    if actual != want or change is None:
        raise Gate("Signed outputs differ from the fixed obligations and change")
    return change


def checked_relay(core, raw, txid, fee_sat):
    (verdict,) = core.rpc("testmempoolaccept", [[raw]])
    if verdict.get("txid") != txid or not verdict.get("allowed"):
        raise Gate("Bitcoin Core policy rejected the signed candidate")
    if sats(verdict["fees"]["base"]) != fee_sat:
        raise Gate("Bitcoin Core fee differs from planned fee")
    return verdict["vsize"]


def prepare(args, core, journal, plan):
    drafts = journal.data("drafts")
    position = len(drafts)
    if drafts and not args.advance:
        return drafts[0]
    if drafts and position == len(plan["groups"]):
        return drafts[-1]
    if drafts:
        previous = drafts[-1]
        latest = observe(args, core, journal, plan)
        if not latest["phases"] or latest["phases"][-1]["status"] != "recovered":
            if previous["position"] > 0:
                return previous
            raise Gate("Initial transaction lacks confirmed spendable change")
        previous_observation = latest["phases"][-1]
        if core.network == "testnet4" and not previous_observation.get("independent_inclusion"):
            raise Gate("Testnet4 advancement requires confirmation from a second node")
        source = previous["change"]
    else:
        source = plan["funding"]
    if not active_output(core, source, plan["confirmations"]):
        raise Gate("Selected funding outpoint is not spendable at the confirmed tip")
    group = plan["groups"][position]
    elapsed = stamp() - plan["started_at"]
    if not max(i["arrival_seconds"] for i in group) <= elapsed < ARRIVAL_SECONDS:
        raise Gate("Invoices have not arrived or the 48-hour arrival window has ended")
    if position == 0 and args.advance:
        raise Gate("Prepare and broadcast the first transaction before advancement")
    payer, recipient = plan["wallets"]
    payments = []
    tx_outputs = []
    for item in group:
        address = core.rpc("getnewaddress", ["", "bech32"], wallet=recipient)
        recipient_info = core.rpc("getaddressinfo", [address], wallet=recipient)
        if not recipient_info["ismine"] or core.rpc("getaddressinfo", [address], wallet=payer)["ismine"]:
            raise Gate("Recipient and payer ownership checks failed")
        payments.append({**item, "script": recipient_info["scriptPubKey"]})
        tx_outputs.append({address: btc(item["sat"])})
    change_address = core.rpc("getrawchangeaddress", ["bech32"], wallet=payer)
    change_info = core.rpc("getaddressinfo", [change_address], wallet=payer)
    if not change_info["ismine"]:
        raise Gate("Change script must belong to the dedicated payer")
    fee = plan["fee_sat"]
    change_sat = source["sat"] - sum(item["sat"] for item in payments) - fee
    if change_sat < MIN_OUTPUT:
        raise Gate("Change falls below the experiment policy floor")
    tx_outputs.append({change_address: btc(change_sat)})
    inputs = [{"txid": source["txid"], "vout": source["vout"], "sequence": 0xFFFFFFFE}]
    raw = core.rpc("createrawtransaction", [inputs, tx_outputs, 0, False])
    signed = core.rpc("signrawtransactionwithwallet", [raw], wallet=payer)
    if not signed["complete"]:
        raise Gate("Payer wallet could not sign the planned transaction")
    raw = signed["hex"]
    decoded = core.rpc("decoderawtransaction", [raw])
    change = validate_tx(decoded, source, payments, change_sat, change_info["scriptPubKey"])
    vsize = checked_relay(core, raw, change["txid"], fee)
    draft = {"position": position, "txid": change["txid"], "source": source, "change": change,
             "payments": payments, "fee_sat": fee, "vsize": vsize, "raw": raw}
    journal.db.execute("INSERT INTO drafts VALUES (?, ?)", (position, dump(draft)))
    return draft


def outpoint_wallet_evidence(core, plan, outpoint):
    evidence = active_output(core, outpoint, plan["confirmations"])
    if not evidence:
        return False
    return outpoint in spendable(core, plan["wallets"][0], plan["confirmations"])


def wallet_transaction(core, txid, wallet):
    try:
        return core.rpc("gettransaction", [txid], wallet=wallet)
    except RPCError as failure:
        if failure.code == -5:
            return None
        raise


def in_mempool(core, txid):
    try:
        core.rpc("getmempoolentry", [txid])
    except RPCError as failure:
        if failure.code == -5:
            return False
        raise
    return True


def independent_receipt(args, primary, tx, plan):
    if args.observer_datadir is None:
        return None
    other = Core(primary.network, args.observer_datadir.resolve(), args.observer_port)
    if primary.datadir == other.datadir or primary.port == other.port:
        raise Gate("Choose a distinct Bitcoin Core observer datadir and port")
    chain_tip(other)
    receipt = inclusion(other, tx["txid"], tx["blockhash"])
    if receipt["confirmations"] < plan["confirmations"]:
        raise Gate("Independent observer has insufficient confirmations")
    return {k: v for k, v in receipt.items() if k != "merkle_proof"}


def observe(args, core, journal, plan):
    drafts = journal.data("drafts")
    before = chain_tip(core)
    phases = []
    for draft in drafts:
        txid = draft["txid"]
        payer, recipient = plan["wallets"]
        wallet_tx = wallet_transaction(core, txid, payer)
        status = "mempool" if in_mempool(core, txid) else "unseen"
        row = {"txid": txid, "position": draft["position"], "status": status}
        if wallet_tx and wallet_tx["confirmations"] < 0:
            row["status"] = "conflicted"
        if wallet_tx and wallet_tx["confirmations"] > 0:
            row["status"] = "confirming"
            row["blockhash"] = wallet_tx["blockhash"]
            row["confirmations"] = wallet_tx["confirmations"]
            if wallet_tx["confirmations"] >= plan["confirmations"]:
                proof = inclusion(core, txid, wallet_tx["blockhash"])
                recipient_tx = wallet_transaction(core, txid, recipient)
                if (proof["confirmations"] < plan["confirmations"] or not recipient_tx
                        or recipient_tx.get("blockhash") != proof["blockhash"]
                        or recipient_tx["confirmations"] < plan["confirmations"]
                        or sats(recipient_tx["amount"]) != sum(p["sat"] for p in draft["payments"])):
                    raise Gate("Recipient receipt disagrees with active-chain settlement")
                row.update(status="confirmed", proof=proof, blockhash=proof["blockhash"])
                row["change_spendable"] = outpoint_wallet_evidence(core, plan, draft["change"])
                if row["change_spendable"]:
                    row["status"] = "recovered"
                independent = independent_receipt(args, core, row, plan)
                if independent:
                    row["independent_inclusion"] = independent
        phases.append(row)
    for parent, child, parent_draft, child_draft in zip(phases, phases[1:], drafts, drafts[1:]):
        if "proof" in parent and "proof" in child and parent_draft["change"] == child_draft["source"]:
            parent["status"] = "reused"
            parent["reuse_txid"] = child["txid"]
    after = chain_tip(core)
    if before["bestblockhash"] != after["bestblockhash"]:
        raise Gate("Active chain changed during observation; retry on the new tip")
    prior = journal.data("observations")
    at = max(stamp(), prior[-1]["at"] if prior else plan["started_at"])
    result = {"event_order": journal.next_event(), "at": at,
              "height": after["blocks"], "tip": after["bestblockhash"],
              "chainwork": after["chainwork"], "phases": phases}
    if prior:
        previous = prior[-1]
        previous_active = (after["blocks"] >= previous["height"] and
                           core.rpc("getblockhash", [previous["height"]]) == previous["tip"])
        result["reorg"] = not previous_active
    journal.db.execute("INSERT INTO observations(data) VALUES (?)", (dump(result),))
    return result


def draft_public(draft):
    return {key: val for key, val in draft.items() if key != "raw"}


def submit(args, core, journal, plan):
    if not args.broadcast:
        raise Gate("Broadcast requires the explicit --broadcast flag")
    if args.network == "testnet4" and plan["profile"] != "canary":
        raise Gate("Testnet4 broadcasting currently requires the bounded canary profile")
    with journal.locked():
        draft = prepare(args, core, journal, plan)
    position, txid = draft["position"], draft["txid"]
    with journal.locked():
        ready = inspect(core, args.campaign, plan["confirmations"])
        known = wallet_transaction(core, txid, plan["wallets"][0])
        if (known and known["confirmations"] > 0) or in_mempool(core, txid):
            return {"txid": txid, "submission": "already_observed"}
        attempted = journal.db.execute("SELECT 1 FROM attempts WHERE position=?", (position,)).fetchone()
        if attempted and not args.retry_same:
            raise Gate("Submission already attempted; observe or explicitly retry identical bytes")
        if not ready["ready"]:
            raise Gate("; ".join(ready["blockers"]))
        if stamp() - plan["started_at"] >= ARRIVAL_SECONDS:
            raise Gate("The 48-hour payment-arrival window has ended")
        if not active_output(core, draft["source"], plan["confirmations"]):
            raise Gate("Reserved input is no longer spendable")
        if any(p["sat"] < MIN_OUTPUT for p in draft["payments"]):
            raise Gate("Payment is below the experiment policy floor")
        checked_relay(core, draft["raw"], txid, draft["fee_sat"])
        if args.network == "testnet4" and position > 0:
            previous = journal.data("drafts")[position - 1]
            tx = wallet_transaction(core, previous["txid"], plan["wallets"][0])
            if not tx or tx["confirmations"] < plan["confirmations"] or not independent_receipt(
                    args, core, {**tx, "txid": previous["txid"]}, plan):
                raise Gate("Recheck the previous confirmation on the independent Testnet4 node")
        if not attempted:
            journal.db.execute("INSERT INTO attempts VALUES (?, ?, ?, ?)",
                               (position, stamp(), ready["height"], journal.next_event()))
    try:
        observed = core.rpc("sendrawtransaction", [draft["raw"]])
    except Gate:
        raise Gate("Submission outcome uncertain; observe the reserved transaction before retry") from None
    if observed != txid:
        raise Gate("Bitcoin Core returned a different transaction ID")
    return {"txid": txid, "submission": "accepted", "fee_sat": draft["fee_sat"]}


def emit_report(directory, journal, plan):
    from report import export

    with journal.locked():
        return export(directory, journal, plan)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", default="testnet4", choices=GENESIS)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--datadir", type=Path)
    parser.add_argument("--rpcport", type=int)
    parser.add_argument("--observer-datadir", type=Path)
    parser.add_argument("--observer-port", type=int)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--confirmations", type=int, default=2)
    plan_parser = commands.add_parser("plan")
    plan_parser.add_argument("--funding", required=True)
    plan_parser.add_argument("--profile", choices=("canary", "individual", "batched"), default="canary")
    plan_parser.add_argument("--confirmations", type=int, default=2)
    plan_parser.add_argument("--fee-sat", type=int, default=400)
    commands.add_parser("dry-run").add_argument("--advance", action="store_true")
    broadcast = commands.add_parser("broadcast-canary")
    broadcast.add_argument("--broadcast", action="store_true")
    broadcast.add_argument("--advance", action="store_true")
    broadcast.add_argument("--retry-same", action="store_true")
    commands.add_parser("observe")
    commands.add_parser("reconcile")
    commands.add_parser("report")
    return parser.parse_args(argv)


def main(argv=None):
    args = cli(argv)
    if __name__ == "__main__":
        sys.modules.setdefault("campaign", sys.modules[__name__])
    if not CAMPAIGN.fullmatch(args.campaign):
        print("Campaign ID must use 1-32 lowercase ASCII letters, digits or hyphens.", file=sys.stderr)
        return 2
    args.state = args.state.resolve()
    journal = Journal(args.state)
    try:
        if args.command == "report":
            result = emit_report(args.state, journal, journal.plan(args))
        else:
            if args.datadir is None:
                raise Gate("Provide the existing Bitcoin Core --datadir for RPC commands")
            args.datadir = args.datadir.resolve()
            core = Core(args.network, args.datadir, args.rpcport)
            if args.command == "preflight":
                result = inspect(core, args.campaign, args.confirmations)
                output(args.state / "testnet4-readiness.json", result)
                print(dump(result))
                return 0 if result["ready"] else 2
            if args.command == "plan":
                result = make_plan(args, core, journal)
            else:
                plan = journal.plan(args)
                chain_tip(core)
                if args.command == "dry-run":
                    with journal.locked():
                        result = draft_public(prepare(args, core, journal, plan))
                elif args.command == "broadcast-canary":
                    result = submit(args, core, journal, plan)
                else:
                    with journal.locked():
                        result = observe(args, core, journal, plan)
                    if args.command == "reconcile":
                        result = emit_report(args.state, journal, plan)
        print(dump(result))
        return 0
    except Gate as error:
        journal.failure(args.command, error)
        print(str(error), file=sys.stderr)
        return 2
    finally:
        journal.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
