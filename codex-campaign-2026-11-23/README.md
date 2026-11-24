# Codex Campaign Archive (`2026-11-23` Ark / Cashu / MNR-04)

Archived from the local Codex workspace `2026-11-23/the-goal-is-paused-at-the`.

## Included

- `outputs/`: Proof Grove HTML demos, JSON verification receipts, benchmark results, and desktop/dashboard screenshots.
- `work/`: Orchestration scripts, release manifests, and UI/prover/pilot source directories (`a100-ui`, `archive-status-ui`, `ark-github-release`, `ark-h100` scripts, `cashu-roadmap-ui`, `cashu-shinigami`, `compute-ui`, `nb3-library`, `prover-ui`, `runpod-native`, `runpod-ui`).

## Excluded (Large Binaries / Build Caches / Browser Profiles / Separate Repos)

- `outputs/ark-h100-pilot/checkpoint.tar` (14.99 GB)
- `outputs/ark-h100-pilot/hopper-build.tar.gz` (63.12 MB)
- `outputs/shinigami-cpu-pilot.tar.gz` (58.71 MB)
- `work/ark-a100-prebuilt.tar.gz` (55.61 MB)
- `work/icicle-koalabear/source.tar.gz` (123.03 MB) and `work/icicle-koalabear/`
- `work/verified-cloud-mnr04-1177764/vk.bin` (65.78 MB)
- `work/live-ui-native/` (Cargo build cache)
- `work/hyperstack-python/` (vendored Python packages)
- `work/*-browser-*` and `edge-fixture/` (ephemeral browser profiles)
- `work/spiral-dlc-preview/` and `work/SatsHedgeZero-mnr04/` (separate git repositories/worktrees)
