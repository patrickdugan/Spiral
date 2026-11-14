import json
import subprocess

import pytest

from conftest import menu_dict
from iob import gate, menu
from iob.errors import Refusal


@pytest.mark.parametrize("exit_code,status", [(1, "accepted"), (1, "parsed"), (-11, "accepted")])
def test_success_payload_requires_successful_process(monkeypatch, exit_code, status):
    m = menu.from_dict(menu_dict())
    object.__setattr__(m, "gate_argv", ("verifier",))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
        a[0], exit_code, json.dumps({"status": status}), ""))
    with pytest.raises(Refusal) as error:
        gate._run(m, [], 10)
    assert error.value.reason == "gate_error"


@pytest.mark.parametrize("payload", ["[]", "null", '"accepted"'])
def test_protocol_requires_an_object(monkeypatch, payload):
    m = menu.from_dict(menu_dict())
    object.__setattr__(m, "gate_argv", ("verifier",))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, payload, ""))
    with pytest.raises(Refusal) as error:
        gate._run(m, [], 10)
    assert error.value.reason == "gate_error"


def test_refusal_exit_preserves_the_verifier_reason(monkeypatch):
    m = menu.from_dict(menu_dict())
    object.__setattr__(m, "gate_argv", ("verifier",))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(
        a[0], 1, json.dumps({"status": "refused", "reason": "proof_rejected"}), ""))
    assert gate._run(m, [], 10)["reason"] == "proof_rejected"
