"""Served-outpoint journal: each proven payment outpoint is served at most once.

JSON lines, appended and fsync'ed before the desk acts on them. The last record for an outpoint
is its state:
- `reserved`: the desk is paying it; a crash leaves it here, and the desk refuses the outpoint
  (`order_in_flight`) until an operator records what happened;
- `paid`: served, with the payout txid;
- `released`: a reservation undone before anything was broadcast.

One desk process per journal.
"""
from __future__ import annotations

import json
import os
import time

from .errors import Refusal


class Ledger:
    def __init__(self, path: str | None):
        self.path = path
        self.state: dict = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        self.state[rec["outpoint"]] = rec

    def _append(self, rec: dict) -> None:
        rec = dict(rec, ts=int(time.time()))
        self.state[rec["outpoint"]] = rec
        if not self.path:
            return
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def check_free(self, outpoint: str) -> None:
        rec = self.state.get(outpoint)
        if rec is None or rec["state"] == "released":
            return
        if rec["state"] == "paid":
            raise Refusal("already_served", f"{outpoint} paid by {rec.get('payout_txid')}")
        raise Refusal("order_in_flight", f"{outpoint} reserved at {rec.get('ts')}")

    def reserve(self, outpoint: str, payout_sats: int, sender_spk: str) -> None:
        self.check_free(outpoint)
        self._append({"outpoint": outpoint, "state": "reserved", "payout_sats": payout_sats, "sender_spk": sender_spk})

    def paid(self, outpoint: str, payout_txid: str) -> None:
        self._append({"outpoint": outpoint, "state": "paid", "payout_txid": payout_txid})

    def release(self, outpoint: str, why: str) -> None:
        self._append({"outpoint": outpoint, "state": "released", "why": why})
