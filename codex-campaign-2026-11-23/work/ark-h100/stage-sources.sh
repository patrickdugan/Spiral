#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
sp1=/root/sp1src/sp1
source_root=/var/tmp/ark-asp-sized-gpu-20261117
revision=b8387fa61e1361d90ee7de49f551863418ca0f08
entry=61ac77be07e24bfdaeb7a46eb1c4eb4d3d492a35d64b0bddb11cf2cebbf36fdf
driver=prover-gpu-cached-gkr-20261122
local_repo=/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat
ark="$local_repo/outputs/zk-rusto-no-bitcoino-ark/Ark"

test "$(git -C "$sp1" rev-parse HEAD)" = "$revision"
test -z "$(git -C "$sp1" status --porcelain --untracked-files=all)"
printf '%s  %s\n' "$entry" "$source_root/$driver/src/main.rs" | sha256sum -c -
mkdir "$here/source" "$here/source/inputs" "$here/source/pins"
git -C "$sp1" archive --format=tar --prefix=sp1/ "$revision" |
    tar -xf - -C "$here/source" --no-same-owner
tar -cf - -C "$source_root" --exclude=target --exclude=.git \
    "$driver" prover sp1-zero-cache-20261122 |
    tar -xf - -C "$here/source" --no-same-owner
cp -- "$local_repo/work/ark-asp-guest/ark-asp-nova-guest" "$here/source/inputs/guest.elf"
cp -- "$ark/.runtime/ark-key.raw" "$here/source/inputs/nova-vk.raw"
cp -- "$ark/.runtime/proof-grove-verified/proof.arp" "$here/source/inputs/nova-proof.arp"
cp -- "$ark/proving-profile.json" "$ark/results/gpu-cached-gkr-build-20261122.json" \
    "$ark/fixtures/bitvm3-pins.proof-grove.json" "$here/source/pins/"
cp -- "$here/native-cache-copy.json" "$here/source/pins/checkpoint-origin.json"
printf '%s\n' "$revision" > "$here/source/pins/sp1-revision"
sha256sum -- "$here/source/inputs/"*
