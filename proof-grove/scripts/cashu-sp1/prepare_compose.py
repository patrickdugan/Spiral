"""Prepare adjacent verified Cashu recursion proofs for the stock arity replay tool."""

import argparse
import hashlib
import json
from pathlib import Path

import index_archive as index
from verify_prefix import MAX_RECEIPT_BYTES, read_bounded


def proof_range(words):
    return {
        'timestamp_range': [index.timestamp(words[88:92]), index.timestamp(words[92:96])],
        'initialized_address_range': [index.limb_value(words[96:99][::-1]), index.limb_value(words[99:102][::-1])],
        'finalized_address_range': [index.limb_value(words[102:105][::-1]), index.limb_value(words[105:108][::-1])],
        'initialized_page_index_range': [index.limb_value(words[108:111][::-1]), index.limb_value(words[111:114][::-1])],
        'finalized_page_index_range': [index.limb_value(words[114:117][::-1]), index.limb_value(words[117:120][::-1])],
        'deferred_proof_range': [words[80], words[81]],
    }


def digest(data):
    return hashlib.sha256(data).hexdigest()


def literal(data):
    return json.dumps(data, separators=(',', ':'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit', type=Path)
    parser.add_argument('compose_input', type=Path)
    parser.add_argument('--start-ordinal', type=int, default=1, help='first child position in the audit, starting at one')
    parser.add_argument('--arity', type=int, choices=(2, 3, 4), default=2)
    args = parser.parse_args()
    plan = json.loads(read_bounded(args.audit / 'composition-plan.json', MAX_RECEIPT_BYTES))
    if (plan['archive_sha256'], plan['program_key']) != (index.ARCHIVE_SHA256, index.PROGRAM_KEY.hex()):
        raise ValueError('unexpected Cashu archive or program key')
    selected = plan.get('selected_proofs', plan['leading_group'])
    *verified, summary = [json.loads(line) for line in
                          read_bounded(args.audit / 'verified.jsonl', MAX_RECEIPT_BYTES).splitlines()]
    if (summary.get('verifier'), summary.get('verified'), summary.get('rejected'), summary.get('effective_nonce')) != (
            'sp1-v6.9.0-stock-cpu-recursion', len(selected), 0, [0, 0, 0, 0]) or len(verified) != len(selected):
        raise ValueError('expected stock verification of the selected archive proofs')
    start = args.start_ordinal - 1
    stop = start + args.arity
    if not 0 <= start < stop <= len(selected):
        raise ValueError('requested compose group is outside the verified prefix')
    group = selected[start:stop]
    children = []
    proof_bytes = []
    ranges = []
    for number, (entry, receipt) in enumerate(zip(group, verified[start:stop], strict=True)):
        name = entry['entry']
        if not index.MEMO_NAME.fullmatch(f'memo/{name}/out0') or receipt['entry'] != name or receipt['status'] != 'verified':
            raise ValueError('unverified or invalid ordered proof entry')
        path = args.audit / 'memo' / name / 'out0'
        source = read_bounded(path, 16 * 1024**2)
        source_hash = digest(source)
        if source_hash != receipt['out0_sha256'] or source_hash != entry['out0_sha256']:
            raise ValueError('proof differs from its verification receipt')
        row, words = index.public_row(source[:index.PREFIX_BYTES])
        ranges.append(proof_range(words))
        proof_bytes.append(source)
        actual = {'entry': name, **index.row_metadata(row, words), 'out0_sha256': source_hash}
        if actual != entry or actual['complete_flag'] or actual['exit_code'] != 0:
            raise ValueError('unexpected authenticated public row')
        children.append({'range_literal': literal(ranges[-1]), 'file': f'child-{number:02}.bin',
                         'bytes': len(source), 'sha256': source_hash})

    if len({entry['entry'] for entry in group}) != len(group):
        raise ValueError('duplicate proof in compose group')
    for left, right in zip(group, group[1:]):
        if left['after'] != right['before'] or right['contains_first_shard']:
            raise ValueError('ordered proofs do not connect along the Cashu prefix')
    for left, right in zip(ranges, ranges[1:]):
        if any(left[field][1] != right[field][0] for field in left):
            raise ValueError('ordered proof ranges do not align')
    aggregate = {field: [ranges[0][field][0], ranges[-1][field][1]] for field in ranges[0]}
    manifest = {'schema': 'nb3-reduction-failure/v1', 'is_complete': False,
                'range_literal': literal(aggregate), 'children': children}
    run = read_bounded(args.audit / 'run.json', 65536)
    if digest(run) != index.MANIFEST_SHA256:
        raise ValueError('unexpected source run manifest')
    encoded = (json.dumps(manifest, indent=2) + '\n').encode()
    if len(encoded) + sum(child['bytes'] for child in children) > 64 * 1024**2:
        raise ValueError('compose request exceeds the stock replay size budget')
    args.compose_input.mkdir()
    (args.compose_input / 'run.json').write_bytes(run)
    capture = args.compose_input / 'reduction-failure'
    capture.mkdir()
    for child, source in zip(children, proof_bytes, strict=True):
        (capture / child['file']).write_bytes(source)
    (capture / 'manifest.json').write_bytes(encoded)
    (args.compose_input / 'manifest-sha256.txt').write_text(digest(encoded) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'manifest_sha256': digest(encoded), 'first_ordinal': args.start_ordinal,
                      'arity': len(group), 'included_core_shards_if_composed': sum(entry['included_core_shards'] for entry in group),
                      'range': aggregate}))


if __name__ == '__main__':
    main()
