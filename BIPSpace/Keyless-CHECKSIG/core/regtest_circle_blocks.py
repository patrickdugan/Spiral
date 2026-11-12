#!/usr/bin/env python3
"""Mine the pinned real Circle-STARK chain in an isolated research Core daemon.

The proof was produced by STWO in an earlier recorded run. This test checks
its exact artifact digest, rebinds only funding outpoints, and submits real
blocks to Core. It preserves every compiled verifier and proof-stage hint.
All coins are regtest coinbase funds. No public-network connections or keys.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal

CORE_REV = 'd0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3'
VECTOR_SHA256 = '3d56ce8d29a2576142148f3733b29e398ad6794d74f07183d9e055ce309fbfd0'
PROOF_RUN = 43168685081
START_VALUE = 10_000_000
STAGES = 72
FEE = 10_000
COIN = 100_000_000


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


class RpcError(RuntimeError):
    pass


class Node:
    def __init__(self, binary: Path, datadir: Path):
        self.binary = binary.resolve()
        self.datadir = datadir.resolve()
        self.datadir.mkdir(parents=True, exist_ok=True)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            self.port = s.getsockname()[1]
        self.password = os.urandom(24).hex()
        self.process = None
        self.console = None

    def rpc(self, method: str, *params):
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': list(params)}).encode()
        auth = base64.b64encode(('keyless:' + self.password).encode()).decode()
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}/', body,
            {'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth})
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            obj = json.loads(response.read(), parse_float=Decimal)
        if obj.get('error') is not None:
            raise RpcError(json.dumps(obj['error']))
        return obj['result']

    def start(self, reindex: bool = False) -> None:
        require(self.process is None, 'Daemon already started')
        self.console = (self.datadir / 'console.log').open('ab')
        args = [str(self.binary), '-regtest', '-server=1', '-listen=0', '-dnsseed=0',
                '-discover=0', '-connect=0', '-networkactive=0', '-persistmempool=0',
                '-acceptnonstdtxn=1', '-assumevalid=0', '-checkblocks=0', '-checklevel=4',
                '-par=2', '-dbcache=128', '-debug=validation', '-debug=mempool',
                '-rpcbind=127.0.0.1', '-rpcallowip=127.0.0.1', '-rpcuser=keyless',
                '-rpcpassword=' + self.password, '-rpcport=' + str(self.port),
                '-datadir=' + str(self.datadir)]
        if reindex:
            args.append('-reindex-chainstate=1')
        self.process = subprocess.Popen(args, stdout=self.console, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError((self.datadir / 'console.log').read_text(errors='replace')[-6000:])
            try:
                self.rpc('getblockchaininfo')
                require(self.rpc('getconnectioncount') == 0, 'Unexpected peer connection')
                require(self.rpc('getnetworkinfo')['networkactive'] is False, 'Networking must stay disabled')
                return
            except (OSError, urllib.error.URLError, RpcError):
                time.sleep(0.1)
        raise TimeoutError('Research Core did not finish RPC startup')

    def stop(self) -> None:
        if self.process is None:
            return
        try:
            self.rpc('stop')
        except (OSError, urllib.error.URLError, RpcError):
            pass
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None
        if self.console:
            self.console.close()
            self.console = None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', required=True, type=Path)
    parser.add_argument('--bitcoind', required=True, type=Path)
    parser.add_argument('--vectors', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(['git', '-C', str(args.core), 'rev-parse', 'HEAD'], text=True).strip()
    require(revision == CORE_REV, 'Wrong Core source revision')
    raw_vectors = args.vectors.read_bytes()
    require(hashlib.sha256(raw_vectors).hexdigest() == VECTOR_SHA256, 'Unrecognized real-proof artifact')
    vectors = json.loads(raw_vectors)
    by_name = {row['name']: row for row in vectors}
    require(len(by_name) == len(vectors) == 223, 'Unexpected proof vector catalogue')
    originals = [by_name[f'circle-chain-stage-{i:03}'] for i in range(STAGES)]
    require(all(row['expected'] for row in originals), 'Unexpected positive vector label')
    root_script = bytes.fromhex(originals[0]['spent_script'])
    control_good = by_name['binding-control-terminal']
    control_bad = by_name['binding-control-wrong-old-state-fresh-witness']
    require(control_good['spent_script'] == control_bad['spent_script'], 'Control must attack the same funded script')

    sys.path.insert(0, str(args.core / 'test/functional'))
    from test_framework.messages import CTransaction, CTxIn, CTxOut, COutPoint
    from test_framework.blocktools import create_block, create_coinbase, add_witness_commitment
    from test_framework.script import CScript, OP_TRUE

    def parse_tx(row):
        source = io.BytesIO(bytes.fromhex(row['tx_hex']))
        tx = CTransaction()
        tx.deserialize(source)
        require(not source.read(), 'Trailing transaction bytes')
        require(len(tx.vin) == len(tx.vout) == 1, 'Unexpected staged transaction shape')
        require(tx.vin[0].scriptSig == b'', 'Unexpected authorization scriptSig')
        return tx

    def rebind(row, parent: str, index: int = 0):
        tx = parse_tx(row)
        stack = tx.wit.vtxinwit[0].scriptWitness.stack
        require(len(stack) >= 3, 'Missing script witness')
        require(stack[-3] == hashlib.sha256(tx.vin[0].prevout.serialize()).digest(), 'Unexpected TXCOMMIT witness position')
        tx.vin[0].prevout = COutPoint(int(parent, 16), index)
        stack[-3] = hashlib.sha256(tx.vin[0].prevout.serialize()).digest()
        # Script/control and every original proof hint remain byte-for-byte.
        original = parse_tx(row).wit.vtxinwit[0].scriptWitness.stack
        require(stack[:-3] == original[:-3] and stack[-2:] == original[-2:], 'Proof or verifier changed during rebinding')
        return tx

    def make_chain(parent, recipient=0, mutation=None):
        result = []
        for i, good in enumerate(originals):
            row = good
            if recipient and i == STAGES - 1:
                row = by_name[good['name'] + '-other-recipient']
            if mutation is not None and i == mutation[0]:
                row = by_name[good['name'] + '-' + mutation[1]]
            tx = rebind(row, parent)
            result.append(tx)
            parent = tx.txid_hex
        return result

    report = {'format': 'keyless-circle-regtest-blocks-v1', 'status': 'running',
              'core_revision': CORE_REV, 'source_proof_run': PROOF_RUN,
              'source_vectors_sha256': VECTOR_SHA256, 'real_circle_stages': STAGES,
              'scope': 'Actual regtest block validation with compile-time opt-in CAT/TXCOMMIT/restricted-P2MR. Pinned eight-query Fibonacci STARK, not an IOB circuit or a Nova verifier inside Script.',
              'public_network_active': False, 'reserve_signatures_created': 0,
              'rejections': [], 'accepted_blocks': []}
    node = Node(args.bitcoind, args.output / 'node')
    try:
        node.start()
        descriptor = node.rpc('getdescriptorinfo', 'raw(51)')['descriptor']
        initial = node.rpc('generatetodescriptor', 101, descriptor)
        coinbase = node.rpc('getblock', initial[0], 2)['tx'][0]
        coinbase_value = int(coinbase['vout'][0]['value'] * COIN)
        control_value = control_good['spent_value']
        funding = CTransaction()
        funding.vin = [CTxIn(COutPoint(int(coinbase['txid'], 16), 0), b'', 0xffffffff)]
        funding.vout = [CTxOut(START_VALUE, root_script),
                        CTxOut(control_value, bytes.fromhex(control_good['spent_script'])),
                        CTxOut(coinbase_value - START_VALUE - control_value - 1000, CScript([OP_TRUE]))]
        fund_block = node.rpc('generateblock', descriptor, [funding.serialize().hex()])['hash']
        require(node.rpc('gettxout', funding.txid_hex, 0)['scriptPubKey']['hex'] == root_script.hex(), 'Vault funding failed')
        chain_a = make_chain(funding.txid_hex)
        chain_b = make_chain(funding.txid_hex, recipient=1)
        require(sum(t.get_weight() for t in chain_a) == 3_437_720, 'Unexpected real-chain weight')
        require(all(a.serialize() == b.serialize() for a, b in zip(chain_a[:-1], chain_b[:-1])), 'Recipient choice changed preceding proof transitions')
        honest_control = rebind(control_good, funding.txid_hex, 1)
        forged_control = rebind(control_bad, funding.txid_hex, 1)
        report['funding_txid'] = funding.txid_hex
        report['funding_block'] = fund_block
        report['root_script'] = root_script.hex()
        report['stage_transaction_weight'] = sum(t.get_weight() for t in chain_a)
        report['fee_per_stage_sats'] = FEE
        report['total_stage_fee_sats'] = STAGES * FEE
        report['terminal_value_sats'] = chain_a[-1].vout[0].nValue
        report['mempool_probe'] = node.rpc('testmempoolaccept', [chain_a[0].serialize().hex()], 0)
        (args.output / 'funding-transaction.hex').write_text(funding.serialize().hex() + '\n')

        def assemble(txs, fees, label):
            tip = node.rpc('getblockheader', node.rpc('getbestblockhash'))
            cb = create_coinbase(tip['height'] + 1, fees=fees)
            cb.vin[0].scriptSig += CScript([label.encode()[:40]])
            block = create_block(int(tip['hash'], 16), cb, tip['time'] + 1, txlist=txs)
            add_witness_commitment(block)
            block.solve()
            return block

        def reject(txs, fees, label):
            before = node.rpc('getbestblockhash')
            block = assemble(txs, fees, label)
            require(block.get_weight() < 4_000_000, 'Attack unexpectedly rejected by size alone')
            start = time.monotonic()
            reason = node.rpc('submitblock', block.serialize().hex())
            require(isinstance(reason, str) and bool(reason), f'Invalid block accepted: {label}')
            require(node.rpc('getbestblockhash') == before, 'Rejected block changed active tip')
            report['rejections'].append({'name': label, 'reason': reason,
                'seconds': time.monotonic() - start, 'weight': block.get_weight()})
            print('REJECTED', label, reason, flush=True)

        def accept(txs, fees, label, save=False):
            block = assemble(txs, fees, label)
            require(block.get_weight() <= 4_000_000, 'Valid test block exceeds consensus weight')
            start = time.monotonic()
            answer = node.rpc('submitblock', block.serialize().hex())
            require(answer is None, f'Valid block refused: {label}: {answer}')
            require(node.rpc('getbestblockhash') == block.hash_hex, 'Block did not become active')
            decoded = node.rpc('getblock', block.hash_hex)
            require(decoded['weight'] == block.get_weight(), 'Core and Python block weight disagree')
            report['accepted_blocks'].append({'name': label, 'hash': block.hash_hex,
                'height': decoded['height'], 'weight': decoded['weight'], 'transactions': decoded['nTx'],
                'seconds': time.monotonic() - start})
            if save:
                (args.output / (label + '.blockhex')).write_text(block.serialize().hex() + '\n')
            print('ACCEPTED', label, decoded['weight'], block.hash_hex, flush=True)
            return block.hash_hex

        for stage in (0, 35, 71):
            for kind in ('wrong-value', 'wrong-successor'):
                altered = make_chain(funding.txid_hex, mutation=(stage, kind))
                # Descendants are relinked so a missing input cannot mask the attack.
                for previous, current in zip(altered, altered[1:]):
                    require(current.vin[0].prevout.hash == previous.txid_int, 'Broken adversarial lineage')
                fees = START_VALUE - altered[-1].vout[0].nValue
                reject(altered, fees, f'stage-{stage:03}-{kind}')
        reject([forged_control], control_value - forged_control.vout[0].nValue, 'fresh-witness-wrong-old-state')
        jump = rebind(originals[-1], funding.txid_hex)
        reject([jump], START_VALUE - jump.vout[0].nValue, 'jump-directly-to-terminal')
        require(node.rpc('gettxout', funding.txid_hex, 0) is not None, 'Invalid block spent reserve')

        full = accept(chain_a + [honest_control], STAGES * FEE + FEE, 'full-proof-one-block', save=True)
        for tx in chain_a[:-1]:
            require(node.rpc('gettxout', tx.txid_hex, 0, False) is None, 'Intermediate state remains unspent')
        terminal = node.rpc('gettxout', chain_a[-1].txid_hex, 0, False)
        require(terminal is not None and int(terminal['value'] * COIN) == 9_280_000, 'Wrong terminal payout')
        require(node.rpc('gettxout', funding.txid_hex, 0, False) is None, 'Vault remains unspent')
        require(node.rpc('verifychain', 4, 0) is True, 'Full block verification failed')
        report['all_stages_in_one_mined_block'] = True

        # Undo the settlement and check the authenticated reserve is restored.
        node.rpc('invalidateblock', full)
        require(node.rpc('getbestblockhash') == fund_block, 'Reorg did not restore funding tip')
        require(node.rpc('gettxout', funding.txid_hex, 0, False) is not None, 'Reorg did not restore reserve')
        require(node.rpc('gettxout', chain_a[-1].txid_hex, 0, False) is None, 'Orphan payout remains in UTXO set')
        report['whole_block_reorg_restores_reserve'] = True

        split_blocks = []
        for chunk in range(3):
            txs = chain_a[24 * chunk:24 * (chunk + 1)]
            split_blocks.append(accept(txs, 24 * FEE, f'proof-chunk-{chunk}'))
            live = node.rpc('gettxout', txs[-1].txid_hex, 0, False)
            require(live is not None and live['scriptPubKey']['hex'] == bytes(txs[-1].vout[0].scriptPubKey).hex(), 'Wrong live stage output')
        report['verification_across_three_blocks'] = True

        # Same funded policy, another allowed destination after a partial reorg.
        node.rpc('invalidateblock', split_blocks[-1])
        require(node.rpc('getbestblockhash') == split_blocks[-2], 'Partial reorg failed')
        require(node.rpc('gettxout', chain_a[47].txid_hex, 0, False) is not None, 'Intermediate state was not restored')
        last_b = accept(chain_b[48:], 24 * FEE, 'alternate-recipient-final-chunk', save=True)
        require(node.rpc('gettxout', chain_a[-1].txid_hex, 0, False) is None, 'Both recipients have an active payout')
        paid_b = node.rpc('gettxout', chain_b[-1].txid_hex, 0, False)
        require(paid_b is not None and int(paid_b['value'] * COIN) == 9_280_000, 'Alternate payout is missing')
        report['partial_reorg_and_alternate_recipient'] = True
        report['terminal_txid'] = chain_b[-1].txid_hex
        report['terminal_script'] = bytes(chain_b[-1].vout[0].scriptPubKey).hex()
        require(node.rpc('verifychain', 4, 0) is True, 'Reorg chain verification failed')

        # Rebuild the chainstate from persisted blocks with the same research rules.
        node.stop()
        node.start(reindex=True)
        require(node.rpc('getbestblockhash') == last_b, 'Reindex selected a different active chain')
        paid_b = node.rpc('gettxout', chain_b[-1].txid_hex, 0, False)
        require(paid_b is not None and int(paid_b['value'] * COIN) == 9_280_000, 'Reindex lost the terminal payout')
        require(node.rpc('verifychain', 4, 0) is True, 'Historical replay verification failed')
        report['reindex_chainstate_verified'] = True
        report['status'] = 'success'
        report['final_height'] = node.rpc('getblockcount')
        report['final_block'] = last_b
    except Exception as error:
        report['status'] = 'failure'
        report['error'] = repr(error)
        raise
    finally:
        node.stop()
        report['github_run_id'] = os.environ.get('GITHUB_RUN_ID')
        report['spiral_revision'] = os.environ.get('GITHUB_SHA')
        (args.output / 'results.json').write_text(json.dumps(report, indent=2, default=str) + '\n')
        print(json.dumps(report, indent=2, default=str), flush=True)


if __name__ == '__main__':
    main()
