"""Anchor tests for patch_core_signet.py (synthetic sources; no Core checkout).

CI also applies the patch to the real pinned source in the keyless job.
"""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("pcs", Path(__file__).with_name("patch_core_signet.py"))
pcs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pcs)


def sources():
    s = {path: f"// head of {path}\n" + old + "// tail\n" for path, old, _ in pcs.EDITS}
    s["src/validation.cpp"] += "    consensus.keyless_research\n"
    return s


class SignetPatch(unittest.TestCase):
    def test_every_edit_lands_once(self):
        out = pcs.plan(sources())
        for path, _, new in pcs.EDITS:
            self.assertIn(new, out[path])

    def test_custom_challenge_is_required(self):
        out = pcs.plan(sources())
        self.assertIn("requires a custom -signetchallenge", out["src/chainparams.cpp"])
        self.assertIn("options.challenge.has_value()", out["src/kernel/chainparams.cpp"])
        self.assertIn("ChainType::SIGNET", out["src/validation.cpp"])

    def test_second_application_refused(self):
        once = pcs.plan(sources())
        with self.assertRaises(RuntimeError):
            pcs.plan(once)

    def test_requires_regtest_patch_first(self):
        s = sources()
        s["src/validation.cpp"] = s["src/validation.cpp"].replace("    consensus.keyless_research\n", "")
        s["src/validation.cpp"] = s["src/validation.cpp"].replace("consensusparams.keyless_research", "x")
        with self.assertRaises(RuntimeError):
            pcs.plan(s)


if __name__ == "__main__":
    unittest.main()
