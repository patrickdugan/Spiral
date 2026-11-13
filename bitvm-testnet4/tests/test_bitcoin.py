import csv
from pathlib import Path

import pytest

from bitvm_demo import bitcoin as b
from bitvm_demo.circuits import Circuit

VECTORS = list(csv.DictReader((Path(__file__).parent / 'data/bip340.csv').open(newline='')))


@pytest.mark.parametrize('vector', [v for v in VECTORS if len(v['message']) == 64], ids=lambda v: v['index'])
def test_official_bip340_verification(vector):
    assert b.verify(bytes.fromhex(vector['message']), bytes.fromhex(vector['public key']),
                    bytes.fromhex(vector['signature'])) == (vector['verification result'] == 'TRUE')


@pytest.mark.parametrize('vector', [v for v in VECTORS if v['secret key'] and len(v['message']) == 64], ids=lambda v: v['index'])
def test_official_bip340_signing(vector):
    secret = int(vector['secret key'], 16)
    assert b.xonly(secret).hex().upper() == vector['public key']
    assert b.sign(bytes.fromhex(vector['message']), secret, bytes.fromhex(vector['aux_rand'])).hex().upper() == vector['signature']


def test_private_state_is_not_in_public_plan(tmp_path):
    c = Circuit.create('half-adder')
    private = tmp_path / 'private.json'
    c.save_private(private)
    public = c.public()
    text = str(public)
    assert c.challenger.to_bytes(32, 'big').hex() not in text
    assert c.refund.to_bytes(32, 'big').hex() not in text
    assert Circuit.load_private(private).public() == public
    with pytest.raises(FileExistsError):
        c.save_private(private)
    with pytest.raises(ValueError):
        Circuit.load_private(private, 'regtest')


@pytest.mark.parametrize('a,b_', [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_truth_tables_and_single_false_gate(a, b_):
    nand = Circuit.create('nand', False, a, b_)
    assert nand.claimed['out'] == 1 - (a & b_) and nand.bad_gates() == []
    assert Circuit.create('nand', True, a, b_).bad_gates() == [0]
    adder = Circuit.create('half-adder', False, a, b_)
    assert adder.claimed['sum'] == a ^ b_ and adder.claimed['carry'] == a & b_
    assert adder.bad_gates() == []
    assert Circuit.create('half-adder', True, a, b_).bad_gates() == [3]


def test_script_has_only_deployed_opcodes_and_claim_bits_are_committed():
    c = Circuit.create('half-adder')
    original = c.taproot()
    success = {80, 98, *range(126, 130), *range(131, 135), *range(137, 139),
               *range(141, 143), *range(149, 154), *range(187, 255)}
    for script, control in zip(original.leaves, original.controls):
        assert not any(op in success for op, data in b.reference.ops(script) if data is None)
        root = b.reference.tapleaf(script)
        for at in range(33, len(control), 32):
            root = b.reference.tapbranch(root, control[at:at + 32])
        internal = b.ec.parse(b'\x02' + control[1:33])
        tweak = int.from_bytes(b.ec.tagged_hash('TapTweak', control[1:33] + root), 'big')
        key = b.ec.add(internal, b.ec.mul(tweak))
        assert original.script_pubkey == b'\x51\x20' + key[0].to_bytes(32, 'big')
        assert key[1] & 1 == control[0] & 1
    c.claimed['sum'] ^= 1
    assert c.taproot().script_pubkey != original.script_pubkey


def test_fresh_runtime_keys_and_signature_context():
    first, second = Circuit.create('nand'), Circuit.create('nand')
    assert first.public()['challenger_pubkey'] != second.public()['challenger_pubkey']
    tx = first.spend('12' * 32, 0, 20000, b'\x51', gate=0)
    message = b.sighash(tx, 20000, first.taproot().script_pubkey, first.refutation_script(0))
    assert b.verify(message, b.xonly(first.challenger), tx.inputs[0].witness[0])
    tx.outputs[0].value -= 1
    wrong = b.sighash(tx, 20000, first.taproot().script_pubkey, first.refutation_script(0))
    assert not b.verify(wrong, b.xonly(first.challenger), tx.inputs[0].witness[0])
