"""Verify the bundle layouts and the archived cache configuration."""
import hashlib
import json
from pathlib import Path
import tarfile


STAGE = Path(__file__).resolve().parent
OUTPUT = STAGE.parents[1] / "outputs/ark-h100-pilot"


def main():
    manifest = json.loads((STAGE / "native-cache-copy-manifest.json").read_bytes())
    with tarfile.open(OUTPUT / "checkpoint.tar", "r:") as archive:
        members = archive.getmembers()
        expected = {f"cache/{name}": entry["bytes"] for name, entry in manifest.items()}
        if len(members) != len(expected) or any(
            not member.isfile() or expected.get(member.name) != member.size
            for member in members
        ) or {member.name for member in members} != expected.keys():
            raise ValueError("checkpoint archive inventory mismatch")
        with archive.extractfile("cache/run.json") as run_config:
            if hashlib.sha256(run_config.read()).hexdigest() != manifest["run.json"]["sha256"]:
                raise ValueError("checkpoint run configuration mismatch")
    with tarfile.open(OUTPUT / "hopper-build.tar.gz", "r:gz") as kit:
        required = {"build-hopper.sh", "run-pilot.sh", "report-pilot.py", "sources.sha256", "inputs.sha256"}
        if not required.issubset({member.name.removeprefix("./") for member in kit.getmembers()}):
            raise ValueError("Hopper source kit is missing a required file")
    print(f"Both archive layouts verified, including {len(manifest):,} checkpoint files.")


if __name__ == "__main__":
    main()
