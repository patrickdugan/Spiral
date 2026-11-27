#!/usr/bin/env python3
"""Scrub and upload all indexed local Claude transcripts to a private Hugging Face dataset."""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi

HUG_TXT = Path(r"C:\Users\patri\OneDrive\Desktop\hug.txt")
CLAUDE_PROJECTS = Path(r"\\?\C:\Users\patri\.claude\projects")
CLAUDE_DIR = Path(__file__).resolve().parent.parent
INDEX_JSONL = CLAUDE_DIR / "index.jsonl"
STAGE_DIR = Path(r"D:\_hf_claude_stage")
REPO_NAME = "spiral-claude-chats"

PATH_SCRUB_RE = re.compile(r"[A-Za-z]:(?:\\\\|/)+Users(?:\\\\|/)+[^\\/\s\"']+", re.IGNORECASE)
UNIX_PATH_SCRUB_RE = re.compile(r"/(?:home|Users)/[^/\s\"']+")
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"hf_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})"
)


def pick_hf_client() -> tuple[HfApi, str]:
    tokens = [l.strip() for l in HUG_TXT.read_text(encoding="utf-8").splitlines() if l.strip()]
    last_err: Exception | None = None
    for tok in tokens:
        try:
            api = HfApi(token=tok)
            me = api.whoami()
            user = me.get("name") or ""
            if user:
                return api, user
        except Exception as e:
            last_err = e
    raise RuntimeError(f"No valid HF token in {HUG_TXT}: {last_err}")


def scrub_line(line: str) -> str:
    s = PATH_SCRUB_RE.sub("~", line)
    s = UNIX_PATH_SCRUB_RE.sub("~", s)
    s = SECRET_RE.sub("[REDACTED]", s)
    return s


def find_session_files() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for proj_dir in CLAUDE_PROJECTS.iterdir():
        if not proj_dir.is_dir():
            continue
        for entry in proj_dir.iterdir():
            if entry.is_file() and entry.suffix == ".jsonl":
                found[entry.stem] = entry
    return found


def main() -> None:
    api, username = pick_hf_client()
    repo_id = f"{username}/{REPO_NAME}"
    print(f"Authenticated HF user: {username}; target private dataset: {repo_id}")

    api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR, ignore_errors=True)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    session_files = find_session_files()
    records = [
        json.loads(line)
        for line in INDEX_JSONL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    manifest_entries: list[dict[str, Any]] = []
    total_raw = 0
    total_gz = 0

    for idx, rec in enumerate(records, 1):
        sid = rec["session_id"]
        src = session_files.get(sid)
        if not src or not src.is_file():
            continue
        month = (rec.get("last_activity_utc") or "unknown")[:7]
        if len(month) != 7:
            month = "unknown"
        rel_path = f"sessions/{month}/{sid}.jsonl.gz"
        dst = STAGE_DIR / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)

        with src.open("r", encoding="utf-8", errors="replace") as fin, gzip.open(
            dst, "wt", encoding="utf-8", compresslevel=6
        ) as fout:
            for line in fin:
                fout.write(scrub_line(line))

        raw_sz = src.stat().st_size
        gz_sz = dst.stat().st_size
        total_raw += raw_sz
        total_gz += gz_sz
        manifest_entries.append(
            {
                "session_id": sid,
                "month": month,
                "title": rec.get("title", ""),
                "project": rec.get("git_repo") or rec.get("project", ""),
                "hf_path": rel_path,
                "raw_bytes": raw_sz,
                "gz_bytes": gz_sz,
            }
        )
        if idx % 50 == 0 or idx == len(records):
            print(f"Scrubbed & compressed {idx}/{len(records)} sessions ({total_gz / (1024**2):.1f} MB gz)")

    shutil.copy2(INDEX_JSONL, STAGE_DIR / "index.jsonl")
    ds_readme = "\n".join(
        [
            "---",
            "pretty_name: Spiral Claude Chats (Private)",
            "---",
            "",
            "# spiral-claude-chats",
            "",
            f"Private archive of {len(manifest_entries)} scrubbed Claude Code & Claude Desktop transcripts.",
            f"- Raw size: {total_raw / (1024**3):.2f} GB",
            f"- Compressed size: {total_gz / (1024**2):.1f} MB",
            "- Index: `index.jsonl`",
            "- Transcripts: `sessions/<YYYY-MM>/<session_id>.jsonl.gz`",
            "",
        ]
    )
    (STAGE_DIR / "README.md").write_text(ds_readme, encoding="utf-8")

    print(f"Uploading {STAGE_DIR} ({total_gz / (1024**2):.1f} MB) to {repo_id}...")
    commit_info = api.upload_folder(
        folder_path=str(STAGE_DIR),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Upload {len(manifest_entries)} scrubbed Claude transcripts",
    )
    print(f"Upload complete: {commit_info.commit_url}")

    manifest = {
        "dataset_repo": repo_id,
        "dataset_url": f"https://huggingface.co/datasets/{repo_id}",
        "private": True,
        "session_count": len(manifest_entries),
        "raw_bytes": total_raw,
        "compressed_bytes": total_gz,
        "index_uri": f"https://huggingface.co/datasets/{repo_id}/resolve/main/index.jsonl",
        "sessions": manifest_entries,
    }
    (CLAUDE_DIR / "hf_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    print(f"Wrote {CLAUDE_DIR / 'hf_manifest.json'} and cleaned {STAGE_DIR}")


if __name__ == "__main__":
    main()
