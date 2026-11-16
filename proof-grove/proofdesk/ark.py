"""Bark-backed monitoring and regtest-only delegated refresh.

Bark validates Ark signatures and ownership. Core independently observes chain
anchors. Neither a JSON wallet response nor an anchor is a full Ark proof here.
The released REST API cannot enforce a fee cap at signing, so dispatch is
deliberately restricted to regtest. An ambiguous POST is never sent twice.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time

from .domain import MAX_SATS, Refused, canonical, digest

OUTPOINT = re.compile(r"[0-9a-f]{64}:(?:0|[1-9][0-9]{0,9})\Z")


def integer(value, low=0, high=MAX_SATS):
    if type(value) is not int or not low <= value <= high:
        raise Refused("invalid_ark_integer")
    return value


def ids(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 100:
        raise Refused("invalid_ark_inputs")
    if any(not isinstance(v, str) or not OUTPOINT.fullmatch(v) for v in value) or len(set(value)) != len(value):
        raise Refused("invalid_ark_inputs")
    return sorted(value)


def refresh_fee(schedule, vtxos, height):
    """Upstream sums fractional ppm charges before a single ceiling."""
    base = integer(schedule.get("base_fee_sat"))
    table = schedule.get("ppm_expiry_table")
    if not isinstance(table, list) or len(table) > 100:
        raise Refused("invalid_ark_fee_schedule")
    previous, ppm, entries = -1, -1, []
    for entry in table:
        threshold = integer(entry.get("expiry_blocks_threshold"), high=2**32-1)
        rate = integer(entry.get("ppm"), high=2**64-1)
        if threshold <= previous or rate < ppm:
            raise Refused("invalid_ark_fee_schedule")
        previous, ppm = threshold, rate
        entries.append((threshold, rate))
    numerator = 0
    for v in vtxos:
        remaining = max(0, integer(v.get("expiry_height"), high=2**32-1) - height)
        rate = next((rate for threshold, rate in reversed(entries) if remaining >= threshold), 0)
        numerator += integer(v.get("amount_sat"), 1) * rate
    return integer(base + (numerator + 999999) // 1000000)


class ArkCaretaker:
    def __init__(self, ledger, bark, core, *, allow_regtest=False, confirmations=2):
        self.ledger, self.bark, self.core = ledger, bark, core
        self.allow_regtest = allow_regtest
        self.confirmations = integer(confirmations, 1, 100)
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS ark_operations (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                request TEXT NOT NULL, result TEXT, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS ark_inputs (
                vtxo TEXT PRIMARY KEY, operation_id TEXT NOT NULL REFERENCES ark_operations(id));
        """)

    def chain(self):
        info = self.core.rpc("getblockchaininfo", [])
        if info.get("initialblockdownload") is not False:
            raise Refused("core_not_ready")
        network = {"main": "mainnet", "regtest": "regtest", "testnet4": "testnet4", "signet": "signet"}.get(info.get("chain"))
        if not network:
            raise Refused("unsupported_ark_network")
        integer(info.get("blocks"), high=2**32-1)
        return info | {"network": network}

    def anchor(self, vtxo, chain):
        identifier = vtxo.get("chain_anchor")
        if not isinstance(identifier, str) or not OUTPOINT.fullmatch(identifier):
            raise Refused("invalid_ark_anchor")
        txid, index = identifier.split(":")
        tx = self.core.rpc("getrawtransaction", [txid, True])
        if tx.get("txid") != txid or integer(tx.get("confirmations", 0)) < self.confirmations:
            raise Refused("ark_anchor_unconfirmed")
        block = self.core.rpc("getblockheader", [tx["blockhash"]])
        if self.core.rpc("getblockhash", [block["height"]]) != tx["blockhash"]:
            raise Refused("ark_anchor_reorged")
        outputs = tx.get("vout", [])
        if int(index) >= len(outputs) or outputs[int(index)].get("n") != int(index):
            raise Refused("invalid_ark_anchor")
        return {"outpoint": identifier, "block_hash": tx["blockhash"], "height": block["height"],
                "confirmations": chain["blocks"] - block["height"] + 1}

    def identity(self):
        return digest({"endpoint": self.bark.http.base, "address_zero": self.bark.read("identity")})

    def snapshot(self):
        chain = self.chain()
        info, vtxos = self.bark.read("info"), self.bark.read("vtxos")
        if not isinstance(info, dict) or info.get("network") != chain["network"] or not isinstance(vtxos, list):
            raise Refused("ark_network_mismatch")
        rows = []
        for v in vtxos:
            ids([v.get("id")]); integer(v.get("amount_sat"), 1)
            remaining = integer(v.get("expiry_height"), high=2**32-1) - chain["blocks"]
            try:
                anchor, error = self.anchor(v, chain), None
            except Refused as e:
                anchor, error = None, e.code
            rows.append({**v, "remaining_blocks": remaining, "anchor_observation": anchor, "anchor_error": error})
        self.unchanged(chain)
        return {"evidence_level": "bark-wallet-report+core-anchor-observation", "network": chain["network"],
                "tip_height": chain["blocks"], "tip_hash": chain["bestblockhash"], "vtxos": rows,
                "regtest_execution": self.allow_regtest and chain["network"] == "regtest" and self.ledger.namespace == "regtest",
                "fee_limit": "preflight only; production dispatch disabled",
                "meaning": "Bark validates Ark signatures and ownership. Core checks active-chain anchors; this desk does not independently verify Ark scripts."}

    def unchanged(self, chain):
        if self.chain()["bestblockhash"] != chain["bestblockhash"]:
            raise Refused("chain_changed_retry")

    def operation(self, identifier):
        row = self.ledger.db.execute("SELECT * FROM ark_operations WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise Refused("unknown_ark_operation")
        return {**dict(row), "request": json.loads(row["request"]), "result": json.loads(row["result"]) if row["result"] else None}

    def operations(self):
        return [{"id": r["id"], "kind": r["kind"], "state": r["state"], "created_at": r["created_at"]}
                for r in self.ledger.db.execute("SELECT id,kind,state,created_at FROM ark_operations ORDER BY created_at")]

    def save(self, identifier, state, result):
        self.ledger.db.execute("UPDATE ark_operations SET state=?,result=? WHERE id=?", (state, canonical(result).decode(), identifier))
        return {"id": identifier, "state": state, "result": result}

    def refresh(self, identifiers, height, max_fee_sats):
        identifiers, height = ids(identifiers), integer(height, 1, 2**32-1)
        cap = integer(max_fee_sats)
        if self.ledger.namespace != "regtest" or not self.allow_regtest or self.chain()["network"] != "regtest":
            raise Refused("ark_production_signing_cap_required")
        identity = self.identity()
        identifier = digest({"wallet": identity, "inputs": identifiers})
        old = self.ledger.db.execute("SELECT id FROM ark_operations WHERE id=?", (identifier,)).fetchone()
        if old:
            op = self.operation(identifier)
            if op["request"]["height"] != height or op["request"]["max_fee_sats"] != cap:
                raise Refused("ark_request_immutable")
            return self.reconcile(identifier)
        snapshot = self.snapshot()
        selected = [v for v in snapshot["vtxos"] if v["id"] in identifiers]
        if len(selected) != len(identifiers) or any(v.get("state", {}).get("type") != "spendable" or v["anchor_error"] for v in selected):
            raise Refused("ark_inputs_not_ready")
        if not snapshot["tip_height"] < height < min(v["expiry_height"] for v in selected):
            raise Refused("invalid_ark_schedule")
        estimate = refresh_fee(self.bark.read("info")["fees"]["refresh"], selected, height)
        if estimate > cap:
            raise Refused("ark_fee_exceeds_preflight_limit")
        request = {"wallet": identity, "inputs": identifiers, "height": height, "max_fee_sats": cap,
                   "estimated_fee_sats": estimate, "input_vtxos": selected}
        db = self.ledger.db
        try:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ark_exit_inputs'").fetchone():
                if any(db.execute("SELECT exit_id FROM ark_exit_inputs WHERE vtxo=?", (v,)).fetchone() for v in identifiers):
                    raise Refused("ark_input_already_reserved")
            db.execute("INSERT INTO ark_operations VALUES (?,'refresh','dispatching',?,NULL,?)", (identifier, canonical(request).decode(), int(time.time())))
            for v in identifiers:
                db.execute("INSERT INTO ark_inputs VALUES (?,?)", (v, identifier))
            db.execute("COMMIT")
        except sqlite3.IntegrityError:
            db.execute("ROLLBACK")
            raise Refused("ark_input_already_reserved") from None
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        # Commit intent BEFORE remote signing. A crash here also requires reconciliation.
        try:
            result = self.bark.delegate_refresh(identifiers, height)
        except Refused:
            return self.save(identifier, "uncertain", {"meaning": "Read wallet rounds/history; no automatic resend."})
        self.save(identifier, "submitted", {"round": result})
        return self.reconcile(identifier)

    def reconcile(self, identifier):
        op = self.operation(identifier); request = op["request"]
        if self.identity() != request["wallet"]:
            raise Refused("ark_wallet_changed")
        chain = self.chain()
        if chain["network"] != "regtest" or self.ledger.namespace != "regtest":
            raise Refused("ark_network_mismatch")
        expected = request["inputs"]
        movements = self.bark.read("history")
        candidates = [m for m in movements if sorted(m.get("input_vtxos", [])) == expected]
        if len(candidates) > 1:
            raise Refused("ark_ambiguous_history")
        if not candidates:
            rounds = [r for r in self.bark.read("rounds") if sorted(r.get("participation", {}).get("inputs", [])) == expected]
            if len(rounds) == 1:
                return self.save(identifier, "pending", {"round": rounds[0]})
            return self.save(identifier, "uncertain", {"meaning": "No unique wallet record; do not resend the signing request."})
        movement = candidates[0]
        if movement.get("subsystem") != {"name": "bark.round", "kind": "refresh"} or movement.get("sent_to"):
            return self.save(identifier, "review_required", {"reason": "Input was used by a different wallet action"})
        status = movement.get("status")
        if status != "successful":
            return self.save(identifier, "failed" if status == "failed" else "pending", {"movement": movement})
        successors = [self.bark.vtxo(v) for v in ids(movement.get("output_vtxos"))]
        total_in = sum(v["amount_sat"] for v in request["input_vtxos"])
        total_out = sum(integer(v.get("amount_sat"), 1) for v in successors)
        fee = total_in - total_out
        if not 0 <= fee <= request["max_fee_sats"] or fee != movement.get("offchain_fee_sat"):
            return self.save(identifier, "review_required", {"reason": "Signed fee differs from the recorded budget", "actual_fee_sats": fee})
        if any(v["expiry_height"] <= max(old["expiry_height"] for old in request["input_vtxos"]) for v in successors):
            return self.save(identifier, "review_required", {"reason": "Successor does not extend the input expiry"})
        for old in expected:
            if self.bark.vtxo(old).get("state", {}).get("type") != "spent":
                return self.save(identifier, "pending", {"movement": movement})
        try:
            anchors = [self.anchor(v, chain) for v in successors]
        except Refused as e:
            return self.save(identifier, "chain_unconfirmed", {"reason": e.code, "successors": successors})
        self.unchanged(chain)
        return self.save(identifier, "confirmed", {"movement_id": movement["id"], "actual_fee_sats": fee,
                         "successors": successors, "anchors": anchors, "tip_hash": chain["bestblockhash"],
                         "evidence_level": "bark-wallet-validation+core-anchor-observation"})
