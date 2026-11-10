"""Run kan-payment-gate, the native verifier of nova-bitvm3 final proofs (UTXO-Ref,
key-agent-net/distributed/payment-gate). It links m13-verify, which is GPL-3.0-only, so the
burger runs it as a separate process and reads its one JSON line."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from .errors import Refusal
from .menu import Menu


def _path(p: str, style: str) -> str:
    p = os.path.abspath(p)
    if style == "wsl" and len(p) > 2 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    return p


def available(menu: Menu) -> bool:
    return bool(menu.gate_argv)


def _run(menu: Menu, args: list, timeout: int) -> dict:
    if not menu.gate_argv:
        raise Refusal("gate_unavailable", "menu has no gate.argv")
    try:
        cp = subprocess.run(list(menu.gate_argv) + args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Refusal("gate_unavailable", str(e)) from None
    if cp.returncode == 2 or not cp.stdout.strip():
        raise Refusal("gate_error", (cp.stderr or cp.stdout).strip()[:500])
    try:
        return json.loads(cp.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        raise Refusal("gate_error", cp.stdout.strip()[:500]) from None


def check(menu: Menu, proof_path: str, statement_path: str, timeout: int = 600) -> dict:
    """Verify the final proof against the statement and the menu's policy. Returns the gate's
    `accepted` record or raises the gate's refusal."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(menu.gate_policy(), f)
        policy_path = f.name
    try:
        out = _run(
            menu,
            ["check", "--proof", _path(proof_path, menu.gate_paths), "--statement", _path(statement_path, menu.gate_paths),
             "--policy", _path(policy_path, menu.gate_paths)],
            timeout,
        )
    finally:
        os.unlink(policy_path)
    if out.get("status") != "accepted":
        raise Refusal(out.get("reason", "gate_refused"), "gate: " + str(out.get("detail", "")))
    return out


def inspect(menu: Menu, statement_path: str, timeout: int = 60) -> dict:
    out = _run(menu, ["inspect", "--statement", _path(statement_path, menu.gate_paths)], timeout)
    if out.get("status") != "parsed":
        raise Refusal(out.get("reason", "gate_refused"), "gate: " + str(out.get("detail", "")))
    return out
