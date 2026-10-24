"""Replay levels (design 8.4), the cross-runtime projection, and the step harness's null arm.

The end-to-end soundness runs through BitAgent's bench live in BitAgent
(``eval/run-runtime-soundness.ts``); here the step harness is driven with
synthetic packets, so these tests need neither BitAgent nor a runtime, except
the R2 test, which skips without Hermes Lite.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from fixtures import PAY_ALICE, PAY_MALLORY, proposal  # noqa: E402

from runtime_control.adapters.hermes_lite import find_hermes_lite, run_hermes_controlled  # noqa: E402
from runtime_control.bitagent_step import StepHarness, tool_for  # noqa: E402
from runtime_control.controller import ScriptedController  # noqa: E402
from runtime_control.demo import DemoLedgerEnvironment, demo_engine_spec  # noqa: E402
from runtime_control.engines import AlwaysHoldController  # noqa: E402
from runtime_control.gateway import ToolGateway  # noqa: E402
from runtime_control.module import ControlModule  # noqa: E402
from runtime_control.replay import audit, compare_projections, replay_controller, replay_decisions, replay_hermes  # noqa: E402
from runtime_control.runs import run_spec  # noqa: E402


def demo_run(run_dir: Path, calls, *, controller=None, runtime=None, call_ids=None):
    run_dir.mkdir(parents=True)
    environment = DemoLedgerEnvironment()
    module = ControlModule(run_dir / "ledger.jsonl", clock=fixtures.FakeClock(), controller=controller)
    spec = run_spec("run-fixture", environment, [demo_engine_spec()], max_actions=20, shim=True, controller=getattr(controller, "controller_id", "none"), runtime=runtime, triggers={"denialStreak": 1} if controller else None)
    opened = module.open_run(spec)
    gateway = ToolGateway(environment, module, run_id=opened["runId"], truth_path=run_dir / "truth.jsonl", io_path=run_dir / "gateway_io.jsonl")
    for n, args in enumerate(calls):
        body = proposal(opened, args, seq=n)
        body["runtime"] = dict(spec["runtime"])
        if call_ids:
            body["provenance"]["nativeCallId"] = f"{call_ids}-{n}"
        if module.decide(body)["verdict"] == "allow":
            gateway.call_tool("ledger_pay", args)
    module.close()
    return run_dir


class ReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_r0_audit_and_r1_decision_replay_with_a_counterfactual_policy(self) -> None:
        run = demo_run(self.root / "a", [PAY_ALICE, PAY_MALLORY, PAY_ALICE])
        self.assertTrue(audit(run)["ok"])
        self.assertTrue(replay_decisions(run)["reproduced"])
        knocked = replay_decisions(run, [demo_engine_spec(allow=("alice", "bob", "mallory"))])
        self.assertEqual([(c["recorded"][0], c["replayed"][0]) for c in knocked["changed"]], [("deny", "allow")])

    def test_r0_audit_catches_a_tampered_ledger(self) -> None:
        run = demo_run(self.root / "a", [PAY_ALICE])
        ledger = run / "ledger.jsonl"
        ledger.write_text(ledger.read_text(encoding="utf-8").replace('"amount":10', '"amount":11', 1), encoding="utf-8")
        self.assertFalse(audit(run)["ok"])

    def test_r1c_controller_packets_rebuild_and_another_controller_can_be_asked(self) -> None:
        script = ScriptedController({"denial_streak": [{"action": "intervene", "kind": "correct", "refs": [], "text": "Only alice or bob."}]})
        run = demo_run(self.root / "a", [PAY_ALICE, PAY_MALLORY, PAY_ALICE], controller=script)
        result = replay_controller(run, controller=AlwaysHoldController())
        self.assertGreaterEqual(result["turns"], 3)
        self.assertTrue(result["packetsReproduced"])
        self.assertEqual({row["counterfactual"]["action"] for row in result["rows"]}, {"hold"})

    def test_the_projection_ignores_the_runtime_and_native_ids_but_not_the_calls(self) -> None:
        hermes = {"commit": "616dda6", "id": "hermes-lite", "shimHash": "h" * 64, "tier": "fork", "version": "control-shim"}
        goose = {"commit": "25a68ae", "id": "goose", "shimHash": "g" * 64, "tier": "fork", "version": "1.53.0"}
        a = demo_run(self.root / "a", [PAY_ALICE, PAY_MALLORY], runtime=hermes, call_ids="call")
        b = demo_run(self.root / "b", [PAY_ALICE, PAY_MALLORY], runtime=goose, call_ids="toolu")
        c = demo_run(self.root / "c", [PAY_ALICE, {"amount": 11, "to": "alice"}], runtime=goose)
        self.assertTrue(compare_projections(a, b)["equal"])
        different = compare_projections(a, c)
        self.assertFalse(different["equal"])
        self.assertEqual(different["left"][0], "proposed")

    @unittest.skipUnless(find_hermes_lite(), "needs Hermes Lite (HERMES_LITE_ROOT)")
    def test_r2_hermes_replayed_against_its_recorded_model_and_gateway_makes_the_same_proposals(self) -> None:
        plan = [{"tool": "ledger_pay", "arguments": PAY_ALICE}, {"tool": "ledger_pay", "arguments": PAY_MALLORY}, {"content": "done"}]
        original = self.root / "orig"
        run_hermes_controlled(run_dir=original, environment=DemoLedgerEnvironment(), engines=[demo_engine_spec()], plan=plan, task="Pay alice 10 units.")
        replayed = replay_hermes(original, self.root / "replay", task="Pay alice 10 units.", environment=DemoLedgerEnvironment(), engines=[demo_engine_spec()])
        self.assertEqual((replayed["replayMisses"], replayed["sameProposals"]), (0, True))


PACKET = {"current_node": "observe", "run": {"status": "ACTIVE", "step": 0}, "task_id": "task-1"}
STEP = {"decision": "advance", "next_node": "inspect", "tool": "host.preflight"}
EXECUTE = {"decision": "advance", "next_node": "execute", "tool": "host.execute_approved"}


class StepHarnessNullArmTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.harness = StepHarness("null", Path(self.temp.name) / "runs")

    def tearDown(self) -> None:
        self.harness.close()
        self.temp.cleanup()

    def start(self, run_id, **extra):
        return self.harness.start_run({"experimentId": "exp", "runId": run_id, "scenarioId": "s#1", "policyId": "oracle", "harnessLevel": "H3"} | extra)

    def test_candidates_reach_the_runner_only_through_the_gateway(self) -> None:
        self.assertEqual((tool_for(STEP), tool_for(EXECUTE), tool_for("garbage")), ("bitagent_step", "bitagent_execute", "bitagent_step"))
        started = self.start("run-a")
        first = self.harness.turn(PACKET, {"attempt": 0, "violations": []}, {"proposed": STEP, "margin": 0.9})
        second = self.harness.turn(PACKET | {"current_node": "approval"}, {"attempt": 0, "violations": []}, {"proposed": EXECUTE})
        self.assertEqual((first["proposed"], first["margin"], second["proposed"]), (STEP, 0.9, EXECUTE))
        summary = self.harness.end_run({"status": "CLOSED", "effects": 1, "violations": [], "cfc": True})
        self.assertEqual((summary["consequentialCommits"], summary["bypasses"], summary["coverage"]["missing"], summary["ledger"][0]), (1, 0, 0, True))
        run_dir = Path(started["runDir"])
        for name in ("contract.json", "ledger.jsonl", "model_io.jsonl", "gateway_io.jsonl", "truth.jsonl", "summary.json"):
            self.assertTrue((run_dir / name).exists(), name)
        self.assertIn("bitagentRunResult", (run_dir / "truth.jsonl").read_text(encoding="utf-8"))

    def test_always_hold_lets_moves_through_and_holds_the_execute(self) -> None:
        self.start("run-hold", controller="always_hold")
        step = self.harness.turn(PACKET, {}, {"proposed": STEP})
        execute = self.harness.turn(PACKET, {}, {"proposed": EXECUTE})
        self.assertEqual((step["submitted"], execute["submitted"], execute["proposed"]), (True, False, None))
        self.assertIn("controller_hold", execute["decisions"][0]["reasonCodes"])
        summary = self.harness.end_run({"status": "HELD"})
        self.assertEqual((summary["consequentialCommits"], summary["controllerActions"]["hold"]), (0, 1))

    def test_runs_reuse_the_servers_and_keep_their_own_ledgers(self) -> None:
        a = Path(self.start("run-1")["runDir"])
        self.harness.turn(PACKET, {}, {"proposed": STEP})
        self.harness.end_run({"status": "CLOSED"})
        b = Path(self.start("run-2")["runDir"])
        self.harness.turn(PACKET, {}, {"proposed": EXECUTE})
        self.harness.end_run({"status": "CLOSED"})
        ledgers = [[json.loads(line)["kind"] for line in (d / "ledger.jsonl").read_text(encoding="utf-8").splitlines()] for d in (a, b)]
        self.assertEqual([kinds.count("run_start") for kinds in ledgers], [1, 1])
        self.assertNotIn("environment_transition", ledgers[0])
        self.assertIn("environment_transition", ledgers[1])


if __name__ == "__main__":
    unittest.main()
