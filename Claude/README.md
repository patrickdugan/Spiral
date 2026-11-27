# Spiral/Claude

Catalog and machine-readable index of local Claude Code & Claude Desktop sessions.

## Files
- `index.jsonl` — One JSON record per session (scrubbed of local user paths and secrets), sorted newest-first.
- `INDEX.md` — Human-readable catalog grouped by month, model, and project/repo.
- `scripts/build_claude_index.py` — Reproducible indexer over `~/.claude/projects` and `AppData/Local/Claude-Data`.

## Regenerate
```powershell
python Claude/scripts/build_claude_index.py
```

Currently indexed: **267** sessions (12,033 user turns, 173,699 assistant turns).
