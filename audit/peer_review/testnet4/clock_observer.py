#!/usr/bin/python3
"""Passive CLN notification clock. No hooks, signing, payments, or routing changes.

Callback receipt time is an observer timestamp, not an internal commit timestamp.
Only selected public fields are recorded; secrets and invoice strings are omitted.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

TOPICS = ['block_added', 'channel_state_changed', 'forward_event', 'sendpay_success', 'sendpay_failure']
FIELDS = set('hash height peer_id channel_id timestamp new_state cause short_channel_id old_state '
    'payment_hash in_channel out_channel in_msat out_msat fee_msat status received_time resolved_time '
    'failcode failreason failcodename style created_index updated_index id groupid partid amount_sent_msat '
    'amount_msat created_at completed_at destination label code erring_index erring_node erring_channel '
    'erring_direction data'.split())


def public_payload(value):
    if isinstance(value, dict):
        return {k: public_payload(v) for k, v in value.items() if k in FIELDS or k in TOPICS}
    if isinstance(value, list):
        return [public_payload(v) for v in value]
    return value


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.sequence, self.previous = 0, '0' * 64
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                row = json.loads(line)
                digest = row.pop('sha256')
                if row['sequence'] != self.sequence + 1 or row['previous_sha256'] != self.previous or digest != self.digest(row):
                    raise ValueError('existing observer journal is inconsistent')
                self.sequence, self.previous = row['sequence'], digest

    @staticmethod
    def digest(row):
        return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def append(self, topic, payload):
        row = {'sequence': self.sequence + 1, 'previous_sha256': self.previous,
            'observer_monotonic_ns': str(time.monotonic_ns()), 'observer_unix_ns': str(time.time_ns()),
            'topic': topic, 'payload': public_payload(payload)}
        row['sha256'] = self.digest(row)
        with self.path.open('a') as out:
            out.write(json.dumps(row, separators=(',', ':')) + '\n')
            out.flush(); os.fsync(out.fileno())
        self.sequence, self.previous = row['sequence'], row['sha256']


def reply(request, result):
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}) + '\n', flush=True)


def main():
    journal = None
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        method = request.get('method')
        if method == 'getmanifest':
            reply(request, {'options': [], 'rpcmethods': [{'name': 'spiral-clock-status', 'usage': '',
                'description': 'Read passive observer sequence and monotonic clock'}],
                'subscriptions': TOPICS, 'hooks': [], 'dynamic': True})
        elif method == 'init':
            config = request['params']['configuration']
            if config['network'] not in ('regtest', 'testnet4'):
                reply(request, {'disable': 'isolated test networks only'}); continue
            journal = Journal(Path('/data') / 'clock-events.jsonl')
            journal.append('observer_started', {})
            reply(request, {})
        elif method == 'spiral-clock-status':
            reply(request, {'sequence': journal.sequence, 'last_sha256': journal.previous,
                'monotonic_ns': str(time.monotonic_ns()), 'passive': True})
        elif method in TOPICS and journal is not None:
            journal.append(method, request.get('params', {}))


if __name__ == '__main__':
    main()
