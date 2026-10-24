"""JSONL server behind BitAgent's RuntimePolicy (src/bench/runtimePolicy.ts in BitAgent).

One process serves one runtime arm for a whole experiment. Each stdin line is a
request and gets one stdout line in reply, in order:

    {"id", "op": "run_start", "run": {experimentId, runId, scenarioId, policyId, harnessLevel, ...}}
    {"id", "op": "turn", "packet": {...}, "context": {...}, "scripted": {"proposed": ..., "margin": ...}, "prompt"?: "..."}
    {"id", "op": "run_end", "result": {status, effects, violations, cfc, ...}}
    {"id", "op": "shutdown"}

Replies are {"id", "ok": true, "result": ...} or {"id", "ok": false, "error": "..."}.
Run directories go to <runs-root>/<experimentId>/<runId>/ (design 8.3).

Usage: python scripts/bitagent_runtime_policy.py --arm null|R0|R1|R2 --runs-root <dir> [--goose-bin <exe>]
           [--model-url http://127.0.0.1:<port> --model-id <alias> --candidate-schema <file.json>]
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime_control.bitagent_step import ARMS, StepHarness  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--goose-bin")
    parser.add_argument("--model-url", help="loopback llama-server for a live actor model; omitted, the actor is scripted")
    parser.add_argument("--model-id", default="actor")
    parser.add_argument("--model-extra", help="JSON object added to every live model request, e.g. a llama-server per-request LoRA scale")
    parser.add_argument("--candidate-schema", help="JSON file: the schema of the tools' candidate argument for a live actor")
    args = parser.parse_args(argv)
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    out = sys.stdout
    sys.stdout = sys.stderr  # nothing but replies on the protocol stream
    schema = json.loads(Path(args.candidate_schema).read_text(encoding="utf-8")) if args.candidate_schema else None
    harness = StepHarness(args.arm, args.runs_root, goose_bin=args.goose_bin, model_upstream=args.model_url, model_id=args.model_id, candidate_schema=schema, model_extra=json.loads(args.model_extra) if args.model_extra else None)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            request = json.loads(line.lstrip(chr(0xFEFF)))
            op = request.get("op")
            try:
                if op == "run_start":
                    result = harness.start_run(request["run"])
                elif op == "turn":
                    result = harness.turn(request["packet"], request.get("context") or {}, request.get("scripted") or {}, request.get("prompt"))
                elif op == "run_end":
                    result = harness.end_run(request.get("result") or {})
                elif op == "shutdown":
                    out.write(json.dumps({"id": request.get("id"), "ok": True, "result": None}) + "\n")
                    out.flush()
                    break
                else:
                    raise ValueError(f"unknown op: {op}")
                reply = {"id": request.get("id"), "ok": True, "result": result}
            except Exception as exc:  # noqa: BLE001 - reported to the caller, which decides
                traceback.print_exc()
                reply = {"error": f"{type(exc).__name__}: {exc}", "id": request.get("id"), "ok": False}
            out.write(json.dumps(reply, default=str) + "\n")
            out.flush()
    finally:
        harness.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
