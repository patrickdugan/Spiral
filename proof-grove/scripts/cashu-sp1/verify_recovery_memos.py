"""Check the newly saved Core memo bytes before resuming an OOM-stopped worker."""

import hashlib
import json
from pathlib import Path
import re
import sys


run, report = map(Path, sys.argv[1:])
baseline = int((report / 'progress-baseline-bytes.txt').read_text())
prior = int((report / 'prior-core-memos.txt').read_text())
progress = (run / 'progress.jsonl').read_bytes()
if not progress.endswith(b'\n') or progress != (report / 'progress.jsonl').read_bytes() or not progress[:baseline].endswith(b'\n'):
    raise SystemExit('The stopped run lacks a complete, matching progress journal.')
events = (json.loads(line) for line in progress[baseline:].splitlines())
keys = []
for event in events:
    if event['kind'] == 'shard' and event['replayed'] is False:
        keys.append(event['key'])
if not keys or len(set(keys)) != len(keys) or any(not re.fullmatch('[a-f0-9]{16}', key) for key in keys):
    raise SystemExit('The stopped run has missing, invalid or repeated fresh memo keys.')
selected = set(keys)
paths = {}
count = 0
for candidate in (run / 'memo/shard').iterdir():
    if not re.fullmatch('[a-f0-9]{64}', candidate.name) or not candidate.is_dir() or candidate.is_symlink():
        continue
    count += 1
    key = candidate.name[:16]
    if key in selected:
        if key in paths:
            raise SystemExit('The stopped run has an ambiguous fresh memo.')
        paths[key] = candidate
if paths.keys() != selected or count != prior + len(keys):
    raise SystemExit('The saved memo directories differ from the stopped run journal.')
for key in keys:
    path = paths[key]
    memo = json.loads((path / 'manifest.json').read_bytes())
    with (path / 'out0').open('rb') as proof:
        actual = hashlib.file_digest(proof, 'sha256').digest()
    if actual != bytes(memo['out0_sha256']):
        raise SystemExit(f'The saved shard differs from its memo digest for {key}.')
print(json.dumps({'new_memos_hash_checked': len(keys), 'saved_memos': count,
                  'progress_sha256': hashlib.sha256(progress).hexdigest()}))
