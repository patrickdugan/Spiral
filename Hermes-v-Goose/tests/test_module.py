"""Decision pipeline, leases, escalations, controller and transport (D1-D8, C2-C5, K2-K5, S2)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import (  # noqa: E402
    PAY_ALICE,
    PAY_ALICE_BIG,
    PAY_CAROL,
    PAY_MALLORY,
    FakeClock,
    commit_request,
    kinds,
    open_module,
    proposal,
    records,
    view_event,
)

from runtime_control.client import ControlClient  # noqa: E402
from runtime_control.errors import ControlError  # noqa: E402
from runtime_control.gateway import ToolGateway  # noqa: E402
from runtime_control.module import ControlModule, utc_now  # noqa: E402
from runtime_control.server import new_tokens, serve_control  # noqa: E402


class DecisionPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_d1_unregistered_tool_is_consequential_and_refused(self) -> None:
        module, _, opened = open_module(self.path)
        decision = module.decide(proposal(opened, {"cmd": "rm -rf /"}, tool="shell"))
        self.assertEqual((decision["verdict"], decision["effectClass"]), ("deny", "state_change"))
        self.assertIn("tool_not_registered", decision["reasonCodes"])

    def test_d2_fingerprint_mismatch_is_refused_and_recorded(self) -> None:
        module, _, opened = open_module(self.path)
        decision = module.decide(proposal(opened, PAY_ALICE, fingerprint="0" * 64))
        self.assertIn("fingerprint_mismatch", decision["reasonCodes"])
        proposed = next(r for r in records(self.path) if r["kind"] == "action_proposed")
        self.assertFalse(proposed["payload"]["fingerprintValid"])

    def test_d3_every_proposal_is_recorded_even_when_refused_before_policy(self) -> None:
        module, _, opened = open_module(self.path)
        decision = module.decide(proposal(opened, PAY_ALICE, agent="stranger"))
        self.assertIn("unknown_actor", decision["reasonCodes"])
        self.assertEqual(kinds(self.path)[1:3], ["action_proposed", "control_decision"])

    def test_d4_an_engine_exception_is_a_denial(self) -> None:
        module, _, opened = open_module(self.path)

        class Broken:
            engine_id = "broken"
            policy_hash = "0" * 64

            def evaluate(self, proposal, state):
                raise RuntimeError("boom")

        module._engines.append(Broken())
        decision = module.decide(proposal(opened, PAY_ALICE))
        self.assertEqual((decision["verdict"], decision["reasonCodes"]), ("deny", ["engine_error"]))

    def test_policy_refusals_carry_the_engine_reason(self) -> None:
        module, _, opened = open_module(self.path)
        self.assertEqual(module.decide(proposal(opened, PAY_ALICE_BIG))["reasonCodes"], ["per_call_cap"])
        self.assertEqual(module.decide(proposal(opened, PAY_MALLORY, seq=1))["reasonCodes"], ["recipient_not_allowed"])

    def test_reads_take_the_short_path_without_a_lease(self) -> None:
        module, _, opened = open_module(self.path)
        decision = module.decide(proposal(opened, {}, tool="ledger_status"))
        self.assertEqual((decision["verdict"], decision["effectClass"]), ("allow", "read"))
        self.assertNotIn("lease_issued", kinds(self.path))

    def test_d6_identical_calls_get_one_lease_each_and_a_third_commit_is_a_bypass(self) -> None:
        module, _, opened = open_module(self.path, shim=True)
        first = module.decide(proposal(opened, PAY_ALICE, seq=1))
        second = module.decide(proposal(opened, PAY_ALICE, seq=2))
        self.assertNotEqual(first["lease"]["leaseId"], second["lease"]["leaseId"])
        request = commit_request(opened, PAY_ALICE)
        results = [module.commit(request) for _ in range(3)]
        self.assertEqual([r["committed"] for r in results], [True, True, False])
        self.assertEqual([r.get("leaseId") for r in results[:2]], [first["lease"]["leaseId"], second["lease"]["leaseId"]])
        self.assertIn("shim_required", results[2]["reasonCodes"])
        self.assertEqual(kinds(self.path).count("bypass_detected"), 1)

    def test_d7_an_expired_lease_is_refused_and_released(self) -> None:
        clock = FakeClock()
        module, _, opened = open_module(self.path, clock=clock, lease_ttl_ms=1_000)
        module.decide(proposal(opened, PAY_ALICE))
        self.assertEqual(module.state.reserved, 1)
        clock.advance(1_001)
        self.assertFalse(module.commit(commit_request(opened, PAY_ALICE))["committed"])
        expired = [r["payload"] for r in records(self.path) if r["kind"] == "lease_expired"]
        self.assertEqual(expired[0]["cause"], "ttl")
        self.assertEqual((module.state.reserved, module.state.spent), (0, 0))

    def test_d8_a_state_change_between_decide_and_commit_fails_the_recheck(self) -> None:
        module, environment, opened = open_module(self.path)
        self.assertEqual(module.decide(proposal(opened, PAY_ALICE))["verdict"], "allow")
        module.event("environment_view", view_event(environment, paid_total=95), "harness")
        result = module.commit(commit_request(opened, PAY_ALICE))
        self.assertEqual((result["committed"], result["reasonCodes"]), (False, ["total_cap"]))
        expired = [r["payload"] for r in records(self.path) if r["kind"] == "lease_expired"]
        self.assertEqual(expired[0]["cause"], "recheck_failed")

    def test_budget_caps_consequential_actions(self) -> None:
        module, _, opened = open_module(self.path, max_actions=1)
        self.assertEqual(module.decide(proposal(opened, PAY_ALICE, seq=1))["verdict"], "allow")
        refused = module.decide(proposal(opened, PAY_ALICE, seq=2))
        self.assertEqual((refused["verdict"], refused["reasonCodes"]), ("deny", ["budget_exhausted"]))

    def test_projection_carries_no_lease_or_truth(self) -> None:
        module, _, opened = open_module(self.path)
        module.decide(proposal(opened, PAY_ALICE))
        text = json.dumps(module.projection())
        for forbidden in ("leaseId", "authorized", "unauthorized", "env_view"):
            self.assertNotIn(forbidden, text)


class EscalationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_c5_an_escalation_blocks_until_the_principal_answers(self) -> None:
        module, _, opened = open_module(self.path)
        result: dict = {}
        worker = threading.Thread(target=lambda: result.update(module.decide(proposal(opened, PAY_CAROL), wait_ms=10_000)))
        worker.start()
        for _ in range(200):
            if module.state.escalations:
                break
            threading.Event().wait(0.01)
        (escalation_id,) = module.state.escalations
        module.resolve_escalation(escalation_id, {"decision": "approve", "by": "principal"})
        worker.join(5)
        self.assertEqual(result["verdict"], "allow")
        self.assertIn("lease", result)

    def test_c5_an_unanswered_escalation_is_denied_on_timeout(self) -> None:
        module, _, opened = open_module(self.path)
        module._clock = utc_now
        decision = module.decide(proposal(opened, PAY_CAROL), wait_ms=50)
        self.assertEqual((decision["verdict"], decision["reasonCodes"]), ("deny", ["escalation_timeout"]))

    def test_k5_an_open_question_survives_a_restart(self) -> None:
        module, _, opened = open_module(self.path)
        decision = module.decide(proposal(opened, PAY_CAROL))
        self.assertEqual(decision["verdict"], "escalate")
        resumed = ControlModule.resume(self.path, clock=FakeClock())
        self.assertEqual(resumed.projection()["openQuestions"], [decision["escalationId"]])
        final = resumed.resolve_escalation(decision["escalationId"], {"decision": "reject"})
        self.assertEqual((final["verdict"], final["reasonCodes"]), ("deny", ["principal_rejected"]))

    def test_a_principal_approval_survives_the_commit_recheck_but_a_later_hard_deny_does_not(self) -> None:
        module, environment, opened = open_module(self.path, principal="scripted_approve")
        self.assertEqual(module.decide(proposal(opened, PAY_CAROL, seq=1))["verdict"], "allow")
        self.assertTrue(module.commit(commit_request(opened, PAY_CAROL))["committed"])
        self.assertEqual(module.decide(proposal(opened, PAY_CAROL, seq=2))["verdict"], "allow")
        module.event("environment_view", view_event(environment, paid_total=99), "harness")
        refused = module.commit(commit_request(opened, PAY_CAROL))
        self.assertFalse(refused["committed"])
        self.assertIn("total_cap", refused["reasonCodes"])

    def test_closing_withdraws_open_questions(self) -> None:
        module, _, opened = open_module(self.path)
        module.decide(proposal(opened, PAY_CAROL))
        module.close()
        statuses = [r["payload"]["status"] for r in records(self.path) if r["kind"] == "escalation"]
        self.assertEqual(statuses, ["open", "withdrawn"])


class ControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_k2_always_hold_denies_admitted_calls_and_issues_no_lease(self) -> None:
        module, _, opened = open_module(self.path, controller="always_hold")
        decision = module.decide(proposal(opened, PAY_ALICE))
        self.assertEqual((decision["verdict"], decision["reasonCodes"]), ("deny", ["controller_hold"]))
        self.assertNotIn("lease_issued", kinds(self.path))

    def test_k3_no_controller_output_can_admit_what_the_engines_refused(self) -> None:
        class Rogue:
            controller_id = "rogue"

            def turn(self, thread, events, trigger):
                return {"action": "allow"}

        module, _, opened = open_module(self.path, controller_obj=Rogue())
        self.assertEqual(module.decide(proposal(opened, PAY_MALLORY, seq=1))["verdict"], "deny")
        self.assertNotIn("controller_turn", kinds(self.path))
        malformed = module.decide(proposal(opened, PAY_ALICE, seq=2))
        self.assertEqual((malformed["verdict"], malformed["reasonCodes"]), ("deny", ["controller_unavailable"]))

    def test_k4_a_failing_controller_holds_by_default(self) -> None:
        class Crashing:
            controller_id = "crashing"

            def turn(self, thread, events, trigger):
                raise TimeoutError("model server down")

        module, _, opened = open_module(self.path, controller_obj=Crashing())
        self.assertEqual(module.decide(proposal(opened, PAY_ALICE))["reasonCodes"], ["controller_unavailable"])

    def test_halt_run_stops_every_later_decision(self) -> None:
        class Halting:
            controller_id = "halting"

            def turn(self, thread, events, trigger):
                return {"action": "halt_run", "reasonCode": "drift"}

        module, _, opened = open_module(self.path, controller_obj=Halting())
        self.assertEqual(module.decide(proposal(opened, PAY_ALICE, seq=1))["reasonCodes"], ["drift"])
        self.assertEqual(module.state.status, "HELD")
        self.assertIn("run_not_active", module.decide(proposal(opened, PAY_ALICE, seq=2))["reasonCodes"])


class TransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def serve(self, **kwargs):
        module, environment, opened = open_module(self.root / "ledger.jsonl", **kwargs)
        tokens = new_tokens()
        server, url = serve_control(module, tokens)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return module, environment, opened, tokens, url

    def test_s2_each_role_reaches_only_its_routes(self) -> None:
        _, _, opened, tokens, url = self.serve()
        shim = ControlClient(url, tokens["shim"])
        gateway = ControlClient(url, tokens["gateway"])
        self.assertEqual(shim.decide(proposal(opened, PAY_ALICE))["verdict"], "allow")
        with self.assertRaises(ControlError) as caught:
            shim.commit(commit_request(opened, PAY_ALICE))
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(ControlError) as caught:
            gateway.decide(proposal(opened, PAY_ALICE))
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(ControlError) as caught:
            shim.event("grant_issued", {"view": {}})
        self.assertEqual(caught.exception.code, "event_not_allowed")
        with self.assertRaises(urllib.error.HTTPError) as caught_http:
            urllib.request.urlopen(urllib.request.Request(url + "/v1/projection"), timeout=5)
        self.assertEqual(caught_http.exception.code, 401)

    def test_c3_with_the_control_module_down_every_call_is_denied(self) -> None:
        _, environment, opened, tokens, _ = self.serve(shim=False)
        dead = ControlClient("http://127.0.0.1:9", tokens["gateway"], timeout_s=1)
        gateway = ToolGateway(environment, dead, run_id=opened["runId"], truth_path=self.root / "truth.jsonl")
        before = environment.view()
        result = gateway.call_tool("ledger_pay", PAY_ALICE)
        self.assertTrue(result["isError"])
        self.assertIn("control_unavailable", result["content"][0]["text"])
        self.assertEqual(environment.view(), before)

    def test_c2_c4_gateway_without_shim_decides_alone_and_flags_bypass(self) -> None:
        _, environment, opened, tokens, url = self.serve(shim=True)
        gateway = ToolGateway(environment, ControlClient(url, tokens["gateway"]), run_id=opened["runId"], truth_path=self.root / "truth.jsonl")
        result = gateway.call_tool("ledger_pay", PAY_ALICE)
        self.assertTrue(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["reasonCodes"], ["shim_required"])
        self.assertEqual(environment.view()["paid_total"], 0)
        self.assertIn("bypass_detected", kinds(self.root / "ledger.jsonl"))

    def test_an_allowed_call_commits_and_reports_the_new_view(self) -> None:
        module, environment, opened, tokens, url = self.serve(shim=False)
        gateway = ToolGateway(environment, ControlClient(url, tokens["gateway"]), run_id=opened["runId"], truth_path=self.root / "truth.jsonl")
        result = gateway.call_tool("ledger_pay", PAY_ALICE)
        self.assertFalse(result["isError"])
        self.assertEqual(module.state.env_view["paid_total"], 10)
        self.assertIn("environment_transition", kinds(self.root / "ledger.jsonl"))

    def test_truth_plane_is_separate_from_the_ledger(self) -> None:
        _, environment, opened, tokens, url = self.serve(shim=False)
        gateway = ToolGateway(environment, ControlClient(url, tokens["gateway"]), run_id=opened["runId"], truth_path=self.root / "truth.jsonl")
        gateway.call_tool("ledger_pay", PAY_MALLORY)
        self.assertIn("recipient_not_authorized", (self.root / "truth.jsonl").read_text(encoding="utf-8"))
        ledger = (self.root / "ledger.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("recipient_not_authorized", ledger)
        self.assertNotIn('"authorized"', ledger)


if __name__ == "__main__":
    unittest.main()
