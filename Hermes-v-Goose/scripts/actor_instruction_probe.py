"""Replay recorded actor requests with their last instruction replaced, and count tool calls.

Phase 9 found the runtime actor answering BitAgent's A1 turn in text ("Reply
with one JSON object" won over an appended "call the tool" line). This sends
the exact requests a runtime made, with that instruction swapped for another,
to see whether the model then calls the tool.

Usage: python scripts/actor_instruction_probe.py --runs <runs dir> --url http://127.0.0.1:<port>
           --old-tail <file with the text to replace> --new-tail <file with the replacement> [--limit 6]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--old-tail", required=True)
    parser.add_argument("--new-tail", required=True)
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args(argv)
    old, new = Path(args.old_tail).read_text(encoding="utf-8"), Path(args.new_tail).read_text(encoding="utf-8")
    sent = calls = 0
    for run in sorted(Path(args.runs).glob("a.*"))[: args.limit]:
        line = (run / "model_io.jsonl").read_text(encoding="utf-8").splitlines()[0]
        body = json.loads(line)["request"]
        last = body["messages"][-1]
        if old not in str(last.get("content")):
            print(json.dumps({"run": run.name, "skipped": "old text not found"}))
            continue
        last["content"] = str(last["content"]).replace(old, new)
        body = dict(body) | {"stream": False}
        body.pop("stream_options", None)
        request = urllib.request.Request(args.url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=600) as response:
            message = json.loads(response.read())["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        sent += 1
        calls += bool(tool_calls)
        print(json.dumps({"run": run.name, "toolCalls": [(c["function"]["name"], c["function"]["arguments"][:200]) for c in tool_calls], "content": (message.get("content") or "")[:200]}), flush=True)
    print(json.dumps({"sent": sent, "withToolCall": calls}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
