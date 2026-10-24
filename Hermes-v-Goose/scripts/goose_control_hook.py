"""Entry point goose runs for the control-gate plugin's PreToolUse hook.

Any uncaught error exits non-zero, which goose treats as a hook failure; the
plugin sets ``on_failure: block``, so the tool call is refused.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime_control.shims.goose_hook import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
