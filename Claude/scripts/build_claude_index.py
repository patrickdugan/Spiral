#!/usr/bin/env python3
"""Build a scrubbed, machine- and human-readable catalog of local Claude chats under Spiral/Claude."""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLAUDE_PROJECTS = Path(r"\\?\C:\Users\patri\.claude\projects")
CLAUDE_DESKTOP_SESSIONS = Path(
    r"\\?\C:\Users\patri\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\claude-code-sessions"
)
OUT_DIR = Path(__file__).resolve().parent.parent

PATH_SCRUB_RE = re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s\"']+", re.IGNORECASE)
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,})"
)


def scrub(text: str | None) -> str:
    if not text:
        return ""
    s = PATH_SCRUB_RE.sub("~", text)
    s = SECRET_RE.sub("[REDACTED]", s)
    return " ".join(s.split())


def iso_from_ms(ms: int | float | None) -> str:
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def load_desktop_metadata() -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    if not CLAUDE_DESKTOP_SESSIONS.exists():
        return meta
    for root, _, files in os.walk(CLAUDE_DESKTOP_SESSIONS):
        for fn in files:
            if not (fn.startswith("local_") and fn.endswith(".json")):
                continue
            p = Path(root) / fn
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
            cli_id = data.get("cliSessionId") or ""
            if cli_id:
                meta[cli_id] = data
    return meta


def extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def decode_project_dir(name: str) -> str:
    if "scratch-workspaces-" in name:
        return "claude-desktop-scratch"
    s = name
    for prefix in (
        "C--Users-patri-OneDrive-Documents-GitHub-",
        "C--Users-patri-Documents-GitHub-",
        "C--Users-patri-OneDrive-Documents-",
        "C--Users-patri-Documents-",
        "C--Users-patri-",
    ):
        if s.startswith(prefix):
            return s[len(prefix) :] or "home"
    return s[:80]


def parse_session_jsonl(jsonl_path: Path) -> dict[str, Any]:
    user_turns = 0
    assistant_turns = 0
    first_prompt = ""
    first_ts = ""
    last_ts = ""
    models: Counter[str] = Counter()
    cwd = ""

    with jsonl_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            ts = obj.get("timestamp")
            if isinstance(ts, str) and ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts

            if not cwd and isinstance(obj.get("cwd"), str):
                cwd = obj["cwd"]

            typ = obj.get("type")
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}

            if typ == "user" or msg.get("role") == "user":
                txt = extract_text_from_content(msg.get("content", obj.get("content", "")))
                if txt.strip():
                    user_turns += 1
                    if not first_prompt:
                        first_prompt = scrub(txt)[:240]
            elif typ == "assistant" or msg.get("role") == "assistant":
                assistant_turns += 1
                m = msg.get("model") or obj.get("model")
                if isinstance(m, str) and m:
                    models[m] += 1

    return {
        "user_turns": user_turns,
        "assistant_turns": assistant_turns,
        "first_prompt": first_prompt,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "model": models.most_common(1)[0][0] if models else "",
        "cwd": scrub(cwd),
    }


def main() -> None:
    desktop_meta = load_desktop_metadata()
    records: list[dict[str, Any]] = []

    for proj_dir in sorted(CLAUDE_PROJECTS.iterdir()):
        if not proj_dir.is_dir():
            continue
        project_label = decode_project_dir(proj_dir.name)
        for entry in proj_dir.iterdir():
            if not (entry.is_file() and entry.suffix == ".jsonl"):
                continue
            session_id = entry.stem
            sess_subdir = proj_dir / session_id

            custom_title = ""
            ct_file = sess_subdir / "custom-title.json"
            if ct_file.is_file():
                try:
                    custom_title = scrub(
                        json.loads(ct_file.read_text(encoding="utf-8", errors="replace")).get("customTitle", "")
                    )
                except Exception:
                    pass

            subagent_dir = sess_subdir / "subagents"
            subagent_files = 0
            if subagent_dir.is_dir():
                subagent_files = sum(1 for x in subagent_dir.iterdir() if x.suffix == ".jsonl")

            parsed = parse_session_jsonl(entry)
            if parsed["user_turns"] == 0 and parsed["assistant_turns"] == 0 and not custom_title:
                continue

            dmeta = desktop_meta.get(session_id, {})
            created_utc = parsed["first_ts"] or iso_from_ms(dmeta.get("createdAt"))
            last_utc = parsed["last_ts"] or iso_from_ms(dmeta.get("lastActivityAt"))
            if not last_utc:
                st = entry.stat()
                last_utc = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            git_anchors = dmeta.get("gitAnchors") or []
            git_repo = ""
            if git_anchors and isinstance(git_anchors[0], dict):
                gr = git_anchors[0].get("gitRoot", "")
                if gr:
                    git_repo = Path(gr).name

            title = custom_title or scrub(dmeta.get("title", "")) or parsed["first_prompt"][:100] or session_id
            cwd_scrubbed = scrub(dmeta.get("cwd")) or parsed["cwd"]

            records.append(
                {
                    "session_id": session_id,
                    "desktop_session_id": dmeta.get("sessionId", ""),
                    "title": title,
                    "project": project_label,
                    "git_repo": git_repo,
                    "cwd": cwd_scrubbed,
                    "created_utc": created_utc,
                    "last_activity_utc": last_utc,
                    "model": parsed["model"],
                    "user_turns": parsed["user_turns"],
                    "assistant_turns": parsed["assistant_turns"],
                    "subagent_files": subagent_files,
                    "size_bytes": entry.stat().st_size,
                    "first_user_prompt": parsed["first_prompt"],
                }
            )

    records.sort(key=lambda r: r["last_activity_utc"] or "", reverse=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_out = OUT_DIR / "index.jsonl"
    with jsonl_out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Build summary stats and Markdown index
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_month: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    total_user = 0
    total_asst = 0
    total_bytes = 0

    for r in records:
        proj_key = r["git_repo"] or r["project"] or "unknown"
        by_project[proj_key].append(r)
        if len(r["last_activity_utc"]) >= 7:
            by_month[r["last_activity_utc"][:7]] += 1
        if r["model"]:
            by_model[r["model"]] += 1
        total_user += r["user_turns"]
        total_asst += r["assistant_turns"]
        total_bytes += r["size_bytes"]

    md_lines = [
        "# Claude Chat Index",
        "",
        f"- **Total indexed sessions**: {len(records)}",
        f"- **Total user / assistant turns**: {total_user:,} / {total_asst:,}",
        f"- **Total local transcript size**: {total_bytes / (1024**3):.2f} GB (raw `.jsonl` transcripts kept local)",
        f"- **Date range**: {records[-1]['last_activity_utc'][:10] if records else 'N/A'} to {records[0]['last_activity_utc'][:10] if records else 'N/A'}",
        "",
        "## Sessions by Month",
        "",
        "| Month | Sessions |",
        "|---|---|",
    ]
    for m, c in sorted(by_month.items(), reverse=True):
        md_lines.append(f"| {m} | {c} |")

    md_lines += [
        "",
        "## Top Models",
        "",
        "| Model | Sessions |",
        "|---|---|",
    ]
    for m, c in by_model.most_common():
        md_lines.append(f"| `{m}` | {c} |")

    md_lines += [
        "",
        "## Sessions by Project / Repo",
        "",
    ]
    for proj_key, items in sorted(by_project.items(), key=lambda kv: len(kv[1]), reverse=True):
        md_lines.append(f"### {proj_key} ({len(items)} sessions)")
        md_lines.append("")
        md_lines.append("| Date (UTC) | Title | Turns (U/A) | Model | Session ID |")
        md_lines.append("|---|---|---:|---|---|")
        for r in items:
            dt = r["last_activity_utc"][:10]
            title_clean = r["title"].replace("|", "\\|")[:90]
            turns = f"{r['user_turns']}/{r['assistant_turns']}"
            model = f"`{r['model']}`" if r["model"] else ""
            md_lines.append(f"| {dt} | {title_clean} | {turns} | {model} | `{r['session_id'][:8]}` |")
        md_lines.append("")

    (OUT_DIR / "INDEX.md").write_text("\n".join(md_lines), encoding="utf-8")

    readme = "\n".join(
        [
            "# Spiral/Claude",
            "",
            "Catalog and machine-readable index of local Claude Code & Claude Desktop sessions.",
            "",
            "## Files",
            "- `index.jsonl` — One JSON record per session (scrubbed of local user paths and secrets), sorted newest-first.",
            "- `INDEX.md` — Human-readable catalog grouped by month, model, and project/repo.",
            "- `scripts/build_claude_index.py` — Reproducible indexer over `~/.claude/projects` and `AppData/Local/Claude-Data`.",
            "",
            "## Regenerate",
            "```powershell",
            "python Claude/scripts/build_claude_index.py",
            "```",
            "",
            f"Currently indexed: **{len(records)}** sessions ({total_user:,} user turns, {total_asst:,} assistant turns).",
            "",
        ]
    )
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    print(f"Indexed {len(records)} sessions -> {jsonl_out} ({jsonl_out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
