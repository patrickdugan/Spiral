import copy
import struct

import pytest

from iob import btc, sender
from iob.errors import Refusal

BLOCK_975067 = "000000000000000000017809af97fdd5530149e411b2ab091db4f405e355fe22"
# The script input 0 of a652ab0c spent: output 1 of 862239f7...876e, which mempool.space
# reports as bc1qcfgpeswyzk9sh9qxxa53lqrnd92whjy2gl8awg (950,000 sats).
PAYER_SPK = "0014c2501cc1c4158b0b940637691f80736954ebc88a"

DER = bytes.fromhex("3044" + "0220" + "11" * 32 + "0220" + "22" * 32) + b"\x01"
PK = b"\x02" + b"\x33" * 32


def tx_of(real):
    return btc.parse_tx(bytes.fromhex(real["tx_hex"]))


def test_real_sender(real):
    tx = tx_of(real)
    sender.verify_proof(real["sender_proof"], BLOCK_975067, tx)
    s = sender.resolve(tx)
    assert s.script_pubkey.hex() == PAYER_SPK and s.kind == "p2wpkh" and s.rule == "input0:p2wpkh"


def _flip_hex(h: str, byte: int) -> str:
    b = bytearray(bytes.fromhex(h))
    b[byte] ^= 1
    return b.hex()


def test_real_sender_proof_tampering(real):
    tx = tx_of(real)
    sp = real["sender_proof"]
    cases = []

    bad = copy.deepcopy(sp); bad["header"] = _flip_hex(bad["header"], 76)  # nonce
    cases.append(("sender_proof_header", bad, tx))

    bad = copy.deepcopy(sp); bad["coinbase_branch"][3] = _flip_hex(bad["coinbase_branch"][3], 0)
    cases.append(("sender_proof_coinbase", bad, tx))

    bad = copy.deepcopy(sp); bad["tx_branch"][0] = _flip_hex(bad["tx_branch"][0], 5)
    cases.append(("sender_proof_tx", bad, tx))

    bad = copy.deepcopy(sp); bad["index"] = 2
    cases.append(("sender_proof_tx", bad, tx))

    bad = copy.deepcopy(sp); bad["wtx_branch"][0] = _flip_hex(bad["wtx_branch"][0], 5)
    cases.append(("sender_proof_witness", bad, tx))

    # another witness for the same txid: the pubkey's last byte changed
    forged = copy.deepcopy(tx)
    forged.inputs[0].witness[1] = forged.inputs[0].witness[1][:-1] + b"\x00"
    assert forged.txid() == tx.txid()
    cases.append(("sender_proof_witness", sp, forged))

    # coinbase with another witness reserved value: same txid, commitment no longer matches
    cb = btc.parse_tx(bytes.fromhex(sp["coinbase"]))
    cb.inputs[0].witness = [b"\x01" * 32]
    bad = copy.deepcopy(sp); bad["coinbase"] = cb.serialize().hex()
    cases.append(("sender_proof_witness", bad, tx))

    bad = copy.deepcopy(sp); bad["coinbase_branch"] = bad["coinbase_branch"][:-1]
    cases.append(("sender_proof_malformed", bad, tx))

    bad = copy.deepcopy(sp); bad["version"] = "IOB-SP0"
    cases.append(("sender_proof_malformed", bad, tx))

    for reason, proof, t in cases:
        with pytest.raises(Refusal) as e:
            sender.verify_proof(proof, BLOCK_975067, t)
        assert e.value.reason == reason, (reason, e.value)

    with pytest.raises(Refusal) as e:
        sender.verify_proof(sp, "00" * 32, tx)
    assert e.value.reason == "sender_proof_header"


# --- synthetic blocks -------------------------------------------------------------------------


def mk_tx(inputs, outputs):
    return btc.Tx(2, [btc.TxIn(b"\x07" * 32, i, ss, 0xFFFFFFFD, list(w)) for i, (ss, w) in enumerate(inputs)],
                  [btc.TxOut(v, s) for v, s in outputs], 0)


def mk_block(txs: list) -> bytes:
    wtxids = [b"\x00" * 32] + [t.wtxid() for t in txs]
    reserved = b"\x00" * 32
    commit = btc.sha256d(btc.merkle_root(wtxids) + reserved)
    cb = btc.Tx(2, [btc.TxIn(b"\x00" * 32, 0xFFFFFFFF, b"\x03\x01\x02\x03" + b"\x00" * 20, 0xFFFFFFFF, [reserved])],
                [btc.TxOut(50_0000_0000, btc.p2wpkh(b"\x09" * 20)), btc.TxOut(0, bytes.fromhex("6a24aa21a9ed") + commit)], 0)
    all_txs = [cb] + txs
    root = btc.merkle_root([t.txid() for t in all_txs])
    header = struct.pack("<i", 0x20000000) + b"\x05" * 32 + root + struct.pack("<III", 1_700_000_000, 0x1D00FFFF, 7)
    return header + btc.ser_compact(len(all_txs)) + b"".join(t.serialize() for t in all_txs)


def test_build_and_verify_synthetic():
    pay = mk_tx([(b"", [DER, PK])], [(100_000, btc.p2wpkh(b"\x01" * 20))])
    filler = [mk_tx([(b"", [DER, b"\x03" + bytes([i]) * 32])], [(1000 + i, btc.p2tr(b"\x02" * 32))]) for i in range(5)]
    block = mk_block(filler[:2] + [pay] + filler[2:])
    sp = sender.build_proof(block, pay.txid()[::-1].hex())
    assert sp["index"] == 3
    block_hash = btc.sha256d(block[:80])[::-1].hex()
    sender.verify_proof(sp, block_hash, btc.parse_tx(bytes.fromhex(sp["tx"])))
    assert sender.resolve(pay).script_pubkey == btc.p2wpkh(btc.hash160(PK))


def _resolve(ss: bytes, wit: list, outputs=None):
    return sender.resolve(mk_tx([(ss, wit)], outputs or [(1000, btc.p2wpkh(b"\x01" * 20))]))


def test_input_rules():
    redeem_wpkh = b"\x00\x14" + btc.hash160(PK)
    wscript = b"\x52" + btc.push(PK) + btc.push(b"\x03" + b"\x44" * 32) + b"\x52\xae"
    redeem_wsh = b"\x00\x20" + btc.sha256(wscript)

    s = _resolve(btc.push(DER) + btc.push(PK), [])
    assert (s.kind, s.script_pubkey) == ("p2pkh", btc.p2pkh(btc.hash160(PK)))

    redeem = b"\x51"
    s = _resolve(btc.push(redeem), [])
    assert (s.kind, s.script_pubkey) == ("p2sh", btc.p2sh(btc.hash160(redeem)))

    s = _resolve(btc.push(redeem_wpkh), [DER, PK])
    assert (s.kind, s.rule, s.script_pubkey) == ("p2sh", "input0:p2sh-p2wpkh", btc.p2sh(btc.hash160(redeem_wpkh)))

    s = _resolve(btc.push(redeem_wsh), [b"", DER, wscript])
    assert (s.rule, s.script_pubkey) == ("input0:p2sh-p2wsh", btc.p2sh(btc.hash160(redeem_wsh)))

    s = _resolve(b"", [b"", DER, wscript])
    assert (s.kind, s.script_pubkey) == ("p2wsh", btc.p2wsh(btc.sha256(wscript)))

    # nested program that does not match the witness
    with pytest.raises(Refusal):
        _resolve(btc.push(b"\x00\x14" + b"\x00" * 20), [DER, PK])


@pytest.mark.parametrize("ss,wit,why", [
    (b"", [b"\x01" * 64], "taproot_key_path"),
    (b"", [b"\x01" * 65], "taproot_key_path"),
    (b"", [b"\x01" * 64, b"\x50annex"], "taproot_key_path"),
    (b"", [b"\x01" * 64, b"\x51", b"\xc0" + b"\x02" * 32], "taproot_script_path"),
    (btc.push(DER), [], "P2PK"),
    (b"\x00" + btc.push(DER) + btc.push(DER), [], "multisig"),
    (b"\x76", [], "push-only"),
])
def test_unresolvable(ss, wit, why):
    with pytest.raises(Refusal) as e:
        _resolve(ss, wit)
    assert e.value.reason == "sender_unresolvable" and why in e.value.detail


def test_declared_return_wins():
    ret = btc.p2tr(b"\x0a" * 32)
    s = _resolve(b"", [b"\x01" * 64], [(1000, btc.p2wpkh(b"\x01" * 20)), (0, b"\x6a" + btc.push(b"IOB1" + ret))])
    assert (s.rule, s.kind, s.script_pubkey) == ("declared", "p2tr", ret)

    with pytest.raises(Refusal) as e:
        _resolve(b"", [], [(0, b"\x6a" + btc.push(b"IOB1" + ret)), (0, b"\x6a" + btc.push(b"IOB1" + ret))])
    assert e.value.reason == "ambiguous_return_script"

    with pytest.raises(Refusal) as e:
        _resolve(b"", [], [(0, b"\x6a" + btc.push(b"IOB1" + b"\x6a\x01\x00"))])
    assert e.value.reason == "return_script_nonstandard"
