# Spiral/Codex

Catalog and machine-readable index of local Codex sessions (`~/.codex/sessions` and `archived_sessions`).

## Files
- `index.jsonl` — One JSON record per session (scrubbed of local user paths and secrets), sorted newest-first.
- `INDEX.md` — Human-readable catalog grouped by month, model, and project/workspace.
- `hf_manifest.json` — Manifest linking each session to the private Hugging Face dataset `AlephFunk/spiral-codex-chats`.
- `scripts/build_codex_index.py` — Reproducible indexer.
- `scripts/upload_codex_hf.py` — Scrubs, gzips, and uploads transcripts to the private HF dataset.

Currently indexed: **237** sessions (7,027 user turns, 10,847 assistant turns).
