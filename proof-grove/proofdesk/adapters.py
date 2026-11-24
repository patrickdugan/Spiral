"""Provider clients and a read-only Core observer. Upstream owns wire schemas.

Cashu quote state and Bark wallet data are operator reports, never proof evidence.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .domain import ChainView, Evidence, Refused

RESPONSE_LIMIT = 2 * 1024 * 1024


class CoreRPCError(Refused):
    def __init__(self, rpc_code):
        self.rpc_code = rpc_code
        super().__init__("core_rpc_error")  # Never include upstream messages or credentials.


class HTTP:
    def __init__(self, base: str, headers: dict | None = None):
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise Refused("invalid_endpoint")
        if parsed.scheme != "https" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise Refused("https_required")
        if parsed.query or parsed.fragment:
            raise Refused("invalid_endpoint")
        self.base, self.headers = base.rstrip("/"), headers or {}

    def request(self, path: str, body: dict | None = None) -> dict | list:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=payload,
                                         headers={"Content-Type": "application/json", **self.headers})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
                raw = response.read(RESPONSE_LIMIT + 1)
            if len(raw) > RESPONSE_LIMIT:
                raise Refused("upstream_response_too_large")
            return json.loads(raw)
        except (OSError, ValueError, urllib.error.HTTPError):
            # URLs, credentials, invoices and quote IDs must not be echoed in logs.
            raise Refused("upstream_unavailable") from None


class CoreClient:
    def __init__(self, url: str, username: str, password: str):
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise Refused("core_loopback_required")
        auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.http = HTTP(url, {"Authorization": f"Basic {auth}"})
        self.cookie_file=None

    @classmethod
    def from_config(cls,config):
        if config.get('cookie_file'):
            client=cls(config['url'],'','');client.cookie_file=Path(config['cookie_file']);return client
        import os
        return cls(config['url'],config['username'],os.environ[config['password_env']])

    def rpc(self, method: str, params: list) -> object:
        # This explicit list cannot sign or broadcast.
        if method not in ("getblockchaininfo", "getblockhash", "getblockheader", "getrawtransaction", "validateaddress",
                          "decoderawtransaction", "gettxout", "getmempoolentry", "testmempoolaccept",
                          "getdescriptorinfo", "deriveaddresses", "createpsbt", "utxoupdatepsbt", "decodepsbt",
                          "gettxspendingprevout", "getindexinfo"):
            raise Refused("rpc_not_allowed")
        return self._call(method, params)

    def _call(self, method: str, params: list, path: str = "") -> object:
        if self.cookie_file:
            try:
                credential=self.cookie_file.read_bytes().strip()
                if not credential or b':' not in credential:raise OSError('invalid cookie')
                self.http.headers['Authorization']='Basic '+base64.b64encode(credential).decode()
            except OSError:raise Refused('core_cookie_unavailable') from None
        record = self.http.request(path, {"jsonrpc": "2.0", "id": "proof-grove", "method": method, "params": params})
        if isinstance(record, dict) and isinstance(record.get("error"), dict) and type(record["error"].get("code")) is int:
            raise CoreRPCError(record["error"]["code"])
        if not isinstance(record, dict) or record.get("error") is not None or "result" not in record:
            raise Refused("core_rpc_error")
        return record["result"]

    def view_for(self, evidence: Evidence) -> ChainView:
        before = self.rpc("getblockchaininfo", [])
        network = {"main": "mainnet", "testnet4": "testnet4", "regtest": "regtest"}.get(before.get("chain"))
        if network != evidence.network or before.get("initialblockdownload") is not False:
            raise Refused("core_not_ready")
        if self.rpc("getblockhash", [evidence.block_height]) != evidence.block_hash:
            raise Refused("payment_reorged")
        if self.rpc("getblockhash", [evidence.tip_height]) != evidence.tip_hash:
            raise Refused("proof_fork")
        after = self.rpc("getblockchaininfo", [])
        if before.get("bestblockhash") != after.get("bestblockhash"):
            raise Refused("chain_changed_retry")
        return ChainView(network, after["bestblockhash"], after["blocks"], int(time.time()),
                         evidence.block_hash, evidence.block_height, "bitcoin-core")


class CashuClient:
    def __init__(self, url: str):
        self.http = HTTP(url)

    def info(self) -> dict:
        record = self.http.request("/v1/info")
        if not isinstance(record, dict):
            raise Refused("cashu_response_invalid")
        return {"name": record.get("name", "Unnamed mint"), "version": record.get("version"),
                "methods": record.get("nuts", {}).get("4", {}).get("methods", []),
                "evidence_level": "operator-report"}

    def raw_quote(self, quote_id: str) -> dict:
        if not isinstance(quote_id,str) or not 1 <= len(quote_id) <= 200:
            raise Refused("invalid_quote")
        value = self.http.request("/v1/mint/quote/onchain/" + urllib.parse.quote(quote_id,safe=""))
        if not isinstance(value,dict):
            raise Refused("cashu_response_invalid")
        return value

    def quote(self, method: str, quote_id: str) -> dict:
        if method not in ("bolt11", "onchain", "arkoor") or not quote_id or len(quote_id) > 200:
            raise Refused("invalid_quote")
        record = self.http.request("/v1/mint/quote/" + method + "/" + urllib.parse.quote(quote_id, safe=""))
        if not isinstance(record, dict):
            raise Refused("cashu_response_invalid")
        return {key: record.get(key) for key in ("state", "amount_paid", "amount_issued", "updated_at")} | {
            "evidence_level": "operator-report", "method": method,
            "meaning": "Quote status only; no blind signatures or Cashu token validity verified."}


class BarkClient:
    def __init__(self, url: str, bearer: str = ""):
        if urllib.parse.urlsplit(url).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise Refused("bark_loopback_required")
        self.http = HTTP(url, {"Authorization": "Bearer " + bearer} if bearer else None)

    def read(self, resource: str):
        paths = {"info": "/wallet/ark-info", "vtxos": "/wallet/vtxos",
                 "rounds": "/wallet/rounds", "history": "/history",
                 "identity": "/wallet/addresses/index/0", "tip": "/bitcoin/tip"}
        if resource not in paths:
            raise Refused("bark_resource_not_allowed")
        return self.http.request("/api/v1" + paths[resource])

    def vtxo(self, identifier: str) -> dict:
        return self.http.request("/api/v1/wallet/vtxos/" + urllib.parse.quote(identifier, safe=""))

    def delegate_refresh(self, identifiers: list[str], height: int) -> dict:
        return self.http.request("/api/v1/wallet/refresh/delegated/vtxos", {"vtxos": identifiers, "height": height})

    def presign(self, identifiers: list[str], fee_rate: int) -> dict:
        return self.http.request("/api/v1/exits/presign", {"vtxos": identifiers, "fee_rate_sat_per_vb": fee_rate})

    def history(self) -> dict:
        record = self.http.request("/api/v1/history")
        # Preserve upstream schema for an operator to inspect locally, without promoting it.
        return {"evidence_level": "operator-report", "history": record,
                "meaning": "Bark-reported movements; no chain or Ark script proof established here."}
