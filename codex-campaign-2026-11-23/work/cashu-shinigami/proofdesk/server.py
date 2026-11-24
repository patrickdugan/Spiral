"""Loopback-only dashboard. Configuration, executables and recipients are server-owned."""
from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import demo
from .adapters import BarkClient, CashuClient
from .archive import bundle
from .cashu import CashuBridge
from .ark import ArkCaretaker
from .exits import ExitRecovery
from .domain import Ledger, Refused, Rules, canonical, plan_vtxo
from .regtest import payment_from_regtest
from .verifier import M16Gate, PROOF_LIMIT, STATEMENT_SIZE

WEB = Path(__file__).resolve().parent.parent / "web"


class Desk:
    def __init__(self, mode: str = "demo", ledger: Ledger | None = None,
                 gate=None, core=None, config: dict | None = None, shinigami=None):
        if mode not in ("demo", "live", "regtest"):
            raise Refused("invalid_mode")
        self.mode, self.ledger, self.gate, self.core = mode, ledger, gate, core
        self.shinigami = shinigami
        self.config = config or {}
        self.lock = threading.RLock()
        self.last = demo.run_case("cashu") if mode == "demo" else None
        self.cashu = CashuBridge(
            ledger, CashuClient(self.config["cashu_url"]), core,
            shinigami_policy_sha256=shinigami.policy_sha256 if shinigami else None,
        ) if ledger and core and self.config.get("cashu_url") else None
        self.ark = ArkCaretaker(ledger, BarkClient(self.config["bark_url"], self.config.get("bark_bearer", "")), core,
                               allow_regtest=self.config.get("ark_regtest_execution") is True) if ledger and core and self.config.get("bark_url") else None
        self.exits = ExitRecovery(ledger, core, broadcaster=self.config.get("ark_regtest_exit_broadcast") is True) if ledger and core else None

    def status(self) -> dict:
        return {"app": "Proof Grove", "version": "0.4.0", "mode": self.mode,
                "ark_wallet_configured": self.ark is not None,
                "native_verifier": "configured" if self.gate else "not configured",
                "shinigami_verifier": "configured" if self.shinigami else "not configured",
                "chain_observer": "configured" if self.core else "not configured",
                "settlement": "proof-gated Cashu issuance" if self.cashu else "preparation only", "custody": "Cashu remains mint-custodial; Ark retains expiry and operator liveness requirements.",
                "intents": [asdict(self.ledger.intent(r[0])) for r in self.ledger.db.execute("SELECT id FROM intents")] if self.ledger else []}

    def verify(self, body: dict) -> dict:
        if self.mode not in ("live","regtest") or not self.core or not self.ledger:
            raise Refused("live_verifier_not_configured")
        intent = self.ledger.intent(body.get("intent_id", ""))
        if self.mode == "regtest":
            evidence = payment_from_regtest(self.core,body.get("txid",""),body.get("vout"))
            rules = Rules("regtest",self.config.get("min_confirmations",2),mode="regtest")
        else:
            if not self.gate:
                raise Refused("live_verifier_not_configured")
            try:
                statement = base64.b64decode(body.get("statement_base64", ""), validate=True)
                proof = base64.b64decode(body.get("proof_base64", ""), validate=True)
            except (ValueError, TypeError, binascii.Error):
                raise Refused("invalid_artifact_encoding") from None
            if len(statement) != STATEMENT_SIZE or not 0 < len(proof) <= PROOF_LIMIT:
                raise Refused("artifact_size")
            policy = {**self.gate.policy,"scripts":[{"id":intent.id,"script_sha256":intent.script_sha256,"min_value_sats":intent.amount_sats}]}
            evidence = M16Gate(self.gate.argv,self.gate.expected_hash,policy,self.gate.timeout).verify(statement,proof)
            rules = Rules(policy["network"],policy["min_confirmations"],int(policy["min_tip_chainwork"],16),
                          self.config.get("max_tip_lag",12),self.config.get("max_view_age_seconds",120),"live")
        if self.shinigami is not None and intent.rail == "cashu":
            evidence = self.shinigami.verify(evidence)
        chain = self.core.view_for(evidence)
        receipt = self.ledger.prepare(intent.id, evidence, chain, rules, int(time.time()))
        return {"decision": {"accepted": True, "code": "prepared", "receipt": receipt},
                "evidence_level": evidence.kind, "simulation": False,
                "receipts": self.ledger.receipts()}


def make_server(desk: Desk, port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Paths may contain private quote identifiers.

        def _guard(self, mutation: bool = False):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in hosts:
                raise Refused("invalid_host")
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + host for host in hosts}:
                raise Refused("invalid_origin")
            if mutation and self.headers.get("X-Proof-Grove") != "1":
                raise Refused("same_origin_header_required")

        def _send(self, status: int, payload: bytes, content_type: str = "application/json"):
            try:
                self._send_response(status, payload, content_type)
            except (BrokenPipeError, ConnectionResetError):
                # The operation may already be committed. A disconnected client
                # gets no second response; it can reconcile the saved operation.
                self.close_connection = True

        def _send_response(self, status: int, payload: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def _error(self, exc: Exception):
            if isinstance(exc, Refused):
                self._send(400, canonical({"error": exc.code, "detail": exc.detail}))
            else:
                self._send(500, canonical({"error": "internal_error"}))

        def do_GET(self):
            try:
                self._guard()
                url = urlsplit(self.path)
                path = url.path
                with desk.lock:
                    if path == "/api/status":
                        value = desk.status()
                    elif path == "/api/cases":
                        value = {"cases": demo.CASES if desk.mode == "demo" else [], "current": desk.last}
                    elif path == "/api/receipts":
                        value = {"receipts": desk.ledger.receipts() if desk.ledger else (desk.last or {}).get("receipts", [])}
                    elif path in ("/api/archive", "/api/archive/manifest"):
                        receipts = desk.ledger.receipts() if desk.ledger else (desk.last or {}).get("receipts", [])
                        data, manifest = bundle(receipts)
                        if path.endswith("manifest"):
                            value = manifest
                        else:
                            self._send(200, data)
                            return
                    elif path == "/api/vtxos":
                        value = {"evidence_level": "fixture", "tip_height": 1005, "vtxos": demo.vtxos(), "plans": demo.plans()} if desk.mode == "demo" else {
                            "evidence_level": "not-connected", "vtxos": [], "plans": [],
                            "meaning": "Supply independently validated VTXOs to the CLI planner."}
                    elif path == "/api/cashu/info":
                        value = CashuClient(desk.config["cashu_url"]).info() if desk.config.get("cashu_url") else {"evidence_level": "not-connected"}
                    elif path == "/api/cashu/operations":
                        value = {"operations":[{"intent_id":r["intent_id"],"state":r["state"],"request_sha256":r["payload_hash"],"wallet_verification":"required"} for r in desk.ledger.db.execute("SELECT intent_id,state,payload_hash FROM cashu_issuance")] if desk.cashu else []}
                    elif path == "/api/cashu/quote":
                        if not desk.config.get("cashu_url"):
                            raise Refused("cashu_not_configured")
                        query = parse_qs(url.query)
                        value = CashuClient(desk.config["cashu_url"]).quote(query.get("method", [""])[0], query.get("quote", [""])[0])
                    elif path == "/api/bark/history":
                        value = BarkClient(desk.config["bark_url"], desk.config.get("bark_bearer", "")).history() if desk.config.get("bark_url") else {"evidence_level": "not-connected"}
                    elif path == "/api/ark/wallet":
                        value = {**desk.ark.snapshot(), "exit_broadcast_enabled": desk.exits.broadcaster if desk.exits else False} if desk.ark else {"evidence_level": "not-connected", "vtxos": []}
                    elif path == "/api/ark/operations":
                        value = {"operations": desk.ark.operations() if desk.ark else []}
                    elif path == "/api/ark/exits":
                        value = {"exits": desk.exits.records() if desk.exits else [], "broadcast_enabled": bool(desk.exits and desk.exits.broadcaster)}
                    elif path == "/api/ark/exits/bundle":
                        if not desk.exits:raise Refused("exit_not_configured")
                        value = desk.exits.bundle(parse_qs(url.query).get("id", [""])[0])
                    elif path == "/api/sources":
                        value = json.loads((WEB.parent / "docs" / "sources.json").read_text(encoding="utf-8"))
                    elif path in ("/", "/index.html", "/styles.css", "/app.js", "/icon.svg"):
                        file = WEB / ("index.html" if path == "/" else path.lstrip("/"))
                        self._send(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
                        return
                    else:
                        self._send(404, canonical({"error": "not_found"}))
                        return
                    self._send(200, canonical(value))
            except Exception as exc:
                self._error(exc)

        def do_POST(self):
            try:
                self._guard(mutation=True)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 6 * 1024 * 1024:
                    raise Refused("request_size")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise Refused("json_required")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise Refused("json_object_required")
                with desk.lock:
                    if self.path == "/api/run" and desk.mode == "demo":
                        desk.last = demo.run_case(body.get("case", ""))
                        value = desk.last
                    elif self.path == "/api/verify":
                        value = desk.verify(body)
                    elif self.path == "/api/cashu/bind":
                        if not desk.cashu:
                            raise Refused("cashu_not_configured")
                        network = "regtest" if desk.mode == "regtest" else desk.gate.policy["network"]
                        value = desk.cashu.bind(body.get("quote_id"),body.get("pubkey"),body.get("amount_sats"),network,body.get("authorization"))
                    elif self.path == "/api/cashu/issue":
                        if not desk.cashu:
                            raise Refused("cashu_not_configured")
                        value = desk.cashu.issue(body.get("intent_id"),body.get("payload"),body.get("authorization"))
                    elif self.path == "/api/plan":
                        value = {"plan": plan_vtxo(body["vtxo"], body["tip_height"]), "evidence_level": "caller-supplied", "executed": False}
                    elif self.path == "/api/ark/refresh":
                        if not desk.ark:
                            raise Refused("ark_not_configured")
                        value = desk.ark.refresh(body.get("vtxos"), body.get("height"), body.get("max_fee_sats"))
                    elif self.path == "/api/ark/reconcile":
                        if not desk.ark:
                            raise Refused("ark_not_configured")
                        value = desk.ark.reconcile(body.get("id"))
                    elif self.path == "/api/ark/exits/prepare":
                        if not desk.exits or not desk.ark:raise Refused("exit_not_configured")
                        value = desk.exits.prepare(desk.ark, body.get("vtxos"), body.get("fee_rate"), body.get("max_fee_sats"))
                    elif self.path == "/api/ark/exits/advance":
                        if not desk.exits:raise Refused("exit_not_configured")
                        value = desk.exits.advance(body.get("id"), broadcast=body.get("broadcast") is True)
                    else:
                        raise Refused("operation_not_available")
                    self._send(200, canonical(value))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                self._error(exc if isinstance(exc, Refused) else Refused("invalid_request"))
            except Exception as exc:
                self._error(exc)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
