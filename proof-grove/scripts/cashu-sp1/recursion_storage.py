"""Select and persist a scratch location for raw Cashu recursion."""

import argparse
import json
import os
from pathlib import Path
import re
import tempfile


GIB = 1024 ** 3
MIB = 1024 ** 2
GROUP_SIZE = 128
LINUX_RESERVE = 2 * GIB
BACKING_RESERVE = 32 * GIB


def required_scratch(shards, group_size=GROUP_SIZE):
    if type(shards) is not int or not 1 <= shards < 1 << 31 or not 2 <= group_size <= 256:
        raise ValueError('invalid shard count or recursion group size')
    groups = (shards + group_size - 1) // group_size
    during_group = groups - 1 + 2 * min(shards, group_size) - 1
    final_tree = 2 * groups - 1
    # Archived normalized leaves and reduction proofs each use 1,272,542 bytes.
    # Allow 1.5 MiB per proof and 192 MiB for staging, receipts and metadata.
    return max(during_group, final_tree) * (3 * MIB // 2) + 192 * MIB


def select(shards, index_sha256, filesystem_free, backing_linux_free, backing_host_free, prior=None):
    if re.fullmatch('[0-9a-f]{64}', index_sha256) is None:
        raise ValueError('expected the independently verified shard index digest')
    if any(type(value) is not int or value < 0 for value in (filesystem_free, backing_linux_free, backing_host_free)):
        raise ValueError('invalid recursion storage measurements')
    needed = required_scratch(shards)
    common = {
        'schema': 'proof-grove/cashu-recursion-storage/v1', 'shard_index_sha256': index_sha256,
        'shards': shards, 'group_size': GROUP_SIZE, 'scratch_budget_bytes': needed,
    }
    if prior is not None:
        site = prior.get('site')
        if site not in ('checkpoint', 'backing') or prior != {**common, 'site': site}:
            raise ValueError('recorded recursion storage differs from the verified archive')
        # Completed groups already occupy space on the recorded device.
        enough = (filesystem_free >= LINUX_RESERVE if site == 'checkpoint'
                  else backing_host_free >= BACKING_RESERVE and backing_linux_free >= LINUX_RESERVE)
        if not enough:
            raise ValueError('recorded recursion workspace is below its disk reserve')
        return prior

    if filesystem_free >= LINUX_RESERVE + needed:
        return {**common, 'site': 'checkpoint'}
    if backing_host_free >= BACKING_RESERVE + needed and backing_linux_free >= LINUX_RESERVE + needed:
        return {**common, 'site': 'backing'}
    raise ValueError('neither recursion workspace fits the proof budget and disk reserve')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('shards', type=int)
    parser.add_argument('index_sha256')
    parser.add_argument('filesystem_free', type=int)
    parser.add_argument('backing_linux_free', type=int)
    parser.add_argument('backing_host_free', type=int)
    args = parser.parse_args()
    path = args.receipt
    try:
        prior = None
        if path.is_symlink():
            raise ValueError('recursion storage receipt must be a regular file')
        if path.exists():
            with path.open('rb') as stream:
                data = stream.read(4097)
            if len(data) > 4096:
                raise ValueError('recursion storage receipt exceeds its byte budget')
            prior = json.loads(data)
            if not isinstance(prior, dict):
                raise ValueError('invalid recursion storage receipt')
        result = select(args.shards, args.index_sha256, args.filesystem_free, args.backing_linux_free,
                        args.backing_host_free, prior)
        if prior is None:
            # The caller holds the pinned Core job lock across selection and recursion.
            with tempfile.TemporaryDirectory(dir=path.parent) as temporary:
                candidate = Path(temporary) / path.name
                with candidate.open('x', encoding='utf-8') as stream:
                    stream.write(json.dumps(result, indent=2) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(candidate, path)
    except (AttributeError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f'Recursion storage is unavailable: {error}\n')
    print(result['site'], result['group_size'])


if __name__ == '__main__':
    main()
