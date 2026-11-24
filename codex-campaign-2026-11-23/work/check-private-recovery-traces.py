"""Exercise private restore against WSL memo trace files without exporting them."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile


scripts, cache = map(Path, sys.argv[1:3])
sys.path.insert(0, str(scripts))
from restore_private_memos import restore_archive


root = cache / 'memo/shard'
samples = []
for memo in root.iterdir():
    if (memo / 'chunks.json').is_file():
        files = list(memo.iterdir())
        if sum(file.stat().st_size for file in files) < 6 * 1024**2:
            samples.append((memo, files))
    if len(samples) == 3:
        break
assert len(samples) == 3

encoded = io.BytesIO()
with tarfile.open(fileobj=encoded, mode='w') as archive:
    for memo, files in samples:
        for file in sorted(files):
            archive.add(file, arcname=f'cache/memo/shard/{memo.name}/{file.name}', recursive=False)

archive_bytes = encoded.getvalue()
fragments = {}
parts = []
for index, offset in enumerate(range(0, len(archive_bytes), 262144)):
    data = archive_bytes[offset:offset+262144]
    key = f'out/{index:06}.part'
    fragments[key] = data
    parts.append({'key': key, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})

with tempfile.TemporaryDirectory() as temporary:
    restored = Path(temporary)
    counts = restore_archive(parts, lambda key: io.BytesIO(fragments[key]), restored,
                             hashlib.sha256(archive_bytes).hexdigest())
    assert counts == {'shard': 3}
    for memo, files in samples:
        for file in files:
            recovered = restored / 'cache' / 'memo' / 'shard' / memo.name / file.name
            assert recovered.read_bytes() == file.read_bytes()
print(json.dumps({'real_memos_restored': counts['shard'], 'bytes': len(archive_bytes), 'parts': len(parts)}))
