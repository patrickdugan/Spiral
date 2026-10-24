"""Egress sink: the HTTP(S) proxy a controlled runtime is given, which refuses everything.

A runtime under test must reach nothing off the machine. Its environment names
this sink as ``HTTP_PROXY``/``HTTPS_PROXY`` (``NO_PROXY`` keeps loopback direct,
so the gateway and model proxy still work). Every request that reaches the
sink, ``CONNECT`` tunnels included, is answered ``403`` at once and recorded,
so a run's report lists each off-machine request the runtime tried to make.

A closed port would also refuse, but on Windows each connect to a closed
loopback port takes about two seconds to fail, and clients retry; an
answering sink fails them immediately.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

LOOPBACK = "127.0.0.1,localhost,::1"
PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


def serve_egress_sink(record_path: str | Path) -> tuple[ThreadingHTTPServer, str]:
    """Start the sink on loopback. Returns the running server and its proxy URL."""
    path = Path(record_path)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return None

        def _refuse(self) -> None:
            with lock, path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"at": time.time(), "method": self.command, "target": self.path}) + "\n")
            self.send_response(403, "egress blocked")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.close_connection = True

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_CONNECT = _refuse

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def egress_env(sink_url: str) -> dict[str, str]:
    """Proxy variables that send every non-loopback request to the sink."""
    env = {key: sink_url for key in PROXY_KEYS}
    env["NO_PROXY"] = env["no_proxy"] = LOOPBACK
    return env


def egress_attempts(record_path: str | Path) -> list[dict[str, Any]]:
    path = Path(record_path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
