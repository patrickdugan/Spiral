"""Drive goose over the Agent Client Protocol (``goose acp``, JSON-RPC on stdio).

ACP is goose's headless session surface. Unlike ``goose run`` it keeps a session
open across prompts and accepts ``_goose/unstable/session/steer``, which the
controller thread will use to deliver interventions (design section 6.7). goose
announces the run a steer must name in a ``session_info_update`` whose meta
carries ``goose.activeRunId``.

The client advertises no file-system or terminal capability, so goose cannot
ask it to read or write files. Permission requests (none are expected in
``GOOSE_MODE=auto``) are answered with a rejection.
"""

from __future__ import annotations

import itertools
import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Mapping


ACP_PROTOCOL_VERSION = 1


class AcpError(RuntimeError):
    def __init__(self, error: Mapping[str, Any]) -> None:
        super().__init__(json.dumps(error))
        self.error = dict(error)


class GooseAcpSession:
    def __init__(
        self,
        goose_bin: str | Path,
        *,
        environment: Mapping[str, str],
        cwd: str | Path,
        transcript_path: str | Path | None = None,
        on_update: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self._process = subprocess.Popen(
            [str(goose_bin), "acp"],
            cwd=str(cwd),
            env=dict(environment),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._pending: dict[int, dict[str, Any]] = {}
        self._events = threading.Condition()
        self.updates: list[dict[str, Any]] = []
        self.active_run_id: str | None = None
        self.session_id: str | None = None
        self._on_update = on_update
        self._transcript = open(transcript_path, "a", encoding="utf-8") if transcript_path else None
        self._stderr: list[str] = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    # ---------------------------------------------------------------- transport

    def _log(self, direction: str, message: Mapping[str, Any]) -> None:
        if self._transcript:
            self._transcript.write(json.dumps({"dir": direction, "msg": message}) + "\n")
            self._transcript.flush()

    def _send(self, message: Mapping[str, Any]) -> None:
        self._log("out", message)
        with self._lock:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()

    def _read_stderr(self) -> None:
        for line in self._process.stderr:
            self._stderr.append(line)

    def _read_stdout(self) -> None:
        for line in self._process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._log("in", message)
            if "method" in message and "id" in message:
                self._answer_agent_request(message)
            elif "method" in message:
                self._notification(message)
            else:
                with self._events:
                    self._pending[int(message["id"])] = message
                    self._events.notify_all()
        with self._events:
            self._events.notify_all()

    def _answer_agent_request(self, message: Mapping[str, Any]) -> None:
        if message["method"] == "session/request_permission":
            self._send({"id": message["id"], "jsonrpc": "2.0", "result": {"outcome": {"outcome": "cancelled"}}})
        else:
            self._send({"error": {"code": -32601, "message": f"client does not support {message['method']}"}, "id": message["id"], "jsonrpc": "2.0"})

    def _notification(self, message: Mapping[str, Any]) -> None:
        if message.get("method") != "session/update":
            return
        update = (message.get("params") or {}).get("update") or {}
        meta = update.get("_meta") if isinstance(update.get("_meta"), dict) else {}
        goose_meta = meta.get("goose") if isinstance(meta.get("goose"), dict) else {}
        with self._events:
            if "activeRunId" in goose_meta:
                self.active_run_id = goose_meta["activeRunId"]
            self.updates.append(dict(update))
            self._events.notify_all()
        if self._on_update:
            self._on_update(update)

    def request(self, method: str, params: Mapping[str, Any], *, timeout_s: float = 120.0) -> Any:
        request_id = next(self._ids)
        self._send({"id": request_id, "jsonrpc": "2.0", "method": method, "params": dict(params)})
        with self._events:
            ready = self._events.wait_for(lambda: request_id in self._pending or self._process.poll() is not None, timeout=timeout_s)
            if not ready:
                raise TimeoutError(f"{method} timed out after {timeout_s}s")
            if request_id not in self._pending:
                raise AcpError({"message": "goose acp exited", "stderr": "".join(self._stderr[-20:])})
            reply = self._pending.pop(request_id)
        if "error" in reply:
            raise AcpError(reply["error"])
        return reply.get("result")

    # ---------------------------------------------------------------- protocol

    def initialize(self) -> dict[str, Any]:
        return self.request(
            "initialize",
            {"clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}, "protocolVersion": ACP_PROTOCOL_VERSION},
        )

    def new_session(self, cwd: str | Path, mcp_servers: list[dict[str, Any]]) -> str:
        result = self.request("session/new", {"cwd": str(cwd), "mcpServers": mcp_servers})
        self.session_id = result["sessionId"]
        return self.session_id

    def prompt(self, text: str, *, timeout_s: float = 300.0) -> dict[str, Any]:
        return self.request("session/prompt", {"prompt": [{"text": text, "type": "text"}], "sessionId": self.session_id}, timeout_s=timeout_s)

    def steer(self, text: str) -> Any:
        """Queue user input into the active run (controller interventions use this)."""
        if not self.active_run_id:
            raise RuntimeError("no active run to steer")
        return self.request(
            "_goose/unstable/session/steer",
            {"expectedRunId": self.active_run_id, "prompt": [{"text": text, "type": "text"}], "sessionId": self.session_id},
        )

    def tool_calls(self) -> list[dict[str, Any]]:
        """Tool calls as goose reported them in session/update notifications, by id."""
        calls: dict[str, dict[str, Any]] = {}
        for update in self.updates:
            kind = update.get("sessionUpdate")
            if kind in ("tool_call", "tool_call_update") and update.get("toolCallId"):
                entry = calls.setdefault(update["toolCallId"], {"id": update["toolCallId"]})
                for key in ("title", "status", "rawInput", "rawOutput", "content"):
                    if key in update:
                        entry[key] = update[key]
        return list(calls.values())

    def close(self) -> str:
        try:
            self._process.stdin.close()
        except OSError:
            pass
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=10)
        for stream in (self._process.stdout, self._process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        if self._transcript:
            self._transcript.close()
        return "".join(self._stderr)
