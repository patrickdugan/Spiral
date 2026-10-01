"""Inline the replay JSON into the arena template to produce a self-contained page.

Run from the repository root after generating the replay:

    python -m spiral_ln.swarm_replay --output output/swarm_compromise/replay.json
    python ui/arena/build_arena.py
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE = Path("ui/arena/index.template.html")
REPLAY = Path("output/swarm_compromise/replay.json")
OUT = Path("ui/arena/index.html")


def main() -> int:
    template = TEMPLATE.read_text(encoding="utf-8")
    data = REPLAY.read_text(encoding="utf-8")
    if "</script" in data.lower():
        raise ValueError("replay data contains a closing script tag; refusing to inline")
    html = template.replace("__REPLAY_JSON__", data)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
