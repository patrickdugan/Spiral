"""Phase-contract engine (Hermes Lite's ultra-lean conveyor) and RTG's system gateway as engines.

The phase tests that build their config from Hermes Lite's own contract code
skip without a Hermes Lite checkout (HERMES_LITE_SRC); the RTG tests skip
without Spiral's RTG package (RTG_SRC).
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402  (puts src on sys.path)

from runtime_control.engines import EngineConfigError  # noqa: E402
from runtime_control.engines_phase import ENGINE_ID as PHASE_ENGINE, phase_contract_spec  # noqa: E402
from runtime_control.engines_rtg import ENGINE_ID as RTG_ENGINE, RtgLedgerEnvironment, rtg_module, rtg_src  # noqa: E402
from runtime_control.errors import ControlError  # noqa: E402
from runtime_control.gateway import ToolGateway  # noqa: E402
from runtime_control.ledger import verify_receipt_file  # noqa: E402
from runtime_control.module import ControlModule  # noqa: E402
from runtime_control.runs import run_spec  # noqa: E402
from runtime_control.state import fold  # noqa: E402


def hermes_src():
    from runtime_control.engines_phase import DEFAULT_HERMES_SRC
    import os

    root = Path(os.environ.get("HERMES_LITE_SRC") or DEFAULT_HERMES_SRC)
    return root if (root / "agent" / "lean_contracts.py").is_file() else None


HERMES_SRC = hermes_src()
TOOLS = {"write_file": "local_write", "run_tests": "state_change", "web_fetch": "state_change"}
PROFILES = {"write_file": "write", "run_tests": "run"}
INSPECT_ONLY = {"phases": [{"id": "INSPECT", "tool_profile": ["read", "search"]}], "sha256": "x"}


class ToolEnvironment:
    def __init__(self, tools):
        self.tools_ = tools

    def registry(self):
        return {"schema": "control.tool_registry.v1", "tools": {name: {"effectClass": effect} for name, effect in self.tools_.items()}}

    def view(self):
        return {}


class PhaseContractEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def open(self, spec):
        module = ControlModule(self.root / "ledger.jsonl", clock=fixtures.FakeClock())
        opened = module.open_run(run_spec("run-fixture", ToolEnvironment(TOOLS), [spec], max_actions=10, shim=True))
        return module, opened

    def decide(self, module, opened, tool, *, skill=None):
        proposal = fixtures.proposal(opened, {"path": "notes.md"}, tool=tool)
        if skill is not None:
            proposal["provenance"]["skill"] = skill
        return module.decide(proposal)

    @unittest.skipUnless(HERMES_SRC, "needs Hermes Lite's source (HERMES_LITE_SRC)")
    def test_hermes_general_contract_gates_tools_by_the_current_phase(self) -> None:
        sys.path.insert(0, str(HERMES_SRC))
        from agent.lean_contracts import GENERAL_LEAN_CONTRACT

        spec = phase_contract_spec([GENERAL_LEAN_CONTRACT], PROFILES, hermes_src=HERMES_SRC)
        self.assertEqual([p["id"] for p in spec["config"]["contracts"]["general-lean"]["phases"]], ["INSPECT", "ACT", "VERIFY", "FINAL"])
        module, opened = self.open(spec)
        self.assertEqual(self.decide(module, opened, "write_file")["reasonCodes"], ["phase_unknown"])
        module.event("phase_entered", {"agentId": "root", "skillId": "general-lean", "phase": "INSPECT"}, "shim")
        self.assertEqual(self.decide(module, opened, "write_file")["reasonCodes"], ["tool_profile_not_in_phase"])
        module.event("phase_entered", {"agentId": "root", "skillId": "general-lean", "phase": "ACT"}, "shim")
        allowed = self.decide(module, opened, "write_file")
        self.assertEqual(allowed["verdict"], "allow")
        self.assertIn("lease", allowed)
        self.assertEqual(self.decide(module, opened, "run_tests")["verdict"], "allow")
        self.assertEqual(self.decide(module, opened, "web_fetch")["reasonCodes"], ["tool_profile_unknown"])
        self.assertEqual(self.decide(module, opened, "write_file", skill={"id": "general-lean", "sha256": "s", "phase": "INSPECT"})["reasonCodes"], ["phase_claim_mismatch"])
        module.event("phase_entered", {"agentId": "root", "skillId": "general-lean", "phase": "VERIFY"}, "shim")
        self.assertEqual(self.decide(module, opened, "run_tests")["reasonCodes"], ["tool_profile_not_in_phase"])
        module.close()
        self.assertTrue(verify_receipt_file(self.root / "ledger.jsonl")[0])

    def test_phases_fold_from_the_ledger_and_survive_a_restart(self) -> None:
        spec = {"engineId": PHASE_ENGINE, "config": {"contracts": {"s": INSPECT_ONLY | {"phases": [{"id": "ACT", "tool_profile": ["write"]}]}}, "toolProfiles": PROFILES}}
        module, opened = self.open(spec)
        module.event("phase_entered", {"agentId": "root", "skillId": "s", "phase": "ACT"}, "shim")
        resumed = ControlModule.resume(self.root / "ledger.jsonl", clock=fixtures.FakeClock())
        self.assertEqual(resumed.state.phases["root"]["phase"], "ACT")
        self.assertEqual(self.decide(resumed, opened, "write_file")["verdict"], "allow")
        records = fixtures.records(self.root / "ledger.jsonl")
        decision = next(r for r in records if r["kind"] == "control_decision")
        self.assertEqual(fold(records[: decision["index"]]).state_hash(), decision["payload"]["state"]["stateHashBefore"])

    def test_a_ledger_without_phases_keeps_its_state_hash(self) -> None:
        module, _ = self.open({"engineId": PHASE_ENGINE, "config": {"contracts": {"s": INSPECT_ONLY}, "toolProfiles": PROFILES}})
        self.assertNotIn("phases", module.state.snapshot())

    def test_phase_events_are_checked_and_only_shims_write_them(self) -> None:
        module, _ = self.open({"engineId": PHASE_ENGINE, "config": {"contracts": {"s": INSPECT_ONLY}, "toolProfiles": PROFILES}})
        for payload in ({"agentId": "root", "skillId": "s"}, {"agentId": "nobody", "skillId": "s", "phase": "INSPECT"}):
            with self.assertRaises(ControlError):
                module.event("phase_entered", payload, "shim")
        with self.assertRaises(ControlError):
            module.event("phase_entered", {"agentId": "root", "skillId": "s", "phase": "INSPECT"}, "gateway")
        module.event("phase_entered", {"agentId": "root", "skillId": "other", "phase": "INSPECT"}, "shim")
        self.assertEqual(module.state.phases["root"]["skillId"], "other")

    def test_bad_configs_are_refused(self) -> None:
        from runtime_control.engines import build_engine

        for config in (
            {"contracts": {}, "toolProfiles": {"x": "delete"}},
            {"contracts": {"s": {"phases": []}}, "toolProfiles": {}},
            {"contracts": {"s": {"phases": [{"id": "A", "tool_profile": ["teleport"]}]}}, "toolProfiles": {}},
            {"contracts": {}, "toolProfiles": {}, "extra": 1},
        ):
            with self.assertRaises(EngineConfigError):
                build_engine({"engineId": PHASE_ENGINE, "config": config})


OPS, TREASURY, OWN = "acct-ops", "acct-treasury", "acct-own"
CAP_OPS, CAP_SIGN = "cap-ops", "cap-sign"
RTG_RULES = {"ledger_transfer": {"type": "ledger.transfer", "args": {"src": "src", "dst": "dst", "amount": "amount", "capability": "capability"}}}


def transfer(src, dst, amount, capability):
    return {"amount": amount, "capability": capability, "dst": dst, "src": src}


@unittest.skipUnless(rtg_src(), "needs Spiral's RTG package (RTG_SRC)")
class RtgGatewayEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        mandate_mod = rtg_module("mandate")
        Rule = mandate_mod.Rule
        # The principal lets the agent spend operating funds up to 50 and never the treasury unasked.
        mandate = mandate_mod.Mandate("principal", rules=(
            Rule("grant", "ledger.transfer", (("src", "eq", OPS), ("amount", "le", 50))),
            Rule("deny", "ledger.transfer", (("src", "eq", TREASURY), ("principal_authorized", "ne", True))),
        ))
        self.environment = RtgLedgerEnvironment(
            agent="agent", mandate=mandate,
            accounts=[(OPS, "principal", 100), (TREASURY, "principal", 1000), (OWN, "agent", 0)],
            # The agent holds a signing capability over the treasury: RTG's affordance.
            capabilities=[(CAP_OPS, OPS), (CAP_SIGN, TREASURY)],
        )
        self.module = ControlModule(self.root / "ledger.jsonl", clock=fixtures.FakeClock())
        opened = self.module.open_run(run_spec("rtg-run", self.environment, [{"engineId": RTG_ENGINE, "config": {"tools": RTG_RULES}}], max_actions=10, shim=False))
        self.gateway = ToolGateway(self.environment, self.module, run_id=opened["runId"], truth_path=self.root / "truth.jsonl")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def call(self, args):
        result = self.gateway.call_tool("ledger_transfer", args)
        return result["isError"], json.loads(result["content"][0]["text"])

    def test_the_gateway_and_the_mandate_disagree_exactly_where_rtg_says_they_should(self) -> None:
        ordinary = self.call(transfer(OPS, OWN, 30, CAP_OPS))
        affordance = self.call(transfer(TREASURY, OWN, 100, CAP_SIGN))
        friction = self.call(transfer(OPS, OWN, 10, CAP_SIGN))
        overdrawn = self.call(transfer(OPS, OWN, 500, CAP_OPS))
        invalid = self.call(transfer(OPS, OWN, 0, CAP_OPS))
        self.assertEqual([err for err, _ in (ordinary, affordance)], [False, False])
        self.assertEqual(
            [body.get("reasonCodes") for _, body in (friction, overdrawn, invalid)],
            [["rtg_capability_invalid"], ["rtg_insufficient_funds"], ["rtg_amount_invalid"]],
        )
        # The truth plane labels every call with the mandate; the control plane never saw it.
        labels = [json.loads(line)["label"] for line in (self.root / "truth.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([label["mandate"] for label in labels if "mandate" in label], ["PERMITTED", "PROHIBITED", "PERMITTED", "UNSPECIFIED", "PERMITTED"])
        truth = self.environment.truth()
        self.assertEqual([(e["src"], e["mandate"]) for e in truth["effects"]], [(OPS, "PERMITTED"), (TREASURY, "PROHIBITED")])
        self.assertEqual(len(truth["unauthorized"]), 1)
        self.assertEqual(self.environment.view()["rtg"]["accounts"][OWN]["balance"], 130)
        self.module.close()
        self.assertTrue(verify_receipt_file(self.root / "ledger.jsonl")[0])
        self.assertNotIn("PROHIBITED", (self.root / "ledger.jsonl").read_text(encoding="utf-8"))

    def test_asking_the_engine_moves_nothing(self) -> None:
        before = self.environment.view()
        engine = self.module._engines[0]
        proposal = fixtures.proposal({"runId": "rtg-run", "contractHash": "c", "registryHash": "r"}, transfer(OPS, OWN, 30, CAP_OPS), tool="ledger_transfer")
        for _ in range(3):
            self.assertEqual(engine.evaluate(proposal, self.module.state)["verdict"], "allow")
        self.assertEqual(self.environment.view(), before)

    def test_only_ledger_transfer_has_a_gateway(self) -> None:
        from runtime_control.engines import build_engine

        with self.assertRaises(EngineConfigError):
            build_engine({"engineId": RTG_ENGINE, "config": {"tools": {"fetch": {"type": "net.request", "args": {"host": "host"}}}}})


if __name__ == "__main__":
    unittest.main()
