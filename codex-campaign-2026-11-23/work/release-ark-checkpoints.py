"""Publish the self-contained Ark proof memo as independently extractable tar assets."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPO = "patrickdugan/zk-rusto-no-bitcoino"
TAG = "ark-679-checkpoints-20261123"
BASE = "https://api.github.com/repos/" + REPO
TARGET = "a183eeffe63715cedca729100a1f74267a68200d"
CHECKPOINT_SHA = "2ec3db943ca16b2380a38309ab92a1d381002277afb386bfbd4d47cc681afc96"
RUN_SHA = "a800d7026670d6d2a1240ea6e60d1f8171b2216ffe103b8e826cd36693ce3238"
MEMO_NAME = re.compile(r"cache/memo/(shard|reduce)/([a-f0-9]{64})/(manifest\.json|out[01])\Z")
PART_LIMIT = 128 * 1024**2


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def credential():
    payload = f"protocol=https\nhost=github.com\npath={REPO}.git\n\n"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    lookup = subprocess.run(["git", "credential", "fill"], input=payload, text=True,
                            capture_output=True, check=True, env=env, timeout=15)
    fields = dict(line.split("=", 1) for line in lookup.stdout.splitlines() if "=" in line)
    if not fields.get("password"):
        raise RuntimeError("No saved GitHub credential with release access")
    return fields["password"]


class Releases:
    def __init__(self):
        self.headers = {
            "Authorization": "Bearer " + credential(), "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Ark-checkpoint-release",
        }
        self.opener = build_opener(NoRedirect())

    def api(self, method, path, body=None, missing=False):
        headers = {**self.headers, "Content-Type": "application/json"}
        data = json.dumps(body).encode() if body is not None else None
        request = Request(BASE + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=35) as response:
                return json.load(response) if response.status != 204 else None
        except HTTPError as error:
            if missing and error.code == 404:
                return None
            raise RuntimeError(f"GitHub {method} {path} returned HTTP {error.code}") from None

    def assets(self, release_id):
        rows = []
        for page in range(1, 12):
            part = self.api("GET", f"/releases/{release_id}/assets?per_page=100&page={page}")
            rows.extend(part)
            if len(part) < 100:
                return {row["name"]: row for row in rows}
        raise RuntimeError("Unexpected release asset count")

    def draft(self, tag=TAG, target=TARGET, name="Ark height-679 resumable checkpoint shards"):
        release = self.api("GET", f"/releases/tags/{tag}", missing=True)
        if release is None:
            existing = self.api("GET", "/releases?per_page=100")
            release = next((row for row in existing if row["tag_name"] == tag), None)
        if release is None:
            release = self.api("POST", "/releases", {
                "tag_name": tag, "target_commitish": target, "name": name,
                "body": "Staging audited proof memo entries for an incomplete SP1 run.",
                "draft": True, "prerelease": True, "make_latest": "false",
            })
        if not release["draft"]:
            raise RuntimeError("Requested release tag is already published")
        return int(release["id"])

    def ensure_asset(self, release_id, file, expected, present):
        upload_path = f"/repos/{REPO}/releases/{release_id}/assets?name={quote(file.name)}"
        headers = {**self.headers, "Content-Type": "application/octet-stream",
                   "Content-Length": str(file.stat().st_size)}
        for attempt in range(3):
            existing = present.get(file.name)
            if existing and existing["state"] == "starter" and existing.get("digest") is None:
                self.api("DELETE", f"/releases/assets/{int(existing['id'])}")
                present.pop(file.name, None)
                existing = None
            if existing:
                if existing["digest"] == "sha256:" + expected and existing["size"] == file.stat().st_size:
                    return
                raise RuntimeError(f"Conflicting existing release asset: {file.name}")
            connection = http.client.HTTPSConnection("uploads.github.com", timeout=90)
            try:
                with file.open("rb") as body:
                    connection.request("POST", upload_path, body=body, headers=headers)
                    response = connection.getresponse()
                    if response.status == 201:
                        asset = json.load(response)
                        if asset["size"] != file.stat().st_size or asset["digest"] != "sha256:" + expected:
                            raise RuntimeError("GitHub asset digest or length differs from local shard")
                        present[file.name] = asset
                        return
                    if response.status not in {422, 429, 502, 503, 504}:
                        raise RuntimeError(f"GitHub upload returned HTTP {response.status}")
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(3 * (attempt + 1))
            present.update(self.assets(release_id))
        raise RuntimeError(f"GitHub upload did not complete for {file.name}")


def members(tar):
    groups = defaultdict(dict)
    run = None
    for member in tar:
        match = MEMO_NAME.fullmatch(member.name)
        if match:
            if not member.isreg() or not 0 < member.size <= 2**22:
                raise RuntimeError("Unexpected memo entry type or size")
            kind, key, filename = match.groups()
            entry = groups[kind, key]
            if filename in entry:
                raise RuntimeError("Duplicate memo entry")
            entry[filename] = member
        elif member.name == "cache/run.json" and member.isreg() and member.size <= 8192:
            if run is not None:
                raise RuntimeError("Duplicate run.json")
            run = tar.extractfile(member).read()
    if run is None or hashlib.sha256(run).hexdigest() != RUN_SHA:
        raise RuntimeError("Archived run configuration differs from expected pin")
    counts = {kind: sum(entry[0] == kind for entry in groups) for kind in ("shard", "reduce")}
    if counts != {"shard": 1727, "reduce": 6624}:
        raise RuntimeError("Unexpected memo entry counts")
    return groups, run, counts


def write_exact(tar, name, data):
    header = tarfile.TarInfo(name)
    header.size = len(data)
    header.mode = 0o644
    tar.addfile(header, io.BytesIO(data))


def write_shards(archive, work, on_part):
    with tarfile.open(archive, "r:") as tar:
        groups, run, counts = members(tar)
        part = 1
        name = lambda i: work / f"ark-679-checkpoints-{i:03}.tar"
        shard = tarfile.open(name(part), "w")
        write_exact(shard, "cache/run.json", run)
        try:
            for (kind, _), files in groups.items():
                expected = {"manifest.json", "out0", "out1"} if kind == "shard" else {"manifest.json", "out0"}
                if set(files) != expected:
                    raise RuntimeError("Incomplete cached proof entry")
                estimate = sum(entry.size + 1024 for entry in files.values())
                if shard.offset + estimate > PART_LIMIT:
                    shard.close()
                    on_part(name(part))
                    part += 1
                    shard = tarfile.open(name(part), "w")
                manifest = tar.extractfile(files["manifest.json"]).read()
                fields = json.loads(manifest)
                if fields["version"] != 1 or fields["chunks"]:
                    raise RuntimeError("Memo entry is not self-contained")
                write_exact(shard, files["manifest.json"].name, manifest)
                for output in sorted(expected - {"manifest.json"}):
                    data = tar.extractfile(files[output]).read()
                    if hashlib.sha256(data).digest() != bytes(fields[output + "_sha256"]):
                        raise RuntimeError("Memo proof output digest mismatch")
                    write_exact(shard, files[output].name, data)
        finally:
            shard.close()
        on_part(name(part))
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=True)
    with args.archive.open("rb") as archive:
        if hashlib.file_digest(archive, "sha256").hexdigest() != CHECKPOINT_SHA:
            raise RuntimeError("Source checkpoint archive does not match its pin")

    github = Releases() if args.publish else None
    release_id = github.draft() if github else None
    remote = github.assets(release_id) if github else {}
    assembled = []
    if release_id:
        print(json.dumps({"draft_release": release_id, "tag": TAG}), flush=True)

    def publish_part(file):
        with file.open("rb") as body:
            sha = hashlib.file_digest(body, "sha256").hexdigest()
        if github:
            github.ensure_asset(release_id, file, sha, remote)
        artifact = {"name": file.name, "bytes": file.stat().st_size, "sha256": sha}
        file.unlink()
        return artifact

    workers = 5
    with ThreadPoolExecutor(max_workers=workers) as queue:
        pending = []

        def collect():
            artifact = pending.pop(0).result()
            assembled.append(artifact)
            if len(assembled) == 1 or len(assembled) % 8 == 0:
                print(json.dumps({"validated_assets": len(assembled), "latest": artifact["name"]}), flush=True)

        def stage(file):
            pending.append(queue.submit(publish_part, file))
            if len(pending) >= workers + 2:
                collect()

        counts = write_shards(args.archive, args.scratch, stage)
        while pending:
            collect()
    manifest = {
        "schema": "ark-sp1/resumable-memo-release/v1", "sp1_revision": "b8387fa61e1361d90ee7de49f551863418ca0f08",
        "chain": "regtest", "height": 679, "vtxos": 4, "policy_sats": 79440,
        "source_archive_sha256": CHECKPOINT_SHA, "run_json_sha256": RUN_SHA,
        "memo_counts": counts, "full_sp1_proof_verified": False, "m13_verified": False,
        "bitvm3_onchain_verified": False, "assets": list(assembled),
    }
    info = args.scratch / "manifest.json"
    info.write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    sums = args.scratch / "SHA256SUMS"
    sums.write_text("".join(f"{row['sha256']}  {row['name']}\n" for row in assembled), encoding="ascii")
    if github:
        github.ensure_asset(release_id, info, hashlib.sha256(info.read_bytes()).hexdigest(), remote)
        github.ensure_asset(release_id, sums, hashlib.sha256(sums.read_bytes()).hexdigest(), remote)
        actual = github.assets(release_id)
        if set(actual) != {a["name"] for a in assembled} | {info.name, sums.name}:
            raise RuntimeError("Remote release asset inventory differs from manifest")
        for shard in assembled:
            asset = actual[shard["name"]]
            if asset["state"] != "uploaded" or asset["size"] != shard["bytes"] or asset["digest"] != "sha256:" + shard["sha256"]:
                raise RuntimeError("Remote release asset differs from verified manifest")
        body = (
            "Reusable SP1 proof memo for the historical four-VTXO Ark regtest policy at height 679. "
            f"This snapshot contains **{counts['shard']:,} core** and **{counts['reduce']:,} recursion** entries.\n\n"
            "Each tar asset extracts independently into one new directory. Run `sha256sum -c SHA256SUMS`, "
            "then extract every tar into that directory with `tar -xf <part> -C <new-directory>`. "
            "The resulting `cache/` directory contains the pinned run configuration and complete memo entries. "
            "The prover must use the matching guest and inputs whose digests are listed in `cache/run.json`.\n\n"
            "This is a resumable checkpoint snapshot. SP1 compression, SDK verification, M13 and final BitVM3 checks remain separate. "
            "Raw trace storage, source inputs, Shinigami data and M14 setup material are excluded."
        )
        released = github.api("PATCH", f"/releases/{release_id}", {
            "draft": False, "prerelease": True, "make_latest": "false", "body": body,
        })
        if released["draft"] or released["tag_name"] != TAG:
            raise RuntimeError("GitHub did not confirm release publication")
        print(json.dumps({"published": released["html_url"], "assets": len(actual), "counts": counts}), flush=True)


if __name__ == "__main__":
    main()
