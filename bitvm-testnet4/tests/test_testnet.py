import base64
import copy
import hashlib
import json

import pytest

from bitvm_demo import bitcoin as b
from bitvm_demo import testnet as t


def test_psbt_preserves_unsigned_transaction_and_witness_coin():
    script = b'\x51\x20' + b'\x21' * 32
    tx = b.btc.Tx(2, [b.btc.TxIn(b'\x42' * 32, 3, b'', 0xfffffffd)], [b.btc.TxOut(98000, script)], 0)
    reader = b.btc.Reader(base64.b64decode(t.psbt(tx, 100000, script)))
    assert reader.take(5) == b'psbt\xff'
    def entry():
        key = reader.take(reader.compact())
        return key, reader.take(reader.compact())
    assert entry() == (b'\x00', tx.stripped())
    assert reader.compact() == 0
    assert entry() == (b'\x01', (100000).to_bytes(8, 'little') + b'\x22' + script)
    assert reader.compact() == 0  # end of the input map
    assert reader.compact() == 0  # empty output map
    assert reader.done()
    tx.inputs.append(tx.inputs[0])
    with pytest.raises(ValueError): t.psbt(tx, 100000, script)


@pytest.mark.parametrize('chain,genesis,ibd', [
    ('main', t.TESTNET4_GENESIS, False), ('test', t.TESTNET4_GENESIS, False),
    ('testnet4', '00' * 32, False), ('testnet4', t.TESTNET4_GENESIS, True),
])
def test_public_observer_requires_testnet4_identity_and_sync(chain, genesis, ibd):
    class Stub(t.CoreCLI):
        def __init__(self): pass
        def call(self, method, *args):
            return {'chain': chain, 'initialblockdownload': ibd} if method == 'getblockchaininfo' else genesis
    with pytest.raises(ValueError): Stub().verify_testnet4(True)


def receipt():
    return {'status': 'passed', 'source': t.NOVA_SOURCE, 'proof_sha256': t.NOVA_PROOF,
            'statement_sha256': t.NOVA_STATEMENT, 'binary_sha256': 'ab' * 32,
            'steps': [{'name': name, 'exit_code': 0} for name in ['rustc', 'cargo', 'build', 'transport', 'run']],
            'cases': [{'case': name, 'accepted': name == 'real-nova-proof', 'rejected': name != 'real-nova-proof',
                       'ciphertexts': 785442492, 'input_bits': 8635080}
                      for name in ['real-nova-proof', 'tampered-proof-input', 'wrong-statement']]}


def test_anchor_is_only_a_canonical_receipt_commitment(tmp_path):
    data = receipt()
    file = tmp_path / 'receipt.json'
    file.write_text(json.dumps(data))
    expected = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).digest()
    assert t.nova_anchor(file) == b'BVM3\x01' + expected
    assert t.nova_anchor(None) is None


@pytest.mark.parametrize('mutation', ['incomplete', 'proof', 'statement', 'source', 'binary', 'run', 'accepted-negative', 'dimensions'])
def test_anchor_refuses_incomplete_or_different_verifier_receipts(tmp_path, mutation):
    data = copy.deepcopy(receipt())
    if mutation == 'incomplete': data['status'] = 'running'
    elif mutation in ['proof', 'statement']: data[mutation + '_sha256'] = '00' * 32
    elif mutation == 'source': data['source'] = '00' * 20
    elif mutation == 'binary': del data['binary_sha256']
    elif mutation == 'run': data['steps'][-1]['exit_code'] = 1
    elif mutation == 'accepted-negative': data['cases'][1]['accepted'] = True
    else: data['cases'][2]['ciphertexts'] -= 1
    file = tmp_path / 'receipt.json'
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError): t.nova_anchor(file)


def test_plan_refuses_private_keys_in_source_checkout(tmp_path):
    with pytest.raises(ValueError): t.make_plan(b.ROOT / 'private-test', tmp_path / 'public')
    assert not (tmp_path / 'public').exists()


def test_signing_check_rejects_networked_signer_before_signing():
    class Stub:
        def verify_testnet4(self): return {'blocks': 0}
        def call(self, method, *args):
            assert method == 'getconnectioncount'
            return 1
    with pytest.raises(ValueError): t.signing_check(Stub(), {})


def test_optional_cpu_probe_must_pass_before_anchoring(tmp_path):
    data = receipt()
    data['steps'].append({'name': 'cpu_probe', 'exit_code': 0})
    file = tmp_path / 'receipt.json'
    file.write_text(json.dumps(data))
    assert t.nova_anchor(file) is not None
    data['steps'][-1]['exit_code'] = 1
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError): t.nova_anchor(file)


def test_build_only_receipt_is_never_anchorable(tmp_path):
    data = receipt()
    data['status'] = 'built_not_verified'
    file = tmp_path / 'receipt.json'
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError): t.nova_anchor(file)
