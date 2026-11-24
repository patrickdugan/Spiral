"""Restore a checksummed seed and continuously export immutable Ark memo entries."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time
from urllib.request import Request, urlopen

ENTRY = re.compile(r"[a-f0-9]{64}")
MEMBER = re.compile(r"cache/memo/(shard|reduce)/[a-f0-9]{64}/(manifest\.json|out[01]|chunks\.json|chunk[0-9]+)")
SIZE = 16 * 1024**2
BATCH = 192 * 1024**2


def network(url, data=None, maximum=None):
    for attempt in range(5):
        try:
            request = Request(url, data=data, method="PUT" if data is not None else "GET")
            with urlopen(request, timeout=32) as response:
                return response.read(maximum)
        except (OSError, TimeoutError):
            if attempt == 4:
                raise
            time.sleep(2 + attempt * 2)


def checkpoint_paths(root):
    for kind in ("shard", "reduce"):
        for entry in (root / "cache/memo" / kind).iterdir():
            if ENTRY.fullmatch(entry.name) and entry.is_dir() and not entry.is_symlink():
                yield entry


def restore(root, config):
    seed = config["seed"]
    digest = hashlib.sha256()

    def get(item):
        data = network(item["url"], maximum=item["bytes"] + 1)
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise RuntimeError("bad private seed fragment")
        return data

    class Reader(io.RawIOBase):
        def __init__(self, pool):
            self.pool = pool
            self.tasks = deque()
            self.items = iter(seed["parts"])
            self.current = memoryview(b"")
            for _ in range(12):
                self.schedule()

        def schedule(self):
            item = next(self.items, None)
            if item is not None:
                self.tasks.append(self.pool.submit(get, item))

        def readable(self):
            return True

        def readinto(self, target):
            if not self.current:
                if not self.tasks:
                    return 0
                part = self.tasks.popleft().result()
                digest.update(part)
                self.current = memoryview(part)
                self.schedule()
            size = min(len(target), len(self.current))
            target[:size] = self.current[:size]
            self.current = self.current[size:]
            return size

    with ThreadPoolExecutor(max_workers=8) as pool:
        with io.BufferedReader(Reader(pool)) as stream:
            with tarfile.open(fileobj=stream, mode="r|") as archive:
                for item in archive:
                    if not item.isfile() or not MEMBER.fullmatch(item.name):
                        raise ValueError("unexpected private seed member")
                    archive.extract(item, root, filter="data")
            while stream.read(64 * 1024):
                pass
    if digest.hexdigest() != seed["sha256"]:
        raise RuntimeError("private seed stream digest mismatch")
    counts = {"shard": 0, "reduce": 0}
    for entry in checkpoint_paths(root):
        counts[entry.parent.name] += 1
    if counts != {"shard": 4421, "reduce": 15926}:
        raise RuntimeError("restored seed differs from the held checkpoint inventory")
    (root / "seed-restored.json").write_text(json.dumps(counts), encoding="ascii")


def export(root, config):
    # The seed is complete before this snapshot. The prover starts after the
    # exporter writes its ready marker, so every later memo directory is new.
    seen = set(checkpoint_paths(root))
    index = {"schema": "ark/spot-memo-export/v1", "seed_sha256": config["seed"]["sha256"],
             "updated_at_unix": int(time.time()), "batches": [], "entries": 0}
    network(config["index_url"], json.dumps(index).encode())
    (root / "checkpoint-export-ready").touch()
    serial = 0

    def publish(entries):
        nonlocal serial
        parts = []
        spool = root / "current-delta.tar"
        with tarfile.open(spool, "w") as tar:
            for entry in entries:
                for path in sorted(entry.iterdir()):
                    label = path.relative_to(root).as_posix()
                    if path.is_symlink() or not path.is_file() or not MEMBER.fullmatch(label):
                        raise ValueError("unexpected output memo layout")
                    tar.add(path, arcname=label, recursive=False)
        with spool.open("rb") as handle:
            while data := handle.read(SIZE):
                if serial >= len(config["output_urls"]):
                    raise RuntimeError("durable checkpoint object budget exhausted")
                network(config["output_urls"][serial], data)
                parts.append({"key": f"out/{serial:06}.part", "sha256": hashlib.sha256(data).hexdigest(),
                              "bytes": len(data)})
                serial += 1
        index["entries"] += len(entries)
        index["batches"].append({"parts": parts, "entries": len(entries)})
        index["updated_at_unix"] = int(time.time())
        network(config["index_url"], json.dumps(index).encode())
        spool.unlink()
        seen.update(entries)

    def scan():
        pending = []
        size = 0
        for entry in sorted(set(checkpoint_paths(root)) - seen):
            entry_bytes = sum(path.stat().st_size for path in entry.iterdir())
            if pending and size + entry_bytes > BATCH:
                publish(pending)
                pending, size = [], 0
            pending.append(entry)
            size += entry_bytes
        if pending:
            publish(pending)

    while True:
        finishing = (root / "stop-export").exists()
        scan()
        (root / "checkpoint-export-ok").touch()
        if finishing:
            (root / "checkpoint-export-finished").touch()
            return
        time.sleep(75)


def main():
    root = Path(sys.argv[2]).resolve(strict=True)
    config = json.loads((root / "transport.json").read_text())
    {"restore": restore, "export": export}[sys.argv[1]](root, config)


if __name__ == "__main__":
    main()
