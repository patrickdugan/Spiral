"""Mine stock-Core BitVM gate demos and adversarial cases with zero peers."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bitvm_demo import bitcoin as b
from bitvm_demo.circuits import Circuit


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def require(value, message):
    if not value:
        raise ValueError(message)


def run(args):
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    f = load('bitvm_core_fixture', args.fixture_source / 'scripts/research/keyless_checksig_rpc.py')
    infrastructure = load('bitvm_stock_fixture', args.fixture_source / 'scripts/research/keyless_checksig_adversarial.py')
    directory = tempfile.TemporaryDirectory(prefix='stock-bitvm-gates-')
    node = infrastructure.core_class(f)(args.core.resolve(), Path(directory.name))
    report = {'status': 'running', 'scope': 'Stock-opcode fixed-claim gate refutation, not a full BitVM bridge',
              'network': 'regtest', 'started_at': datetime.now(timezone.utc).isoformat(), 'command': sys.argv,
              'core_sha256': hashlib.sha256(args.core.read_bytes()).hexdigest(),
              'code_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(ROOT.rglob('*.py')) if '__pycache__' not in p.parts},
              'rejected': {}, 'accepted': {}, 'refunds': {}}
    try:
        require(node.start()['chain'] == 'regtest', 'not regtest')
        require(node.rpc('getblockhash', [0]) == b.REGTEST_GENESIS, 'wrong genesis')
        require(node.rpc('getblockcount') == 0 and node.rpc('getconnectioncount') == 0, 'fresh isolated chain required')
        base = f.Leaf(b'\x51')
        base_spk, base_control = base.output()
        address = f.address(base_spk[2:])
        blocks = node.rpc('generatetoaddress', [101, address])
        coinbase = node.rpc('getblock', [blocks[0], 2])['tx'][0]
        coin = next(v for v in coinbase['vout'] if v['scriptPubKey']['hex'] == base_spk.hex())
        cases = []
        for malicious in [True, False]:
            for a, bit_b in [(0, 0), (0, 1), (1, 0), (1, 1)]:
                cases.append((f'nand-{a}{bit_b}-' + ('false' if malicious else 'true'), Circuit.create('nand', malicious, a, bit_b)))
        cases += [('half-adder-false', Circuit.create('half-adder', True)),
                  ('half-adder-true', Circuit.create('half-adder', False))]
        amount = 20000
        coin_value = f.satoshis(coin['value'])
        funding = f.Tx((f.Input(bytes.fromhex(coinbase['txid'])[::-1], coin['n'], coin_value, base_spk),),
                       tuple(f.Output(amount, c.taproot().script_pubkey) for _, c in cases) +
                       (f.Output(coin_value - amount * len(cases) - 2000, base_spk),))
        raw, funding_id = funding.serialize([[base.script, base_control]])
        require(node.rpc('sendrawtransaction', [raw]) == funding_id, 'funding txid differs')
        funding_block = node.rpc('generatetoaddress', [1, address])[0]
        report['funding'] = {'txid': funding_id, 'raw': raw, 'block': funding_block, 'height': 102, 'collateral_sats': amount}
        report['circuits'] = {name: c.public('regtest') for name, c in cases}
        def reject(name, tx, script=True):
            serialized = tx.serialize().hex()
            dry = node.rpc('testmempoolaccept', [[serialized]])[0]
            require(dry['allowed'] is False, name + ' accepted by mempool')
            before = node.rpc('getblockcount')
            try:
                node.rpc('generateblock', [address, [serialized]])
            except f.RpcError as error:
                if script:
                    require('script' in str(error.error).lower(), name + ' failed outside Script')
                block_error = error.error
            else:
                raise ValueError(name + ' accepted in a block')
            require(node.rpc('getblockcount') == before, name + ' advanced height')
            report['rejected'][name] = {'raw': serialized, 'dry_run': dry, 'block_error': block_error,
                                        'height_before': before, 'height_after': node.rpc('getblockcount')}
        def accept(name, tx, group):
            serialized = tx.serialize().hex()
            dry = node.rpc('testmempoolaccept', [[serialized]])[0]
            require(dry['allowed'] is True, name + ' rejected by mempool: ' + str(dry))
            block = node.rpc('generateblock', [address, [serialized]])['hash']
            txid = tx.txid()[::-1].hex()
            require(txid in node.rpc('getblock', [block])['tx'], name + ' absent from block')
            require(f.satoshis(node.rpc('gettxout', [txid, 0])['value']) == amount - 2000, name + ' output value differs')
            group[name] = {'raw': serialized, 'dry_run': dry, 'block': block,
                           'block_raw': node.rpc('getblock', [block, 0]), 'txid': txid,
                           'height': node.rpc('getblockcount'), 'payout_sats': amount - 2000}
        for index, (name, circuit) in enumerate(cases):
            if not circuit.bad_gates():
                early = circuit.spend(funding_id, index, amount, base_spk, refund=True)
                reject(name + '-early-refund', early, script=False)
                wrong_version = b.btc.parse_tx(early.serialize())
                wrong_version.version = 1
                wrong_version.inputs[0].witness[0] = b.sign(b.sighash(wrong_version, amount, circuit.taproot().script_pubkey,
                                                                    circuit.refund_script), circuit.refund)
                reject(name + '-refund-version-one', wrong_version)
            for gate in range(len(circuit.gates)):
                if gate not in circuit.bad_gates():
                    reject(name + f'-honest-gate-{gate}', circuit.spend(funding_id, index, amount, base_spk, gate=gate))
        bad = cases[0][1]
        original = bad.spend(funding_id, 0, amount, base_spk, gate=0)
        def copy():
            return b.btc.parse_tx(original.serialize())
        tx = copy()
        tx.inputs[0].witness[1] = bytes([tx.inputs[0].witness[1][0] ^ 1]) + tx.inputs[0].witness[1][1:]
        reject('changed-wire-opening', tx)
        tx = copy()
        tx.outputs[0].value -= 1
        reject('changed-output-with-stale-signature', tx)
        tx = copy()
        tx.inputs[0].witness[0] = b.sign(b.sighash(tx, amount, bad.taproot().script_pubkey, bad.refutation_script(0)), bad.refund)
        reject('wrong-party-signature', tx)
        tx = copy()
        tx.inputs[0].witness[-1] = tx.inputs[0].witness[-1][:-1] + bytes([tx.inputs[0].witness[-1][-1] ^ 1])
        reject('changed-taproot-path', tx)
        tx = copy()
        tx.inputs[0].witness.insert(0, b'\x01')
        reject('extra-stack-element', tx)
        tx = copy()
        tx.inputs[0].witness[0] = b.sign(b.sighash(tx, amount + 1, bad.taproot().script_pubkey, bad.refutation_script(0)), bad.challenger)
        reject('wrong-spent-amount-signature', tx)
        tx = copy()
        tx.inputs[0].witness.append(b'\x50' + b'context-change')
        reject('unexpected-annex-with-stale-signature', tx)
        for index, (name, circuit) in enumerate(cases):
            bad_gates = circuit.bad_gates()
            if bad_gates:
                accept(name, circuit.spend(funding_id, index, amount, base_spk, gate=bad_gates[0]), report['accepted'])
        for index, (name, circuit) in enumerate(cases):
            if not circuit.bad_gates():
                accept(name, circuit.spend(funding_id, index, amount, base_spk, refund=True), report['refunds'])
        replay = bad.spend(funding_id, 0, amount, base_spk, gate=0, fee_sats=2001).serialize().hex()
        before = node.rpc('testmempoolaccept', [[replay]])[0]
        require(before['allowed'] is False, 'spent input replay accepted')
        height = node.rpc('getblockcount')
        node.stop()
        require(node.start()['blocks'] == height, 'restart lost height')
        after = node.rpc('testmempoolaccept', [[replay]])[0]
        require(after['allowed'] is False, 'restart restored spent input')
        for index in range(len(cases)):
            require(node.rpc('gettxout', [funding_id, index]) is None, 'restart restored spent collateral')
        report.update(status='passed', final_height=height, rejected_count=len(report['rejected']),
                      accepted_refutations=len(report['accepted']), accepted_refunds=len(report['refunds']),
                      replay={'before': before, 'after': after, 'raw': replay},
                      restart_preserved=True, peer_count=node.rpc('getconnectioncount'))
        require(report['peer_count'] == 0, 'unexpected peer')
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        try:
            node.stop()
        except BaseException as error:
            report.update(status='failed', shutdown_error=f'{type(error).__name__}: {error}')
            raise
        finally:
            node.log.close()
            report['node_exit_codes'] = node.exit_codes
            if report['status'] == 'passed' and node.exit_codes != [0, 0]:
                report.update(status='failed', shutdown_error='two clean exits required')
            shutil.copyfile(Path(directory.name) / 'node.log', args.output / 'node.log')
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            directory.cleanup()
    require(report['status'] == 'passed', 'regtest campaign did not pass')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--fixture-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args())
    print(json.dumps({key: result[key] for key in ['status', 'rejected_count', 'accepted_refutations', 'accepted_refunds',
                                                  'restart_preserved', 'peer_count', 'node_exit_codes']}, indent=2))


if __name__ == '__main__':
    main()
