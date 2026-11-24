"""Extract the exact archived MNR-04 proof and verifier inputs into an isolated folder."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

cli = argparse.ArgumentParser()
cli.add_argument("result", type=Path)
cli.add_argument("new_directory", type=Path)
args = cli.parse_args()
args.new_directory.mkdir()
with tarfile.open(args.result, "r:gz") as archive:
    pairs = [
        ("mnr04/core-archive.json", "core-archive.json", 2**20),
        ("mnr04/proof/proof.bin", "proof.bin", 2**20),
        ("mnr04/benchmark.json", "benchmark.json", 2**20),
    ]
    for remote, local, maximum in pairs:
        entry = archive.getmember("./" + remote)
        if not entry.isfile() or not 0 < entry.size <= maximum:
            raise RuntimeError("Unexpected MNR-04 artifact in pilot export")
        (args.new_directory / local).write_bytes(archive.extractfile(entry).read())
bench = json.loads((args.new_directory / "benchmark.json").read_text())
if hashlib.sha256((args.new_directory / "proof.bin").read_bytes()).hexdigest() != bench["independent_verification"]["proof_sha256"]:
    raise RuntimeError("Pilot proof differs from worker-side independent verification")
print(bench["independent_verification"]["vk_sha256"])
