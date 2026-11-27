#!/usr/bin/env python3
"""Volatility and demand-timing regimes for CBM-SHZ-01 from public Lighter BTC trades.

Input: the per-second cache written by SatsHedgeZero research/latency_value/trades_daily.py
(public AWS Lighter trades; per-second taker volume, trade count and last trade price).
Output (committed): per-day aggregates only, namely realised one-minute volatility, tail
quantiles of one-minute returns, a 288-bucket intraday intensity profile, the taker-buy
share and the distribution of mean trade size. No price level or price path is written.

Regimes are chosen ex post as the calm (lowest realised volatility), median and volatile
(highest) days. They are calibration targets for synthetic paths; the empirical replay
arm reads the local price path directly and commits only results.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def day_stats(path: Path) -> dict:
    z = np.load(path)
    px = z["last_px"].astype(float)
    ok = ~np.isnan(px)
    idx = np.where(ok, np.arange(len(px)), -1)
    np.maximum.accumulate(idx, out=idx)
    pxf = np.where(idx >= 0, px[np.maximum(idx, 0)], np.nan)
    minute = pxf[59::60]
    r = np.diff(np.log(minute))
    r = r[np.isfinite(r)]
    vol = z["buy_usd"] + z["sell_usd"]
    cnt = z["count"]
    prof = vol.reshape(288, 300).sum(1)
    sec_mean = vol[cnt > 0] / cnt[cnt > 0]
    return dict(
        day=path.stem.split("_")[-1],
        minutes=int(len(r)),
        sigma_1m=float(r.std()),
        abs_r1m_q999=float(np.quantile(np.abs(r), 0.999)),
        abs_r1m_max=float(np.abs(r).max()),
        kurtosis_1m=float(((r - r.mean()) ** 4).mean() / r.var() ** 2),
        daily_volume_usd=float(vol.sum()),
        trades=int(cnt.sum()),
        buy_share=float(z["buy_usd"].sum() / vol.sum()),
        intensity_profile_288=(prof / prof.sum()).round(6).tolist(),
        mean_trade_usd_q=[float(x) for x in np.quantile(sec_mean, [0.1, 0.25, 0.5, 0.75, 0.9, 0.99])],
        liquidation_share=float(z["liq_usd"].sum() / vol.sum()),
        price_median_rounded_k=float(np.round(np.nanmedian(pxf) / 1000)),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True, help="SHZ_LV cache dir with trades_BTC_<day>.npz")
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    days = [day_stats(p) for p in sorted(a.cache.glob("trades_BTC_*.npz"))]
    days = [d for d in days if d["minutes"] > 1400]
    order = sorted(days, key=lambda d: d["sigma_1m"])
    regimes = {"calm": order[0]["day"], "median": order[len(order) // 2]["day"], "volatile": order[-1]["day"]}
    doc = dict(schema="cbm-shz-01/lighter-regimes/v1", source="public Lighter BTC trades (AWS public blockchain), per-second cache",
               days=days, regimes=regimes, price_path_published=False)
    a.output.write_text(json.dumps(doc, indent=1) + "\n")
    for k, v in regimes.items():
        d = next(x for x in days if x["day"] == v)
        print(k, v, f"sigma_1m={d['sigma_1m']:.6f} vol=${d['daily_volume_usd']/1e6:.0f}M kurt={d['kurtosis_1m']:.1f}")


if __name__ == "__main__":
    main()
