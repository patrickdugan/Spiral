"""Time a llama-server whose requests alternate between an adapter's default scale and scale 0.

Phase 9 wants the actor (base + adapter, applied by default) and the controller
(base: the adapter at scale 0 per request) on one GPU server. This measures
whether switching costs anything: each real controller packet is sent twice in
a row with the adapter off, then once with it on, cycling, with the prompt cache
off so every request evaluates its whole prompt.

Usage: python scripts/lora_switch_bench.py --runs <collect runs> --url http://127.0.0.1:<port> [--packets 6]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime_control.controller import CONTROL_ACTION_SCHEMA  # noqa: E402
from runtime_control.replay import replay_controller  # noqa: E402

OFF = {"lora": [{"id": 0, "scale": 0}]}


class Capture:
    controller_id = "capture"

    def __init__(self) -> None:
        self.packets: list[dict] = []

    def turn(self, thread, events, trigger, packet=None):
        self.packets.append(packet)
        return {"action": "pass"}


def ask(url: str, packet: dict, extra: dict) -> tuple[float, str]:
    body = {"cache_prompt": False, "max_tokens": 64, "messages": packet["messages"], "model": "x", "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "control_action", "schema": CONTROL_ACTION_SCHEMA, "strict": True}}} | extra
    started = time.perf_counter()
    request = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        content = json.loads(response.read())["choices"][0]["message"]["content"]
    return time.perf_counter() - started, content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--packets", type=int, default=6)
    args = parser.parse_args(argv)
    capture = Capture()
    for run in sorted(Path(args.runs).iterdir())[::20]:
        if (run / "ledger.jsonl").exists():
            replay_controller(run, capture)
        if len(capture.packets) >= args.packets:
            break
    rows = []
    for packet in capture.packets[: args.packets]:
        for label, extra in (("off-after-on", OFF), ("off-again", OFF), ("on-after-off", {})):
            seconds, content = ask(args.url.rstrip("/"), packet, extra)
            rows.append({"label": label, "seconds": round(seconds, 2), "answer": content[:80]})
            print(json.dumps(rows[-1]), flush=True)
    summary = {label: round(statistics.median(r["seconds"] for r in rows if r["label"] == label), 2) for label in ("off-after-on", "off-again", "on-after-off")}
    print(json.dumps({"medianSeconds": summary}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
