from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import runpy
import tarfile
import tempfile
from types import SimpleNamespace


work = Path(__file__).resolve().parent
publisher = runpy.run_path(str(work / "publish-ark-spot-delta.py"))
restore = runpy.run_path(str(publisher["ARK"] / "scripts/restore_memo_releases.py"))
seed_sha = "a" * 64
public_prefix = "cache/memo/reduce/" + "b" * 64
private_prefix = "cache/memo/shard/" + "c" * 64
public_output = b"fixture certified memo bytes"
private_output = b"private trace-backed output"
trace = b"private raw witness trace"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def memo(prefix, output, chunks):
    manifest = {
        "version": 1, "chunks": chunks,
        "out0_sha256": list(hashlib.sha256(output).digest()), "out1_sha256": None,
    }
    return {f"{prefix}/out0": output, f"{prefix}/manifest.json": json.dumps(manifest).encode()}


def tar_bytes(members):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return stream.getvalue()


class FakeGitHub:
    def __init__(self):
        self.drafted = False
        self.published = False
        self.corrupt_post_publish = True
        self.uploads = {}

    def api(self, method, endpoint, data=None, missing=False):
        if method == "GET":
            if not self.drafted:
                assert missing
                return None
            return {"id": 17, "draft": not self.published,
                    "prerelease": self.published, "html_url": "https://example.test/release"}
        assert method == "PATCH" and endpoint == "/releases/17"
        assert data["draft"] is False and data["prerelease"] is True
        assert set(self.uploads) == {"ark-679-spot-001.tar", "manifest.json", "SHA256SUMS"}
        self.published = True

    def draft(self, tag, target, name):
        self.drafted = True
        return 17

    def assets(self, release_id):
        assert release_id == 17
        assets = {name: record.copy() for name, record in self.uploads.items()}
        if self.published and self.corrupt_post_publish:
            assets["ark-679-spot-001.tar"]["digest"] = "sha256:" + "0" * 64
        return assets

    def ensure_asset(self, release_id, path, expected, present):
        assert release_id == 17 and not self.published
        data = path.read_bytes()
        assert digest(data) == expected
        self.uploads[path.name] = {"state": "uploaded", "size": len(data), "digest": "sha256:" + expected}


def main(temp):
    private = memo(private_prefix, private_output, [[7, list(hashlib.sha256(trace).digest())]])
    private[f"{private_prefix}/chunks.json"] = b'{"ids":[7]}'
    private[f"{private_prefix}/chunk0"] = trace
    public = memo(public_prefix, public_output, [])
    encoded = tar_bytes(public | private)
    parts = {f"out/{i:06}.part": part for i, part in enumerate((encoded[:3072], encoded[3072:]))}
    batch = {"entries": 2, "parts": [
        {"key": key, "bytes": len(data), "sha256": digest(data)} for key, data in parts.items()
    ]}
    index = {"schema": "ark/spot-memo-export/v1", "seed_sha256": seed_sha,
             "entries": 2, "batches": [batch]}

    stage_root = temp / "stage"
    stage_root.mkdir()
    run_dir = temp / "run"
    run_dir.mkdir()
    (run_dir / "durable-memo-index.json").write_text(json.dumps(index))
    events = []
    store = SimpleNamespace(get_object=lambda **kwargs: {"Body": io.BytesIO(parts[kwargs["Key"]])})
    pilot = SimpleNamespace(name="check-0123456789", run_dir=run_dir, store=store,
                            note=lambda **event: events.append(event))
    github = FakeGitHub()
    publish = publisher["publish_spot"]
    publish.__globals__["Path"] = lambda path: stage_root
    publish.__globals__["shutil"] = SimpleNamespace(
        disk_usage=lambda path: SimpleNamespace(free=16 * 1024**3)
    )
    publisher["common"]["helpers"]["Releases"] = lambda: github

    try:
        publish(pilot, seed_sha)
    except ValueError as error:
        assert "asset verification failed" in str(error)
    else:
        raise AssertionError("corrupt hosted digest was accepted")
    assert github.published and not events
    assert not (run_dir / "spot-public-release.json").exists()
    stage = stage_root / "ark-679-spot-0123456789"
    manifest = json.loads((stage / "manifest.json").read_bytes())
    assert manifest["public_delta_counts"] == {"reduce": 1}
    assert manifest["excluded_trace_backed_counts"] == {"shard": 1}
    shard = manifest["assets"][0]
    raw = (stage / shard["name"]).read_bytes()
    assert trace not in raw and private_output not in raw
    destination = temp / "restore"
    counts = restore["restore_shard"](
        stage, shard, destination, run_pin=restore["RUN_PIN"], allow_run=False,
    )
    assert counts == Counter({"reduce": 1})
    assert (destination / public_prefix / "out0").read_bytes() == public_output

    github.corrupt_post_publish = False
    publish(pilot, seed_sha)
    assert not any(stage.iterdir())
    assert (run_dir / "spot-public-release.json").is_file() and len(events) == 1
    for malformed in (
        public | {f"{public_prefix}/chunk0": trace},
        public | {f"{public_prefix}/out0": b"changed"},
    ):
        try:
            list(publisher["batch_memos"](io.BytesIO(tar_bytes(malformed))))
        except ValueError:
            pass
        else:
            raise AssertionError("malformed public memo was accepted")
    print("Spot export fixture passed: draft, hosted SHA verification, restore, and gated cleanup")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(dir=work) as directory:
        main(Path(directory))
