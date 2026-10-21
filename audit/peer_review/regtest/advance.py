"""Advance the owned regtest block clock; never present this as wall-time data."""
from bootstrap import core
from fund import mine
from observe import snapshot
from pay import action
import sys

target = int(sys.argv[1])
label = sys.argv[2]
height = core('getblockcount')
if not height < target <= 10000:
    raise RuntimeError('Expected increasing, bounded local height')
action(label, lambda: {'height': mine(target - height), 'clock': 'accelerated-owned-regtest'})
snapshot(label)
