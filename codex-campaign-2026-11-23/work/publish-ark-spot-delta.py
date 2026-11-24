"""Recover the Spot run's public memos from its private checksummed export."""
from collections import Counter
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import tarfile


WORK = Path(__file__).resolve().parent
common = runpy.run_path(str(WORK / "publish-ark-held-delta.py"))
ARK = WORK.parents[2] / "2026-11-15/new-chat/outputs/zk-rusto-no-bitcoino-ark/Ark"
validate_public_memo = runpy.run_path(str(ARK / "scripts/restore_memo_releases.py"))["validate_public_memo"]
MEMBER = re.compile(r"(cache/memo/(shard|reduce)/[a-f0-9]{64})/(manifest\.json|out[01]|chunks\.json|chunk[0-9]+)")
PART_SIZE = 16 * 1024**2
BATCH_LIMIT = 224 * 1024**2


def audit_entry(members, fields):
    if "manifest.json" not in fields:
        raise ValueError("Spot memo entry is missing its manifest")
    manifest = json.loads(fields["manifest.json"])
    if manifest["version"] != 1 or not isinstance(manifest["chunks"], list):
        raise ValueError("invalid Spot memo manifest")
    if manifest["chunks"]:
        return False
    if members != fields.keys():
        raise ValueError("self-contained Spot memo has unexpected trace files")
    validate_public_memo(manifest, fields)
    return True


def batch_memos(batch):
    with tarfile.open(fileobj=batch, mode="r:") as archive:
        current = None
        members = set()
        fields = {}
        for member in archive:
            match = MEMBER.fullmatch(member.name)
            if not match or not member.isfile() or member.size <= 0:
                raise ValueError("unexpected Spot memo tar member")
            prefix, kind, filename = match.groups()
            if current is not None and current[0] != prefix:
                yield (*current, fields, audit_entry(members, fields))
                fields = {}
                members = set()
            current = (prefix, kind)
            if filename in members:
                raise ValueError("duplicate Spot memo tar member")
            members.add(filename)
            if filename in {"manifest.json", "out0", "out1"}:
                if member.size > 4 * 1024**2:
                    raise ValueError("Spot memo output exceeds the supported size")
                fields[filename] = archive.extractfile(member).read()
        if current is not None:
            yield (*current, fields, audit_entry(members, fields))


def records(pilot, index, public, private):
    seen = set()
    serial = 0
    for batch in index["batches"]:
        if not 0 < sum(part["bytes"] for part in batch["parts"]) <= BATCH_LIMIT:
            raise ValueError("Spot export batch is outside the bounded size")
        with io.BytesIO() as encoded:
            for part in batch["parts"]:
                size = part["bytes"]
                key = f"out/{serial:06}.part"
                if key != part["key"] or serial >= 2048 or not 0 < size <= PART_SIZE:
                    raise ValueError("Spot export part index is invalid")
                with pilot.store.get_object(Bucket=pilot.name, Key=key)["Body"] as stream:
                    data = stream.read(size + 1)
                if len(data) != size or hashlib.sha256(data).hexdigest() != part["sha256"]:
                    raise ValueError("Spot export part digest differs from its checkpoint index")
                encoded.write(data)
                serial += 1
            encoded.seek(0)
            count = 0
            for prefix, kind, fields, eligible in batch_memos(encoded):
                if prefix in seen:
                    raise ValueError("Spot export includes a duplicate memo entry")
                seen.add(prefix)
                count += 1
                if eligible:
                    public[kind] += 1
                    yield PurePosixPath(prefix), fields
                else:
                    private[kind] += 1
            if count != batch["entries"]:
                raise ValueError("Spot export batch entry count differs from its index")
    if len(seen) != index["entries"]:
        raise ValueError("Spot export overall entry count differs from its index")


def publish_spot(pilot, seed_sha256):
    index_path = pilot.run_dir / "durable-memo-index.json"
    if not index_path.is_file():
        return
    index = json.loads(index_path.read_bytes())
    if index["schema"] != "ark/spot-memo-export/v1" or index["seed_sha256"] != seed_sha256:
        raise ValueError("durable Spot index belongs to a different seed")
    if not index["entries"]:
        return
    suffix = pilot.name[-10:]
    if not re.fullmatch("[a-f0-9]{10}", suffix):
        raise ValueError("invalid Spot campaign identifier")
    drive = Path(r"D:\Codex-offload") / ("ark-679-spot-" + suffix)
    if drive.resolve() != drive or not drive.parent.is_dir():
        raise ValueError("invalid D drive spot staging directory")
    approximate_bytes = sum(part["bytes"] for batch in index["batches"] for part in batch["parts"])
    if shutil.disk_usage(drive.parent).free < approximate_bytes + 8 * 1024**3:
        raise RuntimeError("Spot shards will remain in private storage because D has insufficient free space")
    drive.mkdir(exist_ok=True)

    public = Counter()
    private = Counter()
    parts = common["pack_memos"](records(pilot, index, public, private), drive, "ark-679-spot")
    if not parts:
        return
    helper = common["helpers"]
    upstream = f"https://github.com/{helper['REPO']}/releases/tag/"
    manifest = {
        "schema": "ark-sp1/resumable-spot-memo-delta/v1", "chain": "regtest", "height": 679,
        "policy_sats": 79440, "vtxos": 4, "run_json_sha256": helper["RUN_SHA"],
        "previous_releases": [upstream + common["OLD_TAG"], upstream + common["TAG"]],
        "private_seed_archive_sha256": seed_sha256, "public_delta_counts": dict(public),
        "excluded_trace_backed_counts": dict(private), "assets": parts,
    }
    metadata = drive / "manifest.json"
    metadata.write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    checksums = drive / "SHA256SUMS"
    checksums.write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in parts), encoding="ascii")
    expected = parts + [common["part_metadata"](metadata), common["part_metadata"](checksums)]
    body = (
        "Public, independently extractable Ark SP1 memo entries written by the eight-hour Spot campaign. "
        f"This delta adds **{public['shard']:,} core** and **{public['reduce']:,} recursion** entries. "
        "Verify SHA256SUMS and overlay the shards on the two earlier releases listed in the manifest. "
        "Entries requiring raw trace chunks remain in the private recovery snapshot. "
        "This release records resumable checkpoints only."
    )
    result = common["complete_release"]("ark-679-spot-" + suffix, "Ark height-679 Spot checkpoint delta",
                                         helper["TARGET"], body, drive, expected)
    (pilot.run_dir / "spot-public-release.json").write_text(
        json.dumps({"release": result["html_url"], "counts": dict(public), "assets": expected}, indent=2) + "\n",
        encoding="ascii",
    )
    for item in expected:
        path = drive / item["name"]
        if path.is_symlink() or path.resolve(strict=True).parent != drive:
            raise ValueError("Spot release cleanup path escaped the staging directory")
        path.unlink()
    pilot.note(spot_public_release=result["html_url"], spot_public_memos=dict(public))
