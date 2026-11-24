"""Emit a validated tar stream of held Ark memo entries missing from the public base."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

PIN = "a800d7026670d6d2a1240ea6e60d1f8171b2216ffe103b8e826cd36693ce3238"
KEY = re.compile(r"[a-f0-9]{64}")


def files_for(entry, manifest):
    outputs = {"out0": bytes(manifest["out0_sha256"])}
    if manifest["out1_sha256"] is not None:
        outputs["out1"] = bytes(manifest["out1_sha256"])
    chunks = manifest["chunks"]
    if chunks:
        index = entry / "chunks.json"
        if index.is_symlink() or json.loads(index.read_bytes())["ids"] != [item[0] for item in chunks]:
            raise ValueError(f"invalid chunk index: {entry.name}")
        outputs["chunks.json"] = None
        outputs.update({f"chunk{i}": bytes(digest) for i, (_, digest) in enumerate(chunks)})
    for name, expected in outputs.items():
        path = entry / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing memo file: {path}")
        if expected is not None:
            with path.open("rb") as handle:
                if hashlib.file_digest(handle, "sha256").digest() != expected:
                    raise ValueError(f"corrupt memo file: {path}")
        yield path


def base_index(archive):
    result = {}
    with tarfile.open(archive, "r:") as tar:
        for entry in tar:
            p = PurePosixPath(entry.name).parts
            if len(p) == 5 and p[:2] == ("cache", "memo") and p[4] == "manifest.json" and entry.isfile():
                result[(p[2], p[3])] = tar.extractfile(entry).read()
    if len(result) != 8351:
        raise ValueError("published checkpoint archive inventory mismatch")
    return result


def entries(root):
    for kind in ("shard", "reduce"):
        for entry in sorted((root / "memo" / kind).iterdir()):
            if KEY.fullmatch(entry.name) and entry.is_dir() and not entry.is_symlink():
                yield kind, entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    parser.add_argument("published_base", type=Path)
    parser.add_argument("--public-memos", action="store_true")
    args = parser.parse_args()
    root = args.cache.resolve(strict=True)
    if hashlib.sha256((root / "run.json").read_bytes()).hexdigest() != PIN:
        raise ValueError("held cache configuration does not match the pinned proving input")
    base = base_index(args.published_base)
    pending = []
    discarded = set(base)
    counts = {"shard": 0, "reduce": 0}
    for kind, entry in entries(root):
        counts[kind] += 1
        pair = kind, entry.name
        path = entry / "manifest.json"
        if path.is_symlink():
            raise ValueError("unexpected memo manifest link")
        manifest = path.read_bytes()
        discarded.discard(pair)
        if base.get(pair) != manifest:
            pending.append((kind, entry, manifest))
    if counts != {"shard": 4421, "reduce": 15926} or discarded:
        raise ValueError(f"held checkpoint set changed or does not contain the published base: {counts}")
    total_pending = len(pending)
    if args.public_memos:
        pending = [item for item in pending if not json.loads(item[2])["chunks"]]
        public_counts = {kind: sum(item[0] == kind for item in pending) for kind in counts}
        if public_counts != {"shard": 1919, "reduce": 9302} or total_pending - len(pending) != 775:
            raise ValueError(f"unexpected public memo inventory: {public_counts}")
    print(json.dumps({"cached": counts, "delta_entries": len(pending), "public": args.public_memos}),
          file=sys.stderr, flush=True)
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
        for kind, entry, encoded in pending:
            manifest = json.loads(encoded)
            if manifest["version"] != 1:
                raise ValueError("unsupported memo entry")
            prefix = f"cache/memo/{kind}/{entry.name}"
            for path in files_for(entry, manifest):
                tar.add(path, arcname=f"{prefix}/{path.name}", recursive=False)
            tar.add(entry / "manifest.json", arcname=f"{prefix}/manifest.json", recursive=False)


if __name__ == "__main__":
    main()
