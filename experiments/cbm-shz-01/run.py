#!/usr/bin/env python3
"""Execute the registered CBM-SHZ-01 sweeps (spec: SPEC.md) and write aggregate results.

Synthetic-path cells (calibrated to Lighter BTC regimes) are deterministic and reproducible
in CI. The empirical-replay cell reads the local per-second Lighter cache and is run only
where that cache exists; its aggregate output is committed.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cbm.sim import Scenario, run, load_regimes  # noqa: E402

SWEEPS = {
    "regime": ("regime", ["calm", "median", "volatile"]),
    "imbalance_corr": ("imbalance_corr", [0.0, 0.3, 0.7, 1.0]),
    "leverage": ("leverage", [2.0, 5.0, 10.0, 20.0]),
    "maturity_h": ("maturity_h", [1.0, 24.0, 168.0]),
    "settle_period_h": ("settle_period_h", [0.25, 1.0, 6.0, 24.0]),
    "topology": ("topology", ["mesh", "star"]),
    "vault_edge_density": ("vault_edge_density", [1.0, 0.5, 0.25]),
    "vault_budget_frac": ("vault_budget_frac", [1.0, 0.9, 0.7]),
    "offline_frac": ("offline_frac", [0.0, 0.05, 0.2]),
    "funding_rate": ("funding_rate", [0.0025, 0.01, 0.05, 0.10]),
    "feerate": ("feerate", [2.0, 10.0, 50.0, 200.0]),
    "proof_batch_h": ("proof_batch_h", [0.25, 1.0, 6.0, 24.0]),
    "challenge_blocks": ("challenge_blocks", [6, 36, 144, 1008]),
    "advance_scope": ("advance_scope", ["all", "payouts"]),
    "daily_volume_usd": ("daily_volume_usd", [1e6, 2e7, 1e8]),
    "n_routers": ("n_routers", [1, 4, 16]),
}
KEEP = ("peak_btc", "btc_days", "capital_duration_days", "capital_btc_days_by_owner", "reuse_delay_h", "lp_recovery_delay_h",
        "chain_vb", "gross_settlement_btc", "net_settlement_btc", "deferred_btc", "unserved_btc", "impaired_claims_btc",
        "customer_cost_btc", "provider_cost_btc", "system_cost_btc", "system_cost_bps", "fee_ceiling_bps_vs_A", "provider_cost_bps",
        "fee_feasible_vs_A", "surplus_bps_vs_A", "capital_btc_days_saved_vs_A", "fee_ceiling_sat_per_btc_day_saved",
        "proof_cost_btc", "proof_batches", "peak_lp_advance_btc", "verification", "objects", "by_owner")


def slim(out):
    o = {k: out[k] for k in ("scenario", "contracts", "matched_btc", "gross_obligation_btc", "unenforceable_shortfall_btc")}
    o["arch"] = {a: {k: v for k, v in x.items() if k in KEEP} for a, x in out["arch"].items()}
    return o


def cells(base: Scenario, seeds):
    yield "base", base, seeds
    for sweep, (field, values) in SWEEPS.items():
        for v in values:
            if getattr(base, field) == v:
                continue
            yield f"{sweep}={v}", replace(base, **{field: v}, name=f"{sweep}={v}"), seeds[:1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regimes", type=Path, default=HERE / "data" / "lighter_regimes.json")
    ap.add_argument("--cache", type=Path, default=Path(os.environ.get("SHZ_LV_CACHE", "")) if os.environ.get("SHZ_LV_CACHE") else None)
    ap.add_argument("--horizon-days", type=float, default=7.0)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--output", type=Path, default=HERE / "results" / "sweeps.json")
    ap.add_argument("--empirical", action="store_true", help="also run the local empirical-replay cell")
    a = ap.parse_args()
    reg = load_regimes(a.regimes)
    base = Scenario(horizon_days=a.horizon_days)
    res = dict(schema="cbm-shz-01/sweeps/v1", base=asdict(base), cells={})
    t0 = time.time()
    for name, sc, seeds in cells(base, a.seeds):
        if a.only and not any(name.startswith(x) for x in a.only):
            continue
        runs = [slim(run(replace(sc, seed=sd), reg)) for sd in seeds]
        res["cells"][name] = runs
        A, C, D = (runs[0]["arch"][k] for k in ("A", "C", "D"))
        print(f"{name:28s} n={runs[0]['contracts']:7d} A={A['btc_days']:8.1f} C={C['btc_days']:8.1f} D={D['btc_days']:8.1f} "
              f"C_ceil={C['fee_ceiling_bps_vs_A']:.3f} C_prov={C['provider_cost_bps']:.3f} D_prov={D['provider_cost_bps']:.3f} "
              f"[{time.time() - t0:.0f}s]", flush=True)
    if a.empirical:
        if a.cache is None:
            raise SystemExit("--empirical needs SHZ_LV_CACHE")
        sc = replace(base, price_mode="empirical", name="empirical-replay")
        res["cells"]["empirical-replay"] = [slim(run(replace(sc, seed=sd), reg, a.cache)) for sd in a.seeds[:1]]
        print("empirical-replay done", flush=True)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(res, indent=1, default=float) + "\n")
    print("wrote", a.output, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
