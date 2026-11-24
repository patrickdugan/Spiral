"""Privately stage the newer held Ark memo and hand it to the overnight runner."""
import argparse
import base64
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import time

WORK = Path(__file__).resolve().parent
prior = runpy.run_path(str(WORK / "ark-a100-hyperstack.py"))
ArkPilot = prior["ArkPilot"]
emit = prior["emit"]
CHUNK = 4 * 1024**2
LINUX = "/mnt/c/Users/patri/Documents/Codex/2026-11-23/the-goal-is-paused-at-the"
CACHE = "/var/tmp/ark-asp-full-20261117/prover-transient"


def valid_kit(artifact):
    pin = artifact.with_suffix(".ready").read_text(encoding="ascii").strip()
    if not re.fullmatch("[a-f0-9]{64}", pin) or prior["digest"](artifact) != pin:
        raise RuntimeError("pinned A100 kit hash mismatch")
    return pin


def stage(pilot):
    upstream = ["wsl.exe", "-u", "root", "--", "/usr/bin/python3",
                f"{LINUX}/work/overnight-cache-stream.py", CACHE,
                f"{LINUX}/outputs/ark-h100-pilot/checkpoint.tar"]
    rows = []
    stream_sha = hashlib.sha256()
    byte_count = 0

    def send(index, data):
        name = f"seed/{index:06}.part"
        digest = hashlib.sha256(data).hexdigest()
        md5 = base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode()
        for attempt in range(7):
            try:
                pilot.store.put_object(Bucket=pilot.name, Key=name, Body=data, ContentMD5=md5)
                return {"key": name, "bytes": len(data), "sha256": digest}
            except Exception:
                time.sleep(min(30, 2**attempt))
        raise RuntimeError(f"private seed transfer failed at part {index}")

    with (pilot.run_dir / "seed-verifier.log").open("wb") as log:
        with subprocess.Popen(upstream, stdout=subprocess.PIPE, stderr=log) as producer:
            with ThreadPoolExecutor(max_workers=10) as pool:
                pending = deque()
                with (pilot.run_dir / "seed-parts.jsonl").open("w", encoding="ascii") as journal:
                    def collect():
                        nonlocal byte_count
                        record = pending.popleft().result()
                        rows.append(record)
                        journal.write(json.dumps(record) + "\n")
                        journal.flush()
                        byte_count += record["bytes"]
                        if len(rows) % 64 == 0:
                            emit(stage="private_checkpoint_staging", uploaded_bytes=byte_count, parts=len(rows))
                        if byte_count > 32 * 1024**3:
                            raise RuntimeError("checkpoint exceeded planned storage cap")

                    try:
                        for index in range(8192):
                            data = producer.stdout.read(CHUNK)
                            if not data:
                                break
                            stream_sha.update(data)
                            pending.append(pool.submit(send, index, data))
                            if len(pending) >= 20:
                                collect()
                        while pending:
                            collect()
                    except BaseException:
                        producer.terminate()
                        raise
            if producer.wait(timeout=30) != 0 or byte_count < 8 * 1024**3:
                raise RuntimeError("held cache source verification did not finish")
    index = {"parts": rows, "sha256": stream_sha.hexdigest(), "bytes": byte_count,
             "core": 4421, "recursion": 15926}
    (pilot.run_dir / "seed-verified.json").write_text(json.dumps(index), encoding="ascii")
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("key_file", type=Path)
    args = parser.parse_args()
    credential = args.key_file.read_text(encoding="utf-8-sig").strip()
    kit = WORK / "ark-a100-prebuilt.tar.gz"
    manifest = WORK / "ark-github-release/manifest.json"
    pilot = ArkPilot(credential, kit, None, WORK, manifest)
    pilot.kit_sha = valid_kit(kit)
    try:
        if pilot.inventory():
            raise RuntimeError("an account VM is already present; overnight single-instance preflight stopped")
        pilot.initialize_storage()
        emit(stage="private_checkpoint_staging", resource=pilot.name)
        index = stage(pilot)
        pilot.upload(kit, "kit.tar.gz", pilot.kit_sha, 3)
        pilot.note(stage="overnight_staged", seed_sha256=index["sha256"], seed_bytes=index["bytes"])
        emit(stage="overnight_staged", bytes=index["bytes"], parts=len(index["parts"]))
        follow = WORK / "ark-overnight-launch.py"
        end = time.monotonic() + 3600
        while not follow.is_file() and time.monotonic() < end:
            time.sleep(5)
        if not follow.is_file():
            raise TimeoutError("overnight launcher preparation timed out")
        runpy.run_path(str(follow))["launch_overnight"](pilot, index)
    except BaseException as error:
        emit(stage="overnight_ended", error=type(error).__name__,
             detail=str(error) if isinstance(error, (RuntimeError, TimeoutError)) else "")
        raise SystemExit(1)
    finally:
        try:
            pilot.cleanup()
        finally:
            if pilot.storage_requested:
                for key in pilot.storage_keys():
                    pilot.api("DELETE", f"object-storage/access-keys/{int(key['id'])}", missing_ok=True)
            for path in (pilot.ssh_key, pilot.ssh_key.with_suffix(".pub")):
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
