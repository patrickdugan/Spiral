"""Read the pinned SP1 6.9 Cashu archive and locate candidate recursion rows."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import tarfile

ARCHIVE_SHA256 = 'b2786320ba2abc774a8e2438db8272d0f94b409dd47008992c4b7bb4baf2ed26'
ARCHIVE_BYTES = 1459101865
MANIFEST_SHA256 = '5e4364995592388b0f15ff006974d055eb6eca065784e27ca91d89a0b3962463'
CONTROL_SHA256 = '66a86a5e07905b02d5481c949ef7513d2f43dffed1aa8ac8f7c2ea9da3d1d6b9'
PROGRAM_KEY = bytes.fromhex('8435f74771e40b1730e5665236465e32988a563b687c8f3f151d0823c15a2757')
COUNTS = {'shard': 1537, 'reduce': 239}
FIELDS = struct.Struct('<187I')
PREFIX_BYTES = 4096
KOALABEAR_MODULUS = 0x7F000001
MEMO_NAME = re.compile(r'memo/(shard|reduce)/([0-9a-f]{64})/out0')


class HashedReader:
    def __init__(self, source):
        self.source = source
        self.digest = hashlib.sha256()

    def read(self, size):
        data = self.source.read(size)
        self.digest.update(data)
        return data


def public_row(prefix):
    key_offset = prefix.find(PROGRAM_KEY)
    row_start = key_offset - 136 * 4
    if (row_start < 8 or prefix.count(PROGRAM_KEY) != 1
            or row_start + FIELDS.size > len(prefix)
            or struct.unpack_from('<Q', prefix, row_start - 8)[0] != 187):
        raise ValueError('expected a single SP1 6.9 recursion public row')
    row = prefix[row_start:row_start + FIELDS.size]
    words = FIELDS.unpack(row)
    if max(words) >= KOALABEAR_MODULUS or any(words[183:187]):
        raise ValueError('unexpected SP1 field encoding or effective nonce')
    if words[166] not in (0, 1) or words[168] not in (0, 1) or words[167] >= (1 << 24):
        raise ValueError('invalid SP1 recursion flags or shard count')
    return row, words


def limb_value(words):
    result = 0
    for word in words:
        if word >= 1 << 16:
            raise ValueError('range limb exceeds 16 bits')
        result = (result << 16) + word
    return result


def timestamp(words):
    high, middle, low, clock = words
    if high >= 1 << 16 or middle >= 1 << 8 or low >= 1 << 8 or clock >= 1 << 16:
        raise ValueError('timestamp limb exceeds SP1 6.9 range')
    return (high << 32) | (middle << 24) | (low << 16) | clock


def boundary(words, offsets):
    return hashlib.sha256(b''.join(struct.pack(f'<{width}I', *words[at:at + width])
                                  for at, width in offsets)).hexdigest()


# These are the before/after field pairs checked by SP1 6.9's compose circuit.
TRANSITIONS = ((0, 32, 32), (64, 72, 8), (80, 81, 1), (82, 85, 3), (88, 92, 4),
               (96, 99, 3), (102, 105, 3), (108, 111, 3), (114, 117, 3),
               (120, 128, 8), (169, 170, 1), (171, 172, 1), (173, 174, 1))


def row_metadata(row, words):
    return {
        'public_row_sha256': hashlib.sha256(row).hexdigest(),
        'before': boundary(words, [(before, width) for before, _, width in TRANSITIONS]),
        'after': boundary(words, [(after, width) for _, after, width in TRANSITIONS]),
        'timestamp': [timestamp(words[88:92]), timestamp(words[92:96])],
        'contains_first_shard': bool(words[166]),
        'included_core_shards': words[167],
        'complete_flag': bool(words[168]),
        'exit_code': words[170],
    }


def index_archive(archive_path, control_path):
    if archive_path.stat().st_size != ARCHIVE_BYTES:
        raise ValueError('checkpoint differs from its pinned archive size')
    if not 0 < control_path.stat().st_size <= 16 * 1024**2:
        raise ValueError('invalid verified control leaf size')
    control = control_path.read_bytes()
    if hashlib.sha256(control).hexdigest() != CONTROL_SHA256:
        raise ValueError('verified control leaf changed')
    control_row, control_words = public_row(control[:PREFIX_BYTES])
    if (timestamp(control_words[88:92]), timestamp(control_words[92:96])) != (1, 3920561):
        raise ValueError('decoded row differs from the stock verifier control range')
    key_root = control_words[144:152]

    entries = {}
    counts = dict.fromkeys(COUNTS, 0)
    with archive_path.open('rb') as source:
        hashed = HashedReader(source)
        with tarfile.open(fileobj=hashed, mode='r|gz', bufsize=1024 * 1024) as archive:
            manifest = archive.next()
            if manifest is None or manifest.name != 'run.json' or not manifest.isfile() or manifest.size > 65536:
                raise ValueError('expected the pinned run manifest first')
            manifest_bytes = archive.extractfile(manifest).read()
            if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
                raise ValueError('checkpoint manifest changed')

            for member in archive:
                match = MEMO_NAME.fullmatch(member.name)
                if not match:
                    continue
                kind, name = match.groups()
                entry = f'{kind}/{name}'
                counts[kind] += 1
                if entry in entries or counts[kind] > COUNTS[kind] or not member.isfile() or not 0 < member.size <= 32 * 1024**2:
                    raise ValueError(f'invalid archive entry {entry}')
                row, words = public_row(archive.extractfile(member).read(PREFIX_BYTES))
                if words[144:152] != key_root:
                    raise ValueError(f'entry {entry} has a different key root')
                entries[entry] = row_metadata(row, words)
        while hashed.read(1024 * 1024):
            pass
        if hashed.digest.hexdigest() != ARCHIVE_SHA256 or counts != COUNTS:
            raise ValueError('the complete archive hash or memo counts differ from the checkpoint receipt')

    control_digest = hashlib.sha256(control_row).hexdigest()
    anchors = [entry for entry, row in entries.items() if row['public_row_sha256'] == control_digest]
    if len(anchors) != 1:
        raise ValueError('expected one match for the independently verified control row')
    return entries, anchors[0]


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('archive', type=Path)
    args.add_argument('verified_leaf', type=Path)
    args.add_argument('output', type=Path)
    values = args.parse_args()
    entries, anchor = index_archive(values.archive, values.verified_leaf)
    summary = {
        'schema': 'proof-grove-cashu/sp1-recursion-candidate-index/v1',
        'scope': 'Candidate public rows. Verify the selected proofs and final SP1 composition independently.',
        'archive_sha256': ARCHIVE_SHA256, 'run_sha256': MANIFEST_SHA256,
        'control_leaf_sha256': CONTROL_SHA256, 'matching_control_entry': anchor,
        'counts': COUNTS, 'complete_flag_candidates': [key for key, row in entries.items() if row['complete_flag']],
        'entries': entries,
    }
    with values.output.open('x', encoding='utf-8') as output:
        json.dump(summary, output, indent=2)
        output.write('\n')
    print(json.dumps({key: value for key, value in summary.items() if key != 'entries'}))


if __name__ == '__main__':
    main()
