"""Policy decisions shared by the CLI, HTTP service and deterministic demo.

No method signs, broadcasts, issues ecash, or labels an operator receipt a ZK proof.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_SATS = 2_100_000_000_000_000


class Refused(ValueError):
    def __init__(self, code: str, detail: str = ""):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def positive(value: int, field: str, maximum: int = MAX_SATS) -> int:
    if type(value) is not int or not 0 < value <= maximum:
        raise Refused("invalid_integer", field)
    return value


def hash32(value: str, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise Refused("invalid_hash", field)
    return value


@dataclass(frozen=True)
class Intent:
    id: str
    network: str
    script_sha256: str
    amount_sats: int
    beneficiary: str
    rail: str
    expires_at: int

    def validate(self) -> None:
        if not isinstance(self.id, str) or not 1 <= len(self.id) <= 100:
            raise Refused("invalid_intent")
        if self.network not in ("mainnet", "testnet4", "regtest"):
            raise Refused("wrong_network")
        hash32(self.script_sha256, "script_sha256")
        positive(self.amount_sats, "amount_sats")
        positive(self.expires_at, "expires_at", 2**53 - 1)
        if self.rail not in ("cashu", "ark") or not isinstance(self.beneficiary, str) or not self.beneficiary:
            raise Refused("invalid_destination")


@dataclass(frozen=True)
class Evidence:
    network: str
    txid: str
    vout: int
    value_sats: int
    script_sha256: str
    block_hash: str
    block_height: int
    tip_hash: str
    tip_height: int
    tip_chainwork: int
    confirmations: int
    statement_sha256: str
    proof_sha256: str
    kind: str
    shinigami_proof_sha256: str | None = None
    shinigami_policy_sha256: str | None = None

    def validate(self) -> None:
        for field in ("txid", "script_sha256", "block_hash", "tip_hash", "statement_sha256", "proof_sha256"):
            hash32(getattr(self, field), field)
        if self.shinigami_proof_sha256 is not None or self.shinigami_policy_sha256 is not None:
            hash32(self.shinigami_proof_sha256, "shinigami_proof_sha256")
            hash32(self.shinigami_policy_sha256, "shinigami_policy_sha256")
        if type(self.vout) is not int or not 0 <= self.vout < 2**32:
            raise Refused("invalid_vout")
        for field in ("block_height", "tip_height", "confirmations", "tip_chainwork", "value_sats"):
            positive(getattr(self, field), field, MAX_SATS if field == "value_sats" else 2**256 - 1)
        if self.tip_height != self.block_height + self.confirmations - 1:
            raise Refused("inconsistent_confirmations")

    @property
    def outpoint(self) -> str:
        return f"{self.txid}:{self.vout}"


@dataclass(frozen=True)
class ChainView:
    network: str
    tip_hash: str
    tip_height: int
    observed_at: int
    block_hash: str
    block_height: int
    source: str


@dataclass(frozen=True)
class Rules:
    network: str
    min_confirmations: int = 6
    min_chainwork: int = 1
    max_tip_lag: int = 12
    max_view_age_seconds: int = 120
    mode: str = "live"


def decide(intent: Intent, evidence: Evidence, chain: ChainView, rules: Rules, now: int,
           *, enforce_payment_deadline: bool = True) -> dict:
    intent.validate()
    evidence.validate()
    if not (intent.network == evidence.network == chain.network == rules.network):
        raise Refused("wrong_network")
    if rules.mode not in ("demo", "live", "regtest"):
        raise Refused("invalid_mode")
    if rules.mode == "live" and (evidence.kind != "m16-verified" or chain.source != "bitcoin-core"):
        raise Refused("verified_evidence_required")
    if rules.mode == "demo" and (evidence.kind != "fixture" or chain.source != "fixture"):
        raise Refused("demo_namespace_required")
    if rules.mode == "regtest" and (rules.network != "regtest" or evidence.kind != "core-regtest" or chain.source != "bitcoin-core"):
        raise Refused("regtest_evidence_required")
    if enforce_payment_deadline and now >= intent.expires_at:
        raise Refused("intent_expired")
    if not 0 <= now - chain.observed_at <= rules.max_view_age_seconds:
        raise Refused("chain_view_stale")
    if chain.block_hash != evidence.block_hash or chain.block_height != evidence.block_height:
        raise Refused("payment_reorged")
    if not 0 <= chain.tip_height - evidence.tip_height <= rules.max_tip_lag:
        raise Refused("proof_tip_stale")
    if chain.tip_height == evidence.tip_height and chain.tip_hash != evidence.tip_hash:
        raise Refused("proof_fork")
    if evidence.tip_chainwork < rules.min_chainwork:
        raise Refused("chainwork_below_floor")
    if evidence.confirmations < rules.min_confirmations:
        raise Refused("too_few_confirmations")
    if evidence.script_sha256 != intent.script_sha256:
        raise Refused("wrong_payment_script")
    if evidence.value_sats != intent.amount_sats:
        raise Refused("wrong_amount", "This intent requires the exact amount; overpayments are not silently retained.")
    receipt = {
        "state": "prepared", "evidence_level": evidence.kind,
        "intent_id": intent.id, "network": intent.network,
        "outpoint": evidence.outpoint, "amount_sats": intent.amount_sats,
        "beneficiary": intent.beneficiary, "rail": intent.rail,
        "statement_sha256": evidence.statement_sha256, "proof_sha256": evidence.proof_sha256,
        "chain_tip": chain.tip_hash, "checked_at": now,
        "meaning": "Payment accepted by policy; this receipt records admission, not settlement.",
    }
    if evidence.shinigami_proof_sha256 is not None:
        receipt["shinigami_proof_sha256"] = evidence.shinigami_proof_sha256
        receipt["shinigami_policy_sha256"] = evidence.shinigami_policy_sha256
    return receipt


class Ledger:
    """One transaction reserves an outpoint, intent and durable outbox entry.

    Demo and live require different database files and immutable namespace metadata.
    """
    def __init__(self, path: str | Path, namespace: str):
        if namespace not in ("demo", "live", "regtest"):
            raise Refused("invalid_mode")
        self.namespace = namespace
        self.db = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intents (
                id TEXT PRIMARY KEY, network TEXT NOT NULL, script_sha256 TEXT NOT NULL,
                body TEXT NOT NULL, UNIQUE(network,script_sha256));
            CREATE TABLE IF NOT EXISTS claims (
                network TEXT NOT NULL, outpoint TEXT NOT NULL, intent_id TEXT UNIQUE NOT NULL,
                receipt TEXT NOT NULL, PRIMARY KEY(network,outpoint),
                FOREIGN KEY(intent_id) REFERENCES intents(id));
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, intent_id TEXT UNIQUE NOT NULL,
                state TEXT NOT NULL CHECK(state='prepared'), body TEXT NOT NULL,
                FOREIGN KEY(intent_id) REFERENCES intents(id));
            CREATE TABLE IF NOT EXISTS payment_evidence (
                intent_id TEXT PRIMARY KEY REFERENCES intents(id), evidence TEXT NOT NULL, rules TEXT NOT NULL);
        """)
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('namespace',?)", (namespace,))
        if self.db.execute("SELECT value FROM metadata WHERE key='namespace'").fetchone()[0] != namespace:
            self.close()
            raise Refused("database_namespace_mismatch")

    def close(self) -> None:
        self.db.close()

    def add_intent(self, intent: Intent) -> None:
        intent.validate()
        body = canonical(asdict(intent)).decode()
        self.db.execute("INSERT OR IGNORE INTO intents VALUES (?,?,?,?)",
                        (intent.id, intent.network, intent.script_sha256, body))
        row = self.db.execute("SELECT body FROM intents WHERE id=?", (intent.id,)).fetchone()
        if row is None:
            raise Refused("deposit_script_reused", "Each intent needs its own deposit script, never reassigned to another recipient.")
        if row[0] != body:
            raise Refused("intent_immutable")

    def intent(self, intent_id: str) -> Intent:
        row = self.db.execute("SELECT body FROM intents WHERE id=?", (intent_id,)).fetchone()
        if row is None:
            raise Refused("unknown_intent")
        return Intent(**json.loads(row[0]))

    def prepare(self, intent_id: str, evidence: Evidence, chain: ChainView, rules: Rules, now: int) -> dict:
        if rules.mode != self.namespace:
            raise Refused("database_namespace_mismatch")
        intent = self.intent(intent_id)
        receipt = decide(intent, evidence, chain, rules, now)
        recorded = asdict(evidence)
        if evidence.shinigami_proof_sha256 is None:
            # Preserve the IDs and idempotency of existing admissions.
            del recorded["shinigami_proof_sha256"], recorded["shinigami_policy_sha256"]
        receipt["id"] = digest({"namespace": self.namespace, "intent": asdict(intent), "evidence": recorded})
        receipt["namespace"] = self.namespace
        encoded = canonical(receipt).decode()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute("SELECT receipt FROM claims WHERE network=? AND outpoint=?",
                                  (evidence.network, evidence.outpoint)).fetchone()
            if old:
                previous = json.loads(old[0])
                if previous["intent_id"] == intent_id and previous["id"] == receipt["id"]:
                    self.db.execute("INSERT OR IGNORE INTO payment_evidence VALUES (?,?,?)",
                                    (intent_id,canonical(recorded).decode(),canonical(asdict(rules)).decode()))
                    self.db.execute("COMMIT")
                    return {**previous, "idempotent_replay": True}
                raise Refused("payment_already_claimed")
            self.db.execute("INSERT INTO claims VALUES (?,?,?,?)",
                            (evidence.network, evidence.outpoint, intent_id, encoded))
            self.db.execute("INSERT INTO outbox VALUES (?,?,'prepared',?)", (receipt["id"], intent_id, encoded))
            self.db.execute("INSERT INTO payment_evidence VALUES (?,?,?)",
                            (intent_id,canonical(recorded).decode(),canonical(asdict(rules)).decode()))
            self.db.execute("COMMIT")
            return {**receipt, "idempotent_replay": False}
        except (sqlite3.IntegrityError, Refused) as exc:
            self.db.execute("ROLLBACK")
            if isinstance(exc, Refused):
                raise
            raise Refused("intent_already_prepared") from None
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def receipts(self) -> list[dict]:
        return [json.loads(r[0]) for r in self.db.execute("SELECT receipt FROM claims ORDER BY rowid")]

    def admitted(self, intent_id: str) -> tuple[dict, Evidence, Rules]:
        row = self.db.execute("SELECT claims.receipt, payment_evidence.evidence, payment_evidence.rules "
                              "FROM claims JOIN payment_evidence USING(intent_id) WHERE intent_id=?", (intent_id,)).fetchone()
        if row is None:
            raise Refused("payment_admission_required")
        return json.loads(row[0]), Evidence(**json.loads(row[1])), Rules(**json.loads(row[2]))


def plan_vtxo(vtxo: dict, tip_height: int, *, refresh_before: int = 144,
              exit_before: int = 72, max_fee_sats: int = 1000) -> dict:
    """Permissionless planning only; Bark must validate/sign any actual operation.

    Exit safety includes a caller-supplied, independently validated worst-case package
    confirmation budget. A boolean does not establish Bitcoin spendability.
    """
    for field in ("value_sats", "expiry_height", "exit_budget_blocks"):
        positive(vtxo.get(field), field, 2**32 - 1 if field != "value_sats" else MAX_SATS)
    if type(tip_height) is not int or tip_height < 0:
        raise Refused("invalid_tip")
    if not (type(exit_before) is int and type(refresh_before) is int and 0 < exit_before < refresh_before):
        raise Refused("invalid_refresh_policy")
    positive(max_fee_sats, "max_fee_sats")
    remaining = vtxo["expiry_height"] - tip_height
    result = {"id": str(vtxo.get("id", "")), "remaining_blocks": remaining,
              "expiry_height": vtxo["expiry_height"], "value_sats": vtxo["value_sats"],
              "max_fee_sats": max_fee_sats, "executed": False}
    if remaining <= vtxo["exit_budget_blocks"]:
        return {**result, "action": "urgent", "reason": "Insufficient conservative exit runway; manual recovery review required."}
    if vtxo.get("exit_package_validated") is not True:
        return {**result, "action": "prepare_exit", "reason": "Have Bark validate and presign an exit package before unattended delegation."}
    if remaining <= exit_before or vtxo.get("operator_online") is not True:
        return {**result, "action": "delegate_exit", "reason": "Use the presigned exit through an independent broadcaster; observe confirmation before expiry."}
    if remaining <= refresh_before:
        return {**result, "action": "refresh", "reason": "Request a new VTXO from Bark within the fee cap; verify the successor before retiring this one."}
    return {**result, "action": "hold", "reason": "Within the configured safety window; continue monitoring chain height."}
