#!/usr/bin/env python3
"""Figures for the paper section "Where the Rent Moves" from committed results only."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "paper" / "tex" / "figs_rent"
plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e1e0d9", "grid.linewidth": 0.5})
INK, MUTED = "#0b0b0b", "#898781"
COL = {"traders": "#2a78d6", "router_operators": "#eb6834", "lp": "#1baf7a", "operator": "#eda100"}
LABEL = {"traders": "traders", "router_operators": "router operators", "lp": "LP advances", "operator": "operator bond"}


def load():
    return json.loads((HERE / "results" / "sweeps.json").read_text())


def cell(sw, name, arch, key):
    return sw["cells"][name][0]["arch"][arch][key]


def fig_capital(sw):
    base = sw["cells"]["base"][0]
    archs = ["A", "B", "B_pm", "C", "C_pm", "D", "E", "E_pm"]
    fig, ax = plt.subplots(figsize=(5.6, 2.4))
    bottom = [0.0] * len(archs)
    for owner in ("traders", "router_operators", "lp", "operator"):
        vals = [base["arch"][a]["capital_btc_days_by_owner"].get(owner, 0.0) / base["matched_btc"] for a in archs]
        ax.bar(archs, vals, bottom=bottom, color=COL[owner], label=LABEL[owner], width=0.65, edgecolor="white", linewidth=0.6)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_ylabel("locked BTC-days per BTC matched")
    ax.legend(frameon=False, fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / "capital_by_arch.pdf")
    plt.close(fig)


def fig_feasibility(sw):
    fig, axes = plt.subplots(1, 2, figsize=(5.6, 2.2))
    for ax, (field, vals, xlabel) in zip(axes, (("funding_rate", [0.0025, 0.01, 0.05, 0.10], "trader BTC funding rate"),
                                              ("feerate", [2.0, 10.0, 50.0, 200.0], "fee rate (sat/vB)"))):
        names = [f"{field}={v}" if f"{field}={v}" in sw["cells"] else "base" for v in vals]
        ceil = [cell(sw, n, "C", "fee_ceiling_bps_vs_A") for n in names]
        prov = [cell(sw, n, "C", "provider_cost_bps") for n in names]
        dprov = [cell(sw, n, "D", "provider_cost_bps") for n in names]
        dceil = [cell(sw, n, "D", "fee_ceiling_bps_vs_A") for n in names]
        ax.plot(vals, ceil, color="#2a78d6", lw=1.5, marker="o", ms=3, label="C fee ceiling")
        ax.plot(vals, prov, color="#2a78d6", lw=1.5, ls="--", marker="o", ms=3, label="C provider cost")
        ax.plot(vals, dceil, color="#1baf7a", lw=1.5, marker="s", ms=3, label="D fee ceiling")
        ax.plot(vals, dprov, color="#1baf7a", lw=1.5, ls="--", marker="s", ms=3, label="D provider cost")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel(xlabel)
    axes[0].set_ylabel("bp of matched notional")
    axes[0].legend(frameon=False, fontsize=6)
    fig.tight_layout()
    fig.savefig(OUT / "fee_feasibility.pdf")
    plt.close(fig)


def fig_challenge(sw):
    blocks = [6, 36, 144, 1008]
    names = [f"challenge_blocks={b}" if f"challenge_blocks={b}" in sw["cells"] else "base" for b in blocks]
    fig, ax = plt.subplots(figsize=(2.8, 2.2))
    rel = lambda n, a: cell(sw, n, a, "btc_days") / cell(sw, n, "A", "btc_days")
    ax.plot(blocks, [rel(n, "D") for n in names], color="#1baf7a", lw=1.5, marker="s", ms=3, label="D / A")
    ax.plot(blocks, [rel(n, "C") for n in names], color="#2a78d6", lw=1.5, marker="o", ms=3, label="C / A")
    ax.plot(blocks, [rel(n, "E") for n in names], color=MUTED, lw=1.0, ls=":", label="E / A")
    ax.axhline(1.0, color=INK, lw=0.6)
    ax.set_xscale("log")
    ax.set_xlabel("BitVM3 challenge period (blocks)")
    ax.set_ylabel("locked BTC-time relative to A")
    ax.legend(frameon=False, fontsize=6)
    fig.tight_layout()
    fig.savefig(OUT / "challenge_period.pdf")
    plt.close(fig)


def fig_maturity(sw):
    mats = [1.0, 24.0, 168.0]
    names = [f"maturity_h={m}" if f"maturity_h={m}" in sw["cells"] else "base" for m in mats]
    fig, ax = plt.subplots(figsize=(2.8, 2.2))
    for a, c, ls in (("A", "#eb6834", "-"), ("C", "#2a78d6", "-"), ("C_pm", "#2a78d6", "--"), ("E", MUTED, ":")):
        ax.plot(mats, [cell(sw, n, a, "capital_duration_days") for n in names], color=c, ls=ls, lw=1.5, marker="o", ms=3, label=a)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("contract maturity (hours)")
    ax.set_ylabel("capital duration (days)")
    ax.legend(frameon=False, fontsize=6)
    fig.tight_layout()
    fig.savefig(OUT / "maturity.pdf")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sw = load()
    fig_capital(sw); fig_feasibility(sw); fig_challenge(sw); fig_maturity(sw)
    print("figures in", OUT)


if __name__ == "__main__":
    main()
