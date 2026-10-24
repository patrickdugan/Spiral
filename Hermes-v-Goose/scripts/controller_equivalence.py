"""Record, or check, a controller server's raw answers on a fixed sample of qualification packets.

Used when the controller's server changes configuration (phase 9: the same base
weights with the actor's adapter loaded but not applied): every answer must take
the same action before results from the two configurations are treated as one
controller. Identical raw text is reported too, but not required.

Usage: python scripts/controller_equivalence.py --runs <collect runs> --url http://127.0.0.1:<port>/v1
           --model <alias> --out <file.json> [--against <earlier file.json>] [--every 7]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime_control.controller import CONTROL_ACTION_SCHEMA, ModelController  # noqa: E402
from runtime_control.replay import replay_controller  # noqa: E402


class Recorder(ModelController):
    """The model controller's exact request, keeping the raw answer text."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.answers: list[str] = []

    def turn(self, thread, events, trigger, packet=None):
        import urllib.request

        body = {"max_tokens": self.max_tokens, "messages": packet["messages"], "model": self.model, "temperature": 0,
                "response_format": {"type": "json_schema", "json_schema": {"name": "control_action", "schema": CONTROL_ACTION_SCHEMA, "strict": True}}} | self.extra
        request = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            content = json.loads(response.read())["choices"][0]["message"]["content"]
        self.answers.append(content)
        return json.loads(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--against")
    parser.add_argument("--every", type=int, default=7, help="take every Nth run directory that has controller turns")
    parser.add_argument("--extra", help="JSON object added to each request, e.g. a per-request LoRA scale")
    args = parser.parse_args(argv)
    runs = [p for p in sorted(Path(args.runs).iterdir()) if (p / "ledger.jsonl").exists()][:: args.every]
    rows = []
    for run in runs:
        recorder = Recorder(args.url, args.model, timeout_s=300, extra=json.loads(args.extra) if args.extra else None)
        replay_controller(run, recorder)
        rows.extend({"answer": answer, "run": run.name, "turn": n} for n, answer in enumerate(recorder.answers))
    Path(args.out).write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    result = {"answers": len(rows), "runs": len(runs)}
    if args.against:
        # The decision must match; free text need not: one server asked the same request twice at
        # temperature 0 already words a long intervention differently (prompt-cache reuse), 1 of 22.
        earlier = json.loads(Path(args.against).read_text(encoding="utf-8"))
        action = lambda row: json.loads(row["answer"]).get("action")  # noqa: E731
        same_turns = len(earlier) == len(rows) and all((a["run"], a["turn"]) == (b["run"], b["turn"]) for a, b in zip(earlier, rows))
        result["identical"] = same_turns and all(action(a) == action(b) for a, b in zip(earlier, rows))
        result["rawIdentical"] = sum(1 for a, b in zip(earlier, rows) if a == b)
        result["differentActions"] = [[a, b] for a, b in zip(earlier, rows) if action(a) != action(b)][:10]
    print(json.dumps(result, indent=2))
    return 0 if result.get("identical", True) else 1


if __name__ == "__main__":
    sys.exit(main())
