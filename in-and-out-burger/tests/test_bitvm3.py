"""BIP340 signing against the published vectors, and the BitVM3 claim graph's structure.

The graph's spends themselves are checked against Bitcoin Core by scripts/bitvm3_regtest.py
(results/bitvm3-regtest.json) and on testnet4 (results/testnet4-bitvm3/).
"""
import hashlib

import pytest

from iob import bitvm3 as bv
from iob import btc, ec
from iob import taproot as tr

# BIP340 test vectors 0-3 (secret, message, aux, signature).
VECTORS = [
    ("0000000000000000000000000000000000000000000000000000000000000003",
     "0000000000000000000000000000000000000000000000000000000000000000",
     "0000000000000000000000000000000000000000000000000000000000000000",
     "e907831f80848d1069a5371b402410364bdf1c5f8307b0084c55f1ce2dca821525f66a4a85ea8b71e482a74f382d2ce5ebeee8fdb2172f477df4900d310536c0"),
    ("b7e151628aed2a6abf7158809cf4f3c762e7160f38b4da56a784d9045190cfef",
     "243f6a8885a308d313198a2e03707344a4093822299f31d0082efa98ec4e6c89",
     "0000000000000000000000000000000000000000000000000000000000000001",
     "6896bd60eeae296db48a229ff71dfe071bde413e6d43f917dc8dcf8c78de33418906d11ac976abccb20b091292bff4ea897efcb639ea871cfa95f6de339e4b0a"),
    ("c90fdaa22168c234c4c6628b80dc1cd129024e088a67cc74020bbea63b14e5c9",
     "7e2d58d8b3bcdf1abadec7829054f90dda9805aab56c77333024b9d0a508b75c",
     "c87aa53824b4d7ae2eb035a2b5bbbccc080e76cdc6d1692c4b0b62d798e6d906",
     "5831aaeed7b44bb74e5eab94ba9d4294c49bcf2a60728d8b4c200f50dd313c1bab745879a5ad954a72c45a91c3a51d3c7adea98d82f8481e0e1e03674a6f3fb7"),
    ("0b432b2677937381aef05bb02a66ecd012773062cf3fa2549e44f58ed2401710",
     "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "7eb0509757e246f19449885651611cb965ecc1a187dd51b64fda1edc9637d5ec97582b9cb13db3933705b32ba982af5af25fd78881ebb32771fc5922efc66ea3"),
]


@pytest.mark.parametrize("secret,msg,aux,sig", VECTORS)
def test_bip340_vectors(secret, msg, aux, sig):
    s = int(secret, 16)
    got = tr.schnorr_sign(bytes.fromhex(msg), s, bytes.fromhex(aux))
    assert got.hex() == sig
    assert tr.schnorr_verify(bytes.fromhex(msg), tr.xonly(s), got)
    bad = bytearray(got)
    bad[63] ^= 1
    assert not tr.schnorr_verify(bytes.fromhex(msg), tr.xonly(s), bytes(bad))


def test_nums_key_is_bip341s():
    # H = lift_x(SHA256(uncompressed G)), BIP341's example of a provably unspendable internal key.
    g = b"\x04" + ec.G[0].to_bytes(32, "big") + ec.G[1].to_bytes(32, "big")
    assert hashlib.sha256(g).digest() == tr.NUMS_X
    assert tr.lift_x(int.from_bytes(tr.NUMS_X, "big")) is not None


def test_script_numbers():
    assert tr.num(0) == b"\x00" and tr.num(6) == b"\x56" and tr.num(16) == b"\x60"
    assert tr.num(144) == b"\x02\x90\x00"  # 0x90 has its sign bit set, so a 0x00 byte follows
    assert tr.num(127) == b"\x01\x7f"


def _graph(reject=b"\x11" * 32):
    parties = bv.Parties(desk=11, claimant=22, watch=33)
    inst = bv.Instance("honest", "aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32, reject.hex(), btc.p2pkh(b"\x44" * 20))
    return bv.Graph(parties, inst, "ee" * 32, 0, 25_000, btc.p2wpkh(b"\x55" * 20))


def test_graph_shape():
    g = _graph()
    payout, disprove = g.K.leaves
    assert payout == b"\x56\xb2\x75\x20" + tr.xonly(11) + b"\xac"
    assert disprove == b"\xa8\x20" + b"\x11" * 32 + b"\x88\x20" + tr.xonly(33) + b"\xac"
    assert g.claim.outs[1].script_pubkey == b"\x6a\x24IOB3" + g.inst.claim_id()
    assert g.payout.ins[0].sequence == bv.WINDOW_BLOCKS and g.payout.version == 2
    assert g.payout.ins[0].txid == g.claim_txid and g.payout.outs[0].script_pubkey == g.inst.payout_spk
    assert g.vault_value - g.claim_fee == g.k_value > g.payout_value > 0
    # The claim and payout pay 2 sat/vB at their signed size.
    assert g.claim_fee == bv.FEE_SAT_VB * g.signed_claim(g.presign()).vsize()
    assert g.k_value - g.payout_value == bv.FEE_SAT_VB * g.signed_payout(g.presign()).vsize()


def test_claim_id_binds_every_field():
    base = _graph().inst
    seen = {base.claim_id()}
    for field, value in [("name", "other"), ("statement_committed_sha256", "ab" * 32), ("program_vk_digest", "ab" * 32),
                         ("ciphertext_commitment", "ab" * 32), ("accept_label_sha256", "ab" * 32),
                         ("reject_label_sha256", "ab" * 32), ("payout_spk", btc.p2pkh(b"\x45" * 20))]:
        changed = bv.Instance(**{**base.__dict__, field: value})
        assert changed.claim_id() not in seen
        seen.add(changed.claim_id())


def test_presignatures_cover_the_payout_destination():
    g = _graph()
    pre = g.presign()
    good = g.signed_payout(pre)
    m = tr.sighash_script_path(good, 0, [(g.k_value, g.K.script_pubkey)], g.K.leaves[0])
    assert tr.schnorr_verify(m, tr.xonly(11), good.ins[0].witness[0])
    moved = g.payout_redirected(pre, btc.p2wpkh(b"\x66" * 20))
    m2 = tr.sighash_script_path(moved, 0, [(g.k_value, g.K.script_pubkey)], g.K.leaves[0])
    assert not tr.schnorr_verify(m2, tr.xonly(11), moved.ins[0].witness[0])
