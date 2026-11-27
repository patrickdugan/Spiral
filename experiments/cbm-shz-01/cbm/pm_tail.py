#!/usr/bin/env python3
"""How often does BTC move by more than the portfolio-margin gap before close-out?

For every day of the public Lighter BTC trade cache and every start minute, the absolute log
return over h = remargin + liquidation lag minutes is compared with the gap
g = mult x sigma x sqrt(h). Two sigma choices: the fixed median-regime sigma (what C_pmg
uses) and the day's own realised sigma (an oracle that a real margin model can only
approximate). The exceedance probability times the default rate is the expected share of
defaulters whose claims GapBuffer.lean does not cover. Aggregates only are written.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def minute_prices(path: Path) -> np.ndarray:
    px = np.load(path)["last_px"].astype(float)
    ok = ~np.isnan(px)
    idx = np.where(ok, np.arange(len(px)), -1)
    np.maximum.accumulate(idx, out=idx)
    pxf = np.where(idx >= 0, px[np.maximum(idx, 0)], np.nan)
    return pxf[59::60]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--regimes", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    reg = json.loads(a.regimes.read_text())
    base_sigma = next(d["sigma_1m"] for d in reg["days"] if d["day"] == reg["regimes"]["median"])
    days = sorted(a.cache.glob("trades_BTC_*.npz"))
    series = [minute_prices(p) for p in days]
    rows = []
    for h in (10, 15, 65):
        for mult in (2.0, 4.0, 6.0, 8.0):
            tot = exc_fixed = exc_own = 0
            worst = []
            for lp in (np.log(s) for s in series):
                r1 = np.diff(lp)
                r1 = r1[np.isfinite(r1)]
                if len(r1) < 1000:
                    continue
                own = r1.std()
                rh = lp[h:] - lp[:-h]
                rh = np.abs(rh[np.isfinite(rh)])
                tot += len(rh)
                exc_fixed += int((rh > mult * base_sigma * np.sqrt(h)).sum())
                exc_own += int((rh > mult * own * np.sqrt(h)).sum())
                worst.append(float(rh.max() / (base_sigma * np.sqrt(h))))
            rows.append(dict(horizon_min=h, mult=mult, windows=tot,
                             exceed_fixed_median_sigma=exc_fixed / tot, exceed_own_day_sigma=exc_own / tot,
                             worst_move_in_median_sigma_units=max(worst)))
            print(rows[-1])
    a.output.write_text(json.dumps(dict(schema="cbm-shz-01/pm-tail/v1", days=len(series), base_sigma_1m=base_sigma,
                                        rows=rows, price_path_published=False), indent=1) + "\n")


if __name__ == "__main__":
    main()
