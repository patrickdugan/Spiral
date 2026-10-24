"""The controller thread (design tests K1, K4, K6-K10, and the action grammar)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from fixtures import PAY_ALICE, PAY_CAROL, PAY_MALLORY, proposal  # noqa: E402

from runtime_control.controller import (  # noqa: E402
    PARTITION,
    ModelController,
    PacketOverflow,
    ScriptedController,
    build_packet,
    fold_thread,
    render_record,
    replay_trigger_positions,
    trigger_policy,
)
from runtime_control.demo import DemoLedgerEnvironment, demo_engine_spec  # noqa: E402
from runtime_control.gateway import ToolGateway  # noqa: E402
from runtime_control.ledger import verify_receipt_file  # noqa: E402
from runtime_control.module import ControlModule  # noqa: E402
from runtime_control.proxy import ModelProxy, serve_proxy_http  # noqa: E402
from runtime_control.runs import run_spec  # noqa: E402


SECRET = "SECRET-memo-7f3a"
CORRECT = {"action": "intervene", "kind": "correct", "refs": [], "text": "Pay only alice or bob."}


class ControllerThreadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "ledger.jsonl"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def open(self, controller, *, triggers=None, channel=None, contract=None, principal="external"):
        self.environment = DemoLedgerEnvironment()
        self.module = ControlModule(self.path, clock=fixtures.FakeClock(), controller=controller)
        spec = run_spec("run-fixture", self.environment, [demo_engine_spec()], max_actions=20, shim=True, controller=controller.controller_id,
                        triggers=triggers, intervention_channel=channel, contract=contract, principal=principal)
        self.opened = self.module.open_run(spec)
        self.gateway = ToolGateway(self.environment, self.module, run_id=self.opened["runId"], truth_path=self.root / "truth.jsonl")
        return self.module, self.opened

    def pay(self, args):
        """A shim decision and, on allow, the gateway call, as a runtime would make them."""
        decision = self.module.decide(proposal(self.opened, args))
        if decision["verdict"] == "allow":
            return decision, json.loads(self.gateway.call_tool("ledger_pay", args)["content"][0]["text"])
        return decision, None

    def records(self):
        return fixtures.records(self.path)

    def turns(self):
        return [r for r in self.records() if r["kind"] == "controller_turn"]

    # ------------------------------------------------------------ K1, K10

    def test_k1_rebuilding_the_thread_reproduces_every_turns_packet(self) -> None:
        controller = ScriptedController({"denial_streak": [CORRECT]})
        self.open(controller, triggers={"denialStreak": 1, "digestEvery": 2})
        for args in (PAY_ALICE, PAY_MALLORY, PAY_ALICE, PAY_MALLORY, {"amount": 5, "to": "bob"}):
            self.pay(args)
        self.module.close()
        records = self.records()
        turns = self.turns()
        self.assertGreaterEqual(len(turns), 6)
        for turn in turns:
            j, payload = turn["index"], turn["payload"]
            prefix = records[:j]
            thread = fold_thread(prefix)
            start, end = payload["eventRange"]
            self.assertEqual((start, end), (thread["lastEventIndex"] + 1, j - 1))
            events = [line for r in prefix[start:] if (line := render_record(r, prefix[0]["payload"]["registry"])) is not None]
            packet = build_packet(thread, events, payload["trigger"])
            self.assertEqual((packet["sha256"], packet["inputTokens"]), (payload["packetSha256"], payload["inputTokens"]), j)
        # The scripted controller saw exactly the packets the ledger records.
        self.assertEqual([s["packetSha256"] for s in controller.seen], [t["payload"]["packetSha256"] for t in turns])
        self.assertTrue(verify_receipt_file(self.path)[0])

    def test_k10_the_trigger_policy_puts_turns_where_a_replay_of_the_ledger_does(self) -> None:
        triggers = {"denialStreak": 2, "digestEvery": 3, "onAnswer": True}
        self.open(ScriptedController([]), triggers=triggers)
        for args in (PAY_MALLORY, PAY_MALLORY, PAY_ALICE, PAY_MALLORY, PAY_MALLORY, PAY_MALLORY, PAY_MALLORY):
            self.pay(args)
        escalated = self.module.decide(proposal(self.opened, PAY_CAROL))
        self.module.resolve_escalation(escalated["escalationId"], {"by": "test", "decision": "reject"})
        records = self.records()
        recorded = [(t["payload"]["trigger"]["kind"], t["payload"]["trigger"]["index"]) for t in self.turns() if t["payload"]["trigger"]["kind"] != "admitted_consequential"]
        self.assertEqual(recorded, replay_trigger_positions(records, trigger_policy({"triggers": triggers})))
        self.assertEqual([kind for kind, _ in recorded].count("denial_streak"), 3)
        self.assertIn("question_answered", [kind for kind, _ in recorded])

    # ------------------------------------------------------------ K6, K7

    def test_k6_no_free_text_reaches_the_controller_unless_the_registry_shows_it(self) -> None:
        controller = ScriptedController({"denial_streak": [{"action": "pass"}]})
        self.open(controller, triggers={"denialStreak": 1})
        self.pay(PAY_ALICE | {"memo": SECRET})
        self.gateway.call_tool("ledger_status", {})
        self.pay(PAY_MALLORY | {"memo": SECRET + "-again"})
        packets = "\n".join(line for seen in controller.seen for line in seen["events"])
        self.assertNotIn(SECRET, packets)
        self.assertIn('to: "alice"', packets)          # registry marks `to` and `amount` controller-visible
        self.assertRegex(packets, r"memo: <\d+B [0-9a-f]{12}>")
        self.assertNotIn('"balance"', packets)          # tool results appear only as status and size
        self.assertNotIn(SECRET, (self.path).read_text(encoding="utf-8").split('"kind":"controller_turn"')[-1])

    def test_k7_the_packet_keeps_to_its_partition_and_fails_closed_when_the_card_cannot_fit(self) -> None:
        thread = fold_thread([])
        events = [f"#{n} proposed  root ledger_pay {{amount: {n}, to: \"alice\"}} surface:agent_loop" for n in range(2000)]
        packet = build_packet(thread, events, {"index": 2000, "kind": "digest"})
        self.assertLessEqual(packet["tokens"]["events"], PARTITION["events"])
        self.assertGreater(packet["dropped"]["events"], 0)
        self.assertLessEqual(packet["inputTokens"], sum(PARTITION.values()) - PARTITION["output"])
        self.assertIn("#1999 ", packet["messages"][1]["content"])     # the oldest events go first
        with self.assertRaises(PacketOverflow):
            build_packet(thread | {"contractCard": {"contract": {"task": "x" * 4000}}}, [], {"index": 0, "kind": "digest"})
        # Through the module the overflowing turn holds the call.
        self.open(ScriptedController([]), contract={"task": "y" * 4000})
        decision, _ = self.pay(PAY_ALICE)
        self.assertEqual((decision["verdict"], decision["reasonCodes"]), ("deny", ["controller_unavailable"]))
        self.assertEqual(self.turns()[-1]["payload"]["failure"], "packet_overflow")

    # ------------------------------------------------------------ K8, K9: interventions

    def test_k8_an_intervention_reaches_the_actor_on_the_gateway_trailer_and_is_recorded(self) -> None:
        self.open(ScriptedController({"denial_streak": [CORRECT]}), triggers={"denialStreak": 1})
        self.pay(PAY_MALLORY)
        pending = self.module.pending_interventions("root")
        self.assertEqual([(p["kind"], p["text"]) for p in pending], [("correct", CORRECT["text"])])
        _, body = self.pay(PAY_ALICE)
        self.assertEqual(body["interventions"], [{"kind": "correct", "text": CORRECT["text"]}])
        self.assertEqual(self.module.pending_interventions(), [])
        delivered = [r for r in self.records() if r["kind"] == "intervention" and r["payload"]["status"] == "delivered"]
        self.assertEqual(len(delivered), 1)
        self.assertEqual((delivered[0]["payload"]["channel"], delivered[0]["payload"]["atIndex"]), ("gateway_trailer", delivered[0]["index"]))
        # The thread knows it was delivered and that the next call was admitted.
        thread = fold_thread(self.records())
        self.assertEqual([(i["delivered"], i["followed"]) for i in thread["interventions"]], [(True, "unknown")])

    def test_k8_with_a_native_channel_the_trailer_stays_quiet_and_the_runtime_records_delivery(self) -> None:
        self.open(ScriptedController({"denial_streak": [CORRECT]}), triggers={"denialStreak": 1}, channel="native")
        self.pay(PAY_MALLORY)
        _, body = self.pay(PAY_ALICE)
        self.assertNotIn("interventions", body)
        [item] = self.module.pending_interventions("root")
        delivered = self.module.deliver_intervention(item["interventionId"], "hermes_message")
        self.assertEqual(delivered["channel"], "hermes_message")
        self.pay({"amount": 5, "to": "bob"})
        thread = fold_thread(self.records())
        self.assertEqual(thread["interventions"][0]["followed"], "yes")   # the next decision after delivery was an allow

    def test_k9_after_a_compaction_the_reminder_reaches_the_actor_before_its_next_proposal(self) -> None:
        remind = {"action": "intervene", "kind": "remind", "refs": [], "text": "Open question pending; cap 50 per payment."}
        self.open(ScriptedController({"context_compacted": [remind]}), triggers={"onCompaction": True}, channel="native")
        self.pay(PAY_ALICE)
        self.module.event("context_compacted", {"agentId": "root", "beforeTokens": 11000, "afterTokens": 3000}, "shim")
        # The runtime's channel runs before its next model call, hence before its next proposal.
        for item in self.module.pending_interventions("root"):
            self.module.deliver_intervention(item["interventionId"], "hermes_message")
        self.pay(PAY_ALICE)
        records = self.records()
        delivery = next(r["index"] for r in records if r["kind"] == "intervention" and r["payload"]["status"] == "delivered")
        compaction = next(r["index"] for r in records if r["kind"] == "context_compacted")
        next_proposal = next(r["index"] for r in records if r["kind"] == "action_proposed" and r["index"] > compaction)
        self.assertLess(delivery, next_proposal)
        self.assertEqual(self.turns()[-2]["payload"]["trigger"]["kind"], "context_compacted")

    def test_interventions_are_only_delivered_once(self) -> None:
        from runtime_control.errors import ControlError

        self.open(ScriptedController({"denial_streak": [CORRECT]}), triggers={"denialStreak": 1}, channel="native")
        self.pay(PAY_MALLORY)
        [item] = self.module.pending_interventions()
        self.module.deliver_intervention(item["interventionId"], "hermes_message")
        with self.assertRaises(ControlError):
            self.module.deliver_intervention(item["interventionId"], "hermes_message")

    # ------------------------------------------------------------ questions and grammar

    def test_ask_principal_words_the_question_and_the_thread_keeps_it_open(self) -> None:
        ask = {"action": "ask_principal", "questionId": "q1", "summary": "Pay alice 10 for the invoice the user named?", "blocking": []}
        self.open(ScriptedController({"admitted_consequential": [ask]}))
        decision, _ = self.pay(PAY_ALICE)
        self.assertEqual((decision["verdict"], decision["reasonCodes"]), ("escalate", ["controller_question"]))
        [question] = fold_thread(self.records())["openQuestions"]
        self.assertEqual((question["status"], question["summary"]), ("open", ask["summary"]))

    def test_engine_escalations_can_go_to_the_controller_which_cannot_admit_them(self) -> None:
        controller = ScriptedController({"engine_escalate": [{"action": "pass"}, {"action": "hold", "reasonCode": "not_now"}]})
        self.open(controller, triggers={"onEscalate": True})
        first = self.module.decide(proposal(self.opened, PAY_CAROL))
        second = self.module.decide(proposal(self.opened, PAY_CAROL | {"amount": 6}))
        self.assertEqual((first["verdict"], second["verdict"], second["reasonCodes"]), ("escalate", "deny", ["recipient_needs_approval", "not_now"]))

    def test_over_long_or_out_of_grammar_actions_are_never_obeyed(self) -> None:
        bad = [
            {"action": "intervene", "kind": "correct", "refs": [], "text": "x" * 601},
            {"action": "intervene", "kind": "threaten", "refs": [], "text": "hi"},
            {"action": "hold", "reasonCode": "x" * 49},
            {"action": "ask_principal", "questionId": "q", "summary": "s", "blocking": "not a list"},
        ]
        self.open(ScriptedController(bad))
        for _ in bad:
            decision, _ = self.pay(PAY_ALICE)
            self.assertEqual(decision["reasonCodes"], ["controller_unavailable"])
        self.assertEqual({t["payload"]["failure"] for t in self.turns()}, {"malformed_action"})
        self.assertNotIn("intervention", [r["kind"] for r in self.records()])

    # ------------------------------------------------------------ model controller, K4

    def test_a_model_controller_answers_through_the_proxy_under_the_grammar(self) -> None:
        action = {"action": "intervene", "kind": "correct", "refs": [3], "text": "Stay within the allowlist."}
        proxy = ModelProxy(mode="scripted", model_id="controller-model", record_path=self.root / "controller_io.jsonl",
                           responder=lambda body: {"role": "assistant", "content": json.dumps(action)})
        server, url = serve_proxy_http(proxy)
        try:
            self.open(ModelController(url + "/v1", "controller-model"))
            decision, _ = self.pay(PAY_ALICE)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(decision["verdict"], "allow")
        turn = self.turns()[0]["payload"]
        self.assertEqual((turn["controllerId"], turn["output"]["action"]), ("model", "intervene"))
        self.assertIn("modelHash", turn)
        [line] = (self.root / "controller_io.jsonl").read_text(encoding="utf-8").splitlines()
        request = json.loads(line)["request"]
        self.assertEqual(request["response_format"]["type"], "json_schema")
        self.assertEqual(request["messages"], build_packet(fold_thread(self.records()[: self.turns()[0]["index"]]), [
            line for r in self.records()[: self.turns()[0]["index"]] if (line := render_record(r, self.records()[0]["payload"]["registry"])) is not None
        ], turn["trigger"])["messages"])

    def test_k4_a_model_controller_that_times_out_holds_the_call(self) -> None:
        class Slow(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return None

            def do_POST(self):
                time.sleep(2)
                self.send_response(500)
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            self.open(ModelController(f"http://127.0.0.1:{server.server_address[1]}/v1", "slow", timeout_s=0.3))
            decision, _ = self.pay(PAY_ALICE)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(decision["reasonCodes"], ["controller_unavailable"])
        self.assertEqual(self.turns()[0]["payload"]["failure"], "controller_error")
        # The engines' own refusals are unaffected (K4).
        decision, _ = self.pay(PAY_MALLORY)
        self.assertEqual(decision["reasonCodes"], ["recipient_not_allowed"])


if __name__ == "__main__":
    unittest.main()
