#!/usr/bin/env python3
"""CI check: re-run the base cell (seed 1) and compare with committed results/sweeps.json."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cbm.sim import Scenario, load_regimes, run  # noqa: E402
from run import slim  # noqa: E402

KEYS = ("peak_btc", "btc_days", "chain_vb", "gross_settlement_btc", "net_settlement_btc", "customer_cost_btc",
        "provider_cost_btc", "fee_ceiling_bps_vs_A", "surplus_bps_vs_A", "impaired_claims_btc")


def main():
    sw = json.loads((HERE / "results" / "sweeps.json").read_text())
    committed = sw["cells"]["base"][0]
    base = Scenario(**sw["base"])
    fresh = slim(run(replace(base, seed=committed["scenario"]["seed"]), load_regimes(HERE / "data" / "lighter_regimes.json")))
    bad = []
    assert fresh["contracts"] == committed["contracts"], (fresh["contracts"], committed["contracts"])
    for arch, a in committed["arch"].items():
        for k in KEYS:
            if k not in a:
                continue
            x, y = a[k], fresh["arch"][arch][k]
            if not math.isclose(x, y, rel_tol=1e-6, abs_tol=1e-9):
                bad.append((arch, k, x, y))
    if bad:
        for b in bad:
            print("MISMATCH", *b)
        sys.exit(1)
    print(f"base cell reproduces: {committed['contracts']} contracts, {len(committed['arch'])} architectures, {len(KEYS)} metrics each")


if __name__ == "__main__":
    main()
