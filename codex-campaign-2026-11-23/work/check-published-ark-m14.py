import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


repo = "patrickdugan/zk-rusto-no-bitcoino"
tag = "ark-679-m14-public-setup-20261123"
api = f"https://api.github.com/repos/{repo}/releases"
download = f"https://github.com/{repo}/releases/download/{tag}"
staging = Path(r"D:\Codex-offload\ark-679-m14-public-20261123")
result = Path(r"C:\Users\patri\Documents\Codex\2026-11-15\new-chat\outputs\zk-rusto-no-bitcoino-ark\Ark\results\m14-bounded-setup-20261123.json")


def read(url):
    request = Request(url, headers={"User-Agent": "Ark-Public-Setup-Audit"})
    with urlopen(request, timeout=30) as response:
        return response.read()


receipt = json.loads(Path("work/ark-m14-public-release.json").read_bytes())
release = json.loads(read(f"{api}/tags/{tag}"))
if release["draft"] or not release["prerelease"] or release["html_url"] != receipt["release"]:
    raise ValueError("mismatch in the published prerelease metadata")

expected = {item["name"]: (item["bytes"], item["sha256"]) for item in receipt["assets"]}
observed = {}
for page in range(1, 4):
    batch = json.loads(read(f"{api}/{release['id']}/assets?per_page=100&page={page}"))
    for item in batch:
        if item["name"] in observed or item["state"] != "uploaded":
            raise ValueError("unexpected release asset state")
        observed[item["name"]] = (item["size"], item["digest"].removeprefix("sha256:"))
    if len(batch) < 100:
        break
if expected != observed:
    raise ValueError("remote asset hashes or sizes differ from the packaging receipt")

index = read(f"{download}/manifest.json")
manifest = json.loads(index)
native = read(f"{download}/m14-native-manifest.json")
report = json.loads(result.read_bytes())
if (hashlib.sha256(index).hexdigest() != expected["manifest.json"][1]
        or hashlib.sha256(native).hexdigest() != report["manifest_file_sha256"]
        or manifest["schema"] != "ark-m14/public-setup-shards/v1"
        or manifest["statement"] != json.loads(native)["statement"]
        or manifest["statement"] != report["statement"]
        or manifest["manifest_sha256"] != report["manifest_sha256"]
        or set(manifest["files"]) != {"ciphertexts.bin", "input-commitments.bin"}):
    raise ValueError("published manifests differ from the originally verified setup")

parts = set()
for name, spec in manifest["files"].items():
    if any(spec[key] != report["artifacts"][name][key] for key in ("bytes", "sha256")):
        raise ValueError("published full-artifact digest differs from the setup report")
    if sum(part["bytes"] for part in spec["ordered_shards"]) != spec["bytes"]:
        raise ValueError("shard sizes differ from the public artifact size")
    for part in spec["ordered_shards"]:
        label = part["name"]
        if label in parts or expected[label] != (part["bytes"], part["sha256"]):
            raise ValueError("manifest shard differs from the exact remote inventory")
        parts.add(label)
if set(expected) - parts != {"manifest.json", "m14-native-manifest.json", "SHA256SUMS"}:
    raise ValueError("unexpected ancillary release asset")
if not staging.is_dir() or any(staging.iterdir()):
    raise ValueError("the verified release staging area was not emptied")
print(json.dumps({
    "release": release["html_url"],
    "assets": len(expected),
    "setup_shards": len(parts),
    "setup_bytes": sum(spec["bytes"] for spec in manifest["files"].values()),
    "empty_d_staging": True,
}))
