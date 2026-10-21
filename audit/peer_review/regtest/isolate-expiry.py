"""Disable further optional pool issuance, retaining existing backing and claims.
This is an explicit isolation intervention; default consensus/timelocks stay intact.
"""
from bootstrap import RUNTIME, docker
from attest import save
import hashlib
import json

path = RUNTIME / 'config/captaind.toml'
before = path.read_text()
old = 'vtxo_targets = [ "1000sat:10", "10000sat:10" ]'
if old not in before:
    raise RuntimeError('expected source-default pool target; inspect prior intervention')
after = before.replace(old, 'vtxo_targets = []')
save('pool-issuance-intervention.json', {'reason': 'isolate original board expiry from automatic pool replenishment',
    'before_sha256': hashlib.sha256(before.encode()).hexdigest(), 'after_sha256': hashlib.sha256(after.encode()).hexdigest(),
    'old_targets': ['1000sat:10','10000sat:10'], 'new_targets': [], 'new_external_funding': 0})
docker('stop', 'spiral-captaind')
path.write_text(after)
(RUNTIME / 'config/fixture-settings.json').write_text(json.dumps({'disable_pool_issuance': True}))
docker('start', 'spiral-captaind')
print('Optional automatic pool issuance disabled; existing pool assets preserved.')
