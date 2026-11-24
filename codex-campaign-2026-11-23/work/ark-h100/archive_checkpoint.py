"""Pack the retained, previously verified cache for an isolated Hopper trial."""
import ctypes
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile


ROOT = Path(__file__).resolve().parents[2]
STAGE = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent / "2026-11-15/new-chat/work/ark-proof-cache-20261122/prover-transient"
OUTPUT = ROOT / "outputs/ark-h100-pilot"


class HashStream:
    def __init__(self, file):
        self.file = file
        self.digest = hashlib.sha256()

    def read(self, size):
        block = self.file.read(size)
        self.digest.update(block)
        return block

    def write(self, block):
        self.digest.update(block)
        return self.file.write(block)


def main():
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00100000)  # process background mode
    metadata = json.loads((STAGE / "native-cache-copy.json").read_bytes())
    manifest_bytes = (STAGE / "native-cache-copy-manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != metadata["manifest_sha256"]:
        raise ValueError("checkpoint manifest hash mismatch")
    manifest = json.loads(manifest_bytes)
    size = sum(entry["bytes"] for entry in manifest.values())
    if (len(manifest), size) != (metadata["files"], metadata["bytes"]):
        raise ValueError("checkpoint inventory totals mismatch")
    if shutil.disk_usage(ROOT).free < size + (15 << 30):
        raise RuntimeError("insufficient free space to pack the archive with 15 GiB remaining")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source = SOURCE.resolve(strict=True)
    pending = STAGE / "checkpoint.tar.partial"
    archive = OUTPUT / "checkpoint.tar"
    if archive.exists():
        raise FileExistsError(archive)
    with pending.open("xb") as raw:
        stream = HashStream(raw)
        with tarfile.open(mode="w|", fileobj=stream, bufsize=1 << 20) as package:
            for index, (name, expected) in enumerate(sorted(manifest.items()), 1):
                relative = PurePosixPath(name)
                path = source.joinpath(*relative.parts)
                if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                    raise ValueError(f"unsafe checkpoint path: {name}")
                if path.is_symlink() or path.stat().st_size != expected["bytes"]:
                    raise ValueError(f"checkpoint metadata mismatch: {name}")
                member = tarfile.TarInfo(f"cache/{name}")
                member.size = expected["bytes"]
                member.mode = 0o600
                with path.open("rb") as file:
                    hashed = HashStream(file)
                    package.addfile(member, hashed)
                    if hashed.digest.hexdigest() != expected["sha256"]:
                        raise ValueError(f"checkpoint file hash mismatch: {name}")
                if index % 5000 == 0:
                    print(f"Verified and packed {index:,} of {len(manifest):,} files", flush=True)
    pending.rename(archive)
    (OUTPUT / "checkpoint.sha256").write_text(f"{stream.digest.hexdigest()}  checkpoint.tar\n", encoding="ascii")
    print(f"Verified {len(manifest):,} files and {size:,} source bytes")


if __name__ == "__main__":
    main()
