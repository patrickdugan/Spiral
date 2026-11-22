"""Unit and HTTP tests for Proof Grove's Cairo/Shinigami (Stwo) and Nova (ArkTransitionV1) gates."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from proofdesk.ark_zk import (
    ARK_NOVA_VK_DIGEST,
    SHINIGAMI_PROGRAM_HASH,
    ArkTransitionNovaGate,
    VtxoExitStarkGate,
    validate_ark_nova_public,
    validate_exit_statement,
)
from proofdesk.domain import Refused
from proofdesk.server import Desk, make_server


def sample_exit_statement() -> dict:
    return {
        "program_hash": SHINIGAMI_PROGRAM_HASH,
        "anchor": {
            "txid": "11" * 32,
            "vout": 0,
            "amount": 10330,
            "script_pubkey": "5120df276373d95787ca03caa6b7f1d3be22d9470cde4b8dc693627e93dc588f4534",
        },
        "vtxo": {
            "txid": "22" * 32,
            "vout": 0,
            "amount": 10000,
            "script_pubkey": "5120e2b1152658195dae2fb792bdf7adb276e1c21f06b33588b9bd8429591bb964ea",
        },
        "transaction_count": 4,
    }


def sample_nova_public() -> dict:
    return {
        "schema": "ark-transition-nova-public-v1",
        "vk_digest": ARK_NOVA_VK_DIGEST,
        "statement_digest": "aa" * 32,
        "r1": "bb" * 32,
        "gamma": "cc" * 32,
        "steps": 28,
        "fee_bound_sat": 1000,
        "expect": {
            "n_tx": 4,
            "n_in": 8,
            "sum_in": 400000,
            "sum_out": 399200,
            "sum_fee": 800,
        },
    }


class FakeCore:
    def __init__(self, amount_btc: float = 0.00010330, confs: int = 6):
        self.amount_btc = amount_btc
        self.confs = confs

    def rpc(self, method: str, params: list):
        if method == "gettxout":
            return {"value": self.amount_btc, "confirmations": self.confs}
        raise Refused("rpc_not_allowed")


class ArkZkGateTests(unittest.TestCase):
    def test_exit_statement_validation_rejects_bad_program_and_inflation(self):
        valid = validate_exit_statement(sample_exit_statement())
        self.assertEqual(valid["program_hash"], SHINIGAMI_PROGRAM_HASH)

        bad_prog = sample_exit_statement()
        bad_prog["program_hash"] = "0x" + "00" * 32
        with self.assertRaises(Refused) as ctx:
            validate_exit_statement(bad_prog)
        self.assertEqual(ctx.exception.code, "shinigami_program_hash_mismatch")

        inflated = sample_exit_statement()
        inflated["vtxo"]["amount"] = 10331
        with self.assertRaises(Refused) as ctx:
            validate_exit_statement(inflated)
        self.assertEqual(ctx.exception.code, "exit_value_inflation")

    def test_nova_public_validation_rejects_bad_vk_and_conservation_break(self):
        valid = validate_ark_nova_public(sample_nova_public())
        self.assertEqual(valid["vk_digest"], ARK_NOVA_VK_DIGEST)

        bad_vk = sample_nova_public()
        bad_vk["vk_digest"] = "00" * 32
        with self.assertRaises(Refused) as ctx:
            validate_ark_nova_public(bad_vk)
        self.assertEqual(ctx.exception.code, "ark_nova_vk_mismatch")

        bad_sum = sample_nova_public()
        bad_sum["expect"]["sum_out"] = 399201
        with self.assertRaises(Refused) as ctx:
            validate_ark_nova_public(bad_sum)
        self.assertEqual(ctx.exception.code, "nova_conservation_mismatch")

    def test_gates_enforce_pinned_binary_and_http_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create a tiny executable python wrapper that accepts proofs unless they contain b"BAD"
            stub = Path(tmp) / "fake_gate.py"
            stub.write_text(
                "import sys, pathlib\n"
                "raw = b''.join(pathlib.Path(a).read_bytes() for a in sys.argv[1:] if pathlib.Path(a).is_file())\n"
                "sys.exit(1 if b'BAD' in raw else 0)\n",
                encoding="utf-8",
            )
            py_sha = hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()

            stwo_gate = VtxoExitStarkGate([sys.executable, str(stub)], py_sha)
            res_stwo = stwo_gate.verify(sample_exit_statement(), b"GOOD_STWO_PROOF", core=FakeCore())
            self.assertTrue(res_stwo["proof_verified"])
            self.assertFalse(res_stwo["zero_knowledge"])
            self.assertEqual(res_stwo["archive_privacy"], "redacted-hash-only")
            self.assertTrue(res_stwo["anchor_observation"]["unspent"])

            with self.assertRaises(Refused) as ctx:
                stwo_gate.verify(sample_exit_statement(), b"BAD_STWO_PROOF", core=FakeCore())
            self.assertEqual(ctx.exception.code, "stwo_proof_rejected")

            nova_gate = ArkTransitionNovaGate([sys.executable, str(stub)], py_sha)
            res_nova = nova_gate.verify(sample_nova_public(), b"GOOD_NOVA_PROOF")
            self.assertTrue(res_nova["proof_verified"])
            self.assertTrue(res_nova["zero_knowledge"])

            with self.assertRaises(Refused) as ctx:
                nova_gate.verify(sample_nova_public(), b"BAD_NOVA_PROOF")
            self.assertEqual(ctx.exception.code, "ark_nova_proof_rejected")

            # Verify HTTP endpoints on Desk server
            desk = Desk(
                mode="demo",
                core=FakeCore(),
                config={
                    "shinigami_verifier_argv": [sys.executable, str(stub)],
                    "shinigami_verifier_sha256": py_sha,
                    "ark_nova_verifier_argv": [sys.executable, str(stub)],
                    "ark_nova_verifier_sha256": py_sha,
                },
            )
            srv = make_server(desk, port=0)
            port = srv.server_address[1]
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                conn = HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", "/api/ark/proofs", headers={"Host": f"127.0.0.1:{port}"})
                r = conn.getresponse()
                cat = json.loads(r.read().decode("utf-8"))
                self.assertEqual(r.status, 200)
                self.assertTrue(cat["gates"]["shinigami_stwo_exit"]["configured"])
                self.assertTrue(cat["gates"]["ark_transition_nova"]["configured"])

                headers = {
                    "Host": f"127.0.0.1:{port}",
                    "Content-Type": "application/json",
                    "X-Proof-Grove": "1",
                }
                conn.request(
                    "POST",
                    "/api/ark/round/check",
                    body=json.dumps({
                        "public": sample_nova_public(),
                        "proof_base64": base64.b64encode(b"GOOD_NOVA_PROOF").decode(),
                    }),
                    headers=headers,
                )
                r2 = conn.getresponse()
                body2 = json.loads(r2.read().decode("utf-8"))
                self.assertEqual(r2.status, 200)
                self.assertTrue(body2["proof_verified"])

                conn.request(
                    "POST",
                    "/api/ark/vtxo-proof/check",
                    body=json.dumps({
                        "statement": sample_exit_statement(),
                        "proof_base64": base64.b64encode(b"GOOD_STWO_PROOF").decode(),
                    }),
                    headers=headers,
                )
                r3 = conn.getresponse()
                body3 = json.loads(r3.read().decode("utf-8"))
                self.assertEqual(r3.status, 200)
                self.assertTrue(body3["proof_verified"])
                self.assertFalse(body3["zero_knowledge"])
                conn.close()
            finally:
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
