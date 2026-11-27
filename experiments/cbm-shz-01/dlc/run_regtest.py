#!/usr/bin/env python3
"""Run the oracle-attested DLC release end to end on an isolated regtest (synthetic prices)."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "regtest"))
from clearing_release_regtest import Regtest  # noqa: E402
from oracle_dlc import Campaign, Node  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bitcoind", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--price1", type=float, default=101_500.0)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="cbm-dlc-") as tmp:
        node = Regtest(a.bitcoind, tmp)
        node.start()
        try:
            rpc = Node(Path(tmp) / "regtest" / ".cookie", node.port)
            rpc("createwallet", ["payer", False, False, "", False, True, True])
            miner = rpc("getnewaddress", wallet="payer")
            rpc("generatetoaddress", [110, miner])
            run = Path(tmp) / "run"
            c = Campaign(rpc, run, "dlc-rt", testnet=True, mine=lambda k: rpc("generatetoaddress", [k, miner]))
            c.extra_wallets = ["payer"]
            run.mkdir(parents=True, exist_ok=True)
            seed = bytes(range(32))
            c.setup("payer", 20_000, 30_000, 100_000.0, 10, 144, seed)
            c.presign_and_fund()
            c.close(a.price1, {"synthetic": True}, 2)
            c.reuse("payer")
            rep = c.report()
        finally:
            node.stop()
    txt = json.dumps(rep, indent=1, default=str) + "\n"
    if a.out:
        a.out.write_text(txt)
    print(txt)
    raise SystemExit(0 if rep["passed"] else 1)


if __name__ == "__main__":
    main()
