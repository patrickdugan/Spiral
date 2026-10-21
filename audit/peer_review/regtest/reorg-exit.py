"""Orphan the owned exit, expose it unconfirmed, then reconfirm the same tx.

The four observers are paused only while constructing a higher competing tip.
This avoids the pinned server's lower-height startup guard, not its reorg path.
No payment is resent and no new fixture funding is introduced.
"""
import json
import time
from bootstrap import core, docker
from fund import cln, mine
from launch import bark
from attest import DEST, save
from observe import snapshot
from pay import action

OBSERVERS = ['spiral-captaind', 'spiral-watchmand', 'spiral-cln-server', 'spiral-cln-peer']


def wait_height(height):
    for _ in range(60):
        if all(cln(n, 'getinfo')['blockheight'] == height for n in ['server', 'peer']):
            return
        time.sleep(1)
    raise RuntimeError('CLN did not reach replacement tip; inspect existing processes')


def main():
    before = core('getblockchaininfo')
    if before['chain'] != 'regtest' or before['blocks'] != 4445:
        raise RuntimeError('expected captured owned-regtest checkpoint at 4445')
    if (DEST / 'reorg-exit-intent.json').exists():
        raise RuntimeError('reorg already attempted; inspect existing phase, never restart blindly')
    if core('getrawmempool'):
        raise RuntimeError('unrelated mempool activity')
    for name in OBSERVERS:
        state = json.loads(docker('inspect', name).stdout)[0]['State']
        if not state['Running'] or state['Paused']:
            raise RuntimeError(f'observer not running normally: {name}')
    txid = json.loads((DEST / 'action-offboard-18632.json').read_text())['result']['offboard_txid']
    orphan = core('getblockhash', '4443')
    save('reorg-exit-intent.json', {'old_tip': before, 'orphan_root': orphan, 'txid': txid,
        'common_height': 4442, 'replacement_height': 4446, 'final_height': 4449,
        'intervention': 'Pause observers during explicit-empty-block fork construction; resume at a higher tip.',
        'payment_resent': False, 'new_fixture_funding_sat': 0})
    snapshot('reorg-exit-before')
    paused = []
    try:
        for name in OBSERVERS:
            action(f'reorg-pause-{name}', lambda name=name: {'result': docker('pause', name).stdout.strip()})
            paused.append(name)
        action('reorg-invalidate-exit', lambda: {'result': core('invalidateblock', orphan)})
        assert core('getblockcount') == 4442
        assert txid in core('getrawmempool')
        address = core('getnewaddress')
        for height in range(4443, 4447):
            action(f'reorg-empty-block-{height}', lambda: core('generateblock', address, '[]'))
        assert core('getblockcount') == 4446
        assert txid in core('getrawmempool')
        save('reorg-exit-orphaned-headers.json', {
            'old_blocks': [core('getblockheader', h['hash']) for h in json.loads((DEST / 'offboard-source-and-chain.json').read_text())['headers']],
            'replacement_headers': [core('getblockheader', core('getblockhash', str(h))) for h in range(4443, 4447)],
            'core_tip': core('getblockchaininfo'), 'mempool': core('getrawmempool'),
        })
    finally:
        for name in reversed(paused):
            action(f'reorg-unpause-{name}', lambda name=name: {'result': docker('unpause', name).stdout.strip()})
    wait_height(4446)
    action('reorg-client-pending-sync', lambda: json.loads(bark('onchain', 'balance').stdout))
    snapshot('reorg-exit-orphaned')
    assert core('getrawmempool') == [txid]
    action('reorg-reconfirm-exit', lambda: {'height': mine(3)})
    action('reorg-client-confirmed-sync', lambda: json.loads(bark('onchain', 'balance').stdout))
    snapshot('reorg-exit-reconfirmed')
    save('reorg-exit-final-headers.json', {
        'headers': [core('getblockheader', core('getblockhash', str(h))) for h in range(4443, 4450)],
        'old_blocks': [core('getblockheader', h['hash']) for h in json.loads((DEST / 'offboard-source-and-chain.json').read_text())['headers']],
        'tip': core('getblockchaininfo'), 'txid': txid,
    })
    print(json.dumps({'txid': txid, 'tip': core('getblockcount'), 'same_transaction_reconfirmed': True}))


if __name__ == '__main__':
    main()
