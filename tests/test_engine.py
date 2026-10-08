"""The Rust animation engine: committed module, parity with its JS reference, and page inlining.

The engine (ui/arena/engine/src/lib.rs) is compiled to WebAssembly by
ui/arena/engine/build_engine.py and committed, so these tests need no Rust
toolchain. Parity needs Node; it is skipped where Node is unavailable.
"""

import base64
import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from spiral_ln import arena_replay

REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "ui" / "arena" / "engine"
WASM = ENGINE / "diorama_engine.wasm"


def _node():
    found = shutil.which("node")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs" / "node.exe"
    return str(local) if local.exists() else None


def test_engine_module_is_committed_and_is_webassembly():
    data = WASM.read_bytes()
    assert data[:4] == b"\0asm" and len(data) > 1000


def test_engine_matches_its_javascript_reference():
    node = _node()
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, str(ENGINE / "parity.test.mjs"), str(WASM)], capture_output=True, text=True, timeout=120)
    line = next((l for l in proc.stdout.splitlines() if l.startswith("{")), "{}")
    result = json.loads(line)
    assert result.get("ok") is True, proc.stdout + proc.stderr
    assert result["worstRelErr"] < 5e-3


def test_built_page_inlines_the_engine_and_its_reference(tmp_path):
    spec = importlib.util.spec_from_file_location("build_arena", REPO / "ui" / "arena" / "build_arena.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(json.dumps(arena_replay.build_combined()), encoding="utf-8")
    out = tmp_path / "arena.html"
    module.main(["--template", str(REPO / "ui" / "arena" / "index.template.html"), "--replay", str(replay_path), "--out", str(out)])
    html = out.read_text(encoding="utf-8")
    assert "__ENGINE_WASM_B64__" not in html and "/*__ENGINE_REF_JS__*/" not in html
    match = re.search(r'const ENGINE_WASM_B64 = "([A-Za-z0-9+/=]+)";', html)
    assert match and base64.b64decode(match.group(1)) == WASM.read_bytes()
    assert "createRefEngine" in html and "loadEngine().then(boot)" in html
