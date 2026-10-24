"""A stand-in llama-server for dry runs of live-model paths. Never a source of results.

It answers OpenAI chat completions on loopback, and the two endpoints the model
proxy uses to count tokens (``/apply-template``, ``/tokenize``):

* a request that offers tools is an actor turn: the fake finds the BitAgent
  packet in the prompt (or, in BitAgent's A1 prompt, the admissible moves) and
  submits a candidate for its first admissible move (``bitagent_execute`` when
  that move is ``execute``), then says it is done;
* a request with ``response_format`` is a controller turn: the fake answers
  ``hold`` when the rendered events show an execute candidate, else ``pass``;
* anything else gets a short text answer.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping

PACKET = re.compile(r"Packet: (\{.*?\})\nAttempt: ", re.S)
MOVES = re.compile(r"ADMISSIBLE MOVES\n- (\S+)")


def actor_reply(body: Mapping[str, Any]) -> dict[str, Any]:
    messages = body.get("messages") or []
    if any(m.get("role") == "tool" for m in messages):
        return {"content": "submitted", "role": "assistant"}
    text = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "user")
    found, moves = PACKET.search(text), MOVES.search(text)
    if found:
        packet = json.loads(found.group(1))
        decision, node, tool = (packet.get("admissible") or ["hold/hold/host.hold"])[0].split("/")
        candidate: dict[str, Any] = {
            "arg_refs": {}, "authority": "model_candidate", "decision": decision, "effect": "none", "evidence_ids": [],
            "next_node": node, "reason_code": "fake_first_admissible", "risk_flags": [],
            "schema": "bitagent.dag_candidate.v3", "task_id": packet.get("task_id"), "tool": tool,
        }
    elif moves:  # BitAgent's A1 prompt: the move's five fields, which the host completes
        decision, node, tool = moves.group(1).split("/")
        candidate = {"arg_refs": {}, "decision": decision, "next_node": node, "reason_code": "fake_first_admissible", "tool": tool}
    else:
        return {"content": "no packet", "role": "assistant"}
    names = [t["function"]["name"] for t in body.get("tools") or ()]
    wanted = "bitagent_execute" if node == "execute" else "bitagent_step"
    name = next((n for n in names if n == wanted or n.endswith("__" + wanted)), wanted)
    return {"content": None, "role": "assistant", "tool_calls": [{"function": {"arguments": json.dumps({"candidate": candidate}), "name": name}, "id": "call_fake", "type": "function"}]}


def controller_reply(body: Mapping[str, Any]) -> dict[str, Any]:
    text = "\n".join(str(m.get("content") or "") for m in body.get("messages") or ())
    action = {"action": "hold", "reasonCode": "fake_hold"} if 'next_node: "execute"' in text else {"action": "pass"}
    return {"content": json.dumps(action), "role": "assistant"}


def serve_fake_model() -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return None

        def _json(self, body: Any) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            path = self.path.split("?", 1)[0].rstrip("/")
            if path == "/apply-template":
                self._json({"prompt": json.dumps(body.get("messages"))})
            elif path == "/tokenize":
                self._json({"tokens": list(range(len(str(body.get("content", ""))) // 4 + 1))})
            elif path.endswith("/chat/completions"):
                message = controller_reply(body) if body.get("response_format") else actor_reply(body) if body.get("tools") else {"content": "ok", "role": "assistant"}
                finish = "tool_calls" if message.get("tool_calls") else "stop"
                self._json({"choices": [{"finish_reason": finish, "index": 0, "message": message}], "created": 0, "id": "fake", "model": body.get("model", "fake"), "object": "chat.completion", "usage": {"completion_tokens": 1, "prompt_tokens": 1, "total_tokens": 2}})
            else:
                self.send_response(404)
                self.end_headers()

        def do_GET(self) -> None:
            self._json({"data": [{"id": "fake", "object": "model"}], "object": "list"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":  # python -m runtime_control.fake_model: serve until interrupted
    import time

    server, url = serve_fake_model()
    print(url, flush=True)
    while True:
        time.sleep(3600)
