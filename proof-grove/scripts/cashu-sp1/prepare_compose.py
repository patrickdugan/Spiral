"""Prepare a verified two-child Cashu prefix for the stock arity replay tool."""

import argparse
import hashlib
import json
from pathlib import Path

import index_archive as index


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
    args = parser.parse_args()
    transcript = args.audit / 'verified.jsonl'
    plan_path = args.audit / 'composition-plan.json'
    if not all(0 < path.stat().st_size <= 1024 * 1024 for path in (transcript, plan_path)):
        raise ValueError('invalid verification transcript or plan size')
    verified = [json.loads(line) for line in transcript.read_text().splitlines()]
    summary = verified.pop()
    if len(verified) != 4 or summary['verified'] != 4 or summary['rejected'] or summary['effective_nonce'] != [0, 0, 0, 0]:
        raise ValueError('expected four independently verified archive proofs')
    plan = json.loads(plan_path.read_text())
    leading = plan['leading_group'][:2]
    children = []
    proof_bytes = []
    ranges = []
    for number, (entry, receipt) in enumerate(zip(leading, verified[:2], strict=True)):
        name = entry['entry']
        if not index.MEMO_NAME.fullmatch(f'memo/{name}/out0') or receipt['entry'] != name or receipt['status'] != 'verified':
            raise ValueError('unverified or invalid ordered proof entry')
        path = args.audit / 'memo' / name / 'out0'
        if not 0 < path.stat().st_size <= 16 * 1024**2:
            raise ValueError('unexpected proof size')
        source = path.read_bytes()
        source_hash = digest(source)
        if source_hash != receipt['out0_sha256'] or source_hash != entry['out0_sha256']:
            raise ValueError('proof differs from its verification receipt')
        row, words = index.public_row(source[:index.PREFIX_BYTES])
        ranges.append(proof_range(words))
        proof_bytes.append(source)
        if digest(row) != entry['public_row_sha256'] or words[168] != 0:
            raise ValueError('unexpected authenticated public row')
        children.append({'range_literal': literal(ranges[-1]), 'file': f'child-{number:02}.bin',
                         'bytes': len(source), 'sha256': source_hash})

    left, right = leading
    if left['after'] != right['before'] or (left['included_core_shards'], right['included_core_shards']) != (355, 1):
        raise ValueError('ordered proofs do not extend the expected Cashu prefix')
    if any(ranges[0][field][1] != ranges[1][field][0] for field in ranges[0]):
        raise ValueError('ordered proof ranges do not align')
    aggregate = {field: [ranges[0][field][0], ranges[1][field][1]] for field in ranges[0]}
    manifest = {'schema': 'nb3-reduction-failure/v1', 'is_complete': False,
                'range_literal': literal(aggregate), 'children': children}
    run = (args.audit / 'run.json').read_bytes()
    if digest(run) != index.MANIFEST_SHA256:
        raise ValueError('unexpected source run manifest')
    args.compose_input.mkdir()
    (args.compose_input / 'run.json').write_bytes(run)
    capture = args.compose_input / 'reduction-failure'
    capture.mkdir()
    for child, source in zip(children, proof_bytes, strict=True):
        (capture / child['file']).write_bytes(source)
    encoded = (json.dumps(manifest, indent=2) + '\n').encode()
    (capture / 'manifest.json').write_bytes(encoded)
    (args.compose_input / 'manifest-sha256.txt').write_text(digest(encoded) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'manifest_sha256': digest(encoded), 'included_core_shards_if_composed': 356, 'range': aggregate}))


if __name__ == '__main__':
    main()
