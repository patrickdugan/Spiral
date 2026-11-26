#!/bin/bash
set -Eeuo pipefail

volume=/var/tmp/proof-grove-cashu-raw-store
options=$(findmnt -n --mountpoint "$volume" -t btrfs -o OPTIONS)
case ",$options," in
    *,compress-force=zstd:*,*|*,compress-force=zstd,*) ;;
    *) exit 1 ;;
esac
stat -f -c '%i:%a:%S' "$volume"
