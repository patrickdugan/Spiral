#!/usr/bin/env python3
"""Exercise the NVCC cache with a mock compiler and no CUDA toolkit."""

from hashlib import sha256
import json
from pathlib import Path
import os
import runpy
import tempfile
import unittest
from unittest.mock import patch
import zipfile


cache = runpy.run_path(str(Path(__file__).with_name("nvcc-object-cache.py")))
run = cache["run"]


class ObjectCacheTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        (root / "cuda").mkdir()
        (root / "build.rs").write_text("pinned build script")
        (root / "cuda/example.cu").write_text("pinned source")
        self.header = root / "cuda/example.cuh"
        self.header.write_text("pinned header")
        self.cache_dir = root / "cache"
        self.cache_dir.mkdir()
        self.output = root / "example.o"
        self.args = ["-c", "-O3", "-gencode", "arch=compute_86,code=sm_86", "-Icuda/include",
                     "-o", str(self.output), "cuda/example.cu"]
        self.config = {
            "source": str(root), "pin": cache["pinned_source"](root), "nvcc": "/mock/nvcc",
            "compiler": {"host": {}, "files": {}, "versions": {}}, "cache": str(self.cache_dir),
        }
        cwd = Path.cwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(root)
        patcher = patch.dict(os.environ, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def compile(self, nvcc, args):
        self.assertEqual(nvcc, "/mock/nvcc")
        Path(args[-2]).write_bytes(b"new object from successful compiler")
        return 0

    def test_fresh_object_and_corruption(self):
        self.output.write_bytes(b"legacy partial file")
        with patch.dict(run.__globals__, exact_compile=self.compile):
            self.assertEqual(run(self.config, self.args), 0)
        entry, = self.cache_dir.glob("*.zip")
        with zipfile.ZipFile(entry) as archive:
            data = archive.read("object.o")
            receipt = json.loads(archive.read("receipt.json"))
        self.assertEqual(receipt["recipe"]["argv"], ["/mock/nvcc", *self.args])
        self.assertEqual(receipt["object_sha256"], sha256(data).hexdigest())
        self.assertNotEqual(data, b"legacy partial file")
        self.output.unlink()
        with patch.dict(run.__globals__, exact_compile=lambda *_: self.fail("expected a cache hit")):
            self.assertEqual(run(self.config, self.args), 0)
        self.assertEqual(self.output.read_bytes(), data)

        with zipfile.ZipFile(entry, "w") as archive:
            archive.writestr("receipt.json", json.dumps(receipt))
            archive.writestr("object.o", b"hash mismatch")
        with patch.dict(run.__globals__, exact_compile=self.compile):
            self.assertEqual(run(self.config, self.args), 0)
        self.assertEqual(self.output.read_bytes(), data)

    def test_no_admission_without_fresh_success(self):
        self.output.write_bytes(b"previous interrupted build's output")
        with patch.dict(run.__globals__, exact_compile=lambda *_: 1):
            self.assertEqual(run(self.config, self.args), 1)
        with patch.dict(run.__globals__, exact_compile=lambda *_: 0):
            self.assertEqual(run(self.config, self.args), 0)
        self.assertEqual(list(self.cache_dir.iterdir()), [])

    def test_pin_and_passthrough(self):
        with patch.dict(run.__globals__, exact_compile=lambda nvcc, args: 2 if args == ["--version"] else 3):
            self.assertEqual(run(self.config, ["--version"]), 2)
            args = [*self.args]
            args[1] = "-O2"
            self.assertEqual(run(self.config, args), 3)
            with patch.dict(os.environ, NVCC_APPEND_FLAGS="--ptxas-options=-O0"):
                self.assertEqual(run(self.config, self.args), 3)
        self.header.write_text("changed header")
        with self.assertRaisesRegex(ValueError, "source changed"):
            run(self.config, self.args)
        self.assertEqual(list(self.cache_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
