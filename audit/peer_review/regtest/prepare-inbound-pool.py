"""Issue exactly one two-leaf pool from existing regtest funds, then disable issuance."""
import hashlib
import time
from bootstrap import RUNTIME, core, docker
from launch import rpc
from fund import mine
from attest import save, DEST
from observe import snapshot
from pay import action


def restart():
    docker('restart', 'spiral-captaind')
    for _ in range(30):
        if rpc('wallet', check=False).returncode == 0:
            return {'ready': True}
        time.sleep(1)
    raise RuntimeError('captain readiness timeout')


def main():
    if core('getblockchaininfo')['chain'] != 'regtest':
        raise RuntimeError('owned regtest required')
    if (DEST / 'inbound-pool-before.json').exists():
        raise RuntimeError('pool preparation previously started; reconcile instead of retry')
    if core('getrawmempool'):
        raise RuntimeError('unrelated pending transaction; refuse ambiguous pool provenance')
    before = snapshot('inbound-pool-before')
    cfg = RUNTIME / 'config/captaind.toml'
    old = cfg.read_text()
    if old.count('vtxo_targets = []') != 1:
        raise RuntimeError('expected disabled pool issuance')
    # Upstream deliberately ignores one-leaf issuance; two 10k leaves suffice.
    new = old.replace('vtxo_targets = []', 'vtxo_targets = [ "10000sat:2" ]')
    save('inbound-pool-config.json', {
        'before_sha256': hashlib.sha256(old.encode()).hexdigest(),
        'temporary_sha256': hashlib.sha256(new.encode()).hexdigest(),
        'target': '10000sat:2', 'external_funding': 0,
        'rule': 'restore disabled pool configuration before mining or receiving',
    })
    cfg.write_text(new)
    try:
        action('inbound-pool-enable', restart)
        for _ in range(30):
            txids = core('getrawmempool')
            if txids:
                if len(txids) != 1:
                    raise RuntimeError('unexpected transaction count; retain evidence')
                save('inbound-pool-broadcast-id.json', {'txid': txids[0], 'height': core('getblockcount')})
                break
            time.sleep(1)
        else:
            raise RuntimeError('pool issuance not observed')
    finally:
        cfg.write_text(old)
        action('inbound-pool-disable', restart)
    snapshot('inbound-pool-broadcast')
    action('inbound-pool-confirm', lambda: {'height': mine(3)})
    snapshot('inbound-pool-confirmed')


if __name__ == '__main__':
    main()
