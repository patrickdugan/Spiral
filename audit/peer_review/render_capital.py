"""Render the deterministic reference trace; never label this as regtest evidence."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).parent / "capital"
rows = json.loads((root / "trace.json").read_text())
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "svg.hashsalt": "spiral-capital-v1"})
fig, axes = plt.subplots(3, 1, figsize=(10, 10), constrained_layout=True)
x = [r["height"] for r in rows]
for key, label, color in [("fronting_sat", "Outstanding fronting", "#315f9b"),
                          ("unique_committed_sat", "Unique committed economic assets", "#b8702b"),
                          ("htlc_sat", "In-flight HTLCs", "#598b65")]:
    axes[0].step(x, [r[key] for r in rows], where="post", label=label, color=color)
axes[0].set(ylabel="satoshis", title="Reference-model lifecycle — synthetic observations")
axes[0].legend(loc="upper left", fontsize=9)
axes[0].set_ylim(bottom=0)
for key, label, color in [("fronting_sat_blocks", "Fronting integral", "#315f9b"),
                          ("unique_sat_blocks", "Unique committed integral", "#b8702b")]:
    axes[1].plot(x, [r[key] for r in rows], label=label, color=color)
axes[1].set(ylabel="sat-blocks", title="Categories overlap; their integrals must not be added")
axes[1].legend(fontsize=9)
states = ["NOT_CREATED", "FREE", "RESERVED", "COMMITTED", "RECOVERY_DUE", "RECOVERING", "CONFIRMING", "FREE_AGAIN", "TRANSFERRED_OUT"]
colors = plt.get_cmap("tab10")
# Event ordinal retains zero-duration transitions at a shared block height.
for index, key in enumerate(["backing", "reserve", "recovered"]):
    for i, row in enumerate(rows):
        axes[2].scatter(i, index, s=45, color=colors(states.index(row.get(key, "NOT_CREATED"))), marker="s")
axes[2].set(yticks=[0, 1, 2], yticklabels=["Original backing", "Initial reserve", "Recovered output"],
            xlabel="Accepted event ordinal", title="Asset disposition (zero-duration transitions retained)")
from matplotlib.lines import Line2D
handles = [Line2D([0], [0], marker="s", linestyle="", color=colors(i), label=s) for i, s in enumerate(states)]
axes[2].legend(handles=handles, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.28), fontsize=8)
for ax in axes[:2]:
    ax.set_xlabel("Observed block height")
    ax.axvline(10, color="#777777", alpha=.35, linestyle=":")
    ax.axvline(13, color="#777777", alpha=.35, linestyle=":")
    ax.grid(axis="y", alpha=.15)
fig.savefig(root / "capital-trace.png", dpi=160)
fig.savefig(root / "capital-trace.svg", metadata={"Date": None})
svg = root / "capital-trace.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8", newline="\n")
plt.close(fig)
