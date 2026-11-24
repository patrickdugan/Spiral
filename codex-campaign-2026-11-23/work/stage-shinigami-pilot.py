"""Stage only the named local binaries, source files and public input for the pilot."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

WORKSPACE = Path("/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat")
PROOFDESK = WORKSPACE / "outputs/ark-cashu-proofdesk"
BENCHMARK = PROOFDESK / "benchmarks/shinigami"
ARK = WORKSPACE / "outputs/zk-rusto-no-bitcoino-ark/Ark"
RUNTIME = Path("/var/tmp/proof-grove-shinigami-20261123")
SCARB = Path("/root/.asdf/installs/scarb/2.19.6/bin")
ROOT = Path(tempfile.mkdtemp(prefix="proofdesk-shinigami-pilot-"))
PACKAGE = ROOT / "shinigami-cpu-pilot"
RUNNER = PACKAGE / "benchmarks/shinigami"
RUNNER.mkdir(parents=True)
(RUNNER / "bin").mkdir()
(PACKAGE / "proofdesk").mkdir()

for name in ("run.py", "Scarb.toml", "pins.json", "README.md"):
    shutil.copyfile(BENCHMARK / name, RUNNER / name)
for name in ("__init__.py", "shinigami.py", "domain.py", "verifier.py"):
    shutil.copyfile(PROOFDESK / "proofdesk" / name, PACKAGE / "proofdesk" / name)

sources = {
    "bin/scarb": SCARB / "scarb",
    "bin/scarb-execute": SCARB / "scarb-execute",
    "bin/scarb-verify": SCARB / "scarb-verify",
    "bin/prove-clean": Path("/root/build/s3o/prove-clean"),
    "main.executable.json": RUNTIME / "target/dev/main.executable.json",
    "profile.json": RUNTIME / "canonical-without-pedersen-96.json",
    "testnet4-tapleaf-args.json": ARK / "fixtures/testnet4-tapleaf-args.json",
}
pins = json.loads((RUNNER / "pins.json").read_text())
for name, source in sources.items():
    target = RUNNER / name
    shutil.copyfile(source, target)
    with target.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != pins["sha256"][name]:
            raise ValueError(f"SHA-256 mismatch: {name}")
    target.chmod(0o755 if name.startswith("bin/") else 0o644)

if len(sys.argv) == 2:
    archive = Path(sys.argv[1])
    with tarfile.open(archive, "x:gz", compresslevel=1) as bundle:
        bundle.add(PACKAGE, arcname=PACKAGE.name)
print(PACKAGE)
