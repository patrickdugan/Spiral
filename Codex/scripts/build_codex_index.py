#!/usr/bin/env python3
"""Build a scrubbed, machine- and human-readable catalog of local Codex chats under Spiral/Codex."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CODEX_ROOT = Path(r"\\?\C:\Users\patri\.codex")
SESSIONS_DIR = CODEX_ROOT / "sessions"
ARCHIVED_DIR = CODEX_ROOT / "archived_sessions"
SESSION_INDEX = CODEX_ROOT / "session_index.jsonl"
OUT_DIR = Path(__file__).resolve().parent.parent

PATH_SCRUB_RE = re.compile(r"[A-Za-z]:(?:\\\\|/)+Users(?:\\\\|/)+[^\\/\s\"']+", re.IGNORECASE)
UNIX_PATH_SCRUB_RE = re.compile(r"/(?:home|Users)/[^/\s\"']+")
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"hf_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})"
)
UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.IGNORECASE)


def scrub(text: str | None) -> str:
    if not text:
        return ""
    s = PATH_SCRUB_RE.sub("~", text)
    s = UNIX_PATH_SCRUB_RE.sub("~", s)
    s = SECRET_RE.sub("[REDACTED]", s)
    return " ".join(s.split())


def load_thread_names() -> dict[str, dict[str, str]]:
    names: dict[str, dict[str, str]] = {}
    if not SESSION_INDEX.is_file():
        return names
    for line in SESSION_INDEX.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        sid = obj.get("id")
        if sid:
            names[sid] = {
                "thread_name": scrub(obj.get("thread_name", "")),
                "updated_at": obj.get("updated_at", ""),
            }
    return names


def extract_msg_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return " ".join(parts)
    return ""


def parse_rollout(path: Path) -> dict[str, Any]:
    session_id = ""
    cwd = ""
    first_ts = ""
    last_ts = ""
    models: Counter[str] = Counter()
    user_turns = 0
    assistant_turns = 0
    first_prompt = ""

    with path.open("r", encoding="utf-8", errors="replace") as f:
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

            typ = obj.get("type")
            payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}

            if typ == "session_meta":
                if not session_id:
                    session_id = payload.get("session_id") or payload.get("id") or ""
                if not cwd and isinstance(payload.get("cwd"), str):
                    cwd = payload["cwd"]
            elif typ == "event_msg":
                ptyp = payload.get("type")
                if ptyp == "thread_settings_applied":
                    ts_cfg = payload.get("thread_settings") or {}
                    m = ts_cfg.get("model")
                    if isinstance(m, str) and m:
                        models[m] += 1
            elif typ == "response_item" and payload.get("type") == "message":
                role = payload.get("role")
                if role == "user":
                    txt = extract_msg_text(payload.get("content"))
                    # Skip injected environment/AGENTS boilerplate if possible when picking first_prompt
                    user_turns += 1
                    cleaned = scrub(txt)
                    if cleaned and not first_prompt and not cleaned.startswith(("<environment_context>", "# AGENTS.md")):
                        first_prompt = cleaned[:240]
                elif role == "assistant":
                    assistant_turns += 1

    if not session_id:
        m = UUID_RE.search(path.stem)
        session_id = m.group(1) if m else path.stem

    project = ""
    if cwd:
        project = Path(cwd).name or scrub(cwd)

    return {
        "session_id": session_id,
        "cwd": scrub(cwd),
        "project": project or "unknown",
        "created_utc": first_ts,
        "last_activity_utc": last_ts,
        "model": models.most_common(1)[0][0] if models else "",
        "user_turns": user_turns,
        "assistant_turns": assistant_turns,
        "first_user_prompt": first_prompt,
    }


def main() -> None:
    thread_names = load_thread_names()
    rollouts = sorted(SESSIONS_DIR.rglob("*.jsonl")) if SESSIONS_DIR.exists() else []
    if ARCHIVED_DIR.exists():
        rollouts.extend(sorted(ARCHIVED_DIR.glob("*.jsonl")))

    records: list[dict[str, Any]] = []
    source_map: dict[str, str] = {}

    for rp in rollouts:
        parsed = parse_rollout(rp)
        sid = parsed["session_id"]
        tinfo = thread_names.get(sid, {})
        last_utc = parsed["last_activity_utc"] or tinfo.get("updated_at", "")
        if not last_utc:
            last_utc = datetime.fromtimestamp(rp.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        title = tinfo.get("thread_name") or parsed["first_user_prompt"][:100] or sid

        rec = {
            "session_id": sid,
            "title": title,
            "project": parsed["project"],
            "cwd": parsed["cwd"],
            "created_utc": parsed["created_utc"],
            "last_activity_utc": last_utc,
            "model": parsed["model"],
            "user_turns": parsed["user_turns"],
            "assistant_turns": parsed["assistant_turns"],
            "size_bytes": rp.stat().st_size,
            "archived": ARCHIVED_DIR in rp.parents,
            "first_user_prompt": parsed["first_user_prompt"],
        }
        records.append(rec)
        source_map[sid] = str(rp)

    records.sort(key=lambda r: r["last_activity_utc"] or "", reverse=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_out = OUT_DIR / "index.jsonl"
    with jsonl_out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_month: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    total_user = 0
    total_asst = 0
    total_bytes = 0

    for r in records:
        by_project[r["project"]].append(r)
        if len(r["last_activity_utc"]) >= 7:
            by_month[r["last_activity_utc"][:7]] += 1
        if r["model"]:
            by_model[r["model"]] += 1
        total_user += r["user_turns"]
        total_asst += r["assistant_turns"]
        total_bytes += r["size_bytes"]

    md_lines = [
        "# Codex Chat Index",
        "",
        f"- **Total indexed sessions**: {len(records)}",
        f"- **Total user / assistant turns**: {total_user:,} / {total_asst:,}",
        f"- **Total local transcript size**: {total_bytes / (1024**3):.2f} GB (raw `.jsonl` transcripts hosted in private HF dataset)",
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
        "## Sessions by Project / Workspace",
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
            "# Spiral/Codex",
            "",
            "Catalog and machine-readable index of local Codex sessions (`~/.codex/sessions` and `archived_sessions`).",
            "",
            "## Files",
            "- `index.jsonl` — One JSON record per session (scrubbed of local user paths and secrets), sorted newest-first.",
            "- `INDEX.md` — Human-readable catalog grouped by month, model, and project/workspace.",
            "- `hf_manifest.json` — Manifest linking each session to the private Hugging Face dataset `AlephFunk/spiral-codex-chats`.",
            "- `scripts/build_codex_index.py` — Reproducible indexer.",
            "- `scripts/upload_codex_hf.py` — Scrubs, gzips, and uploads transcripts to the private HF dataset.",
            "",
            f"Currently indexed: **{len(records)}** sessions ({total_user:,} user turns, {total_asst:,} assistant turns).",
            "",
        ]
    )
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    print(f"Indexed {len(records)} Codex sessions -> {jsonl_out} ({jsonl_out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
