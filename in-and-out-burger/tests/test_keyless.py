from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from conftest import menu_dict
from iob import btc, desk, gate, keyless, menu, statement
from iob.errors import Refusal
from iob.ledger import Ledger
from iob.rpc import RPCError

reference_path = Path(__file__).resolve().parents[2] / "BIPSpace/Keyless-CHECKSIG/reference.py"
spec = importlib.util.spec_from_file_location("iob_keyless_reference", reference_path)
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)


@pytest.fixture
def approved(real, real_menu, tmp_path, monkeypatch):
    proof = tmp_path / "unit-proof.bin"
    proof.write_bytes(b"unit test verifier response; not a cryptographic proof")
    payment = statement.parse(real["statement"]).payment
    reply = {"payment": {"txid": payment.txid_display, "vout": payment.vout,
                         "value_sats": payment.value_sats, "script_sha256": payment.script_sha256.hex(),
                         "confirmations": payment.confirmations}}
    monkeypatch.setattr(gate, "check", lambda *args, **kw: reply)
    order = desk.Order(real["statement"], real["tx_hex"], real["sender_proof"], str(proof))
    return keyless.prepare(real_menu, order, Ledger(None)), order


def test_approved_order_binds_the_existing_sender_and_price(approved):
    a, _ = approved
    assert a.payout_sats == 948_400 and a.reserve_sats == 950_400
    assert a.recipient_script.hex() == "00144c62077e87ad3a902547c965968d924f64b421e8"
    assert a.link.hex() == "494f4250" + bytes.fromhex(
        "a652ab0cf381413ae854a86bb7e4784811b2d4158a65f26ff64a69eb3eb20045")[::-1].hex() + "00000000"
    record = json.loads(a.context_record)
    assert record["statement_sha256"] == "cae6068f7ad8c4891cb3220702a88b0bc3df54013f45e65df11a9ced531bc869"
    assert record["out_network"] == "regtest"


def test_transcript_matches_the_independent_bip341_reference(approved):
    a, _ = approved
    tx = a.spend("12" * 32, 3)
    spk, control = a.taproot()
    converted = reference.Tx((reference.Input(bytes.fromhex("12" * 32), 3, 950_400, spk),),
                             tuple(reference.Output(o.value, o.script_pubkey) for o in tx.outputs))
    expected = reference.sigmsg(converted, 0, leaf=reference.tapleaf(a.script))
    assert a.sigmsg(tx) == expected
    assert len(expected) == 212
    assert expected[138:170] == a.outputs_hash
    assert expected[170:175] == b"\x02\x00\x00\x00\x00"
    assert expected[-5:] == b"\x02\xff\xff\xff\xff"
    assert [len(v) for v in tx.inputs[0].witness[:3]] == [32, 32, 37]
    assert control[1:] == keyless.NUMS_X and len(control) == 33
    assert spk[:2] == b"\x51\x20"
    assert btc.parse_tx(tx.serialize()).serialize() == tx.serialize()


@pytest.mark.parametrize("field", ["proof_sha256", "statement_sha256", "in_outpoint", "pricing", "gate_policy"])
def test_application_context_changes_the_funding_output(approved, field):
    a, _ = approved
    record = json.loads(a.context_record)
    record[field] = "changed"
    other = replace(a, context_record=json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    assert other.context != a.context and other.taproot()[0] != a.taproot()[0]


@pytest.mark.parametrize("network", ["mainnet", "testnet4", "signet"])
def test_public_payout_networks_refuse_before_verification(real, network):
    m = menu.from_dict(menu_dict(**{"out.network": network}))
    with pytest.raises(Refusal) as error:
        keyless.prepare(m, desk.Order(real["statement"], real["tx_hex"]), Ledger(None))
    assert error.value.reason == "keyless_needs_regtest"


def test_unproven_orders_and_missing_link_refuse(real, real_menu):
    order = desk.Order(real["statement"], real["tx_hex"], real["sender_proof"])
    with pytest.raises(Refusal) as error:
        keyless.prepare(real_menu, order, Ledger(None))
    assert error.value.reason == "proof_required"
    with pytest.raises(Refusal) as error:
        keyless.prepare(replace(real_menu, link_op_return=False), order, Ledger(None))
    assert error.value.reason == "keyless_link_required"


def test_gate_refusal_cannot_produce_a_reserve(approved, real_menu, monkeypatch):
    _, order = approved
    def refuse(*args, **kw):
        raise Refusal("proof_rejected", "independent verifier refused")
    monkeypatch.setattr(gate, "check", refuse)
    with pytest.raises(Refusal) as error:
        keyless.prepare(real_menu, order, Ledger(None))
    assert error.value.reason == "proof_rejected"


def test_proof_digest_describes_the_verified_snapshot(approved, real_menu, monkeypatch):
    _, order = approved
    original = Path(order.proof_path).read_bytes()
    check = gate.check
    def mutate_original(menu_, proof_path, statement_path):
        assert Path(proof_path).read_bytes() == original
        Path(order.proof_path).write_bytes(b"changed after snapshot")
        return check(menu_, proof_path, statement_path)
    monkeypatch.setattr(gate, "check", mutate_original)
    a = keyless.prepare(real_menu, order, Ledger(None))
    assert json.loads(a.context_record)["proof_sha256"] == btc.sha256(original).hex()


class Node:
    def __init__(self, approval, chain="regtest", peers=0):
        self.approval, self.chain, self.peers, self.calls = approval, chain, peers, []
        self.spent = False

    def call(self, method, *args):
        self.calls.append(method)
        a = self.approval
        if method == "getblockchaininfo": return {"chain": self.chain}
        if method == "getblockhash": return keyless.REGTEST_GENESIS
        if method == "getconnectioncount": return self.peers
        if method == "gettxout":
            return None if self.spent else {"scriptPubKey": {"hex": a.taproot()[0].hex()}, "value": "0.00950400"}
        if method == "testmempoolaccept": return [{"allowed": True}]
        if method == "sendrawtransaction":
            self.spent = True
            return btc.parse_tx(bytes.fromhex(args[0])).txid()[::-1].hex()
        raise AssertionError(method)


@pytest.mark.parametrize("chain,peers", [("testnet4", 0), ("main", 0), ("regtest", 1)])
def test_runtime_network_and_peer_checks_precede_spending(approved, chain, peers):
    a, _ = approved
    node = Node(a, chain, peers)
    payer = keyless.KeylessPayer(node, a, "12" * 32, 0, True)
    with pytest.raises(desk.PayError):
        payer.pay(a.recipient_script, a.payout_sats, a.link)
    assert "sendrawtransaction" not in node.calls and "testmempoolaccept" not in node.calls


def test_payer_spends_once_and_requires_exact_approved_arguments(approved):
    a, _ = approved
    node = Node(a)
    payer = keyless.KeylessPayer(node, a, "12" * 32, 0, True)
    with pytest.raises(desk.PayError):
        payer.pay(a.recipient_script, a.payout_sats + 1, a.link)
    assert node.calls == []
    assert payer.pay(a.recipient_script, a.payout_sats, a.link)["broadcast"] is True
    with pytest.raises(desk.PayError):
        payer.pay(a.recipient_script, a.payout_sats, a.link)
    assert node.calls.count("sendrawtransaction") == 1


def test_dry_keyless_payout_does_not_claim_a_signature(approved, real_menu):
    a, order = approved
    result = desk.serve(real_menu, order, Ledger(None), keyless.KeylessPayer(Node(a), a, "12" * 32, 0))
    assert result["status"] == "prepared_not_broadcast"


def test_ambiguous_broadcast_preserves_the_ledger_reservation(approved, real_menu, tmp_path):
    a, order = approved
    node = Node(a)
    call = node.call
    def uncertain(method, *args):
        if method == "sendrawtransaction": raise RPCError("connection lost")
        return call(method, *args)
    node.call = uncertain
    path = str(tmp_path / "ledger.jsonl")
    result = desk.serve(real_menu, order, Ledger(path), keyless.KeylessPayer(node, a, "12" * 32, 0, True))
    assert result["reason"] == "payout_failed" and result["reserved"] is True
    with pytest.raises(Refusal) as error:
        Ledger(path).check_free(json.loads(a.context_record)["in_outpoint"])
    assert error.value.reason == "order_in_flight"
