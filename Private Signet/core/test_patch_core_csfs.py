"""Anchor tests for patch_core_csfs.py (synthetic sources; CI applies it to
the real pinned Core source in the keyless job)."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("pcc", Path(__file__).with_name("patch_core_csfs.py"))
pcc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pcc)


def sources():
    s = {}
    for path, old, _ in pcc.EDITS:
        s[path] = s.get(path, f"// {path}\n") + old + "// next\n"
    return s


class CsfsPatch(unittest.TestCase):
    def test_every_edit_lands_once(self):
        out = pcc.plan(sources())
        for path, _, new in pcc.EDITS:
            self.assertIn(new, out[path])
        self.assertIn("case static_cast<opcodetype>(0xcc)", out["src/script/interpreter.cpp"])
        self.assertIn("SCRIPT_VERIFY_RESEARCH_CSFS", out["src/validation.cpp"])

    def test_gated_on_tapscript_and_flag(self):
        case = pcc.CSFS_CASE
        self.assertIn("sigversion != SigVersion::TAPSCRIPT || !(flags & SCRIPT_VERIFY_RESEARCH_CSFS)", case)
        self.assertIn("VALIDATION_WEIGHT_PER_SIGOP_PASSED", case)
        self.assertIn("msg.size() != 32", case)

    def test_second_application_refused(self):
        once = pcc.plan(sources())
        with self.assertRaises(RuntimeError):
            pcc.plan({**sources(), **once})

    def test_requires_base_patch(self):
        s = sources()
        s["src/script/interpreter.h"] = s["src/script/interpreter.h"].replace("RESEARCH_P2MR", "X")
        with self.assertRaises(RuntimeError):
            pcc.plan(s)


if __name__ == "__main__":
    unittest.main()
