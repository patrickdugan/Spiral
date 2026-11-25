"""Loopback-only dashboard. Configuration, executables and recipients are server-owned."""
from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import threading
import time
import hashlib
import io
import os
import shutil
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from . import demo, protected_evidence_preview, protected_funded_preview, protected_payout_evidence
from .adapters import BarkClient, CashuClient
from .archive import bundle
from .cashu import CashuBridge
from .ark import ArkCaretaker
from .exits import ExitRecovery
from .protected_melt import ProtectedMelt
from .domain import Ledger, Refused, Rules, canonical, plan_vtxo
from .regtest import payment_from_regtest
from .verifier import M16Gate, PROOF_LIMIT, STATEMENT_SIZE, read_bounded
from .access import HostedAccess, AccessDenied

WEB = Path(__file__).resolve().parent.parent / "web"


class Desk:
    def __init__(self, mode: str = "demo", ledger: Ledger | None = None,
                 gate=None, core=None, config: dict | None = None):
        if mode not in ("demo", "live", "regtest"):
            raise Refused("invalid_mode")
        self.mode, self.ledger, self.gate, self.core = mode, ledger, gate, core
        self.config = config or {}
        self.lock = threading.RLock()
        self.last = demo.run_case("cashu") if mode == "demo" else None
        self.cashu = CashuBridge(ledger,CashuClient(self.config["cashu_url"]),core) if ledger and core and self.config.get("cashu_url") else None
        mint_wallet = self.config.get("protected_melt_wallet")
        self.protected_melt = ProtectedMelt(self.cashu, core, mint_wallet) if mode == "regtest" and self.cashu and mint_wallet is not None else None
        self.ark = ArkCaretaker(ledger, BarkClient(self.config["bark_url"], self.config.get("bark_bearer", "")), core,
                               allow_regtest=self.config.get("ark_regtest_execution") is True) if ledger and core and self.config.get("bark_url") else None
        self.exits = ExitRecovery(ledger, core, broadcaster=self.config.get("ark_regtest_exit_broadcast") is True) if ledger and core else None

    def status(self) -> dict:
        return {"app": "Proof Grove", "version": "0.4.0", "mode": self.mode,
                "ark_wallet_configured": self.ark is not None,
                "protected_preview_configured": self.mode == 'demo' and bool(self.config.get('protected_preview')),
                "protected_funded_preview_configured": self.mode == 'demo' and bool(self.config.get('protected_funded_preview')),
                "protected_evidence_preview_configured": self.mode == 'demo' and bool(self.config.get('protected_evidence_preview')),
                "protected_melt_configured": self.protected_melt is not None,
                "native_verifier": "configured" if self.gate else "not configured",
                "chain_observer": "configured" if self.core else "not configured",
                "settlement": "proof-gated Cashu issuance" if self.cashu else "preparation only", "custody": "Cashu remains mint-custodial; Ark retains expiry and operator liveness requirements.",
                "intents": [asdict(self.ledger.intent(r[0])) for r in self.ledger.db.execute("SELECT id FROM intents")] if self.ledger else []}

    def _protected_preview_input(self) -> tuple[dict, bytes]:
        manifest_path = self.config.get('protected_preview')
        if self.mode != 'demo' or not manifest_path:
            raise Refused('protected_preview_not_configured')
        manifest = json.loads(read_bounded(manifest_path, 4096))
        raw = read_bounded(manifest_path.parent / manifest['receipt'], 256 * 1024)
        if hashlib.sha256(raw).hexdigest() != manifest['receipt_sha256']:
            raise Refused('protected_preview_receipt_changed')
        return manifest, raw

    def check_protected_preview(self, case: str) -> dict:
        if case not in ('original', 'beneficiary', 'checkpoint'):
            raise Refused('invalid_protected_preview_case')
        manifest, raw = self._protected_preview_input()
        return self._verify_protected_preview(manifest, raw, case)

    @staticmethod
    def _verify_protected_preview(manifest: dict, raw: bytes, case: str) -> dict:
        receipt = json.loads(raw)
        anchor = manifest['anchor_hash']
        if case == 'beneficiary':
            receipt['payout']['script'] = '0014' + 'ff' * 20
        elif case == 'checkpoint':
            anchor = '00' * 32
        try:
            verified = protected_payout_evidence.verify(
                receipt, manifest['bundle_id'], manifest['anchor_height'], anchor,
                openssl=os.environ.get('PROOF_GROVE_OPENSSL', 'openssl'),
            )
        except ValueError as exc:
            return {'case': case, 'verified': False, 'detail': str(exc)}
        return {'case': case, 'verified': True, 'payout': verified}

    def protected_preview_archive(self) -> bytes:
        manifest, raw = self._protected_preview_input()
        if not self._verify_protected_preview(manifest, raw, 'original')['verified']:
            raise Refused('protected_preview_unverified')
        receipt_name = 'holder-receipt.json'
        pins = {key: manifest[key] for key in ('receipt_sha256', 'bundle_id', 'anchor_height', 'anchor_hash')}
        stream = io.BytesIO()
        with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('preview.json', canonical({'receipt': receipt_name, **pins}))
            archive.writestr(receipt_name, raw)
        return stream.getvalue()

    def chainstate(self) -> dict:
        if not self.core:raise Refused('core_not_configured')
        info=self.core.rpc('getblockchaininfo',[])
        if not isinstance(info,dict):raise Refused('core_response_invalid')
        network={'main':'mainnet','testnet4':'testnet4','regtest':'regtest'}.get(info.get('chain'))
        if not network:raise Refused('unsupported_chain')
        expected='regtest' if self.mode=='regtest' else (self.gate.policy['network'] if self.gate else None)
        if expected and network!=expected:raise Refused('core_network_mismatch')
        return {'evidence_level':'bitcoin-core','network':network,'observed_at':int(time.time()),
                **{k:info.get(k) for k in ('blocks','headers','bestblockhash','chainwork','mediantime','verificationprogress','initialblockdownload')},
                'meaning':'Fresh configured Core observation; this response is not a new ZK proof.'}

    def proof_check(self,body) -> dict:
        if self.mode!='live' or not self.gate:raise Refused('live_verifier_not_configured')
        try:
            statement=base64.b64decode(body.get('statement_base64',''),validate=True)
            proof=base64.b64decode(body.get('proof_base64',''),validate=True)
        except (ValueError,TypeError,binascii.Error):raise Refused('invalid_artifact_encoding') from None
        if len(statement)!=STATEMENT_SIZE or not 0<len(proof)<=PROOF_LIMIT:raise Refused('artifact_size')
        evidence=self.gate.verify(statement,proof)
        # A proof check has no recipient or issuance side effect. Admission uses
        # the original intent-bound endpoint and its stricter freshness policy.
        observation=None;chain_error=None
        if self.core:
            try:
                self.gate.check_anchor(self.core)
                observation=asdict(self.core.view_for(evidence))
            except Refused as error:chain_error=error.code
        else:chain_error='core_not_configured'
        return {'schema':'proof-grove/proof-check/v1','proof_verified':True,'evidence':asdict(evidence),
                'chain_observation':observation,'chain_error':chain_error,'payment_admitted':False,
                'meaning':'Native proof verified. No payment reserved, blind signatures requested or transaction signed.'}

    def recorded_proof(self):
        record=self.config.get('recorded_proof')
        if not isinstance(record,dict):raise Refused('recorded_proof_not_configured')
        return record

    def check_recorded_proof(self):
        record=self.recorded_proof()
        statement=read_bounded(record['statement_file'],STATEMENT_SIZE)
        proof=read_bounded(record['proof_file'],PROOF_LIMIT)
        for key,raw in (('statement',statement),('proof',proof)):
            if hashlib.sha256(raw).hexdigest()!=record[key+'_sha256']:raise Refused('recorded_artifact_changed')
        return self.proof_check({'statement_base64':base64.b64encode(statement).decode(),'proof_base64':base64.b64encode(proof).decode()})

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
        if self.mode=='live':self.gate.check_anchor(self.core)
        chain = self.core.view_for(evidence)
        receipt = self.ledger.prepare(intent.id, evidence, chain, rules, int(time.time()))
        return {"decision": {"accepted": True, "code": "prepared", "receipt": receipt},
                "evidence_level": evidence.kind, "simulation": False,
                "receipts": self.ledger.receipts()}


def make_server(desk: Desk, port: int = 8765, *, access: HostedAccess | None = None,
                bind: str = '127.0.0.1') -> ThreadingHTTPServer:
    if access and desk.mode=='demo':raise Refused('hosted_gateway_requires_connected_mode')
    if bind not in ('127.0.0.1','0.0.0.0') or (bind!='127.0.0.1' and not access):raise Refused('hosted_access_required_for_remote_bind')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Paths may contain private quote identifiers.

        def _guard(self, mutation: bool = False, preflight: bool = False):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if access:hosts.update(access.hosts)
            if self.headers.get("Host") not in hosts:
                raise Refused("invalid_host")
            origin = self.headers.get("Origin")
            origins=set(access.origins) if access else {"http://" + host for host in hosts}
            if origin and origin not in origins:
                raise Refused("invalid_origin")
            if access and not preflight and urlsplit(self.path).path.startswith('/api/'):
                access.authorize(self.headers,urlsplit(self.path).path,mutation)
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
            self._send_headers(status, len(payload), content_type)
            self.wfile.write(payload)

        def _send_headers(self, status: int, size: int, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if access:
                self.send_header('Vary','Origin')
                if self.headers.get('Origin') in access.origins:
                    self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
                    self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
                    self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type, X-Proof-Grove')
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()

        def _funded_preview(self, path):
            publication = desk.config.get('protected_funded_preview') if desk.mode == 'demo' else None
            with protected_funded_preview.verified_archive(publication) as checked:
                if path == '/api/protected/preview/funded':
                    value = {'status': 'pending'} if checked is None else checked[0]
                    self._send(200, canonical(value))
                elif checked is None:
                    raise Refused('funded_preview_pending')
                elif path == '/api/protected/preview/funded/verification':
                    self._send(200, checked[1])
                else:
                    _, _, source, size = checked
                    try:
                        self._send_headers(200, size, 'application/zip')
                        shutil.copyfileobj(source, self.wfile, length=128 * 1024)
                    except (BrokenPipeError, ConnectionResetError):
                        self.close_connection = True

        def _error(self, exc: Exception):
            if isinstance(exc, Refused):
                self._send(exc.status if isinstance(exc,AccessDenied) else 400, canonical({"error": exc.code, "detail": exc.detail}))
            else:
                self._send(500, canonical({"error": "internal_error"}))

        def do_OPTIONS(self):
            try:
                if not access:raise Refused('cors_not_enabled')
                self._guard(preflight=True)
                if self.headers.get('Origin') not in access.origins:raise Refused('invalid_origin')
                if self.headers.get('Access-Control-Request-Method') not in ('GET','POST'):raise Refused('invalid_preflight_method')
                requested={x.strip().lower() for x in self.headers.get('Access-Control-Request-Headers','').split(',') if x.strip()}
                if not requested<={'authorization','content-type','x-proof-grove'}:raise Refused('invalid_preflight_headers')
                self._send(204,b'')
            except Exception as exc:self._error(exc)

        def do_GET(self):
            try:
                self._guard()
                url = urlsplit(self.path)
                path = url.path
                if path in ('/api/protected/preview/funded', '/api/protected/preview/funded/archive',
                            '/api/protected/preview/funded/verification'):
                    self._funded_preview(path)
                    return
                evidence_prefix = '/api/protected/preview/evidence/'
                if path.startswith(evidence_prefix):
                    case, _, suffix = path.removeprefix(evidence_prefix).partition('/')
                    if path.endswith('/') or suffix not in ('', 'archive'):
                        raise Refused('recovery_evidence_unknown_case')
                    manifest = desk.config.get('protected_evidence_preview') if desk.mode == 'demo' else None
                    summary, archive = protected_evidence_preview.checked_archive(manifest, case)
                    if suffix == 'archive':
                        self._send(200, archive, 'application/zip')
                    else:
                        self._send(200, canonical(summary))
                    return
                with desk.lock:
                    if path == "/api/status":
                        value = desk.status()
                        value['hosted_access']={'enabled':bool(access),'mutations':bool(access and access.mutations),
                                                'private_bundles':bool(access and access.private_bundles)}
                    elif path == '/api/protected/preview':
                        value = desk.check_protected_preview(parse_qs(url.query).get('case', ['original'])[0])
                    elif path == '/api/protected/preview/archive':
                        self._send(200, desk.protected_preview_archive(), 'application/zip')
                        return
                    elif path == '/api/chainstate':
                        value=desk.chainstate()
                    elif path == '/api/proofs/recorded':
                        record=desk.recorded_proof()
                        value={k:record[k] for k in ('name','statement_sha256','proof_sha256')}
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
                    elif self.path == '/api/proofs/check':
                        value=desk.proof_check(body)
                    elif self.path == '/api/proofs/recorded/check':
                        if body:raise Refused('recorded_proof_parameters_not_allowed')
                        value=desk.check_recorded_proof()
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
                        value = desk.cashu.issue(body.get("intent_id"),body.get("payload"),body.get("authorization"),
                                                 body.get("protection"))
                    elif self.path in ("/api/cashu/protected/prepare", "/api/cashu/protected/settle", "/api/cashu/protected/status"):
                        if not desk.protected_melt:
                            raise Refused("protected_melt_not_configured")
                        intent, reserve, reserve_id = (body[key] for key in ("intent_id", "bundle", "bundle_id"))
                        if self.path.endswith("/prepare"):
                            value = desk.protected_melt.prepare(intent, reserve, reserve_id)
                        elif self.path.endswith("/settle"):
                            value = desk.protected_melt.settle(intent, reserve, reserve_id, body.get("psbt"))
                        else:
                            value = desk.protected_melt.status(intent, reserve, reserve_id)
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

    return ThreadingHTTPServer((bind, port), Handler)
