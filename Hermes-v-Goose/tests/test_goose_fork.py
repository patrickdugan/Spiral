"""The goose fork's control gate (design tests C1-C3, C9, C10).

Runs a goose binary built from the `control-gate` branch (set GOOSE_FORK_BIN).
The fork proposes calls from inside goose's dispatcher, so it also sees what the
no-fork hook cannot: tool calls made from code-mode scripts, and subagents'
calls. ``tests/test_goose.py`` shows the release binary missing both.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402,F401  (puts src on sys.path)
from test_goose import CODE, DONE, PAY, REFUSED, TASK  # noqa: E402

from runtime_control.adapters.goose import run_goose_controlled  # noqa: E402
from runtime_control.demo import DemoLedgerEnvironment, demo_engine_spec  # noqa: E402


FORK = os.environ.get("GOOSE_FORK_BIN")


@unittest.skipUnless(FORK and Path(FORK).is_file(), "set GOOSE_FORK_BIN to a goose built from the control-gate branch")
class GooseForkTierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    extra_env: dict[str, str] = {}

    def run_goose(self, name: str, plan, **kwargs):
        kwargs["extra_env"] = self.extra_env | kwargs.get("extra_env", {})
        report = run_goose_controlled(
            goose_bin=FORK, run_dir=self.root / name, environment=DemoLedgerEnvironment(), engines=[demo_engine_spec()],
            plan=plan, task=TASK, tier="fork", goose_commit=os.environ.get("GOOSE_FORK_COMMIT"), **kwargs,
        )
        self.assertTrue(report["ledger"][0], report["ledger"][1])
        return report

    @staticmethod
    def rows(report):
        return [(d["path"], d["toolId"], d["verdict"], d["surface"]) for d in report["decisions"]]

    def test_c1_c2_the_gate_proposes_every_call_and_refused_calls_never_reach_the_gateway(self) -> None:
        report = self.run_goose("c1", [PAY, REFUSED, DONE])
        self.assertEqual(report["exitCode"], 0)
        self.assertEqual(report["coverage"], {"missing": [], "requests": 2})
        self.assertEqual(self.rows(report), [("decide", "ledger_pay", "allow", "agent_loop"), ("decide", "ledger_pay", "deny", "agent_loop")])
        self.assertEqual(report["gatewayCalls"], 1)
        self.assertNotIn("bypass_detected", report["kinds"])
        self.assertIn("denied by control gate", report["calls"][1]["response"]["text"])

    def test_c9_code_mode_calls_are_proposed_as_their_own_surface(self) -> None:
        report = self.run_goose(
            "c9", [{"tool": "execute_typescript", "arguments": {"code": CODE}}, DONE],
            drive="acp", builtins=["code_execution"], extra_registry={"execute_typescript": {"effectClass": "none"}},
        )
        self.assertEqual(
            self.rows(report),
            [
                ("decide", "execute_typescript", "allow", "agent_loop"),
                ("decide", "ledger_pay", "allow", "code_mode"),
                ("decide", "ledger_pay", "deny", "code_mode"),
            ],
        )
        self.assertNotIn("bypass_detected", report["kinds"])
        self.assertEqual((report["gatewayCalls"], report["view"]["paid_total"]), (1, 10))

    def test_c10_a_subagent_is_its_own_actor_and_its_lease_reaches_the_gateway(self) -> None:
        plan = [{"tool": "delegate", "arguments": {"instructions": "Pay alice 10 units."}}, PAY, {"content": "child done"}, DONE]
        report = self.run_goose("c10", plan, builtins=["summon"], extra_registry={"delegate": {"effectClass": "delegation"}})
        decisions = report["decisions"]
        self.assertEqual([(d["toolId"], d["verdict"]) for d in decisions], [("delegate", "allow"), ("ledger_pay", "allow")])
        self.assertEqual(decisions[0]["agentId"], "root")
        self.assertTrue(decisions[1]["agentId"].startswith("root/"), decisions[1]["agentId"])
        self.assertEqual(decisions[1]["surface"], "subagent")
        self.assertIn("delegation_spawned", report["kinds"])
        self.assertNotIn("bypass_detected", report["kinds"])
        self.assertEqual(report["view"]["paid_total"], 10)

    def test_c3_with_the_control_module_down_every_call_is_blocked(self) -> None:
        report = self.run_goose("c3", [PAY, DONE], stop_control_before_run=True)
        self.assertEqual((report["decisions"], report["gatewayCalls"], report["view"]["paid_total"]), ([], 0, 0))
        self.assertIn("control_unavailable", report["calls"][0]["response"]["text"])

    def test_required_control_with_an_unusable_config_blocks_every_call(self) -> None:
        report = self.run_goose("broken", [PAY, DONE], extra_env={"GOOSE_CONTROL_CONFIG": str(self.root / "missing.json")})
        self.assertEqual((report["decisions"], report["gatewayCalls"]), ([], 0))
        self.assertIn("unusable", report["calls"][0]["response"]["text"])


class GooseForkStateMachineTests(GooseForkTierTests):
    """The same cases through goose's state-machine loop, which dispatches tools by its own path."""

    extra_env = {"GOOSE_STATE_MACHINE": "1"}


if __name__ == "__main__":
    unittest.main()
