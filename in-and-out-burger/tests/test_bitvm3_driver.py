"""Reject inconsistent garbling reports before logging a verdict or spending a claim."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from iob import bitvm3 as bv, btc

spec = importlib.util.spec_from_file_location("bitvm3_driver", Path(__file__).resolve().parents[1] / "scripts" / "bitvm3_testnet4.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


@pytest.mark.parametrize("field,value", [
    ("verdict", "neither"),
    ("verdict", "reject"),
    ("seed_sha256", "ff" * 32),
    ("input_bits", 9),
    ("ciphertexts", 10),
    ("accept_label_sha256", "ff" * 32),
    ("output_label_sha256", "ff" * 32),
])
def test_dispute_refuses_inconsistent_report(tmp_path, monkeypatch, field, value):
    accept, reject = b"a" * 16, b"r" * 16
    ah, rh = (hashlib.sha256(x).hexdigest() for x in (accept, reject))
    inst = bv.Instance("honest", "aa" * 32, "bb" * 32, "cc" * 32, ah, rh, btc.p2pkh(b"d" * 20))
    graph = bv.Graph(bv.Parties(11, 22, 33), inst, "ee" * 32, 0, 25000, btc.p2wpkh(b"f" * 20))
    setup = {"seed_sha256": "11" * 32, "statement_sha256": "22" * 32,
             "ciphertext_commitment_blake3": inst.ciphertext_commitment,
             "input_bits": 8, "ciphertexts": 4, "accept_label_sha256": ah}
    report = {**setup, "evaluator_commitment_blake3": inst.ciphertext_commitment,
              "reject_label_sha256": rh, "verdict": "accept", "output_label": accept.hex(),
              "output_label_sha256": ah, "proof_sha256": "33" * 32, "seconds": 1}
    report[field] = value
    path = tmp_path / "evaluation.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    st = driver.State(str(tmp_path), "regtest")
    monkeypatch.setattr(driver, "graph_for", lambda *_: (graph, {"m14_setup": setup}))
    rpc = SimpleNamespace(call=lambda *_: {"vout": [{"scriptPubKey": {"hex": graph.claim.outs[1].script_pubkey.hex()}}]})
    with pytest.raises(AssertionError):
        driver.cmd_dispute(SimpleNamespace(name="honest", m14=str(path)), st, rpc)
    assert not (tmp_path / "events.jsonl").exists()


def test_setup_refuses_other_program_with_same_statement_digest(tmp_path):
    final = {"committed_values_sha256": "aa" * 32, "program_vk_digest": "bb" * 32}
    path = tmp_path / "statement.json"
    path.write_text(json.dumps(final), encoding="utf-8")
    setup = {"tool": "m14-claim setup", "statement_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
             "statement": {**final, "program_vk_digest": "cc" * 32}}
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(setup), encoding="utf-8")
    st = driver.State(str(tmp_path), "regtest")
    st.save("statement-check.json", {"ok": True, "statement_sha256": final["committed_values_sha256"]})
    with pytest.raises(AssertionError, match="different final-verifier fields"):
        driver.cmd_setup(SimpleNamespace(m14=str(setup_path), final_statement=str(path)), st, None)
