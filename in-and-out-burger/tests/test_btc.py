import pytest

from conftest import read
from iob import btc

G = bytes.fromhex("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")


def test_ripemd160_vectors():
    vectors = {
        b"": "9c1185a5c5e9fc54612808977ee8f548b2258d31",
        b"a": "0bdc9d2d256b3ee9daae347be6f4dc835a467ffe",
        b"abc": "8eb208f7e05d987a9b044a8e98c6b087f15a0bfc",
        b"message digest": "5d0689ef49d2fae572b881b123a85ffa21595f36",
        b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq": "12a053384a9c0c88e405a06c27dcf49ada62eb2b",
        b"1234567890" * 8: "9b752e45573d4b39f4dbd3323cab82bf63326bfb",
    }
    for msg, want in vectors.items():
        assert btc.ripemd160_pure(msg).hex() == want
    assert btc.ripemd160_pure(b"a" * 1_000_000).hex() == "52783243c1697bdbe16d37f97f68f08325dc1528"


def test_hash160_and_addresses():
    h = btc.hash160(G)
    assert h.hex() == "751e76e8199196d454941c45d1b3a323f1433bd6"
    assert btc.address_to_spk("BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4", "mainnet") == btc.p2wpkh(h)
    assert btc.spk_to_address(btc.p2wpkh(h), "mainnet") == "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
    tr = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"
    assert btc.address_to_spk(tr, "mainnet") == btc.p2tr(G[1:])
    assert btc.spk_to_address(btc.p2tr(G[1:]), "mainnet") == tr
    assert btc.address_to_spk("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2", "mainnet") == btc.p2pkh(bytes.fromhex("77bff20c60e522dfaa3350c39b030a5d004e839a"))
    assert btc.address_to_spk("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy", "mainnet") == btc.p2sh(bytes.fromhex("b472a266d0bd89c13706a4132ccfb16f7c3b9fcb"))
    for spk in (btc.p2pkh(h), btc.p2sh(h), btc.p2wpkh(h), btc.p2wsh(b"\x01" * 32), btc.p2tr(G[1:])):
        for net in btc.NETWORKS:
            assert btc.address_to_spk(btc.spk_to_address(spk, net), net) == spk


@pytest.mark.parametrize("bad", [
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5",           # checksum
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kV8f3t4",           # mixed case
    "bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7k7grplx",  # v1 with bech32 checksum
    "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx",           # wrong network
    "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN3",                   # base58 checksum
])
def test_bad_addresses(bad):
    with pytest.raises(ValueError):
        btc.address_to_spk(bad, "mainnet")


def test_real_payment_tx():
    raw = bytes.fromhex(read("payment-tx.hex", "r").strip())
    tx = btc.parse_tx(raw)
    assert tx.txid()[::-1].hex() == "a652ab0cf381413ae854a86bb7e4784811b2d4158a65f26ff64a69eb3eb20045"
    assert len(tx.stripped()) == 82 and tx.has_witness
    assert tx.outputs[0].value == 940_000
    assert btc.parse_tx(tx.stripped()).txid() == tx.txid()


def test_parse_refusals():
    raw = bytes.fromhex(read("payment-tx.hex", "r").strip())
    with pytest.raises(btc.ParseError):
        btc.parse_tx(raw + b"\x00")
    with pytest.raises(btc.ParseError):
        btc.parse_tx(raw[:-1])
    stripped = btc.parse_tx(raw).stripped()
    # input count 1 re-encoded as fd 01 00
    with pytest.raises(btc.ParseError):
        btc.parse_tx(stripped[:4] + b"\xfd\x01\x00" + stripped[5:])


def test_merkle_branches():
    for n in range(1, 12):
        leaves = [btc.sha256d(bytes([i])) for i in range(n)]
        root = btc.merkle_root(leaves)
        for i in range(n):
            assert btc.root_from_branch(leaves[i], btc.merkle_branch(leaves, i), i) == root
    with pytest.raises(btc.ParseError):
        btc.root_from_branch(leaves[0], btc.merkle_branch(leaves, 0), 1 << 10)


def test_pushes_and_der():
    assert btc.parse_pushes(b"\x00\x02ab\x4c\x01c\x51") == [b"", b"ab", b"c", b"\x01"]
    assert btc.parse_pushes(b"\x76") is None
    assert btc.parse_pushes(b"\x05ab") is None
    der = bytes.fromhex("3044" + "0220" + "11" * 32 + "0220" + "22" * 32) + b"\x01"
    assert btc.is_der_signature(der)
    assert not btc.is_der_signature(der[:-2] + b"\x01")
    assert not btc.is_der_signature(bytes.fromhex("3044" + "0220" + "91" * 32 + "0220" + "22" * 32) + b"\x01")


def test_dust_table_covers_payable_kinds():
    assert set(btc.DUST_SATS) == {"p2pkh", "p2sh", "p2wpkh", "p2wsh", "p2tr"}
