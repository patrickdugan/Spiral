import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CoreProbeGuards(unittest.TestCase):
    def test_optimized_python_fails_before_output_or_process_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "must-not-exist"
            command = [sys.executable, "-O", str(Path(__file__).with_name("core_regtest.py")),
                       "--bitcoind", "/missing/must-not-execute", "--output", str(output)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=10,
                                       env={**os.environ, "PYTHONOPTIMIZE": "1"})
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("requires Python assertions", completed.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
