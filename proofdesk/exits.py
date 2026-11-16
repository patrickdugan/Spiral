"""Saved Bark exit packages and a Core-backed, regtest-only broadcaster.

Preparation checks transaction identities, topology and exact fees. Core checks
scripts/policy as each wave becomes eligible. No boolean or CID substitutes for
those checks. This module needs no Bark connection after a package is saved.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import re
import time

from .ark import ids, integer
from .adapters import CoreRPCError
from .domain import MAX_SATS, Refused, canonical, digest

HEX = re.compile(r"(?:[0-9a-f]{2})+\Z")
TXID = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "proof-grove/ark-exit/v1"


def sats(value):
    try:
        scaled = Decimal(str(value)) * 100000000
        if not scaled.is_finite() or scaled != scaled.to_integral_value():
            raise Refused("invalid_exit_amount")
        return integer(int(scaled))
    except (InvalidOperation, ValueError, TypeError):
        raise Refused("invalid_exit_amount") from None


def chain(core):
    info = core.rpc("getblockchaininfo", [])
    if info.get("chain") != "regtest" or info.get("initialblockdownload") is not False:
        raise Refused("exit_regtest_required")
    return info


def observed(core, txid):
    try:
        tx = core.rpc("getrawtransaction", [txid, True])
    except CoreRPCError as error:
        if error.rpc_code == -5:return None  # Unknown transaction; other observer errors must propagate.
        raise
    if tx.get("txid") != txid:
        raise Refused("exit_transaction_identity")
    if tx.get("confirmations", 0) > 0:
        header = core.rpc("getblockheader", [tx["blockhash"]])
        if core.rpc("getblockhash", [header["height"]]) != tx["blockhash"]:
            return None
        return {"txid": txid, "confirmations": tx["confirmations"], "height": header["height"], "block_hash": tx["blockhash"]}
    if tx.get("confirmations", 0) < 0:
        return None
    try:
        if not isinstance(core.rpc("getmempoolentry", [txid]), dict):raise Refused("core_rpc_error")
    except CoreRPCError as error:
        if error.rpc_code == -5:return None  # Known orphan is not evidence of current mempool admission.
        raise
    return {"txid": txid, "confirmations": 0}


def unpack(core, plan):
    """Decode through Core, then independently bind IDs, order and metadata."""
    if not isinstance(plan, dict) or not isinstance(plan.get("exits"), list) or not isinstance(plan.get("waves"), list):
        raise Refused("invalid_exit_plan")
    requested = ids([entry.get("vtxo_id") for entry in plan["exits"]])
    if len(plan["waves"]) > 100 or len(canonical(plan)) > 1500000:
        raise Refused("exit_plan_too_large")
    if any(entry.get("status", {}).get("type") != "fully-signed" or entry.get("unsigned") != [] for entry in plan["exits"]):
        raise Refused("exit_plan_incomplete")
    txs, waves = {}, []
    def decode(record, wave, role):
        if not isinstance(record, dict):raise Refused("invalid_exit_transaction")
        raw, txid = record.get("tx"), record.get("txid")
        if not isinstance(raw, str) or not 20 <= len(raw) <= 200000 or not HEX.fullmatch(raw):
            raise Refused("invalid_exit_transaction")
        if not isinstance(txid, str) or not TXID.fullmatch(txid) or txid in txs:
            raise Refused("exit_transaction_identity")
        tx = core.rpc("decoderawtransaction", [raw])
        if tx.get("txid") != txid or not tx.get("vin") or not tx.get("vout"):
            raise Refused("exit_transaction_identity")
        txs[txid] = {"raw": raw, "tx": tx, "wave": wave, "role": role}
        if len(txs) > 200:raise Refused("exit_plan_too_large")
        return txid
    for wi, wave in enumerate(plan["waves"]):
        if not isinstance(wave, dict) or not isinstance(wave.get("packages"), list) or not isinstance(wave.get("in_mempool"), list):
            raise Refused("invalid_exit_wave")
        row = {"packages": [], "in_mempool": []}
        if wi and wave["in_mempool"]:raise Refused("invalid_exit_wave")
        for entry in wave["in_mempool"]:
            row["in_mempool"].append(decode(entry, wi, "relayed"))
        for package in wave["packages"]:
            if package.get("vtxo_id") not in requested:raise Refused("exit_target_mismatch")
            parent = decode(package.get("exit"), wi, "parent")
            child = decode(package.get("child"), wi, "child")
            row["packages"].append({"parent": parent, "child": child, "vtxo_id": package["vtxo_id"],
                                    "fee_sats": integer(package["child"].get("fee_info", {}).get("total_fee_sat"))})
        if not row["packages"] and not row["in_mempool"]:raise Refused("invalid_exit_wave")
        waves.append(row)
    return requested, txs, waves


def validate(core, envelope):
    info = chain(core)
    if envelope.get("schema") != SCHEMA or envelope.get("network") != "regtest":
        raise Refused("invalid_exit_bundle")
    cap = integer(envelope.get("max_fee_sats"))
    requested, txs, waves = unpack(core, envelope.get("plan"))
    descriptors = envelope.get("vtxos")
    if not isinstance(descriptors, list) or ids([v.get("id") for v in descriptors]) != requested:
        raise Refused("exit_target_mismatch")
    external, spent, total = {}, set(), 0
    def previous(txid, index):
        integer(index, high=2**32-1)
        if txid in txs:
            tx = txs[txid]["tx"]
        else:
            if not isinstance(txid, str) or not TXID.fullmatch(txid):raise Refused("invalid_exit_prevout")
            if txid not in external:
                value = core.rpc("getrawtransaction", [txid, True])
                if value.get("txid") != txid:raise Refused("exit_transaction_identity")
                external[txid] = value
            tx = external[txid]
        if index >= len(tx["vout"]) or tx["vout"][index].get("n") != index:
            raise Refused("invalid_exit_prevout")
        return tx["vout"][index]
    for txid, entry in txs.items():
        value_in = 0
        for vin in entry["tx"]["vin"]:
            prev, index = vin.get("txid"), vin.get("vout")
            out = previous(prev, index)
            point = (prev, index)
            if point in spent:raise Refused("exit_double_spend")
            spent.add(point)
            if prev in txs:
                own_parent = entry["role"] == "child" and txs[prev]["role"] == "parent" and txs[prev]["wave"] == entry["wave"]
                if txs[prev]["wave"] >= entry["wave"] and not own_parent:
                    raise Refused("exit_wave_dependency")
            value_in += sats(out["value"])
        value_out = sum(sats(out["value"]) for out in entry["tx"]["vout"])
        fee = value_in - value_out
        if not 0 <= fee <= MAX_SATS:raise Refused("invalid_exit_fee")
        entry["fee_sats"] = fee
        if entry["role"] == "parent" and fee != 0:raise Refused("exit_parent_fee_mismatch")
    for wave in waves:
        for package in wave["packages"]:
            parent, child = txs[package["parent"]], txs[package["child"]]
            anchors = [out["n"] for out in parent["tx"]["vout"] if out.get("scriptPubKey", {}).get("hex") == "51024e73" and sats(out["value"]) == 0]
            if len(anchors) != 1 or not any(v.get("txid") == package["parent"] and v.get("vout") == anchors[0] for v in child["tx"]["vin"]):
                raise Refused("exit_fee_anchor_missing")
            # No unrelated zero-fee parent may be smuggled into a package.
            if any(v.get("txid") in txs and txs[v["txid"]]["wave"] == child["wave"] and v["txid"] != package["parent"] for v in child["tx"]["vin"]):
                raise Refused("exit_wave_dependency")
            if child["fee_sats"] != package["fee_sats"]:raise Refused("exit_fee_metadata_mismatch")
            total += child["fee_sats"]
    if total > cap:raise Refused("exit_fee_budget_exceeded")
    necessary = set()
    for vtxo in descriptors:
        txid, index = vtxo["id"].split(":")
        final = previous(txid, int(index))
        if sats(final["value"]) != integer(vtxo.get("amount_sat"), 1):raise Refused("exit_target_mismatch")
        integer(vtxo.get("expiry_height"), 1, 2**32-1)
        integer(vtxo.get("exit_delta"), 1, 65535)
        anchor_txid, anchor_index = ids([vtxo.get("chain_anchor")])[0].split(":")
        # The selected anchor must be an ancestor of the final VTXO outpoint.
        frontier, seen, anchored = [txid], set(), False
        while frontier and not anchored:
            current = frontier.pop()
            if current in seen:continue
            seen.add(current)
            necessary.add(current)
            if len(seen) > 200:raise Refused("exit_ancestry_too_large")
            if current in txs:
                ancestor = txs[current]["tx"]
            else:
                if current not in external:external[current] = core.rpc("getrawtransaction", [current, True])
                ancestor = external[current]
            for vin in ancestor.get("vin", []):
                if vin.get("txid") == anchor_txid and vin.get("vout") == int(anchor_index):anchored = True
                elif vin.get("txid"):frontier.append(vin["txid"])
        if not anchored and vtxo["id"] != vtxo["chain_anchor"]:
            raise Refused("exit_anchor_disconnected")
    if any(entry["role"] == "parent" and txid not in necessary for txid, entry in txs.items()):
        raise Refused("exit_unrelated_transaction")
    if chain(core)["bestblockhash"] != info["bestblockhash"]:raise Refused("chain_changed_retry")
    return {"txs": txs, "waves": waves, "fee_sats": total, "tip_height": info["blocks"], "tip_hash": info["bestblockhash"]}


class ExitRecovery:
    def __init__(self, ledger, core, *, broadcaster=False):
        self.ledger, self.core, self.broadcaster = ledger, core, broadcaster
        self._validated = {}  # Immutable identities/topology/fees only; never eligibility or confirmations.
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS ark_exits (
                id TEXT PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL,
                observation TEXT, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS ark_exit_inputs (
                vtxo TEXT PRIMARY KEY, exit_id TEXT NOT NULL REFERENCES ark_exits(id));
        """)

    def store(self, envelope, expected_id=None):
        if self.ledger.namespace != "regtest":raise Refused("exit_regtest_required")
        identifier = digest(envelope)
        if expected_id is not None and expected_id != identifier:raise Refused("exit_bundle_hash_mismatch")
        checked = validate(self.core, envelope)
        self._validated[identifier] = checked
        db = self.ledger.db
        metadata = {"waves": len(checked["waves"]), "fee_sats": checked["fee_sats"]}
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO ark_exits VALUES (?,?,'prepared',?,?)", (identifier, canonical(envelope).decode(), canonical(metadata).decode(), int(time.time())))
            for v in envelope["vtxos"]:
                if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ark_inputs'").fetchone():
                    if db.execute("SELECT operation_id FROM ark_inputs WHERE vtxo=?", (v["id"],)).fetchone():
                        raise Refused("ark_input_already_reserved")
                old = db.execute("SELECT exit_id FROM ark_exit_inputs WHERE vtxo=?", (v["id"],)).fetchone()
                if old and old[0] != identifier:raise Refused("ark_input_already_reserved")
                db.execute("INSERT OR IGNORE INTO ark_exit_inputs VALUES (?,?)", (v["id"], identifier))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        state = db.execute("SELECT state FROM ark_exits WHERE id=?", (identifier,)).fetchone()[0]
        return {"id": identifier, "state": state, "waves": len(checked["waves"]), "fee_sats": checked["fee_sats"],
                "meaning": "Structure and fees checked. Core script validation occurs before each wave is broadcast."}

    def prepare(self, caretaker, identifiers, fee_rate, max_fee_sats):
        if not caretaker.allow_regtest or self.ledger.namespace != "regtest":raise Refused("exit_regtest_required")
        identifiers = ids(identifiers);integer(fee_rate, 1, 1000);integer(max_fee_sats)
        chain(self.core)
        locks = [self.ledger.db.execute("SELECT exit_id FROM ark_exit_inputs WHERE vtxo=?", (v,)).fetchone() for v in identifiers]
        if any(locks):
            locked = {row[0] for row in locks if row}
            if not all(locks) or len(locked) != 1:raise Refused("ark_input_already_reserved")
            identifier = next(iter(locked));body = self.bundle(identifier)
            if ids([v["id"] for v in body["vtxos"]]) != identifiers or body["max_fee_sats"] != max_fee_sats or body.get("fee_rate_sat_per_vb") != fee_rate:
                raise Refused("exit_request_immutable")
            row = next(row for row in self.records() if row["id"] == identifier)
            return {"id": identifier, "state": row["state"], **(row["observation"] or {}), "idempotent_replay": True}
        if self.ledger.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ark_inputs'").fetchone():
            if any(self.ledger.db.execute("SELECT operation_id FROM ark_inputs WHERE vtxo=?", (v,)).fetchone() for v in identifiers):
                raise Refused("ark_input_already_reserved")
        snapshot = caretaker.snapshot()
        if snapshot["network"] != "regtest":raise Refused("exit_regtest_required")
        selected = [v for v in snapshot["vtxos"] if v["id"] in identifiers]
        if len(selected) != len(identifiers) or any(v["anchor_error"] or v.get("state", {}).get("type") != "spendable" for v in selected):
            raise Refused("ark_inputs_not_ready")
        plan = caretaker.bark.presign(identifiers, fee_rate)
        descriptors = [{key: v[key] for key in ("id", "amount_sat", "chain_anchor", "expiry_height", "exit_delta")} for v in selected]
        envelope = {"schema": SCHEMA, "network": "regtest", "max_fee_sats": max_fee_sats, "fee_rate_sat_per_vb": fee_rate,
                    "vtxos": descriptors, "plan": plan}
        checked = validate(self.core, envelope)
        runway = max(v["exit_delta"] for v in selected) + 6 * len(checked["waves"]) + 6
        if min(v["expiry_height"] for v in selected) - checked["tip_height"] <= runway:
            raise Refused("exit_runway_insufficient")
        return self.store(envelope)

    def bundle(self, identifier):
        row = self.ledger.db.execute("SELECT body FROM ark_exits WHERE id=?", (identifier,)).fetchone()
        if row is None:raise Refused("unknown_exit_bundle")
        body = json.loads(row[0])
        if digest(body) != identifier:raise Refused("exit_bundle_hash_mismatch")
        return body

    def records(self):
        return [{"id": row["id"], "state": row["state"], "created_at": row["created_at"],
                 "observation": json.loads(row["observation"]) if row["observation"] else None}
                for row in self.ledger.db.execute("SELECT id,state,created_at,observation FROM ark_exits ORDER BY created_at")]

    def save(self, identifier, state, observation):
        self.ledger.db.execute("UPDATE ark_exits SET state=?,observation=? WHERE id=?", (state, canonical(observation).decode(), identifier))
        return {"id": identifier, "state": state, **observation}

    def advance(self, identifier, *, broadcast=False):
        if self.ledger.namespace != "regtest":raise Refused("exit_regtest_required")
        body = self.bundle(identifier)
        checked = self._validated.get(identifier)
        if checked is None:
            checked = validate(self.core, body);self._validated[identifier] = checked
        info = chain(self.core)
        if broadcast and not self.broadcaster:raise Refused("exit_broadcast_disabled")
        if info["blocks"] >= min(v["expiry_height"] for v in body["vtxos"]):
            return self.save(identifier, "expiry_reached", {"reason": "Expiry reached; review recovery and competing spends manually"})
        for wi, wave in enumerate(checked["waves"]):
            points = wave["in_mempool"] + [p[k] for p in wave["packages"] for k in ("parent", "child")]
            observations = {txid: observed(self.core, txid) for txid in points}
            if all(row and row["confirmations"] >= 2 for row in observations.values()):continue
            if any(observations[txid] is None for txid in wave["in_mempool"]):
                return self.save(identifier, "needs_represign", {"wave": wi, "reason": "Previously relayed transaction is missing"})
            for package in wave["packages"]:
                if all(observations[package[k]] for k in ("parent", "child")):continue
                if observations[package["child"]] and not observations[package["parent"]]:
                    raise Refused("chain_changed_retry")
                missing = [k for k in ("parent", "child") if not observations[package[k]]]
                raws = [checked["txs"][package[k]]["raw"] for k in missing]
                # Check all external fee inputs are currently available. A successful
                # prior submission is recognized above by its immutable transaction IDs.
                for k in missing:
                    for vin in checked["txs"][package[k]]["tx"]["vin"]:
                        if vin["txid"] == package["parent"] and "parent" in missing:continue
                        if self.core.rpc("gettxout", [vin["txid"], vin["vout"], True]) is None:
                            return self.save(identifier, "inputs_unavailable", {"wave": wi, "reason": "A saved package input is spent, missing or reorged"})
                admission = self.core.rpc("testmempoolaccept", [raws])
                if isinstance(admission, list) and any(row.get("reject-reason") in ("non-final", "non-BIP68-final") for row in admission):
                    return self.save(identifier, "timelock_wait", {"wave": wi, "reason": "Core reports an immature timelock; recheck after the chain advances"})
                complete_check = isinstance(admission, list) and len(admission) == len(raws) and all(row.get("allowed") is True for row in admission)
                # Core 31's dry-run rejects a zero-fee parent before validating
                # its CPFP child. submitpackage performs the combined-fee check.
                # This exact known dry-run limitation is not signature evidence.
                package_check_required = (len(raws) == 2 and isinstance(admission, list) and len(admission) == 2
                    and admission[0].get("txid") == package["parent"] and admission[0].get("allowed") is False
                    and admission[0].get("reject-reason") == "min relay fee not met"
                    and admission[1].get("txid") == package["child"] and "allowed" not in admission[1]
                    and not any(row.get("package-error") for row in admission))
                if not complete_check and not package_check_required:
                    return self.save(identifier, "not_eligible", {"wave": wi, "reason": "Core refused the current package; signatures, inputs, timelocks or relay policy need review"})
                if not broadcast:
                    return self.save(identifier, "requires_package_validation" if package_check_required else "ready",
                                     {"wave": wi, "fee_sats": checked["fee_sats"], "core_package_check": "required on submission" if package_check_required else "passed"})
                # Store state before the only mutating RPC. Retrying sends no new
                # signatures; it first observes these exact transaction IDs.
                self.save(identifier, "submitting", {"wave": wi})
                if chain(self.core)["bestblockhash"] != info["bestblockhash"]:raise Refused("chain_changed_retry")
                try:
                    record = self.core.http.request("", {"jsonrpc": "2.0", "id": "proof-grove-exit", "method": "submitpackage", "params": [raws]})
                except Refused:
                    return self.save(identifier, "submission_uncertain", {"wave": wi, "reason": "Observe the saved transaction IDs before another attempt"})
                if not isinstance(record, dict) or record.get("error") or record.get("result", {}).get("package_msg") != "success":
                    return self.save(identifier, "package_rejected", {"wave": wi, "reason": "Core did not accept the full package; observe saved transaction IDs and review its rejection"})
            return self.save(identifier, "awaiting_confirmations", {"wave": wi, "transactions": list(observations), "required_confirmations": 2})
        targets = []
        for v in body["vtxos"]:
            txid, index = v["id"].split(":"); observation = observed(self.core, txid)
            if not observation or observation["confirmations"] < 2:
                return self.save(identifier, "awaiting_confirmations", {"reason": "Final VTXO transaction is not confirmed"})
            if self.core.rpc("gettxout", [txid, int(index), True]) is None:
                return self.save(identifier, "target_spent", {"reason": "Final VTXO output is spent; verify the owner's claim separately"})
            targets.append({"outpoint": v["id"], "amount_sats": v["amount_sat"], "claim_height": observation["height"] + v["exit_delta"], **observation})
        ready = all(info["blocks"] >= t["claim_height"] for t in targets)
        if chain(self.core)["bestblockhash"] != info["bestblockhash"]:raise Refused("chain_changed_retry")
        return self.save(identifier, "claim_ready" if ready else "exit_confirmed", {"targets": targets, "tip_height": info["blocks"],
                         "meaning": "Owner must sign and confirm the final claim. Expiry and fee liveness still apply."})
