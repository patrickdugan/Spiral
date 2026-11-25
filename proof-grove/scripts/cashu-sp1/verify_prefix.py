"""Check the full archived Cashu prefix against the stock SP1 audit receipt."""

import argparse
import hashlib
import json
from pathlib import Path

import index_archive as index


MAX_RECEIPT_BYTES = 2 * 1024**2
MAX_PROOF_BYTES = 16 * 1024**2


def read_bounded(path, size):
    with path.open('rb') as source:
        contents = source.read(size + 1)
    if not 0 < len(contents) <= size:
        raise ValueError(f'{path.name} exceeds its size budget or is empty')
    return contents


def check_chain(nodes):
    if not nodes or nodes[0]['timestamp'][0] != 1:
        raise ValueError('prefix does not start at the SP1 initial timestamp')
    names = set()
    previous = None
    count = 0
    for node in nodes:
        name = node['entry']
        if name in names or not index.MEMO_NAME.fullmatch(f'memo/{name}/out0'):
            raise ValueError('duplicate or invalid proof in Cashu prefix')
        names.add(name)
        if node['contains_first_shard'] != (previous is None):
            raise ValueError('unexpected first-shard flag in Cashu prefix')
        if node['complete_flag'] or node['exit_code'] != 0 or node['included_core_shards'] <= 0:
            raise ValueError('unexpected completion, exit or shard count in Cashu prefix')
        if (node['before'] == node['after'] or node['timestamp'][1] < node['timestamp'][0]
                or (previous and (previous['after'] != node['before']
                                  or previous['timestamp'][1] != node['timestamp'][0]))):
            raise ValueError('disconnected public rows in Cashu prefix')
        count += node['included_core_shards']
        previous = node
    return count


def verify_prefix(audit):
    plan_bytes = read_bounded(audit / 'composition-plan.json', MAX_RECEIPT_BYTES)
    plan = json.loads(plan_bytes)
    if (plan['archive_sha256'], plan['program_key']) != (index.ARCHIVE_SHA256, index.PROGRAM_KEY.hex()):
        raise ValueError('unexpected Cashu archive or program key')
    if hashlib.sha256(read_bounded(audit / 'run.json', 65536)).hexdigest() != index.MANIFEST_SHA256:
        raise ValueError('unexpected Cashu run manifest')

    selected = plan['selected_proofs']
    transcript_bytes = read_bounded(audit / 'verified.jsonl', MAX_RECEIPT_BYTES)
    *reports, summary = [json.loads(line) for line in transcript_bytes.splitlines()]
    if (summary.get('verifier'), summary.get('verified'), summary.get('rejected'), summary.get('effective_nonce')) != (
            'sp1-v6.9.0-stock-cpu-recursion', len(selected), 0, [0, 0, 0, 0]):
        raise ValueError('the stock verifier did not accept the entire Cashu prefix')
    if len(reports) != len(selected) or len(selected) > sum(index.COUNTS.values()):
        raise ValueError('unexpected stock verifier report count')
    if plan['candidate_path'] != [node['entry'] for node in selected]:
        raise ValueError('verified proofs do not follow the complete planned path')

    matched = []
    for node, report in zip(selected, reports, strict=True):
        name = node['entry']
        if not index.MEMO_NAME.fullmatch(f'memo/{name}/out0'):
            raise ValueError('invalid proof entry in audit plan')
        proof = read_bounded(audit / 'memo' / name / 'out0', MAX_PROOF_BYTES)
        digest = hashlib.sha256(proof).hexdigest()
        if (report.get('entry'), report.get('status'), report.get('out0_sha256')) != (name, 'verified', digest):
            raise ValueError(f'proof differs from its stock verification receipt for {name}')
        row, words = index.public_row(proof[:index.PREFIX_BYTES])
        actual = {'entry': name, **index.row_metadata(row, words), 'out0_sha256': digest}
        if actual != node:
            raise ValueError(f'proof differs from its authenticated planner row for {name}')
        matched.append(actual)

    count = check_chain(matched)
    timestamps = [matched[0]['timestamp'][0], matched[-1]['timestamp'][1]]
    if (count, timestamps) != (plan['candidate_archive_core_shards'], plan['candidate_timestamp_range']):
        raise ValueError('verified coverage differs from the audited plan')
    return {
        'schema': 'proof-grove-cashu/sp1-recursion-prefix/v1',
        'status': 'cashu_recursion_prefix_verified',
        'archive_sha256': index.ARCHIVE_SHA256,
        'program_vk_digest': index.PROGRAM_KEY.hex(),
        'plan_sha256': hashlib.sha256(plan_bytes).hexdigest(),
        'verifier_transcript_sha256': hashlib.sha256(transcript_bytes).hexdigest(),
        'verified_proofs': len(matched),
        'covered_core_shards': count,
        'timestamp_range': timestamps,
        'first_boundary_sha256': matched[0]['before'],
        'last_boundary_sha256': matched[-1]['after'],
        'verifier_elapsed_seconds': summary['seconds'],
        'scope': 'Individually verified recursion proofs with connected public rows, covering an execution prefix.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit_directory', type=Path)
    parser.add_argument('receipt', type=Path)
    args = parser.parse_args()
    receipt = verify_prefix(args.audit_directory)
    with args.receipt.open('x', encoding='utf-8') as output:
        json.dump(receipt, output, indent=2)
        output.write('\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
