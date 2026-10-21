"""Remove unrelated free reserve from the server wallet before original expiry.
Funds stay in an owned quarantine address; they are not new funding or revenue.
"""
from bootstrap import core, docker
from launch import captain, rpc
from fund import mine
from observe import snapshot
from pay import action
from attest import save
import json
import time

mine(3)
snapshot('pool-sweep-confirmed')
address = core('getnewaddress', 'operator-quarantine')
save('quarantine-address.json', {'address': address, 'owner': 'operator', 'location': 'quarantine', 'fronting_pool': False})
# The drain CLI loads the wallet independently. Stop its daemon to avoid two writers.
docker('stop', 'spiral-captaind')
result = action('quarantine-free-reserve', lambda: {'txid': captain('drain', address).stdout.strip()})
docker('start', 'spiral-captaind')
mine(3)
for _ in range(20):
    if json.loads(rpc('wallet').stdout)['rounds']['total_balance'] == 0:
        break
    time.sleep(1)
else:
    raise RuntimeError('Server wallet not empty; cannot claim isolated recovered-asset reuse')
snapshot('free-reserve-quarantined')
