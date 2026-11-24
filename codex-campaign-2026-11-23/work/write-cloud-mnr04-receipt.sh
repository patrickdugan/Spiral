#!/usr/bin/env bash
set -euo pipefail
dest=/mnt/c/Users/patri/Documents/Codex/2026-11-23/the-goal-is-paused-at-the/work/verified-cloud-mnr04-1177764
/var/tmp/shz-mnr04-target/release/shz mnr04-verify "$dest/core-archive.json" "$dest" \
    7fc71a8518976ede1ad97855ee164e63356e4ef11cda43565e1177fa5f082db1 > "$dest/locally-verified.json"