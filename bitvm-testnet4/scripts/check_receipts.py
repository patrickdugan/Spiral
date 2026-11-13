"""Independently check stock-regtest block, witness, claim and signature receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bitvm_demo import bitcoin as b


def check(path):
    report = json.loads(path.read_text())
    assert report['status'] == 'passed' and report['network'] == 'regtest'
    assert report['peer_count'] == 0 and report['node_exit_codes'] == [0, 0]
    assert report['restart_preserved']
    assert len(report['rejected']) == report['rejected_count'] == 30
    for item in report['rejected'].values():
        assert item['dry_run']['allowed'] is False and item['block_error']
        assert item['height_before'] == item['height_after']
        tx = b.btc.parse_tx(bytes.fromhex(item['raw']))
        assert tx.txid()[::-1].hex() == item['dry_run']['txid']
    for item in [report['replay']['before'], report['replay']['after']]:
        assert item['allowed'] is False and item['reject-reason'] == 'missing-inputs'
    funding = b.btc.parse_tx(bytes.fromhex(report['funding']['raw']))
    assert funding.txid()[::-1].hex() == report['funding']['txid']
    records = [(name, item, False) for name, item in report['accepted'].items()]
    records += [(name, item, True) for name, item in report['refunds'].items()]
    records.sort(key=lambda record: record[1]['height'])
    assert len(report['accepted']) == len(report['refunds']) == 5
    previous = report['funding']['block']
    checked = []
    for name, item, refund in records:
        header, transactions = b.btc.parse_block(bytes.fromhex(item['block_raw']))
        blockhash = b.btc.sha256d(header)
        assert blockhash[::-1].hex() == item['block']
        assert header[4:36][::-1].hex() == previous
        previous = item['block']
        compact = struct.unpack_from('<I', header, 72)[0]
        assert compact & 0x00800000 == 0
        target = (compact & 0x007fffff) << (8 * ((compact >> 24) - 3))
        assert 0 < target <= 0x7fffff << (8 * (0x20 - 3))
        assert int.from_bytes(blockhash, 'little') <= target
        assert b.btc.merkle_root([tx.txid() for tx in transactions]) == header[36:68]
        witness_root = b.btc.merkle_root([b'\x00' * 32] + [b.btc.sha256d(tx.serialize()) for tx in transactions[1:]])
        reserved = transactions[0].inputs[0].witness
        assert len(reserved) == 1 and len(reserved[0]) == 32
        commitment = b'\x6a\x24\xaa\x21\xa9\xed' + b.btc.sha256d(witness_root + reserved[0])
        assert any(out.script_pubkey[:38] == commitment for out in transactions[0].outputs)
        tx = b.btc.parse_tx(bytes.fromhex(item['raw']))
        assert tx.txid()[::-1].hex() == item['txid']
        assert any(candidate.serialize() == tx.serialize() for candidate in transactions)
        assert item['dry_run']['allowed'] is True
        assert len(tx.inputs) == len(tx.outputs) == 1 and tx.outputs[0].value == item['payout_sats'] == 18000
        inp = tx.inputs[0]
        assert inp.prev_txid == funding.txid()
        coin = funding.outputs[inp.prev_vout]
        assert coin.value == 20000
        public = report['circuits'][name]
        assert coin.script_pubkey.hex() == public['script_pubkey']
        witness = inp.witness
        script, control = witness[-2:]
        root = b.reference.tapleaf(script)
        for index in range(33, len(control), 32):
            root = b.reference.tapbranch(root, control[index:index + 32])
        internal = b.ec.parse(b'\x02' + control[1:33])
        tweak = int.from_bytes(b.ec.tagged_hash('TapTweak', control[1:33] + root), 'big')
        assert tweak < b.ec.N
        key = b.ec.add(internal, b.ec.mul(tweak))
        assert coin.script_pubkey == b'\x51\x20' + key[0].to_bytes(32, 'big')
        assert control[0] == 0xc0 | key[1] & 1
        if refund:
            assert script.hex() == public['refund_script'] and len(witness) == 3
            assert tx.version >= 2 and inp.sequence == 2 and item['height'] >= report['funding']['height'] + 2
            public_key = public['refund_pubkey']
        else:
            gate = public['refutation_scripts'].index(script.hex())
            assert len(witness) == 6 and gate in public['bad_gates']
            wires = public['gates'][gate]
            for wire, opening in zip(wires, reversed(witness[1:4])):
                assert hashlib.sha256(opening).hexdigest() == public['commitments'][wire]
            a, bit_b, output = [public['claim'][wire] for wire in wires]
            assert output != 1 - (a & bit_b)
            public_key = public['challenger_pubkey']
        assert b.verify(b.sighash(tx, coin.value, coin.script_pubkey, script), bytes.fromhex(public_key), witness[0])
        checked.append({'case': name, 'height': item['height'], 'block': item['block'], 'refund': refund})
    return {'status': 'passed', 'source_receipt_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'network': 'regtest', 'block_pow_merkle_witness_and_signatures_checked': 10,
            'negative_receipts_checked': 30, 'replay_receipts_checked': 2, 'cases': checked}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.receipt), indent=2))
