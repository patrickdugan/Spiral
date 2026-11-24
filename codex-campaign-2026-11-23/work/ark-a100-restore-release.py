"""Restore pinned public memo shards into an isolated A100 pilot directory."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
import time
from urllib.request import urlopen

RELEASE = "https://github.com/patrickdugan/zk-rusto-no-bitcoino/releases/download/ark-679-checkpoints-20261123/"
PART_NAME = re.compile(r"ark-679-checkpoints-[0-9]{3}\.tar")


def fetch_part(item, root, cutoff):
    name = item["name"]
    size = item["bytes"]
    if not PART_NAME.fullmatch(name) or not 0 < size <= 140 * 1024**2:
        raise ValueError("unexpected checkpoint release asset")
    path = root / name
    for attempt in range(3):
        if time.time() >= cutoff:
            raise TimeoutError("checkpoint deadline expired")
        try:
            with urlopen(RELEASE + name, timeout=22) as response, path.open("wb") as dest:
                shutil.copyfileobj(response, dest, length=4 * 1024**2)
            with path.open("rb") as body:
                digest = hashlib.file_digest(body, "sha256").hexdigest()
            if path.stat().st_size == size and digest == item["sha256"]:
                return path
        except OSError:
            pass
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("checkpoint release part failed integrity or HTTP checks")


def main():
    root = Path(sys.argv[1]).resolve()
    expected = sys.argv[2]
    cutoff = int(sys.argv[3])
    with urlopen(RELEASE + "manifest.json", timeout=30) as response:
        encoded = response.read(128 * 1024)
    if hashlib.sha256(encoded).hexdigest() != expected:
        raise RuntimeError("GitHub release manifest does not match its pin")
    manifest = json.loads(encoded)
    parts = manifest["assets"]
    if manifest["memo_counts"] != {"shard": 1727, "reduce": 6624} or not 1 <= len(parts) <= 128:
        raise RuntimeError("unexpected checkpoint inventory")
    with ThreadPoolExecutor(max_workers=8) as queue:
        jobs = [queue.submit(partial(fetch_part, root=root, cutoff=cutoff), item) for item in parts]
        for job in as_completed(jobs):
            part = job.result()
            with tarfile.open(part, "r:") as archive:
                archive.extractall(root, filter="data")
            part.unlink()
    (root / "cache" / "progress.jsonl").touch()


if __name__ == "__main__":
    main()
