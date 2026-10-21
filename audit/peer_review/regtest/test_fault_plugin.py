"""Fault instrument protocol gates, independent of running daemons."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("fault", Path(__file__).with_name("hold-fail-plugin.py"))
fault = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fault)
SCRATCH = (Path.cwd().parent / "fault-test-work").resolve()
SCRATCH.mkdir(exist_ok=True)


class FaultPluginTests(unittest.TestCase):
    def test_nonregtest_disables_and_never_holds(self):
        messages = [{"id": 1, "method": "getmanifest"}, {"id": 2, "method": "init", "params": {"configuration": {"network": "testnet4"}}},
                    {"id": 3, "method": "htlc_accepted", "params": {"htlc": {"payment_hash": "target"}}}]
        output = io.StringIO()
        with patch.object(fault.sys, "stdin", io.StringIO("\n".join(map(json.dumps, messages)))), redirect_stdout(output):
            fault.main()
        responses = [json.loads(line) for line in output.getvalue().splitlines() if line]
        self.assertTrue(responses[0]["result"]["dynamic"])
        self.assertIn("disable", responses[1]["result"])
        self.assertEqual(responses[2]["result"], {"result": "continue"})

    def test_explicit_release_returns_failure_without_preimage(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            control = Path(directory) / "control.json"; events = Path(directory) / "events.jsonl"
            control.write_text(json.dumps({"payment_hash": "target", "release": True}))
            output = io.StringIO()
            with patch.object(fault, "CONTROL", control), patch.object(fault, "EVENTS", events), redirect_stdout(output):
                fault.hold({"id": "held-1", "params": {"htlc": {"amount_msat": 1000000}}}, "target")
            result = json.loads(output.getvalue())
            self.assertEqual(result["result"], {"result": "fail", "failure_message": "2002"})
            self.assertEqual([json.loads(x)["event"] for x in events.read_text().splitlines()], ["receiver_hook_accepted", "receiver_failure_response"])
            self.assertNotIn("payment_key", output.getvalue())

    def test_guard_fails_even_without_control_file(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            output = io.StringIO(); events = Path(directory) / "events.jsonl"
            with patch.object(fault, "CONTROL", Path(directory) / "missing"), patch.object(fault, "EVENTS", events), \
                 patch.object(fault.time, "monotonic", side_effect=[0, 0, 91]), patch.object(fault.time, "sleep"), redirect_stdout(output):
                fault.hold({"id": "guard", "params": {}}, "target")
            self.assertEqual(json.loads(output.getvalue())["result"]["result"], "fail")
            self.assertEqual(json.loads(events.read_text().splitlines()[-1])["trigger"], "90_second_guard")


if __name__ == "__main__":
    unittest.main()
