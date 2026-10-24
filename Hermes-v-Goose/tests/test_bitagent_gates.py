"""BitAgent's run-contract gates as a policy engine: decision-level replay of BitAgent's soundness suite.

``setUpClass`` runs BitAgent's ``eval/export-gate-calls.ts``, which re-runs the
42-scenario control-capability soundness suite twice (unrecorded, then recorded)
and writes every gate evaluation with the verdict the bench got. The tests then
replay those calls through ``BitAgentGatesEngine`` and through the control
module. Skipped without a BitAgent checkout and Node (BITAGENT_APP_ROOT,
BITAGENT_NODE).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402,F401  (puts src on sys.path)

from runtime_control.engines import build_engine  # noqa: E402
from runtime_control.engines_bitagent import ENGINE_ID, find_bitagent  # noqa: E402
from runtime_control.ledger import verify_receipt_file  # noqa: E402
from runtime_control.module import ControlModule  # noqa: E402
from runtime_control.runs import run_spec  # noqa: E402
from runtime_control.wire import PROPOSAL_SCHEMA, PROVENANCE_SCHEMA, call_fingerprint  # noqa: E402


BITAGENT = find_bitagent()
TOOL = "bitagent_execute"
CONTEXT_KEYS = ("contract", "approval", "budget", "receipts", "now", "tipSequence", "leaseSimulationHash")


def engine_for(phase: str, disabled=()):
    return build_engine({"engineId": ENGINE_ID, "config": {"tools": {TOOL: {"envelopeArg": "envelope", "phase": phase}}, "disabled": list(disabled)}})


def proposal_for(request, *, run_id="run-x", contract_hash="c", registry_hash="r"):
    args = {"envelope": request["envelope"]}
    return {
        "schema": PROPOSAL_SCHEMA,
        "actor": {"agentId": "root", "lineage": [run_id]},
        "args": args,
        "contractHash": contract_hash,
        "fingerprint": call_fingerprint(run_id, "root", TOOL, args),
        "proposedAt": "2026-10-09T12:00:00+00:00",
        "provenance": {"schema": PROVENANCE_SCHEMA, "attestation": "shim", "contextTaint": [], "surface": "agent_loop"},
        "runId": run_id,
        "runtime": {"commit": "n/a", "id": "null-runtime", "shimHash": "n/a", "tier": "harness", "version": "1"},
        "seq": 1,
        "tool": {"id": TOOL, "nativeName": TOOL, "registryHash": registry_hash},
    }


def view_for(request):
    return {"bitagent": {key: request[key] for key in CONTEXT_KEYS if key in request}}


class GateEnvironment:
    """Just enough environment for run_start: one envelope tool and the gate context as its view."""

    def __init__(self, view):
        self._view = view

    def registry(self):
        return {"schema": "control.tool_registry.v1", "tools": {TOOL: {"effectClass": "state_change"}}}

    def view(self):
        return self._view


@unittest.skipUnless(BITAGENT, "needs a BitAgent checkout with its gate server and Node (BITAGENT_APP_ROOT, BITAGENT_NODE)")
class BitAgentGatesReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root, node = BITAGENT
        cls.temp = tempfile.TemporaryDirectory()
        out = Path(cls.temp.name) / "gate-calls.jsonl"
        done = subprocess.run(
            [str(node), str(root / "node_modules" / "tsx" / "dist" / "cli.mjs"), "eval/export-gate-calls.ts", str(out)],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=600, stdin=subprocess.DEVNULL,
        )
        cls.summary = json.loads(done.stdout)
        cls.export_exit = done.returncode
        cls.calls = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_the_export_is_of_the_soundness_run_and_recording_changed_nothing(self) -> None:
        self.assertEqual(self.export_exit, 0)
        self.assertEqual((self.summary["scenarioCount"], self.summary["sound"], self.summary["recordingChangedNothing"]), (42, True, True))
        self.assertEqual(len(self.calls), self.summary["calls"])
        self.assertEqual({call["request"]["phase"] for call in self.calls}, {"simulate", "approval", "execute"})

    def test_every_recorded_gate_call_gets_the_same_verdict_through_the_engine(self) -> None:
        engines = {}
        outcomes = Counter()
        mismatches = []
        for call in self.calls:
            request, recorded = call["request"], call["verdict"]
            key = (request["phase"], tuple(request.get("disabled", ())))
            engine = engines.setdefault(key, engine_for(*key))
            result = engine.evaluate(proposal_for(request), SimpleNamespace(env_view=view_for(request)))
            outcomes[result["verdict"]] += 1
            if result["native"] != recorded:
                mismatches.append(request["id"])
            expected = "deny" if not recorded["admitted"] else ("allow" if recorded["nextAuthority"] == "lease" else "escalate")
            self.assertEqual(result["verdict"], expected, request["id"])
            if not recorded["admitted"]:
                self.assertEqual(result["reasonCodes"], recorded["reasonCodes"], request["id"])
        self.assertEqual(mismatches, [])
        self.assertEqual(outcomes["allow"] + outcomes["escalate"], self.summary["admitted"])
        self.assertEqual(sum(outcomes.values()), self.summary["calls"])

    def test_knocking_out_exactly_the_failing_gates_admits_every_refusal(self) -> None:
        # Gates are independent: a refusal is the conjunction of its failing gates, so disabling
        # those gates, and only those, must admit the call (BitAgent's mutation premise).
        refusals = [c for c in self.calls if not c["verdict"]["admitted"]]
        self.assertGreater(len(refusals), 100)
        gates_seen = set()
        for call in refusals:
            request = call["request"]
            failing = {code.split(":")[0] for code in call["verdict"]["reasonCodes"]}
            gates_seen.update(failing)
            knocked_out = sorted(failing | set(request.get("disabled", ())))
            result = engine_for(request["phase"], knocked_out).evaluate(proposal_for(request), SimpleNamespace(env_view=view_for(request)))
            self.assertEqual(result["verdict"], "allow", (request["id"], knocked_out))
        # G15 never refuses in the bench: its runner refuses unattested evidence before an envelope
        # is built (runner.ts, attestationOn). Under the control plane the gate stands alone.
        self.assertEqual(len(gates_seen), 17)
        self.assertNotIn("G15_evidence_attested", gates_seen)

    def test_in_each_gates_mutation_run_that_gate_alone_refuses_something_the_run_admitted(self) -> None:
        # Decision-level form of the soundness report's knockout check (18 of 18 caught): replay the
        # admitted calls of the run with gate Gk disabled, with Gk back on.
        caught = {}
        for call in self.calls:
            disabled = call["request"].get("disabled", [])
            if len(disabled) != 1 or not call["verdict"]["admitted"]:
                continue
            gate, request = disabled[0], call["request"]
            result = engine_for(request["phase"]).evaluate(proposal_for(request), SimpleNamespace(env_view=view_for(request)))
            if result["verdict"] == "deny" and all(code.startswith(gate + ":") for code in result["reasonCodes"]):
                caught.setdefault(gate, result["reasonCodes"])
        self.assertEqual(len(caught), 18, sorted(caught))
        self.assertEqual(caught["G15_evidence_attested"], ["G15_evidence_attested:intent_not_user_attested"])

    def test_a_decision_through_the_control_module_carries_the_gate_verdict(self) -> None:
        admitted = next(c for c in self.calls if c["verdict"]["admitted"] and c["request"]["phase"] == "execute" and not c["request"].get("disabled"))
        refused = next(c for c in self.calls if not c["verdict"]["admitted"] and c["request"]["phase"] == "execute" and not c["request"].get("disabled"))
        spec = {"engineId": ENGINE_ID, "config": {"tools": {TOOL: {"envelopeArg": "envelope", "phase": "execute"}}}}
        for name, call, verdict in (("admitted", admitted, "allow"), ("refused", refused, "deny")):
            with tempfile.TemporaryDirectory() as temp:
                module = ControlModule(Path(temp) / "ledger.jsonl")
                opened = module.open_run(run_spec("run-x", GateEnvironment(view_for(call["request"])), [spec], max_actions=5, shim=True))
                decision = module.decide(proposal_for(call["request"], contract_hash=opened["contractHash"], registry_hash=opened["registryHash"]))
                self.assertEqual(decision["verdict"], verdict, name)
                if verdict == "allow":
                    self.assertIn("lease", decision)
                else:
                    self.assertEqual(decision["reasonCodes"], call["verdict"]["reasonCodes"])
                module.close()
                records = [json.loads(line) for line in (Path(temp) / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
                row = next(r for r in records if r["kind"] == "control_decision")["payload"]["engines"][0]
                self.assertEqual((row["engineId"], row["verdict"]), (ENGINE_ID, call["verdict"]))
                self.assertTrue(verify_receipt_file(Path(temp) / "ledger.jsonl")[0])

    def test_wallet_user_approval_escalates_and_bad_input_denies(self) -> None:
        request = next(c for c in self.calls if c["verdict"]["admitted"])["request"]
        engine = engine_for("execute")

        class Stub:
            def evaluate(self, body):
                return {"admitted": True, "nextAuthority": "wallet_user", "checks": {}, "reasonCodes": []}

        engine.server = Stub()
        state = SimpleNamespace(env_view=view_for(request))
        self.assertEqual(engine.evaluate(proposal_for(request), state)["verdict"], "escalate")
        bad = proposal_for(request) | {"args": {"envelope": "not an envelope"}}
        self.assertEqual(engine.evaluate(bad, state)["reasonCodes"], ["invalid_arguments"])
        self.assertEqual(engine.evaluate(proposal_for(request), SimpleNamespace(env_view={}))["reasonCodes"], ["invalid_arguments"])


if __name__ == "__main__":
    unittest.main()
