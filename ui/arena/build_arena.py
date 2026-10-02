"""Inline a replay JSON into the arena template to produce a self-contained page.

Run from the repository root after generating a replay:

    # swarm-compromise arena (defaults)
    python -m spiral_ln.swarm_replay --output output/swarm_compromise/replay.json
    python ui/arena/build_arena.py

    # RTG control arena
    python -m spiral_ln.rtg_arena_export --output output/rtg_arena/replay.json
    python ui/arena/build_arena.py --replay output/rtg_arena/replay.json --out ui/arena/rtg_index.html
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default="ui/arena/index.template.html")
    parser.add_argument("--replay", default="output/swarm_compromise/replay.json")
    parser.add_argument("--out", default="ui/arena/index.html")
    parser.add_argument("--title", default=None, help="override the page <title>")
    args = parser.parse_args(argv)

    template = Path(args.template).read_text(encoding="utf-8")
    data = Path(args.replay).read_text(encoding="utf-8")
    if "</script" in data.lower():
        raise ValueError("replay data contains a closing script tag; refusing to inline")
    html = template.replace("__REPLAY_JSON__", data)
    if args.title:
        import re

        html = re.sub(r"<title>.*?</title>", f"<title>{args.title}</title>", html, count=1)
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"wrote {args.out} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
