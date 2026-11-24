"""Make the original WSL Cargo path dependencies relative to this copy."""
import os
from pathlib import Path, PurePosixPath
import re
import sys


root = Path(sys.argv[1]).resolve()
base = "/var/tmp/ark-asp-sized-gpu-20261117/"
locations = {
    PurePosixPath("/root/sp1src/sp1"): root / "sp1",
    PurePosixPath(base + "sp1-zero-cache-20261122"): root / "sp1-zero-cache-20261122",
    PurePosixPath(base + "prover"): root / "prover",
}

for manifest in sorted(root.rglob("Cargo.toml")):
    before = manifest.read_text()

    def replace(match):
        path = PurePosixPath(match[2])
        for original, destination in locations.items():
            if path.is_relative_to(original):
                local_path = destination / path.relative_to(original)
                if not (local_path / "Cargo.toml").is_file():
                    raise FileNotFoundError(local_path)
                return match[1] + Path(os.path.relpath(local_path, manifest.parent)).as_posix() + '"'
        raise ValueError(f"unbundled Cargo path in {manifest}: {path}")

    after = re.sub(r'((?:"path"|\bpath)\s*=\s*")(/[^"]+)"', replace, before)
    if after != before:
        manifest.write_text(after)
