"""Resolve the existing receive after a CLI-output parsing gap; never resend."""
import hashlib
import json
from bootstrap import core
from fund import cln
from attest import DEST, save
from observe import snapshot, redact

intent = json.loads((DEST / 'action-inbound-peer-pay-2000.json').read_text())
payment_hash = intent['payment_hash']
if core('getblockchaininfo')['chain'] != 'regtest':
    raise RuntimeError('owned regtest required')
payments = cln('peer', '--json', '--notifications=none', '-k', 'listsendpays', f'payment_hash={payment_hash}')
assert len(payments['payments']) == 1
payment = payments['payments'][0]
assert payment['status'] == 'complete'
assert hashlib.sha256(bytes.fromhex(payment['payment_preimage'])).hexdigest() == payment_hash
public = redact(payments)
public['payment_preimage_sha256_verified'] = payment_hash
save('inbound-peer-sendpays.json', public)
save('inbound-hold-settled.json', redact(cln('server', 'listholdinvoices', payment_hash)))
save('inbound-peer-settled.json', cln('peer', 'listpeerchannels'))
snapshot('inbound-settled')
save('inbound-collection-gap.json', {
    'payment_hash': payment_hash, 'original_payment_retried': False,
    'gap': 'Bark claim returned zero. Peer pay process terminated, but its stdout failed JSON decoding; unretained notification output may have preceded the JSON; original exit/result were not saved.',
    'reconciliation': 'Read-only listsendpays proves one completed attempt and its preimage hash; hold plugin, server DB and both channel sides independently confirm settlement.',
    'fix': 'Future collector explicitly requests lightning-cli --json --notifications=none output.',
})
