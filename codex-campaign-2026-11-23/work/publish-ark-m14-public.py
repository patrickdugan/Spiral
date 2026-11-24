"""Shard the verified M14 public setup files without accessing private state."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import time


WORK = Path(__file__).resolve().parent
ARK = WORK.parents[2] / "2026-11-15" / "new-chat" / "outputs" / "zk-rusto-no-bitcoino-ark" / "Ark"
PUBLIC = "/var/tmp/ark-asp-full-20261117/m14-public-file-backed-20261123/claim-public/"
DRIVE = Path(r"D:\Codex-offload\ark-679-m14-public-20261123")
TAG = "ark-679-m14-public-setup-20261123"
PART_SIZE = 128 * 1024**2
ALLOWED = {"ciphertexts.bin", "input-commitments.bin"}
common = runpy.run_path(str(WORK / "publish-ark-held-delta.py"))


def split_verified(directory, name, expected):
    metadata = []
    digest = hashlib.sha256()
    remaining = expected["bytes"]
    command = ["wsl.exe", "-u", "root", "--", "cat", "--", PUBLIC + name]
    with subprocess.Popen(command, stdout=subprocess.PIPE) as producer:
        try:
            while remaining:
                label = f"{name}.part-{len(metadata) + 1:03}"
                path = directory / label
                need = min(PART_SIZE, remaining)
                with path.open("wb") as target:
                    while need:
                        chunk = producer.stdout.read(min(2 * 1024**2, need))
                        if not chunk:
                            raise EOFError(f"vetted M14 public artifact {name} ended early")
                        target.write(chunk)
                        digest.update(chunk)
                        need -= len(chunk)
                        remaining -= len(chunk)
                metadata.append(common["part_metadata"](path))
                if len(metadata) == 1 or len(metadata) % 16 == 0:
                    common["emit"](stage="m14_public_packing", artifact=name, shards=len(metadata))
            if producer.stdout.read(1) or producer.wait(timeout=20):
                raise ValueError("M14 public artifact exceeds its verified length")
        except BaseException:
            producer.terminate()
            raise
    if digest.hexdigest() != expected["sha256"]:
        raise ValueError(f"full hash changed for the verified M14 public artifact {name}")
    return metadata


def main():
    if DRIVE.resolve() != DRIVE or not DRIVE.parent.is_dir():
        raise ValueError("unexpected M14 public staging path")
    # Avoid competing with the proof seed or the earlier checkpoint upload.
    prerequisite = WORK / "ark-held-delta-release.json"
    cutoff = time.monotonic() + 4 * 3600
    while not prerequisite.is_file() and time.monotonic() < cutoff:
        time.sleep(30)
    if not prerequisite.is_file():
        raise TimeoutError("the checkpoint upload has not released the transfer slot")

    report_file = ARK / "results" / "m14-bounded-setup-20261123.json"
    report = json.loads(report_file.read_bytes())
    if (report["full_circuit_setup_artifacts_verified"] is not True or report["private_state_included"] is not False
            or set(report["artifacts"]) != ALLOWED):
        raise ValueError("M14 receipt does not identify the expected two public artifacts")
    if shutil.disk_usage(DRIVE.parent).free < sum(a["bytes"] for a in report["artifacts"].values()) + 8 * 1024**3:
        raise RuntimeError("not enough D drive space for the bounded public M14 staging copy")
    DRIVE.mkdir(exist_ok=True)
    native_manifest = DRIVE / "m14-native-manifest.json"
    response = subprocess.run(["wsl.exe", "-u", "root", "--", "head", "-c", "65537", PUBLIC + "manifest.json"],
                              capture_output=True, check=True, timeout=30)
    if (len(response.stdout) > 65536
            or hashlib.sha256(response.stdout).hexdigest() != report["manifest_file_sha256"]
            or json.loads(response.stdout)["statement"] != report["statement"]):
        raise ValueError("M14 public manifest differs from the verified setup record")
    native_manifest.write_bytes(response.stdout)
    files = {}
    for name in sorted(ALLOWED):
        files[name] = {**report["artifacts"][name], "ordered_shards": split_verified(DRIVE, name, report["artifacts"][name])}

    index = DRIVE / "manifest.json"
    index.write_text(json.dumps({"schema": "ark-m14/public-setup-shards/v1", "statement": report["statement"],
                                 "manifest_sha256": report["manifest_sha256"], "files": files}, indent=2) + "\n",
                     encoding="ascii")
    assets = [entry for file in files.values() for entry in file["ordered_shards"]]
    assets.extend(common["part_metadata"](path) for path in (native_manifest, index))
    sums = DRIVE / "SHA256SUMS"
    sums.write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in assets), encoding="ascii")
    assets.append(common["part_metadata"](sums))
    body = ("Verified public M14 setup for the height-679 Ark regtest policy. Verify SHA256SUMS and concatenate each "
            "file's ordered shards according to manifest.json. Place the reconstructed files alongside the native manifest "
            "renamed to manifest.json. The checked setup produced 785,442,492 ciphertexts. Honest proof evaluation and "
            "the bit-flip control are recorded separately, after they complete.")
    helpers = common["helpers"]
    observed = common["complete_release"](TAG, "Ark height-679 M14 public setup", helpers["TARGET"], body, DRIVE, assets)
    (WORK / "ark-m14-public-release.json").write_text(
        json.dumps({"release": observed["html_url"], "assets": assets}, indent=2) + "\n", encoding="ascii")
    for item in assets:
        target = DRIVE / item["name"]
        if target.is_symlink() or target.resolve(strict=True).parent != DRIVE:
            raise ValueError("M14 setup cleanup path escaped the staging directory")
        target.unlink()
    common["emit"](stage="published", release=observed["html_url"], assets=len(assets))


if __name__ == "__main__":
    main()
