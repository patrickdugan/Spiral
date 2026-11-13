"""Verify the real M16 order, then fund and adversarially spend its Keyless reserve."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from iob import btc, desk, keyless, menu, statement
from iob.errors import Refusal
from iob.ledger import Ledger
from iob.rpc import RPC


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    require(sha(args.binary) == args.binary_sha256, 'node binary digest mismatch')
    require(sha(args.gate) == args.gate_sha256, 'gate binary digest mismatch')
    require(sha(args.proof) == args.proof_sha256, 'proof digest mismatch')
    source = args.bitcoin_rs_source.resolve()
    spec = importlib.util.spec_from_file_location('iob_node_fixture', source / 'scripts/research/keyless_checksig_rpc.py')
    f = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = f
    spec.loader.exec_module(f)
    base_menu = menu.load(str(ROOT / 'menus/m16-mainnet-replay.json'))
    m = replace(base_menu, gate_argv=(str(args.gate.resolve()),), gate_paths='native')
    fixtures = ROOT / 'fixtures/m16-mainnet'
    order = desk.Order((fixtures / 'statement.bin').read_bytes(), (fixtures / 'payment-tx.hex').read_text().strip(),
                       json.loads((fixtures / 'sender-proof.json').read_text()), str(args.proof.resolve()))
    report = {'status': 'running', 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'command': sys.argv, 'binary_sha256': args.binary_sha256, 'binary_source': args.binary_source,
              'gate_sha256': args.gate_sha256, 'proof_sha256': args.proof_sha256,
              'script_sha256': sha(Path(__file__)), 'helper_sha256': sha(Path(f.__file__)),
              'bitcoin_rs_checkout': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
              'spiral_source': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
              'spiral_dirty': subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True),
              'network': 'regtest', 'genesis': keyless.REGTEST_GENESIS,
              'scope': 'Real host M16 verification followed by a funded fixed-approval Keyless payout; no on-chain M14 verifier or trustless refill claim',
              'proof_rejections': {}, 'consensus_rejections': {}, 'positive_controls': {}}
    directory = tempfile.TemporaryDirectory(prefix='iob-keyless-regtest-')
    node = f.Node(args.binary.resolve(), Path(directory.name))
    try:
        approval = keyless.prepare(m, order, Ledger(None))
        require(approval.payout_sats == 948400, 'real order price differs')
        require(approval.recipient_script.hex() == '00144c62077e87ad3a902547c965968d924f64b421e8', 'derived recipient differs')
        report['approval'] = approval.record()
        def refused(name, changed_order=order, changed_menu=m, ledger=None, expected=None):
            try:
                keyless.prepare(changed_menu, changed_order, ledger or Ledger(None))
            except Refusal as error:
                require(error.reason == expected, name + ': ' + error.reason)
                report['proof_rejections'][name] = {'reason': error.reason, 'detail': error.detail}
            else:
                raise ValueError(name + ' produced a reserve')
        refused('proof_required', replace(order, proof_path=None), expected='proof_required')
        changed = bytearray(args.proof.read_bytes())
        changed[len(changed) // 2] ^= 1
        invalid = args.output / 'corrupted-proof.bin'
        invalid.write_bytes(changed)
        refused('corrupted_proof', replace(order, proof_path=str(invalid)), expected='proof_rejected')
        short = args.output / 'truncated-proof.bin'
        short.write_bytes(args.proof.read_bytes()[:-1])
        refused('truncated_proof', replace(order, proof_path=str(short)), expected='proof_malformed')
        changed_statement = bytearray(order.statement)
        require(changed_statement[1164:1168] == b'PAY1', 'M16 statement layout differs')
        changed_statement[1248:1256] = (1880000).to_bytes(8, 'little')
        refused('changed_statement', replace(order, statement=bytes(changed_statement)), expected='statement_digest_mismatch')
        changed_tx = bytearray.fromhex(order.tx_hex)
        changed_tx[-40] ^= 1
        refused('changed_sender_witness', replace(order, tx_hex=changed_tx.hex()), expected='sender_proof_witness')
        refused('chainwork_floor', changed_menu=replace(m, min_tip_chainwork=statement.parse(order.statement).tip.chainwork + 1),
                expected='chainwork_below_floor')
        refused('confirmations', changed_menu=replace(m, min_confirmations=7), expected='too_few_confirmations')
        for network in ['mainnet', 'testnet4', 'signet']:
            refused('payout_network_' + network, changed_menu=replace(m, out_network=network), expected='keyless_needs_regtest')
        require(node.start()['blocks'] == 0, 'fresh chain required')
        require(node.rpc('getblockhash', [0]) == keyless.REGTEST_GENESIS, 'wrong genesis')
        require(node.rpc('getconnectioncount') == 0, 'public peer present')
        base = f.Leaf(b'\x51')
        spk, control = base.output()
        address = f.address(spk[2:])
        blocks = node.rpc('generatetoaddress', [101, address])
        coinbase = node.rpc('getblock', [blocks[0], 2])['tx'][0]
        coin = next(v for v in coinbase['vout'] if v['scriptPubKey']['hex'] == spk.hex())
        value = f.satoshis(coin['value'])
        reserve_spk, _ = approval.taproot()
        funding = f.Tx((f.Input(bytes.fromhex(coinbase['txid'])[::-1], coin['n'], value, spk),),
                       (f.Output(approval.reserve_sats, reserve_spk), f.Output(approval.reserve_sats, reserve_spk),
                        f.Output(value - 2 * approval.reserve_sats - 2000, spk)))
        funding_raw, funding_id = funding.serialize([[base.script, control]])
        require(node.rpc('sendrawtransaction', [funding_raw]) == funding_id, 'funding txid differs')
        funding_block = node.rpc('generatetoaddress', [1, address])[0]
        require(funding_id in node.rpc('getblock', [funding_block])['tx'], 'funding not confirmed')
        report['funding'] = {'txid': funding_id, 'raw': funding_raw, 'block': funding_block, 'height': 102,
                             'reserve_sats': approval.reserve_sats}
        original = approval.spend(funding_id, 0)
        def clone():
            return btc.parse_tx(original.serialize())
        def reject(name, tx):
            raw = tx.serialize().hex()
            admission = node.rpc('testmempoolaccept', [[raw]])[0]
            require(admission['allowed'] is False, name + ' passed mempool')
            before = node.rpc('getblockcount')
            try:
                node.rpc('generateblock', [address, [raw]])
            except f.RpcError as error:
                require('script' in str(error.error).lower(), name + ' failed outside Script')
                block_error = error.error
            else:
                raise ValueError(name + ' entered a block')
            require(node.rpc('getblockcount') == before, name + ' changed height')
            report['consensus_rejections'][name] = {'raw': raw, 'dry_run': admission,
                                                     'block_error': block_error, 'height_before': before,
                                                     'height_after': node.rpc('getblockcount')}
        for name, mutate in [
            ('recipient', lambda tx: setattr(tx.outputs[0], 'script_pubkey', b'\x51\x20' + f.RECIPIENTS[0])),
            ('amount_lower', lambda tx: setattr(tx.outputs[0], 'value', approval.payout_sats - 1)),
            ('amount_higher', lambda tx: setattr(tx.outputs[0], 'value', approval.payout_sats + 1)),
            ('link_removed', lambda tx: tx.outputs.pop()),
            ('link_changed', lambda tx: setattr(tx.outputs[1], 'script_pubkey', tx.outputs[1].script_pubkey[:-1] + b'\x01')),
            ('extra_output', lambda tx: tx.outputs.append(btc.TxOut(0, b'\x6a'))),
            ('output_order', lambda tx: tx.outputs.reverse()),
            ('version_recommitted', lambda tx: setattr(tx, 'version', 1)),
            ('locktime_recommitted', lambda tx: setattr(tx, 'locktime', 1)),
            ('sequence_recommitted', lambda tx: setattr(tx.inputs[0], 'sequence', 0xfffffffe)),
        ]:
            tx = clone()
            mutate(tx)
            tx.inputs[0].witness = approval.witness(tx)
            reject(name, tx)
        tx = clone()
        script = bytearray(tx.inputs[0].witness[-2])
        script[1] ^= 1
        tx.inputs[0].witness[-2] = bytes(script)
        reject('approval_context_changed', tx)
        tx = clone()
        tx.inputs[0].witness.append(b'\x50' + approval.context)
        reject('unexpected_annex', tx)
        for name, index in [('prevouts_width', 0), ('spent_scripts_width', 1), ('extension_width', 2)]:
            tx = clone()
            tx.inputs[0].witness[index] += b'\x00'
            reject(name, tx)
        extra = f.Input(bytes.fromhex(funding_id)[::-1], 2, value - 2 * approval.reserve_sats - 2000, spk)
        two = f.Tx((f.Input(bytes.fromhex(funding_id)[::-1], 0, approval.reserve_sats, reserve_spk), extra),
                   tuple(f.Output(o.value, o.script_pubkey) for o in original.outputs))
        msg = f.sigmsg(two, 0, leaf=f.tapleaf(approval.script))
        first_stack = [msg[10:42], msg[74:106], msg[175:], approval.script, approval.taproot()[1]]
        two_raw, _ = two.serialize([first_stack, [base.script, control]])
        reject('second_input_recommitted', btc.parse_tx(bytes.fromhex(two_raw)))
        admission = node.rpc('testmempoolaccept', [[original.serialize().hex()]])[0]
        report['positive_controls']['approved_payout'] = admission
        require(admission['allowed'] is True, 'approved payout rejected')
        ledger_path = args.output / 'served.jsonl'
        rpc = RPC(f'http://127.0.0.1:{node.rpc_port}', user='research', password=node.password)
        payer = keyless.KeylessPayer(rpc, approval, funding_id, 0, True)
        served = desk.serve(m, order, Ledger(str(ledger_path)), payer)
        require(served['status'] == 'served' and served['proof'] == 'verified', 'verified order not served')
        payout_id = served['payout']['txid']
        block = node.rpc('generatetoaddress', [1, address])[0]
        require(payout_id in node.rpc('getblock', [block])['tx'], 'payout not confirmed')
        paid = node.rpc('gettxout', [payout_id, 0])
        require(paid['scriptPubKey']['hex'] == approval.recipient_script.hex(), 'confirmed recipient differs')
        require(f.satoshis(paid['value']) == 948400, 'confirmed amount differs')
        replay = desk.serve(m, order, Ledger(str(ledger_path)), payer)
        require(replay['reason'] == 'already_served', 'journal replay accepted')
        raw = original.serialize().hex()
        require(node.rpc('testmempoolaccept', [[raw]])[0]['allowed'] is False, 'spent reserve replay accepted')
        height = node.rpc('getblockcount')
        node.stop()
        require(node.start()['blocks'] == height, 'restart lost height')
        require(node.rpc('gettxout', [funding_id, 0]) is None, 'restart restored spent reserve')
        require(node.rpc('gettxout', [funding_id, 1]) is not None, 'restart lost unused reserve')
        require(f.satoshis(node.rpc('gettxout', [payout_id, 0])['value']) == 948400, 'restart lost payout')
        require(desk.serve(m, order, Ledger(str(ledger_path)), payer)['reason'] == 'already_served', 'restart lost served order')
        require(node.rpc('testmempoolaccept', [[raw]])[0]['allowed'] is False, 'restart accepted spent input')
        report.update(status='passed', served=served, payout_block=block, payout_txid=payout_id,
                      payout_sats=948400, final_height=height, restart_preserved=True,
                      peer_count=node.rpc('getconnectioncount'), proof_rejection_count=len(report['proof_rejections']),
                      consensus_rejection_count=len(report['consensus_rejections']))
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
                report.update(status='failed', shutdown_error='two clean node exits required')
            shutil.copyfile(Path(directory.name) / 'node.log', args.output / 'node.log')
            report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            directory.cleanup()
    require(node.exit_codes == [0, 0], 'two clean node exits required')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['bitcoin-rs-source', 'binary', 'gate', 'proof', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ['binary-sha256', 'binary-source', 'gate-sha256', 'proof-sha256']:
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({key: result[key] for key in ['status', 'payout_sats', 'proof_rejection_count',
                                                 'consensus_rejection_count', 'restart_preserved', 'peer_count', 'node_exit_codes']}, indent=2))


if __name__ == '__main__':
    main()
