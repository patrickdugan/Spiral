#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
kit="$here/source"
out="$here/../../outputs/ark-h100-pilot"
test -f "$kit/pins/sp1-revision"
mkdir -p "$out"
test ! -e "$out/hopper-build.tar.gz"

cp -- "$here/"{build-hopper.sh,run-pilot.sh,report-pilot.py,README.txt} "$kit/"
python3 "$here/relocate-manifests.py" "$kit"
test "$(sha256sum "$kit/prover-gpu-cached-gkr-20261122/src/main.rs" | cut -d' ' -f1)" = \
    61ac77be07e24bfdaeb7a46eb1c4eb4d3d492a35d64b0bddb11cf2cebbf36fdf
for script in "$kit/"*.sh; do bash -n "$script"; done
cd "$kit"
cat > inputs.sha256 <<'EOF'
7ce5812fd76c3b31a5c3c24d117120b02839175636a68586e0fe97d370dcba5d  inputs/guest.elf
504070c1a3255fd853a2bde0b5f3dc6a3f7889227c3630a29675a93ab7981cba  inputs/nova-vk.raw
50d4f80f5b203cb805b35cf4ac13729eb8c76a00461e79e0ef72abcab98ad81f  inputs/nova-proof.arp
EOF
sha256sum -c inputs.sha256
/root/.cargo/bin/cargo metadata --locked --offline --filter-platform x86_64-unknown-linux-gnu \
    --format-version 1 --manifest-path prover-gpu-cached-gkr-20261122/Cargo.toml > "$here/portable-cargo-metadata.json"
python3 - "$here/portable-cargo-metadata.json" <<'PY'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_bytes())
root = Path.cwd()
packages = data["packages"]
local = [Path(item["manifest_path"]) for item in packages if item["source"] is None]
assert len(packages) == 480 and len(local) == 66, (len(packages), len(local))
assert all(path.is_relative_to(root) for path in local)
print(f"Portable Cargo graph verified: {len(packages)} packages, {len(local)} bundled path crates")
PY
find . -type f ! -path ./sources.sha256 -print0 | sort -z | xargs -0 sha256sum > sources.sha256
sha256sum -c --quiet sources.sha256
tar -czf "$here/hopper-build.tar.gz.partial" .
tar -tzf "$here/hopper-build.tar.gz.partial" > "$here/hopper-build-members.txt"
mv -- "$here/hopper-build.tar.gz.partial" "$out/hopper-build.tar.gz"
cd "$out"
sha256sum hopper-build.tar.gz > hopper-build.sha256
cp -- "$kit/README.txt" RUNPOD-PILOT.txt
cat hopper-build.sha256
