import struct

import pytest

from conftest import menu_dict, synthetic_menu, synthetic_statement
from iob import btc, desk, menu, statement
from iob.errors import Refusal
from iob.ledger import Ledger
from test_sender import DER, PK, mk_block, mk_tx

OUTPOINT = "a652ab0cf381413ae854a86bb7e4784811b2d4158a65f26ff64a69eb3eb20045:0"


def order(real, **over):
    d = dict(statement=real["statement"], tx_hex=real["tx_hex"], sender_proof=real["sender_proof"])
    d.update(over)
    return desk.Order(**d)


def refused(m, o, ledger=None, **kw):
    with pytest.raises(Refusal) as e:
        desk.evaluate(m, o, ledger or Ledger(None), **kw)
    return e.value.reason


def test_real_order_unproven(real, real_menu):
    res = desk.evaluate(real_menu, order(real), Ledger(None), allow_unproven=True)
    assert res["proof"] == "absent"
    assert res["statement_sha256"] == "cae6068f7ad8c4891cb3220702a88b0bc3df54013f45e65df11a9ced531bc869"
    assert res["in"]["outpoint"] == OUTPOINT and res["in"]["value_sats"] == 940_000
    assert res["sender"] == {
        "script_pubkey": "0014c2501cc1c4158b0b940637691f80736954ebc88a",
        "kind": "p2wpkh",
        "rule": "input0:p2wpkh",
        "payout_address": "bcrt1qcfgpeswyzk9sh9qxxa53lqrnd92whjy2qs9rzj",
    }
    assert res["payout"]["sats"] == 948_400
    st = statement.parse(real["statement"])
    assert bytes.fromhex(res["_link"]) == b"IOBP" + st.payment.txid_internal + struct.pack("<I", 0)


def test_stripped_tx_takes_witness_from_sender_proof(real, real_menu):
    stripped = btc.parse_tx(bytes.fromhex(real["tx_hex"])).stripped().hex()
    res = desk.evaluate(real_menu, order(real, tx_hex=stripped), Ledger(None), allow_unproven=True)
    assert res["sender"]["kind"] == "p2wpkh"
    assert refused(real_menu, order(real, tx_hex=stripped, sender_proof=None), allow_unproven=True) == "sender_unresolvable"


def test_real_order_refusals(real, real_menu):
    m = real_menu
    assert refused(m, order(real)) == "proof_required"
    assert refused(menu.from_dict(menu_dict(**{"out.network": "mainnet"})), order(real), allow_unproven=True) == "unproven_needs_regtest"
    assert refused(m, order(real, sender_proof=None), allow_unproven=True) == "sender_proof_required"

    tx = bytearray(bytes.fromhex(real["tx_hex"]))
    tx[-40] ^= 1  # inside the witness signature: txid unchanged, wtxid changed
    assert refused(m, order(real, tx_hex=tx.hex()), allow_unproven=True) == "sender_proof_witness"
    tx = bytearray(bytes.fromhex(real["tx_hex"]))
    tx[50] ^= 1  # output value
    assert refused(m, order(real, tx_hex=tx.hex()), allow_unproven=True) == "txid_mismatch"
    assert refused(m, order(real, tx_hex="00"), allow_unproven=True) == "tx_malformed"

    other = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
    assert refused(menu.from_dict(menu_dict(**{"in.address": other})), order(real), allow_unproven=True) == "script_not_registered"
    assert refused(menu.from_dict(menu_dict(**{"in.min_confirmations": 7})), order(real), allow_unproven=True) == "too_few_confirmations"
    assert refused(menu.from_dict(menu_dict(**{"in.min_tip_chainwork": "0x156c4c3c54ad473bac5daf262"})), order(real), allow_unproven=True) == "chainwork_below_floor"
    assert refused(menu.from_dict(menu_dict(**{"in.min_value_sats": 940_001})), order(real), allow_unproven=True) == "value_below_policy"
    tn4 = menu_dict(**{"in.network": "testnet4", "in.address": btc.spk_to_address(m.in_spk, "testnet4")})
    assert refused(menu.from_dict(tn4), order(real), allow_unproven=True) == "wrong_network"

    st = bytearray(real["statement"])
    st[12 + 32 * 5] ^= 1  # z0 element 5: not genesis any more
    assert refused(m, order(real, statement=bytes(st)), allow_unproven=True) == "wrong_genesis"
    st = bytearray(real["statement"])
    st[12 + 2 * statement.STATE_BYTES] ^= 1  # Nova key digest
    assert refused(m, order(real, statement=bytes(st)), allow_unproven=True) == "wrong_nova_key"


def test_ledger_replay(real, real_menu, tmp_path):
    led = Ledger(str(tmp_path / "served.jsonl"))
    led.reserve(OUTPOINT, 1, "00")
    led.paid(OUTPOINT, "ab" * 32)
    assert refused(real_menu, order(real), Ledger(str(tmp_path / "served.jsonl")), allow_unproven=True) == "already_served"


class FakePayer:
    def __init__(self, fail=None):
        self.fail, self.calls = fail, []

    def pay(self, spk, sats, link):
        self.calls.append((spk, sats, link))
        if self.fail is not None:
            raise desk.PayError("boom", self.fail)
        return {"txid": "cd" * 32, "hex": "", "broadcast": True}


def test_serve_with_payer(real, real_menu, tmp_path):
    path = str(tmp_path / "served.jsonl")
    p = FakePayer()
    res = desk.serve(real_menu, order(real), Ledger(path), p, allow_unproven=True)
    assert res["status"] == "served" and res["payout"]["txid"] == "cd" * 32
    spk, sats, link = p.calls[0]
    assert spk.hex() == "0014c2501cc1c4158b0b940637691f80736954ebc88a" and sats == 948_400 and link[:4] == b"IOBP"
    again = desk.serve(real_menu, order(real), Ledger(path), FakePayer(), allow_unproven=True)
    assert (again["status"], again["reason"]) == ("refused", "already_served")


def test_serve_failures(real, real_menu, tmp_path):
    path = str(tmp_path / "served.jsonl")
    res = desk.serve(real_menu, order(real), Ledger(path), FakePayer(fail=False), allow_unproven=True)
    assert (res["reason"], res["reserved"]) == ("payout_failed", False)
    assert desk.serve(real_menu, order(real), Ledger(path), FakePayer(), allow_unproven=True)["status"] == "served"

    path = str(tmp_path / "served2.jsonl")
    res = desk.serve(real_menu, order(real), Ledger(path), FakePayer(fail=True), allow_unproven=True)
    assert (res["reason"], res["reserved"]) == ("payout_failed", True)
    res = desk.serve(real_menu, order(real), Ledger(path), FakePayer(), allow_unproven=True)
    assert res["reason"] == "order_in_flight"


# --- synthetic chains: the other sender rules through the whole desk ---------------------------


def _synthetic(pay_tx: btc.Tx, in_spk: bytes):
    block = mk_block([mk_tx([(b"", [DER, b"\x03" + b"\x01" * 32])], [(5000, btc.p2tr(b"\x02" * 32))]), pay_tx])
    block_hash = btc.sha256d(block[:80])[::-1].hex()
    st = synthetic_statement(pay_tx, 0, block_hash=block_hash)
    from iob import sender
    sp = sender.build_proof(block, pay_tx.txid()[::-1].hex())
    return synthetic_menu(in_spk), st, sp


def test_synthetic_declared_return_from_taproot_spender():
    in_spk = btc.p2wpkh(b"\x0b" * 20)
    ret = btc.p2tr(b"\x0c" * 32)
    pay = mk_tx([(b"", [b"\x01" * 64])], [(200_000, in_spk), (0, b"\x6a" + btc.push(b"IOB1" + ret))])
    m, st, sp = _synthetic(pay, in_spk)
    res = desk.evaluate(m, desk.Order(st, pay.stripped().hex()), Ledger(None), allow_unproven=True)
    assert res["sender"]["rule"] == "declared" and res["sender"]["script_pubkey"] == ret.hex()
    assert res["payout"]["sats"] == 199_000
    # the same spender without the IOB1 output cannot be paid back
    pay2 = mk_tx([(b"", [b"\x01" * 64])], [(200_000, in_spk)])
    m, st, sp = _synthetic(pay2, in_spk)
    assert refused(m, desk.Order(st, pay2.serialize().hex(), sp), allow_unproven=True) == "sender_unresolvable"


def test_synthetic_p2pkh_spender_needs_no_sender_proof():
    in_spk = btc.p2wpkh(b"\x0b" * 20)
    pay = mk_tx([(btc.push(DER) + btc.push(PK), [])], [(50_000, in_spk)])
    m, st, _ = _synthetic(pay, in_spk)
    res = desk.evaluate(m, desk.Order(st, pay.serialize().hex()), Ledger(None), allow_unproven=True)
    assert res["sender"]["script_pubkey"] == btc.p2pkh(btc.hash160(PK)).hex()


def test_synthetic_p2wpkh_spender_with_sender_proof():
    in_spk = btc.p2wpkh(b"\x0b" * 20)
    pay = mk_tx([(b"", [DER, PK])], [(70_000, in_spk)])
    m, st, sp = _synthetic(pay, in_spk)
    res = desk.evaluate(m, desk.Order(st, pay.stripped().hex(), sp), Ledger(None), allow_unproven=True)
    assert res["sender"]["script_pubkey"] == btc.p2wpkh(btc.hash160(PK)).hex()
    assert res["payout"]["sats"] == 69_000
