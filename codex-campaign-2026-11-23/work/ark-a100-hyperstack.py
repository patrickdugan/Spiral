"""Run the Ark checkpoint and the MNR-04 CPU proof on one Hyperstack A100."""
import argparse
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import json
from pathlib import Path
import re
import runpy
import shlex
import sys
import time

WORK = Path(__file__).resolve().parent
storage = runpy.run_path(str(WORK / "hyperstack-shinigami-storage.py"))
StoragePilot = storage["StoragePilot"]
common = storage["common"]
TransferConfig = storage["TransferConfig"]
StorageError = storage["ClientError"]
digest = storage["file_digest"]
emit = storage["emit"]

CHECKPOINT_SHA = "2ec3db943ca16b2380a38309ab92a1d381002277afb386bfbd4d47cc681afc96"
CHECKPOINT_SIZE = 15_722_516_480
RELEASE_MANIFEST = ("https://github.com/patrickdugan/zk-rusto-no-bitcoino/releases/download/"
                    "ark-679-checkpoints-20261123/manifest.json")


class ArkPilot(StoragePilot):
    object_keys = ("kit.tar.gz", "checkpoint.tar", "status.json", "results.tar.gz")

    def __init__(self, credential, artifact, checkpoint, results, release):
        super().__init__(credential, artifact, results)
        self.checkpoint = checkpoint
        self.release = release
        # The parent created this unique local state directory before assigning names.
        self.name = self.name.replace("cashu-shinigami-pilot-", "ark-mnr04-a100-")
        self.kit_sha = None

    def note(self, **fields):
        super().note(**fields)
        target = WORK / "hyperstack-ark-state.json"
        temp = self.run_dir / "display-state.tmp"
        temp.write_bytes((self.run_dir / "state.json").read_bytes())
        for attempt in range(5):
            try:
                temp.replace(target)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)

    def telemetry(self, stage, *, active):
        # Ark uses its own state channel and leaves the Shinigami receipt intact.
        pass

    def upload(self, path, name, expected_sha, parts):
        length = path.stat().st_size
        uploaded = 0
        next_milestone = 10
        counter_lock = threading.Lock()

        def progress(delta):
            nonlocal uploaded, next_milestone
            with counter_lock:
                uploaded += delta
                if uploaded * 100 >= length * next_milestone:
                    emit(stage="staging", artifact=name, percentage=next_milestone)
                    next_milestone += 10

        chunk = 5 * 1024**2
        self.store.upload_file(
            str(path), self.name, name,
            ExtraArgs={"Metadata": {"sha256": expected_sha}},
            Config=TransferConfig(multipart_threshold=chunk, multipart_chunksize=chunk, max_concurrency=parts),
            Callback=progress,
        )
        remote = self.store.head_object(Bucket=self.name, Key=name)
        stored = remote["ContentLength"]
        if stored != length:
            raise RuntimeError(f"staged {name} has {stored} bytes, expected {length}")
        if name == "kit.tar.gz":
            sha = hashlib.sha256()
            step = 2 * 1024**2

            def read_range(offset):
                end = min(offset + step, length) - 1
                for attempt in range(3):
                    try:
                        obj = self.store.get_object(Bucket=self.name, Key=name, Range=f"bytes={offset}-{end}")
                        with obj["Body"] as body:
                            chunk = body.read()
                        if len(chunk) == end - offset + 1:
                            return chunk
                    except Exception:
                        pass
                    time.sleep(1 + attempt)
                raise RuntimeError(f"private kit could not be verified at byte range {offset}-{end}")

            with ThreadPoolExecutor(max_workers=4) as readers:
                for chunk in readers.map(read_range, range(0, length, step)):
                    sha.update(chunk)
            if sha.hexdigest() != expected_sha:
                raise RuntimeError("private kit readback differs from its pinned SHA-256")

    def cloud_init(self, deadline):
        names = self.object_keys
        urls = {
            name: self.store.generate_presigned_url(
                "get_object" if name in names[:2] else "put_object",
                Params={"Bucket": self.name, "Key": name},
                ExpiresIn=3690,
            )
            for name in names
        }
        variables = {
            "kit_url": urls["kit.tar.gz"], "checkpoint_url": urls["checkpoint.tar"],
            "status_url": urls["status.json"], "result_url": urls["results.tar.gz"],
            "kit_sha": self.kit_sha, "checkpoint_sha": CHECKPOINT_SHA, "deadline": str(deadline),
            "release_manifest_sha": digest(self.release) if self.release else "",
            "kit_size": str(self.artifact.stat().st_size),
        }
        assignment = "\n".join(f"{name}={shlex.quote(value)}" for name, value in variables.items())
        return "#!/usr/bin/env bash\n" + assignment + "\n" + (WORK / "ark-a100-bootstrap.sh").read_text()

    def run(self):
        if not self.release and (self.checkpoint.stat().st_size != CHECKPOINT_SIZE or digest(self.checkpoint) != CHECKPOINT_SHA):
            raise RuntimeError("saved checkpoint copy differs from the pinned archive")
        if any(vm["name"].startswith("ark-mnr04-a100-") for vm in self.inventory()):
            raise RuntimeError("a pilot with the same purpose is already present")
        self.initialize_storage()
        if not self.release:
            self.upload(self.checkpoint, "checkpoint.tar", CHECKPOINT_SHA, 3)
            emit(stage="saved_checkpoint_staged", bytes=CHECKPOINT_SIZE, sha256=CHECKPOINT_SHA)

        ready = self.artifact.with_suffix(".ready")
        preparation_cutoff = time.monotonic() + 2400
        while not ready.is_file():
            if time.monotonic() >= preparation_cutoff:
                raise TimeoutError("CPU prebuild did not stage the pinned GPU and Nova kit")
            time.sleep(10)
        self.kit_sha = ready.read_text(encoding="ascii").strip()
        if not re.fullmatch("[0-9a-f]{64}", self.kit_sha) or digest(self.artifact) != self.kit_sha:
            raise RuntimeError("assembled proof kit differs from the locally verified SHA-256")
        self.upload(self.artifact, "kit.tar.gz", self.kit_sha, 3)
        emit(stage="kit_staged", bytes=self.artifact.stat().st_size)
        if self.release:
            emit(stage="waiting_for_verified_github_memo_shards")
            release_cutoff = time.monotonic() + 3600
            while time.monotonic() < release_cutoff:
                if self.release.is_file():
                    local = self.release.read_bytes()
                    release = json.loads(local)
                    if release["source_archive_sha256"] != CHECKPOINT_SHA:
                        raise RuntimeError("public memo shard release is from the wrong saved checkpoint")
                    try:
                        with urlopen(RELEASE_MANIFEST, timeout=12) as response:
                            public = response.read(128 * 1024)
                    except (HTTPError, URLError, TimeoutError):
                        public = None
                    if public == local:
                        break
                time.sleep(20)
            else:
                raise TimeoutError("GitHub memo shards are not publicly retrievable within the staging window")

        deadline = int(time.time()) + 3540
        self.cutoff = time.monotonic() + 3540
        self.launch(self.cloud_init(deadline))
        next_inventory = 0
        last = None
        for _ in common["iteration_until"](self.cutoff - 40):
            if time.monotonic() >= next_inventory:
                vm = self.vm(missing_ok=True)
                if vm is None or vm["status"] in {"DELETED", "FAILED", "ERROR"}:
                    raise RuntimeError("pilot VM exited before the result was exported")
                if any(rule.get("direction", "").lower() == "ingress" for rule in vm.get("security_rules", [])):
                    raise RuntimeError("unexpected inbound access on the pilot")
                next_inventory = time.monotonic() + 45
            try:
                status = self.status()
            except (OSError, TimeoutError, StorageError):
                continue
            if not status:
                continue
            stage = status["stage"]
            if stage != last:
                emit(stage=stage, vm_id=self.vm_id)
                self.note(stage=stage)
                last = stage
            if stage == "failed":
                raise RuntimeError(f"VM failed in phase {status.get('phase', 'unknown')}")
            if stage == "finished":
                size = int(status["artifact_bytes"])
                sha = status["artifact_sha256"]
                if not 0 < size <= 512 * 1024**2 or re.fullmatch("[0-9a-f]{64}", sha) is None:
                    raise RuntimeError("invalid cloud result metadata")
                artifact = self.run_dir / "results.tar.gz"
                self.store.download_file(self.name, "results.tar.gz", str(artifact))
                if artifact.stat().st_size != size or digest(artifact) != sha:
                    raise RuntimeError("cloud result differs from its transport manifest")
                self.note(stage="results_retrieved", result_sha256=sha)
                emit(stage="results_retrieved", sha256=sha, path=str(artifact))
                return
        raise TimeoutError("one-hour pilot budget reached before results were retrieved")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--state-directory", type=Path, default=WORK)
    parser.add_argument("--released-checkpoints", type=Path)
    args = parser.parse_args()
    credential = args.key_file.read_text(encoding="utf-8-sig").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", credential):
        raise SystemExit("Hyperstack credential file has an unexpected format")
    pilot = ArkPilot(credential, args.kit, args.checkpoint, args.state_directory, args.released_checkpoints)
    exit_code = 0
    try:
        pilot.run()
    except (Exception, KeyboardInterrupt) as exc:
        # Credentialed transport errors can contain signed URLs. The bounded API
        # wrapper already redacts those. Other errors are reported by type only.
        kind = type(exc).__name__
        detail = str(exc) if type(exc) in (RuntimeError, TimeoutError) else ""
        emit(error=kind, detail=detail)
        exit_code = 1
    finally:
        for cleanup in (pilot.cleanup, pilot.clean_storage):
            try:
                cleanup()
            except Exception as exc:
                emit(cleanup_error=type(exc).__name__, resource=pilot.name, vm_id=pilot.vm_id)
                exit_code = 1
        for key_file in [pilot.ssh_key, pilot.ssh_key.with_suffix(".pub")]:
            key_file.unlink(missing_ok=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())


