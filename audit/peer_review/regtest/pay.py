"""First funded-to-settled phase. Will not repeat a recorded monetary action."""
from bootstrap import core
from launch import bark
from fund import cln, mine
from attest import save, DEST
from observe import snapshot, redact
import json
import time


def action(label, fn):
    if (DEST / f"action-{label}.json").exists():
        raise RuntimeError(f"{label} already attempted; inspect existing state instead of replaying")
    entry = {"action": label, "monotonic_start_ns": time.monotonic_ns(), "height": core("getblockcount"), "state": "intent"}
    save(f"action-{label}.json", entry)
    try:
        result = fn()
        entry.update(state="returned", monotonic_end_ns=time.monotonic_ns(), result=redact(result))
        save(f"action-{label}.json", entry)
        return result
    except Exception as exc:
        entry.update(state="uncertain-failure", error=str(exc), monotonic_end_ns=time.monotonic_ns())
        save(f"action-{label}.json", entry)
        raise


def main():
    action("board-100k", lambda: json.loads(bark("board", "100000sat").stdout))
    snapshot("board-broadcast")
    mine(3)
    print(bark("balance").stdout)
    snapshot("board-confirmed")
    invoice = action("invoice-60k", lambda: cln("peer", "invoice", "60000000msat", "spiral-first-60k", "owned regtest capital accounting"))
    # This pinned CLI reports completion on stderr and returns empty stdout.
    action("pay-60k", lambda: {"exit_code": bark("send", invoice["bolt11"], "--wait").returncode})
    snapshot("payment-settled")


if __name__ == "__main__":
    main()
