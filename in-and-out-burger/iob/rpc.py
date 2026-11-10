"""Minimal Bitcoin Core JSON-RPC client (cookie or user/password auth)."""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request


class RPCError(Exception):
    pass


class RPC:
    def __init__(self, url: str, cookie: str | None = None, user: str | None = None, password: str | None = None, wallet: str | None = None, timeout: int = 60):
        if cookie:
            with open(cookie, encoding="utf-8") as f:
                user, password = f.read().strip().split(":", 1)
        self.url = url.rstrip("/") + (f"/wallet/{wallet}" if wallet else "")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.timeout = timeout

    def wallet(self, name: str) -> "RPC":
        other = object.__new__(RPC)
        other.url, other.auth, other.timeout = self.url.split("/wallet/")[0] + f"/wallet/{name}", self.auth, self.timeout
        return other

    def call(self, method: str, *params):
        body = json.dumps({"jsonrpc": "1.0", "id": "iob", "method": method, "params": list(params)}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Authorization": self.auth, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                out = json.loads(e.read())
            except Exception:
                raise RPCError(f"{method}: HTTP {e.code}") from None
        except urllib.error.URLError as e:
            raise RPCError(f"{method}: {e.reason}") from None
        if out.get("error"):
            raise RPCError(f"{method}: {out['error'].get('message')}")
        return out["result"]


def btc_amount(sats: int) -> str:
    return f"{sats // 100_000_000}.{sats % 100_000_000:08d}"
