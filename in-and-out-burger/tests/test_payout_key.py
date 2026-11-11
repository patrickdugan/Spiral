import io
import json

import pytest

from conftest import menu_dict
from iob import __main__ as cli
from iob import btc, ec, menu, payout_key, sender
from iob.errors import Refusal

TXID = bytes.fromhex("a652ab0cf381413ae854a86bb7e4784811b2d4158a65f26ff64a69eb3eb20045")[::-1]
PAYER_KEY = bytes.fromhex("0254bb0907cb48ad4c28832b85a448f10bd2118dc582e65738bb71984d54647b3b")


def test_curve_vectors():
    assert ec.serialize(ec.mul(1)).hex() == "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    assert ec.serialize(ec.mul(2)).hex() == "02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
    assert ec.serialize(ec.mul(3)).hex() == "02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"
    assert ec.serialize(ec.mul(ec.N - 1)).hex() == "0379be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    assert ec.mul(ec.N) is None and ec.add(ec.mul(7), ec.mul(ec.N - 7)) is None
    assert ec.add(ec.mul(5), ec.mul(9)) == ec.mul(14) and ec.add(ec.mul(4), ec.mul(4)) == ec.mul(8)


def test_parse_serialize():
    for k in (1, 2, 0xDEADBEEF, ec.N - 2):
        pt = ec.mul(k)
        assert ec.parse(ec.serialize(pt)) == pt
        assert ec.parse(ec.serialize(pt, compressed=False)) == pt
    assert ec.parse(PAYER_KEY)[0] == int.from_bytes(PAYER_KEY[1:], "big")
    with pytest.raises(ValueError):
        ec.parse(b"\x02" + (5).to_bytes(32, "big"))  # x^3 + 7 = 132 is not a square mod p
    with pytest.raises(ValueError):
        ec.parse(b"\x02" + ec.P.to_bytes(32, "big"))
    with pytest.raises(ValueError):
        ec.parse(b"\x04" + (1).to_bytes(32, "big") + (1).to_bytes(32, "big"))
    with pytest.raises(ValueError):
        ec.parse(PAYER_KEY[:-1])


def test_wif_vectors():
    assert payout_key.wif_encode(1, "mainnet") == "KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9M7rFU73sVHnoWn"
    assert payout_key.wif_encode(1, "mainnet", compressed=False) == "5HpHagT65TZzG1PH3CSu63k8DbpvD8s5ip4nEB3kEsreAnchuDf"
    assert payout_key.wif_decode("KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9M7rFU73sVHnoWn") == (1, True, 0x80)
    for net, compressed in (("regtest", True), ("testnet4", False), ("mainnet", True)):
        w = payout_key.wif_encode(0x1234567890ABCDEF, net, compressed)
        assert payout_key.wif_decode(w) == (0x1234567890ABCDEF, compressed, payout_key.WIF_VERSION[net])
    with pytest.raises(ValueError):
        payout_key.wif_encode(ec.N, "mainnet")
    with pytest.raises(ValueError):
        payout_key.wif_decode("1BoatSLRHtKNngkdXEeobR76b53LETtpyT")


def test_tweak_binds_outpoint_and_key():
    t = payout_key.tweak(PAYER_KEY, TXID, 0)
    assert t == int.from_bytes(ec.tagged_hash("IOB/payout-key", TXID + b"\x00\x00\x00\x00" + PAYER_KEY), "big")
    assert payout_key.tweak(PAYER_KEY, TXID, 1) != t
    assert payout_key.tweak(PAYER_KEY, TXID[:-1] + b"\x00", 0) != t
    full = ec.serialize(ec.parse(PAYER_KEY), compressed=False)
    assert payout_key.tweak(full, TXID, 0) != t


@pytest.mark.parametrize("compressed", [True, False])
def test_private_key_matches_public_derivation(compressed):
    for secret in (1, 0xC0FFEE, ec.N - 5, int.from_bytes(btc.sha256(b"payer"), "big")):
        pub = ec.serialize(ec.mul(secret), compressed)
        derived_pub, t = payout_key.derive_pubkey(pub, TXID, 3)
        d = payout_key.derive_private(secret, compressed, TXID, 3)
        assert d == (secret + t) % ec.N
        assert ec.serialize(ec.mul(d), compressed) == derived_pub
        assert derived_pub != pub and len(derived_pub) == len(pub)


def test_real_payer_derived_key_is_fresh():
    new_pk, _ = payout_key.derive_pubkey(PAYER_KEY, TXID, 0)
    assert new_pk.hex() == "02af01bc277eb5c041cd66826e9d6fbcadfc485cd76cc3fec655b2110444d1501f"
    spk = payout_key.script_for(new_pk, "p2wpkh")
    assert btc.spk_to_address(spk, "mainnet") == "bc1qf33qwl5845afqf28e9jedrvjfajtgg0g8lal8q"
    assert spk != btc.p2wpkh(btc.hash160(PAYER_KEY))


def test_script_for_types():
    h = btc.hash160(PAYER_KEY)
    assert payout_key.script_for(PAYER_KEY, "p2pkh") == btc.p2pkh(h)
    assert payout_key.script_for(PAYER_KEY, "p2wpkh") == btc.p2wpkh(h)
    assert payout_key.script_for(PAYER_KEY, "p2sh-p2wpkh") == btc.p2sh(btc.hash160(b"\x00\x14" + h))
    with pytest.raises(ValueError):
        payout_key.script_for(PAYER_KEY, "p2wsh")


def test_derive_sender_leaves_declared_and_script_senders():
    declared = sender.Sender(btc.p2tr(b"\x0c" * 32), "p2tr", "declared")
    assert payout_key.derive_sender(declared, TXID, 0) is declared
    script = sender.Sender(btc.p2wsh(b"\x01" * 32), "p2wsh", "input0:p2wsh")
    assert payout_key.derive_sender(script, TXID, 0) is script
    one_key = sender.Sender(btc.p2wpkh(btc.hash160(PAYER_KEY)), "p2wpkh", "input0:p2wpkh", PAYER_KEY, "p2wpkh")
    d = payout_key.derive_sender(one_key, TXID, 0)
    assert d.rule == "input0:p2wpkh:derived" and d.kind == "p2wpkh"
    assert d.derived_from["spent_script_pubkey"] == one_key.script_pubkey.hex()
    off = sender.Sender(b"", "p2wpkh", "input0:p2wpkh", b"\x02" + (5).to_bytes(32, "big"), "p2wpkh")
    with pytest.raises(Refusal) as e:
        payout_key.derive_sender(off, TXID, 0)
    assert e.value.reason == "sender_key_invalid"


def test_menu_payout_key():
    assert menu.from_dict(menu_dict()).payout_key == "derived"
    d = menu_dict()
    del d["out"]["payout_key"]
    assert menu.from_dict(d).payout_key == "derived"
    assert menu.from_dict(menu_dict(**{"out.payout_key": "spent"})).payout_key == "spent"
    with pytest.raises(ValueError):
        menu.from_dict(menu_dict(**{"out.payout_key": "fresh"}))


def test_cli_payout_key(capsys, monkeypatch):
    outpoint = TXID[::-1].hex() + ":0"
    assert cli.main(["payout-key", "--in-outpoint", outpoint, "--pubkey", PAYER_KEY.hex()]) == 0
    pub_out = json.loads(capsys.readouterr().out)
    assert pub_out["address"] == "bc1qf33qwl5845afqf28e9jedrvjfajtgg0g8lal8q"

    secret = int.from_bytes(btc.sha256(b"payer"), "big")
    monkeypatch.setattr("sys.stdin", io.StringIO(payout_key.wif_encode(secret, "regtest") + "\n"))
    assert cli.main(["payout-key", "--in-outpoint", outpoint, "--type", "p2sh-p2wpkh", "--network", "regtest", "--wif-stdin"]) == 0
    out = json.loads(capsys.readouterr().out)
    d, compressed, _ = payout_key.wif_decode(out["wif"])
    assert compressed and d == payout_key.derive_private(secret, True, TXID, 0)
    assert out["descriptor"] == f"sh(wpkh({out['wif']}))"
    spk = payout_key.script_for(ec.serialize(ec.mul(d)), "p2sh-p2wpkh")
    assert out["script_pubkey"] == spk.hex() and out["address"] == btc.spk_to_address(spk, "regtest")

    monkeypatch.setattr("sys.stdin", io.StringIO(payout_key.wif_encode(secret, "mainnet") + "\n"))
    with pytest.raises(SystemExit):
        cli.main(["payout-key", "--in-outpoint", outpoint, "--network", "regtest", "--wif-stdin"])
