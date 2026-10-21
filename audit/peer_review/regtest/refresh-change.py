"""Re-back the first payment's surviving change before original-board expiry."""
from bootstrap import core
from launch import bark
from fund import mine
from observe import snapshot
from pay import action

height = core('getblockcount')
if height > 1000:
    raise RuntimeError('Unexpected starting height; inspect evidence before advancing')
if height < 1000:
    action('advance-to-1000', lambda: {'height': mine(1000 - height), 'clock': 'accelerated-owned-regtest'})
snapshot('before-change-refresh')
action('refresh-change', lambda: {'stdout': bark('refresh', '--all').stdout})
mine(3)
print(bark('balance').stdout)
snapshot('change-refreshed')
