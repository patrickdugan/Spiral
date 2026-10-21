#!/usr/bin/python3
"""Owned-regtest fault injection, not a production hold-invoice implementation.

Only the configured payment hash is delayed. Fail after explicit release or
90 seconds, and never reveal a preimage. All other HTLCs continue normally.
Protocol: https://docs.corelightning.org/reference/hook-htlc_accepted
"""
import json
import sys
import threading
import time
from pathlib import Path

CONTROL = Path("/data/spiral-fault-control.json")
EVENTS = Path("/data/spiral-fault-events.jsonl")
LOCK = threading.Lock()


def reply(request, result):
    with LOCK:
        print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}) + "\n", flush=True)


def record(event, payment_hash, **fields):
    with LOCK:
        with EVENTS.open("a") as stream:
            stream.write(json.dumps({"event": event, "payment_hash": payment_hash,
                "monotonic_ns": time.monotonic_ns(), **fields}) + "\n")


def hold(request, payment_hash):
    begin = time.monotonic()
    record("receiver_hook_accepted", payment_hash,
           htlc=request["params"].get("htlc"), peer_id=request["params"].get("peer_id"))
    released = False
    while time.monotonic() - begin < 90:
        try:
            control = json.loads(CONTROL.read_text())
            released = control.get("payment_hash") == payment_hash and control.get("release") is True
        except (OSError, ValueError):
            released = False
        if released:
            break
        time.sleep(.05)
    record("receiver_failure_response", payment_hash, trigger="operator_release" if released else "90_second_guard")
    # BOLT #4 permanent_node_failure. The owned receiver deliberately rejects.
    reply(request, {"result": "fail", "failure_message": "2002"})


def main():
    regtest = False
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        method = request.get("method")
        if method == "getmanifest":
            reply(request, {"options": [], "rpcmethods": [], "subscriptions": [],
                            "hooks": [{"name": "htlc_accepted"}], "dynamic": True})
        elif method == "init":
            regtest = request["params"]["configuration"]["network"] == "regtest"
            reply(request, {} if regtest else {"disable": "owned regtest only"})
        elif method == "htlc_accepted":
            params = request["params"]
            payment_hash = params.get("htlc", {}).get("payment_hash") or params.get("onion", {}).get("payment_hash")
            try:
                target = json.loads(CONTROL.read_text()).get("payment_hash")
            except (OSError, ValueError):
                target = None
            if regtest and payment_hash and payment_hash == target:
                threading.Thread(target=hold, args=(request, payment_hash), daemon=True).start()
            else:
                reply(request, {"result": "continue"})


if __name__ == "__main__":
    main()
