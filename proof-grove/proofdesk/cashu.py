"""Proof-admitted NUT-30 issuance bridge. Stores blinded messages, never bearer secrets.

NUT-20 binds quote ownership. NUT-09 restores the same outputs after an ambiguous
response. A received blind signature is not a server assertion of spendable ecash.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import time
from pathlib import Path

from .adapters import CashuClient
from .domain import Intent, Ledger, Refused, canonical, decide, digest, positive


def compressed_point(value: str) -> bool:
    return isinstance(value,str) and len(value)==66 and value[:2] in ("02","03") and all(c in "0123456789abcdef" for c in value)


def verify_issue_authorization(pubkey: str, payload: dict, intent_id: str, authorization: str) -> bool:
    script = Path(__file__).resolve().parent.parent / "wallet" / "public-verify.mjs"
    try:
        cp = subprocess.run(["node",str(script)],input=json.dumps({"pubkey":pubkey,"payload":payload,"intent_id":intent_id,"authorization":authorization}),
                            text=True,capture_output=True,timeout=30,check=False)
        return cp.returncode == 0 and json.loads(cp.stdout).get("valid") is True
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise Refused("cashu_sdk_unavailable") from None


def verify_binding_signature(pubkey: str, payload: dict, authorization: str) -> bool:
    script = Path(__file__).resolve().parent.parent / "wallet" / "public-verify.mjs"
    try:
        cp = subprocess.run(["node",str(script)],input=json.dumps({"action":"bind","pubkey":pubkey,"payload":payload,"authorization":authorization}),
                            text=True,capture_output=True,timeout=30,check=False)
        return cp.returncode == 0 and json.loads(cp.stdout).get("valid") is True
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise Refused("cashu_sdk_unavailable") from None


class CashuBridge:
    def __init__(self, ledger: Ledger, mint: CashuClient, core, signature_verifier=verify_issue_authorization,
                 clock=lambda:int(time.time()),binding_verifier=verify_binding_signature,
                 admission_window_seconds=7*86400):
        if ledger.namespace not in ("live","regtest"):
            raise Refused("real_admission_namespace_required")
        self.ledger,self.mint,self.core = ledger,mint,core
        self.signature_verifier,self.clock = signature_verifier,clock
        self.binding_verifier=binding_verifier
        self.admission_window=positive(admission_window_seconds,"admission_window_seconds",30*86400)
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS cashu_bindings (
                intent_id TEXT PRIMARY KEY REFERENCES intents(id),
                mint_url TEXT NOT NULL, quote_id TEXT NOT NULL, body TEXT NOT NULL,
                UNIQUE(mint_url,quote_id));
            CREATE TABLE IF NOT EXISTS cashu_issuance (
                intent_id TEXT PRIMARY KEY REFERENCES cashu_bindings(intent_id),
                payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, result TEXT, lease TEXT, lease_until INTEGER NOT NULL DEFAULT 0);
        """)

    def _binding(self, intent_id: str) -> dict:
        row = self.ledger.db.execute("SELECT body FROM cashu_bindings WHERE intent_id=?",(intent_id,)).fetchone()
        if row is None:
            raise Refused("cashu_quote_not_bound")
        binding = json.loads(row[0])
        if binding["mint_url"] != self.mint.http.base:
            raise Refused("mint_identity_changed")
        return binding

    @staticmethod
    def _check_quote(quote: dict, binding: dict) -> None:
        for key in ("quote","request","pubkey","unit","method"):
            if quote.get(key) != binding[key]:
                raise Refused("cashu_quote_changed",key)
        paid,issued = quote.get("amount_paid"),quote.get("amount_issued")
        if type(paid) is not int or type(issued) is not int or not 0 <= issued <= paid:
            raise Refused("cashu_accounting_invalid")

    def bind(self, quote_id: str, pubkey: str, amount_sats: int, network: str, authorization: str | None = None) -> dict:
        positive(amount_sats,"amount_sats")
        if not compressed_point(pubkey):
            raise Refused("invalid_quote_pubkey")
        quote = self.mint.raw_quote(quote_id)
        binding = {k:quote.get(k) for k in ("quote","request","pubkey","unit","method")}
        if binding["quote"] != quote_id or binding["pubkey"] != pubkey or binding["unit"] != "sat" or binding["method"] != "onchain":
            raise Refused("cashu_quote_changed")
        if not isinstance(authorization,str) or len(authorization)!=128 or any(c not in "0123456789abcdef" for c in authorization):
            raise Refused("binding_authorization_required")
        authorized={"quote":quote_id,"request":binding["request"],"pubkey":pubkey,"amount_sats":amount_sats}
        if self.binding_verifier(pubkey,authorized,authorization) is not True:
            raise Refused("binding_authorization_invalid")
        identity = digest({"mint":self.mint.http.base,"quote":quote_id})
        intent_id = "cashu:" + identity
        existing = self.ledger.db.execute("SELECT body FROM cashu_bindings WHERE intent_id=?",(intent_id,)).fetchone()
        if existing:
            old = self._binding(intent_id)
            self._check_quote(quote,old)
            if old["amount_sats"] != amount_sats or old["network"] != network:
                raise Refused("cashu_binding_immutable")
            return {"intent":self.ledger.intent(intent_id).__dict__,"quote_bound":True,"idempotent_replay":True}
        self._check_quote(quote,binding)
        if quote["amount_paid"] != 0 or quote["amount_issued"] != 0:
            raise Refused("fresh_unpaid_quote_required")
        chain = self.core.rpc("getblockchaininfo",[])
        if {"main":"mainnet","testnet4":"testnet4","regtest":"regtest"}.get(chain.get("chain")) != network:
            raise Refused("wrong_network")
        address = self.core.rpc("validateaddress",[quote["request"]])
        if address.get("isvalid") is not True or not isinstance(address.get("scriptPubKey"),str):
            raise Refused("invalid_deposit_address")
        script_hash = hashlib.sha256(bytes.fromhex(address["scriptPubKey"])).hexdigest()
        payment_expiry = quote.get("expiry")
        if payment_expiry is not None:
            positive(payment_expiry,"expiry",2**53-1)
            if payment_expiry <= self.clock():
                raise Refused("intent_expired")
        # Quote expiry governs payment eligibility at the mint, not delivery of
        # an expensive proof. Give proof admission its own explicit retention window.
        admission_expiry=self.clock()+self.admission_window
        intent = Intent(intent_id,network,script_hash,amount_sats,"cashu-nut20:"+pubkey,"cashu",admission_expiry)
        binding.update(mint_url=self.mint.http.base,amount_sats=amount_sats,network=network,payment_expiry=payment_expiry)
        try:
            self.ledger.db.execute("BEGIN IMMEDIATE")
            self.ledger.add_intent(intent)
            self.ledger.db.execute("INSERT INTO cashu_bindings VALUES (?,?,?,?)",
                                   (intent.id,self.mint.http.base,quote_id,canonical(binding).decode()))
            self.ledger.db.execute("COMMIT")
        except BaseException:
            if self.ledger.db.in_transaction:
                self.ledger.db.execute("ROLLBACK")
            raise
        return {"intent":intent.__dict__,"quote_bound":True,"idempotent_replay":False}

    def _validate_payload(self, intent: Intent, binding: dict, payload: dict, authorization: str):
        if not isinstance(payload,dict) or set(payload) != {"quote","outputs","signature"} or payload["quote"] != binding["quote"]:
            raise Refused("invalid_mint_payload")
        outputs = payload["outputs"]
        if not isinstance(outputs,list) or not 1 <= len(outputs) <= 128:
            raise Refused("invalid_blinded_outputs")
        total,points = 0,set()
        for output in outputs:
            if not isinstance(output,dict) or set(output) != {"amount","id","B_"}:
                raise Refused("invalid_blinded_outputs")
            amount = positive(output["amount"],"output_amount")
            if amount & (amount-1) or not compressed_point(output["B_"]) or output["B_"] in points:
                raise Refused("invalid_blinded_outputs")
            keyset = output["id"]
            if not isinstance(keyset,str) or len(keyset) not in (16,66) or any(c not in "0123456789abcdef" for c in keyset):
                raise Refused("invalid_keyset")
            total += amount; points.add(output["B_"])
        if total != intent.amount_sats:
            raise Refused("wrong_mint_amount")
        signature = payload["signature"]
        if not isinstance(signature,str) or len(signature)!=128 or any(c not in "0123456789abcdef" for c in signature):
            raise Refused("quote_signature_required")
        if not isinstance(authorization,str) or len(authorization)!=128 or any(c not in "0123456789abcdef" for c in authorization):
            raise Refused("issue_authorization_required")
        if self.signature_verifier(binding["pubkey"],payload,intent.id,authorization) is not True:
            raise Refused("issue_authorization_invalid")

    @staticmethod
    def _validate_signatures(outputs: list, signatures: list) -> list:
        if not isinstance(signatures,list) or len(signatures) != len(outputs):
            raise Refused("mint_signature_response_incomplete")
        for output,signature in zip(outputs,signatures):
            if not isinstance(signature,dict) or any(type(signature.get(k)) is not type(output[k]) or signature[k] != output[k] for k in ("id","amount")) or not compressed_point(signature.get("C_")):
                raise Refused("mint_signature_response_invalid")
        return signatures

    def _restore(self, outputs: list) -> list | None:
        result = self.mint.http.request("/v1/restore",{"outputs":outputs})
        if not isinstance(result,dict) or not isinstance(result.get("outputs"),list) or not isinstance(result.get("signatures"),list):
            raise Refused("mint_restore_invalid")
        if not result["outputs"] and not result["signatures"]:
            return None
        pairs = {}
        if len(result["outputs"]) != len(result["signatures"]):
            raise Refused("mint_restore_incomplete")
        expected = {o["B_"]:o for o in outputs}
        for output,signature in zip(result["outputs"],result["signatures"]):
            if not isinstance(output,dict) or output.get("B_") not in expected or output != expected[output["B_"]] or output["B_"] in pairs:
                raise Refused("mint_restore_invalid")
            pairs[output["B_"]] = signature
        if set(pairs) != set(expected):
            raise Refused("mint_restore_incomplete")
        return self._validate_signatures(outputs,[pairs[o["B_"]] for o in outputs])

    def issue(self, intent_id: str, payload: dict, authorization: str | None = None) -> dict:
        intent = self.ledger.intent(intent_id)
        binding = self._binding(intent_id)
        self._validate_payload(intent,binding,payload,authorization)
        receipt,evidence,rules = self.ledger.admitted(intent_id)
        if receipt["checked_at"] >= intent.expires_at:
            raise Refused("payment_admission_required")
        chain = self.core.view_for(evidence)
        # NUT-30 expiry is a payment deadline. Already admitted funds remain issuable.
        decide(intent,evidence,chain,rules,self.clock(),enforce_payment_deadline=False)
        quote = self.mint.raw_quote(binding["quote"])
        self._check_quote(quote,binding)
        if quote["amount_paid"] < intent.amount_sats:
            raise Refused("mint_payment_pending")
        encoded,packet_hash = canonical(payload).decode(),digest(payload)
        lease,now = secrets.token_hex(16),self.clock()
        db = self.ledger.db
        try:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM cashu_issuance WHERE intent_id=?",(intent_id,)).fetchone()
            if old and old["payload_hash"] != packet_hash:
                raise Refused("mint_outputs_immutable")
            if old and old["result"]:
                db.execute("COMMIT")
                return json.loads(old["result"]) | {"idempotent_replay":True}
            if old and old["lease_until"] > now:
                raise Refused("mint_request_in_progress")
            retry = old is not None
            if old:
                db.execute("UPDATE cashu_issuance SET state='submitting',lease=?,lease_until=? WHERE intent_id=?",(lease,now+120,intent_id))
            else:
                db.execute("INSERT INTO cashu_issuance VALUES (?,?,?,'submitting',NULL,?,?)",(intent_id,packet_hash,encoded,lease,now+120))
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction: db.execute("ROLLBACK")
            raise
        try:
            signatures = self._restore(payload["outputs"]) if retry else None
            if signatures is None:
                if quote["amount_issued"] != 0:
                    raise Refused("mint_reconciliation_required")
                result = self.mint.http.request("/v1/mint/onchain",payload)
                if not isinstance(result,dict):
                    raise Refused("mint_signature_response_invalid")
                signatures = self._validate_signatures(payload["outputs"],result.get("signatures"))
            result = {"state":"blind-signatures-received","signatures":signatures,"request_sha256":packet_hash,
                      "evidence_level":evidence.kind,"wallet_verification":"required",
                      "meaning":"Wallet must unblind and verify mint signatures; this response is not a bearer token."}
            db.execute("UPDATE cashu_issuance SET state='signatures_received',result=?,lease=NULL,lease_until=0 WHERE intent_id=? AND lease=?",
                       (canonical(result).decode(),intent_id,lease))
            return result | {"idempotent_replay":False}
        except BaseException:
            db.execute("UPDATE cashu_issuance SET state='reconcile',lease=NULL,lease_until=0 WHERE intent_id=? AND lease=?",(intent_id,lease))
            raise
