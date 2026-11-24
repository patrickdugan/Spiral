"""Offload the public portion of the held height-679 memo into a release."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy
import subprocess
import tarfile
import time


WORK = Path(__file__).resolve().parent
DRIVE = Path(r"D:\Codex-offload\ark-679-checkpoints-delta-20261123")
RUN = WORK / "cashu-shinigami-pilot-a6e283d956"
TAG = "ark-679-checkpoints-delta-20261123"
OLD_TAG = "ark-679-checkpoints-20261123"
PART_BYTES = 128 * 1024**2
DELTA = {"shard": 1919, "reduce": 9302}
helpers = runpy.run_path(str(WORK / "release-ark-checkpoints.py"))
write_exact = helpers["write_exact"]
MEMO_NAME = helpers["MEMO_NAME"]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def emit(**fields):
    print(json.dumps(fields), flush=True)


def entries(stream):
    counts = Counter()
    seen = set()
    current = None
    fields = {}
    with tarfile.open(fileobj=stream, mode="r|") as source:
        for member in source:
            match = MEMO_NAME.fullmatch(member.name)
            if not (match and member.isreg() and 0 < member.size <= 4 * 1024**2):
                raise ValueError("input contains a non-public memo member")
            kind, key, filename = match.groups()
            entry = (kind, key)
            if current is None:
                current = entry
            if current != entry or entry in seen or filename in fields:
                raise ValueError("duplicate or incomplete memo entry")
            fields[filename] = source.extractfile(member).read()
            if filename != "manifest.json":
                continue
            manifest = json.loads(fields[filename])
            outputs = {"out0", "out1"} if manifest["out1_sha256"] is not None else {"out0"}
            if (set(fields) != outputs | {filename} or manifest["version"] != 1 or manifest["chunks"]
                    or (kind == "reduce" and manifest["out1_sha256"] is not None)):
                raise ValueError("entry does not contain only independent memo outputs")
            for field in outputs:
                if hashlib.sha256(fields[field]).digest() != bytes(manifest[field + "_sha256"]):
                    raise ValueError("corrupt memo output")
            counts[kind] += 1
            seen.add(entry)
            prefix = PurePosixPath(member.name).parent
            yield prefix, fields
            current = None
            fields = {}
    if current is not None or counts != DELTA:
        raise ValueError(f"unexpected audited inventory: {dict(counts)}")


def pack_memos(records, scratch, prefix_name):
    parts = []
    archive = None
    temporary = None

    def commit_part():
        archive.close()
        part = temporary.with_suffix("")
        temporary.replace(part)
        parts.append({"name": part.name, "bytes": part.stat().st_size, "sha256": sha256(part)})
        if len(parts) == 1 or len(parts) % 16 == 0:
            emit(stage="packing", verified_parts=len(parts))

    try:
        for prefix, fields in records:
            estimate = sum(512 + ((len(data) + 511) // 512) * 512 for data in fields.values())
            if archive is None or archive.offset + estimate > PART_BYTES - 10240:
                if archive is not None:
                    commit_part()
                temporary = scratch / f"{prefix_name}-{len(parts) + 1:03}.tar.tmp"
                archive = tarfile.open(temporary, "w", format=tarfile.USTAR_FORMAT)
            for name, data in fields.items():
                write_exact(archive, str(prefix / name), data)
        if archive is not None:
            commit_part()
    finally:
        if archive is not None and not archive.closed:
            archive.close()
    return parts


def pack(stream, scratch):
    return pack_memos(entries(stream), scratch, "ark-679-delta")


def part_metadata(path):
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def verify_remote(actual, expected):
    if set(actual) != {item["name"] for item in expected}:
        raise ValueError("GitHub release asset list differs from the staged list")
    for item in expected:
        found = actual[item["name"]]
        if (found["state"] != "uploaded" or found["size"] != item["bytes"]
                or found["digest"] != "sha256:" + item["sha256"]):
            raise ValueError(f"GitHub release asset verification failed for {item['name']}")


def complete_release(tag, name, target, body, scratch, expected):
    github = helpers["Releases"]()
    existing = github.api("GET", f"/releases/tags/{tag}", missing=True)
    if existing is not None and not existing["draft"]:
        release_id = int(existing["id"])
    else:
        release_id = github.draft(tag, target, name)
        emit(stage="uploading", release_id=release_id, assets=len(expected), tag=tag)
        initial = github.assets(release_id)

        def upload(item):
            github.ensure_asset(release_id, scratch / item["name"], item["sha256"], initial.copy())

        with ThreadPoolExecutor(max_workers=5) as pool:
            for index, _ in enumerate(pool.map(upload, expected), 1):
                if index == 1 or index % 8 == 0:
                    emit(stage="uploading", verified_assets=index, total_assets=len(expected), tag=tag)
        verify_remote(github.assets(release_id), expected)
        github.api("PATCH", f"/releases/{release_id}", {
            "draft": False, "prerelease": True, "make_latest": "false", "body": body,
        })

    observed = github.api("GET", f"/releases/tags/{tag}")
    if observed["id"] != release_id or observed["draft"] or not observed["prerelease"]:
        raise ValueError("could not verify the published Ark prerelease")
    verify_remote(github.assets(release_id), expected)
    return observed


def publish(scratch, parts):
    manifest = {
        "schema": "ark-sp1/resumable-memo-delta/v1",
        "sp1_revision": "b8387fa61e1361d90ee7de49f551863418ca0f08",
        "base_release": f"https://github.com/{helpers['REPO']}/releases/tag/{OLD_TAG}",
        "base_manifest_sha256": sha256(WORK / "ark-github-release" / "manifest.json"),
        "run_json_sha256": helpers["RUN_SHA"], "chain": "regtest", "height": 679,
        "policy_sats": 79440, "vtxos": 4,
        "delta_counts": DELTA, "public_total_counts": {"shard": 3646, "reduce": 15926},
        "held_nonpublic_core_entries": 775, "full_sp1_proof_verified": False,
        "m13_verified": False, "bitvm3_verified": False, "assets": parts,
    }
    metadata = scratch / "manifest.json"
    metadata.write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    checksums = scratch / "SHA256SUMS"
    checksums.write_text("".join(f"{part['sha256']}  {part['name']}\n" for part in parts), encoding="ascii")
    expected = parts + [part_metadata(metadata), part_metadata(checksums)]

    body = (
        "Reusable memo for the four-VTXO, 79,440-sat Ark regtest policy at height 679. "
        "This delta adds **1,919 core** and **9,302 recursion** entries. "
        "Together with the linked base it provides **3,646 core** and **15,926 recursion** entries.\n\n"
        f"Restore the [base snapshot]({manifest['base_release']}) first. Verify each release's `SHA256SUMS`, "
        "then extract each delta tar into the same directory so its `cache/memo/` tree overlays the base. "
        "Use the pinned SP1 revision and input digests in `cache/run.json`.\n\n"
        "775 additional core entries depend on raw traces and remain in the private recovery snapshot. "
        "Final SP1 compression, M13 verification and BitVM3 evaluation were pending when this checkpoint was taken."
    )
    observed = complete_release(TAG, "Ark height-679 checkpoint delta", helpers["TARGET"], body, scratch, expected)
    receipt = {"release": observed["html_url"], "release_id": observed["id"], "assets": expected,
               "scope": manifest["public_total_counts"], "archive_bytes": sum(part["bytes"] for part in parts)}
    (WORK / "ark-held-delta-release.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="ascii")
    for item in expected:
        path = scratch / item["name"]
        if path.resolve(strict=True).parent != scratch or path.is_symlink():
            raise ValueError("staging cleanup path is outside the D drive scratch directory")
        path.unlink()
    emit(stage="published", release=observed["html_url"], assets=len(expected), bytes=receipt["archive_bytes"])


def main():
    scratch = DRIVE.resolve()
    if scratch != DRIVE or not DRIVE.parent.is_dir():
        raise ValueError("unexpected D drive staging location")
    scratch.mkdir(exist_ok=True)
    work = "/mnt/c/" + WORK.as_posix().split(":/", 1)[1]
    source = ["wsl.exe", "-u", "root", "--", "python3", work + "/overnight-cache-stream.py",
              "/var/tmp/ark-asp-full-20261117/prover-transient",
              work + "/../outputs/ark-h100-pilot/checkpoint.tar", "--public-memos"]
    with subprocess.Popen(source, stdout=subprocess.PIPE) as producer:
        try:
            parts = pack(producer.stdout, scratch)
            if producer.stdout.read(64 * 1024).strip(b"\0") or producer.wait(timeout=30):
                raise ValueError("WSL memo verification failed")
        except BaseException:
            producer.terminate()
            raise
    emit(stage="packed", shards=len(parts), bytes=sum(part["bytes"] for part in parts))
    # Leave the laptop's upload bandwidth to the A100's restore seed while it is active.
    emit(stage="awaiting_spot_seed")
    seed = RUN / "seed-verified.json"
    journal = RUN / "seed-parts.jsonl"
    while not seed.is_file() and time.time() - journal.stat().st_mtime < 300:
        time.sleep(30)
    publish(scratch, parts)


if __name__ == "__main__":
    main()
