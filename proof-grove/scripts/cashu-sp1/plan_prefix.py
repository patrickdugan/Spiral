"""Find a Cashu archive prefix and prepare the next compose group for stock verification."""

import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import tarfile

import index_archive as index


def candidate_path(entries, anchor):
    start = entries[anchor]['before']
    by_start = defaultdict(list)
    for name, row in entries.items():
        if row['before'] == row['after']:
            raise ValueError('same-boundary nodes require an explicit composition order')
        by_start[row['before']].append((name, row))
    parents = {start: None}
    distance = {start: 0}
    end_time = {start: entries[anchor]['timestamp'][0]}
    queue = deque([start])
    while queue:
        state = queue.popleft()
        for name, row in sorted(by_start[state], key=lambda entry: (-entry[1]['included_core_shards'], entry[0])):
            after = row['after']
            if after in parents or row['contains_first_shard'] != (state == start):
                continue
            parents[after] = state, name
            distance[after] = distance[state] + 1
            end_time[after] = row['timestamp'][1]
            queue.append(after)

    best = max(parents, key=lambda state: (end_time[state], -distance[state]))
    path = []
    while parents[best] is not None:
        best, name = parents[best]
        path.append(name)
    path.reverse()
    if len(path) < 4 or not path[0].startswith('reduce/'):
        raise ValueError('no archived leading reduction with three connecting proofs')
    return path


def take_audit_inputs(archive_path, selected):
    if archive_path.stat().st_size != index.ARCHIVE_BYTES:
        raise ValueError('checkpoint differs from its pinned archive size')
    found = {}
    manifest_bytes = None
    with archive_path.open('rb') as source:
        hashed = index.HashedReader(source)
        with tarfile.open(fileobj=hashed, mode='r|gz', bufsize=1024 * 1024) as archive:
            for member in archive:
                if member.name == 'run.json':
                    if manifest_bytes is not None or not member.isfile() or member.size > 65536:
                        raise ValueError('invalid run manifest')
                    manifest_bytes = archive.extractfile(member).read()
                    if hashlib.sha256(manifest_bytes).hexdigest() != index.MANIFEST_SHA256:
                        raise ValueError('checkpoint manifest changed')
                    continue
                match = index.MEMO_NAME.fullmatch(member.name)
                if not match:
                    continue
                entry = '/'.join(match.groups())
                if entry not in selected:
                    continue
                if entry in found or not member.isfile() or not 0 < member.size <= 16 * 1024**2:
                    raise ValueError(f'invalid selected archive entry {entry}')
                proof = archive.extractfile(member).read()
                row, _ = index.public_row(proof[:index.PREFIX_BYTES])
                if hashlib.sha256(row).hexdigest() != selected[entry]['public_row_sha256']:
                    raise ValueError(f'archive entry {entry} no longer matches the public-row index')
                found[entry] = proof
        while hashed.read(1024 * 1024):
            pass
        if hashed.digest.hexdigest() != index.ARCHIVE_SHA256 or manifest_bytes is None or found.keys() != selected.keys():
            raise ValueError('the pinned archive or selected memo set changed')
    return manifest_bytes, found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('candidate_index', type=Path)
    parser.add_argument('audit_directory', type=Path)
    args = parser.parse_args()
    if not 0 < args.candidate_index.stat().st_size <= 2 * 1024**2:
        raise ValueError('invalid candidate index size')
    candidate_index = json.loads(args.candidate_index.read_bytes())
    if candidate_index['archive_sha256'] != index.ARCHIVE_SHA256:
        raise ValueError('candidate index refers to a different archive')
    entries = candidate_index['entries']
    path = candidate_path(entries, candidate_index['matching_control_entry'])
    selected = {entry: entries[entry] for entry in path[:4]}
    manifest, proofs = take_audit_inputs(args.archive, selected)

    output = args.audit_directory
    output.mkdir()
    (output / 'run.json').write_bytes(manifest)
    (output / 'entries.txt').write_text('\n'.join(selected) + '\n', encoding='utf-8', newline='\n')
    selected_receipts = []
    for entry, row in selected.items():
        folder = output / 'memo' / entry
        folder.mkdir(parents=True)
        proof = proofs[entry]
        (folder / 'out0').write_bytes(proof)
        selected_receipts.append({'entry': entry, **row, 'out0_sha256': hashlib.sha256(proof).hexdigest()})
    plan = {
        'scope': 'Candidate archive coverage and next compose inputs. A final stock SP1 proof is still required.',
        'archive_sha256': index.ARCHIVE_SHA256, 'program_key': index.PROGRAM_KEY.hex(),
        'leading_group': selected_receipts, 'candidate_path': path,
        'candidate_archive_core_shards': sum(entries[node]['included_core_shards'] for node in path),
        'candidate_timestamp_range': [entries[path[0]]['timestamp'][0], entries[path[-1]]['timestamp'][1]],
    }
    (output / 'composition-plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: val for key, val in plan.items() if key != 'candidate_path'}))


if __name__ == '__main__':
    main()
