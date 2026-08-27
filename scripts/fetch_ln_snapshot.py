"""Extract one public Lightning topology snapshot without downloading its full ZIP.

The source is the Harvard Dataverse dataset described by Valko and Marx Gomez
(2025), DOI 10.7910/DVN/2OAVO6. HTTP range reads are used to open the remote
ZIP, list members, and stream only the selected GML snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


DATASET_DOI = "10.7910/DVN/2OAVO6"
DATAFILE_ID = 12510549
ARCHIVE_NAME = "snapshots.geo.zip"
ARCHIVE_SIZE = 562_027_011
ARCHIVE_MD5 = "e6edd6fd7acae460abd0f70f71c9dbec"
DATAFILE_URL = f"https://dataverse.harvard.edu/api/access/datafile/{DATAFILE_ID}"


class HTTPRangeReader(io.RawIOBase):
    """Small seekable reader backed by cached HTTP byte-range requests."""

    def __init__(self, url: str, block_size: int = 1 << 20, cache_blocks: int = 12) -> None:
        super().__init__()
        self.source_url = url
        self.block_size = block_size
        self.cache_blocks = cache_blocks
        self.position = 0
        self.cache: OrderedDict[int, bytes] = OrderedDict()
        request = Request(
            url,
            headers={"Range": "bytes=0-0", "User-Agent": "Spiral-research-snapshot-fetcher/1.0"},
        )
        with urlopen(request, timeout=60) as response:
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes 0-0/(\d+)", content_range)
            if response.status != 206 or match is None:
                raise OSError("dataset server did not honor the required byte-range request")
            self.length = int(match.group(1))
            self.resolved_url = response.geturl()
            self.etag = response.headers.get("ETag", "")

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.length + offset
        else:
            raise ValueError(f"unknown seek mode: {whence}")
        if position < 0:
            raise OSError("negative seek position")
        self.position = min(position, self.length)
        return self.position

    def _block(self, index: int) -> bytes:
        if index in self.cache:
            self.cache.move_to_end(index)
            return self.cache[index]
        start = index * self.block_size
        end = min(self.length - 1, start + self.block_size - 1)
        request = Request(
            self.resolved_url,
            headers={
                "Range": f"bytes={start}-{end}",
                "User-Agent": "Spiral-research-snapshot-fetcher/1.0",
            },
        )
        with urlopen(request, timeout=90) as response:
            if response.status != 206:
                raise OSError(f"range request returned HTTP {response.status}")
            data = response.read()
        expected = end - start + 1
        if len(data) != expected:
            raise OSError(f"short range read: expected {expected}, received {len(data)}")
        self.cache[index] = data
        self.cache.move_to_end(index)
        while len(self.cache) > self.cache_blocks:
            self.cache.popitem(last=False)
        return data

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.length:
            return b""
        if size is None or size < 0:
            size = self.length - self.position
        size = min(size, self.length - self.position)
        chunks = []
        remaining = size
        while remaining:
            index = self.position // self.block_size
            offset = self.position % self.block_size
            block = self._block(index)
            take = min(remaining, len(block) - offset)
            chunks.append(block[offset : offset + take])
            self.position += take
            remaining -= take
        return b"".join(chunks)


def _snapshot_names(archive: zipfile.ZipFile) -> list[str]:
    return sorted(
        info.filename
        for info in archive.infolist()
        if not info.is_dir() and info.filename.endswith(".gml.geo")
    )


def select_member(names: list[str], requested: str) -> str:
    if not names:
        raise ValueError("archive contains no .gml.geo snapshots")
    if requested == "latest":
        return names[-1]
    exact = [name for name in names if name == requested or Path(name).name == requested]
    if len(exact) != 1:
        raise ValueError(f"snapshot member not found or ambiguous: {requested}")
    return exact[0]


def extract_snapshot(
    requested: str,
    output_dir: str | Path,
    list_only: bool = False,
) -> dict[str, object] | list[str]:
    reader = HTTPRangeReader(DATAFILE_URL)
    if reader.length != ARCHIVE_SIZE:
        raise OSError(f"archive size changed: expected {ARCHIVE_SIZE}, received {reader.length}")
    with zipfile.ZipFile(reader) as archive:
        names = _snapshot_names(archive)
        if list_only:
            return names
        selected = select_member(names, requested)
        info = archive.getinfo(selected)
        output = Path(output_dir).resolve()
        output.mkdir(parents=True, exist_ok=True)
        destination = (output / Path(selected).name).resolve()
        if output not in destination.parents:
            raise ValueError("snapshot destination escaped the output directory")
        digest = hashlib.sha256()
        with archive.open(info) as source, destination.open("wb") as target:
            while chunk := source.read(1 << 20):
                target.write(chunk)
                digest.update(chunk)
        try:
            local_file = destination.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            local_file = destination.as_posix()
        provenance = {
            "schema_version": "1.0",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "dataset_doi": DATASET_DOI,
            "dataverse_datafile_id": DATAFILE_ID,
            "archive_name": ARCHIVE_NAME,
            "archive_size": ARCHIVE_SIZE,
            "archive_md5_from_dataverse": ARCHIVE_MD5,
            "archive_etag": reader.etag,
            "member": selected,
            "member_crc32": f"{info.CRC:08x}",
            "member_compressed_size": info.compress_size,
            "member_uncompressed_size": info.file_size,
            "member_sha256": digest.hexdigest(),
            "local_file": local_file,
            "byte_range_extraction": True,
        }
        provenance_path = output / "snapshot_provenance.json"
        provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
        return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", default="latest", help="ZIP member basename or 'latest'")
    parser.add_argument("--output-dir", default="data/topology")
    parser.add_argument("--list", action="store_true", help="list available snapshot members only")
    args = parser.parse_args()
    result = extract_snapshot(args.member, args.output_dir, args.list)
    if args.list:
        print("\n".join(result))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
