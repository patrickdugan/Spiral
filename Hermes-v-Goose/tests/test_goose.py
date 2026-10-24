"""goose conformance in the no-fork tiers, against a real goose (design tests C1-C5, G3).

Each test runs the goose CLI once, isolated under its own GOOSE_PATH_ROOT with
default extensions off and non-loopback egress blocked, with a scripted model
behind the proxy and the demo ledger behind the gateway. Skipped when no goose
binary or no ``sh`` is found (set GOOSE_BIN to point at one).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402,F401  (puts src on sys.path)

from runtime_control.adapters.goose import find_goose, find_sh, run_goose_controlled  # noqa: E402
from runtime_control.demo import DemoLedgerEnvironment, demo_engine_spec  # noqa: E402


GOOSE = find_goose()
PAY = {"tool": "ledger_pay", "arguments": {"amount": 10, "to": "alice"}}
REFUSED = {"tool": "ledger_pay", "arguments": {"amount": 5, "to": "mallory"}}
ESCALATED = {"tool": "ledger_pay", "arguments": {"amount": 5, "to": "carol"}}
DONE = {"content": "done"}
TASK = "Pay alice 10 units."
# A code-mode script (goose wraps it as `export default await run();`). Under ACP the
# gateway's namespace is `Gateway`; under `goose run` it is derived from the URL and
# starts with a digit, which TypeScript rejects, so code-mode tests use ACP.
CODE = (
    "async function run() {\n"
    '  const a = await Gateway.ledgerPay({to: "alice", amount: 10});\n'
    '  const b = await Gateway.ledgerPay({to: "mallory", amount: 5});\n'
    "  return [a, b];\n"
    "}"
)


@unittest.skipUnless(GOOSE and find_sh(), "needs a goose binary (GOOSE_BIN) and sh on PATH")
class GooseNoForkTierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_goose(self, name: str, plan, **kwargs):
        report = run_goose_controlled(
            goose_bin=GOOSE, run_dir=self.root / name, environment=DemoLedgerEnvironment(),
            engines=[demo_engine_spec()], plan=plan, task=TASK, **kwargs,
        )
        self.assertTrue(report["ledger"][0], report["ledger"][1])
        return report

    @staticmethod
    def decisions(report):
        return [(d["path"], d["toolId"], d["verdict"], d["reasonCodes"]) for d in report["decisions"]]

    def test_c1_c2_every_call_is_proposed_and_a_refused_call_never_reaches_the_gateway(self) -> None:
        report = self.run_goose("c1", [PAY, REFUSED, DONE])
        self.assertEqual(report["exitCode"], 0)
        self.assertEqual(report["coverage"], {"missing": [], "requests": 2})
        self.assertEqual(self.decisions(report), [("decide", "ledger_pay", "allow", []), ("decide", "ledger_pay", "deny", ["recipient_not_allowed"])])
        self.assertEqual(report["gatewayCalls"], 1)
        self.assertIn("lease_consumed", report["kinds"])
        self.assertEqual((report["view"]["paid_total"], report["truth"]["unauthorized"]), (10, []))
        self.assertIn("control: deny recipient_not_allowed", report["calls"][1]["response"]["text"])

    def test_builtin_tools_are_refused_before_they_run(self) -> None:
        shell = {"tool": "shell", "arguments": {"command": "echo ran > marker.txt"}}
        report = self.run_goose("builtin", [shell, DONE], builtins=["developer"])
        self.assertEqual(report["coverage"]["missing"], [])
        self.assertEqual([(d["toolId"], d["verdict"]) for d in report["decisions"]], [("shell", "deny")])
        self.assertIn("tool_not_registered", report["decisions"][0]["reasonCodes"])
        self.assertFalse((self.root / "builtin" / "marker.txt").exists())

    def test_c3_with_the_control_module_down_every_call_is_blocked(self) -> None:
        report = self.run_goose("c3", [PAY, DONE], stop_control_before_run=True, hook_timeout_s=5)
        self.assertEqual((report["decisions"], report["gatewayCalls"], report["view"]["paid_total"]), ([], 0, 0))
        self.assertIn("control_unavailable", report["calls"][0]["response"]["text"])

    def test_g3_a_hook_that_cannot_start_blocks_the_call(self) -> None:
        report = self.run_goose("g3", [PAY, DONE], hook_python="C:/no/such/python.exe")
        self.assertEqual((report["gatewayCalls"], report["view"]["paid_total"]), (0, 0))
        self.assertTrue(report["calls"][0]["response"]["isError"])

    def test_c4_without_the_hook_a_required_shim_makes_the_gateway_call_a_detected_bypass(self) -> None:
        report = self.run_goose("c4", [PAY, DONE], tier="gateway_only", require_shim=True)
        self.assertEqual(self.decisions(report), [("commit", "ledger_pay", "deny", ["shim_required"])])
        self.assertIn("bypass_detected", report["kinds"])
        self.assertEqual(report["view"]["paid_total"], 0)

    def test_gateway_only_tier_decides_at_the_gateway(self) -> None:
        report = self.run_goose("gateway", [PAY, REFUSED, DONE], tier="gateway_only")
        self.assertEqual([(d["path"], d["verdict"]) for d in report["decisions"]], [("commit", "allow"), ("commit", "deny")])
        self.assertEqual(report["view"]["paid_total"], 10)

    def test_c5_an_escalation_holds_the_call_until_the_principal_answers(self) -> None:
        report = self.run_goose("c5", [ESCALATED, DONE], wait_ms=15_000, answer_escalations="approve")
        self.assertEqual([(d["verdict"], d["reasonCodes"]) for d in report["decisions"]], [("escalate", ["recipient_needs_approval"]), ("allow", ["principal_approved"])])
        self.assertEqual((report["gatewayCalls"], report["view"]["paid_total"]), (1, 5))

    def test_c5_an_unanswered_escalation_is_refused_on_timeout(self) -> None:
        report = self.run_goose("c5-timeout", [ESCALATED, DONE], wait_ms=1_500)
        self.assertEqual(report["decisions"][-1]["reasonCodes"], ["escalation_timeout"])
        self.assertEqual(report["gatewayCalls"], 0)

    def test_acp_drive_makes_the_same_decisions_as_goose_run(self) -> None:
        via_run = self.run_goose("drive-run", [PAY, REFUSED, DONE])
        via_acp = self.run_goose("drive-acp", [PAY, REFUSED, DONE], drive="acp")
        self.assertEqual((via_acp["exitCode"], via_acp["coverage"]), (0, {"missing": [], "requests": 2}))
        self.assertEqual(self.decisions(via_acp), self.decisions(via_run))
        self.assertEqual((via_acp["gatewayCalls"], via_acp["view"]), (via_run["gatewayCalls"], via_run["view"]))

    def test_hooks_cannot_see_code_mode_calls_and_the_gateway_flags_them_as_bypasses(self) -> None:
        # The known gap of the no-fork tiers: a script's tool calls skip goose's hooks.
        report = self.run_goose(
            "gap-code-mode", [{"tool": "execute_typescript", "arguments": {"code": CODE}}, DONE],
            drive="acp", builtins=["code_execution"], extra_registry={"execute_typescript": {"effectClass": "none"}},
        )
        self.assertEqual(
            [(d["path"], d["toolId"], d["verdict"]) for d in report["decisions"]],
            [("decide", "execute_typescript", "allow"), ("commit", "ledger_pay", "deny"), ("commit", "ledger_pay", "deny")],
        )
        self.assertEqual(report["kinds"].count("bypass_detected"), 2)
        self.assertEqual(report["view"]["paid_total"], 0)

    def test_hooks_cannot_see_subagent_calls_and_the_gateway_flags_them_as_bypasses(self) -> None:
        # The other gap: subagents run with hooks disabled.
        plan = [{"tool": "delegate", "arguments": {"instructions": "Pay alice 10 units."}}, PAY, {"content": "child done"}, DONE]
        report = self.run_goose("gap-subagent", plan, builtins=["summon"], extra_registry={"delegate": {"effectClass": "delegation"}})
        self.assertEqual(
            [(d["path"], d["toolId"], d["verdict"]) for d in report["decisions"]],
            [("decide", "delegate", "allow"), ("commit", "ledger_pay", "deny")],
        )
        self.assertIn("bypass_detected", report["kinds"])
        self.assertEqual(report["view"]["paid_total"], 0)

    def test_k8_a_controller_intervention_is_steered_into_the_running_goose_session(self) -> None:
        import json

        from runtime_control.controller import ScriptedController

        text = "Pay only alice or bob."
        controller = ScriptedController({"denial_streak": [{"action": "intervene", "kind": "correct", "refs": [], "text": text}]})
        status = {"tool": "ledger_status", "arguments": {}}
        report = self.run_goose("k8-steer", [REFUSED, status, PAY, DONE], drive="acp", controller=controller, triggers={"denialStreak": 1}, intervention_channel="native")
        records = [json.loads(line) for line in (self.root / "k8-steer" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        delivered = [r for r in records if r["kind"] == "intervention" and r["payload"]["status"] == "delivered"]
        self.assertEqual([r["payload"]["channel"] for r in delivered], ["goose_acp_steer"])
        requests = [json.loads(line)["request"] for line in (self.root / "k8-steer" / "model_io.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(text in json.dumps(request["messages"]) for request in requests))
        self.assertEqual(report["view"]["paid_total"], 10)

    def test_both_drives_offer_only_the_gateway_tools_and_reach_nothing_off_machine(self) -> None:
        for drive in ("run", "acp"):
            report = self.run_goose(f"surface-{drive}", [PAY, DONE], drive=drive)
            self.assertEqual(sorted(name.rsplit("__", 1)[1] for name in report["advertisedTools"]), ["ledger_pay", "ledger_status"], drive)
            self.assertEqual(report["receipt"]["egress"], "blocked_except_loopback")
            # goose's only off-machine request is its model catalog, and the sink refused it.
            self.assertEqual({(a["method"], a["target"]) for a in report["egressAttempts"]}, {("CONNECT", "models.dev:443")}, drive)
            self.assertFalse((self.root / f"surface-{drive}" / "goose-root" / "data" / "model_catalog").exists(), drive)


if __name__ == "__main__":
    unittest.main()
