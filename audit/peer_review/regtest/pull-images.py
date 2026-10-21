"""Resolve no tags: download only the four reviewed immutable manifests."""
from bootstrap import RUNTIME, IMAGES, docker
import shutil

if shutil.disk_usage('/mnt/c').free < 6 * 1024**3:
    raise RuntimeError('Need at least 6 GiB host free space before pulling images')

for component, ref in IMAGES.items():
    print(f"Pulling {component}: {ref}", flush=True)
    result = docker("pull", ref, check=False)
    (RUNTIME / f"logs/pull-{component}.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"pull failed: {component}; inspect private log")
print("Pinned images available", flush=True)
