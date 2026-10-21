"""Summarize every frozen-budget holdout; do not select winning seeds/cells."""
import hashlib
import json
import math
import random
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

root = Path("audit/peer_review/capital")
cells = ["zero", "drain", "accumulate", "steady"]
artifacts = {c: json.loads((root / f"fixed-budget-result-{c}.json").read_text(encoding="utf-8")) for c in cells}
expected_seeds = list(range(301, 325))

def stats(values):
    if not values:
        return {"n": 0, "mean": None, "bootstrap95": None}
    mean = statistics.mean(values)
    r = random.Random(1907)
    means = sorted(statistics.mean(r.choices(values, k=len(values))) for _ in range(2000))
    return {"n": len(values), "mean": mean, "min": min(values), "max": max(values), "bootstrap95": [means[49], means[1949]]}

summary = []
comparisons = []
channel_summary = []
delivery_image = []
ratio_image = []
ratio_n = []
labels = []
for cell in cells:
    data = artifacts[cell]
    pilot = root / f"fixed-budget-pilot-{cell}.json"
    assert data["pilot_file_sha256"] == hashlib.sha256(pilot.read_bytes()).hexdigest()
    for initial in [0, 250000]:
        rows = [r for r in data["rows"] if r["initial_gross_holder_sat"] == initial]
        assert [r["seed"] for r in rows] == expected_seeds
        groups = [c["group_size"] for c in rows[0]["channels"]]
        image_row = []
        for delay in [6, 144]:
            results = [next(a["result"] for a in r["ark"] if a["delay"] == delay) for r in rows]
            offered = [x["offered_sat"] for x in results]
            assert all(x["offered_sat"] == r["channels"][0]["offered_sat"] for x, r in zip(results, rows))
            s = {"cell": cell, "initial": initial, "delay": delay,
                 "delivery": stats([x["delivery_rate"] for x in results]),
                 "target_passes": sum(x["target_met"] for x in results),
                 "outbound_delivery": stats([x["directional_value_sat"]["out_delivered"] / x["directional_value_sat"]["out_offered"] for x in results]),
                 "initial_funded_sat": results[0]["initial_funded_resource_sat"],
                 "miner_fees": stats([x["miner_fees_sat"] for x in results]),
                 "fronting_sat_blocks": stats([int(x["integrals_sat_blocks"]["fronting"]) for x in results]),
                 "funding_per_offered_blocks": stats([x["per_offered_blocks"]["initialFunding"] for x in results]),
                 "funding_per_delivered_blocks": stats([x["per_delivered_blocks"]["initialFunding"] for x in results if x["delivered_sat"]]),
                 "terminal_W_sat": stats([x["terminal"]["W_sat"] for x in results]),
                 "expired_holder_sat": stats([x["terminal"]["expired_holder_sat"] for x in results])}
            summary.append(s); image_row.append(s["delivery"]["mean"] * 100)
            for group in groups:
                paired = [(x, next(c for c in r["channels"] if c["group_size"] == group)) for x, r in zip(results, rows)]
                accepted = [(a, c) for a, c in paired if a["target_met"] and c["target_met"]]
                ratios = [a["per_delivered_blocks"]["initialFunding"] / c["per_delivered_blocks"] for a, c in accepted]
                comparisons.append({"cell": cell, "initial": initial, "delay": delay, "group": group,
                    "both_target_passes": len(accepted), "paired_funding_per_delivered_ratio": stats(ratios),
                    "fixed_funding_ratio_if_target_met": accepted[0][0]["initial_funded_resource_sat"] / accepted[0][1]["initial_funded_resource_sat"] if accepted else None})
        for group in groups:
            results = [next(c for c in r["channels"] if c["group_size"] == group) for r in rows]
            c = {"cell": cell, "initial": initial, "group": group, "delivery": stats([x["delivery_rate"] for x in results]),
                 "target_passes": sum(x["target_met"] for x in results), "initial_funded_sat": results[0]["initial_funded_resource_sat"]}
            channel_summary.append(c)
            if group in {groups[0], groups[-1]}:
                image_row.append(c["delivery"]["mean"] * 100)
        delivery_image.append(image_row)
        paired = [next(c for c in comparisons if c["cell"] == cell and c["initial"] == initial and c["delay"] == d and c["group"] == g)
                  for d in [6, 144] for g in [groups[0], groups[-1]]]
        ratio_image.append([c["paired_funding_per_delivered_ratio"]["mean"] or math.nan for c in paired])
        ratio_n.append([c["both_target_passes"] for c in paired])
        labels.append(f"{cell} / {'250k' if initial else 'zero'}")

output = {"evidence_class": "conditional_single_participant_fee_aware_forecast", "ark": summary, "channels": channel_summary, "comparisons": comparisons,
          "interval_method": "2,000 paired-seed percentile bootstrap resamples, deterministic seed 1907; intervals describe Monte Carlo seed variation only, not implementation uncertainty",
          "interpretation": "Conditional ratios exclude target-failing pairs and report their retained n explicitly; missing ratios are not zero or proof of superiority."}
(root / "fixed-budget-summary.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8", newline="\n")

lines = ["# Frozen-budget, fee-aware forecast results", "", "This is the single-participant transaction scenario defined in [the committed protocol](capital_fixed_budget_protocol.md). "
         "It uses disjoint pilot and holdout seeds, the recorded retained-backing semantics, and pinned integer fees. "
         "It does not estimate pooled-tree amortization or measured operational latency.", "",
         "![Delivery and eligible paired funding ratios](capital/fixed-budget-comparison.png)", "",
         "## Service results", "", "All means include 24 holdout seeds. The target is 99% of gross offered value. "
         "Funding includes idle wallet, physical roots, and both sides of channels once; holder claims and fronting are overlays.", "",
         "| Demand | Initial per holder | Recovery delay | Mean delivery | Target passes | Initial funding (sat) | Mean miner fees (sat) |", "|---|---:|---:|---:|---:|---:|---:|"]
for s in summary:
    lines.append(f"| {s['cell']} | {s['initial']:,} | {s['delay']} | {s['delivery']['mean']:.2%} | {s['target_passes']}/24 | {s['initial_funded_sat']:,} | {s['miner_fees']['mean']:,.0f} |")
lines += ["", "## Channels and pooled groups", "", "Groups share directional capacity but cannot spend other holders' balances. All offered events remain in the denominator.", "",
          "| Demand | Initial per holder | Group size | Mean delivery | Target passes | Initial funding (sat) |", "|---|---:|---:|---:|---:|---:|"]
for s in channel_summary:
    lines.append(f"| {s['cell']} | {s['initial']:,} | {s['group']} | {s['delivery']['mean']:.2%} | {s['target_passes']}/24 | {s['initial_funded_sat']:,} |")
lines += ["", "## Eligible matched-service ratios", "", "Ratios below divide Ark's fixed funding sat-blocks per delivered sat by the channel/group counterpart on the same seed. "
          "A ratio is published only when both meet 99%. Values above one favor the channel/group under this policy. "
          "Intervals describe paired-seed variation, conditional on meeting the target; they do not cover transaction-policy uncertainty.", "",
          "| Demand | Initial | Delay | Group | Both pass | Mean ratio | Bootstrap 95% |", "|---|---:|---:|---:|---:|---:|---|"]
for c in comparisons:
    s = c["paired_funding_per_delivered_ratio"]
    ratio = f"{s['mean']:.3f}" if s['mean'] is not None else "unavailable"
    interval = f"[{s['bootstrap95'][0]:.3f}, {s['bootstrap95'][1]:.3f}]" if s['bootstrap95'] else "—"
    lines.append(f"| {c['cell']} | {c['initial']:,} | {c['delay']} | {c['group']} | {c['both_target_passes']}/24 | {ratio} | {interval} |")
lines += ["", "## Audit interpretation", "",
          "The result JSON files publish exact terminal roots, active/expired claims, exhausted recovery shortfalls, and the future eligible sweep schedule. "
          "No obligation disappears at the horizon. Sat-seconds remain null. The instantaneous in-flight integral is a forecast assumption, not a measured duration.", "",
          "The 100–109-sat steady receipts cannot support the declared fee plus a fresh 330-sat round output. More capital does not repair that policy mismatch. "
          "Pooled receipt inventory and batching may produce different results and require their own verified adapter and predeclared campaign.", "",
          "The single-participant miner costs are material. A broader ranking of Ark versus channels is not justified by this cost scenario alone. "
          "The completed live outgoing/recovery/reuse trace supports the capital lock rule; live inbound, failure/revocation, exit, repeated clean restarts and testnet4 clocks remain separate validation work.", ""]
lines += ["The channel opening cost and directional buffers are held at their observed fixture values. "
          "They are not a fitted reserve/commitment-fee model for arbitrary channel sizes. "
          "Meeting the invoice-delivery target also does not imply immediate spendability of every terminal holder claim; expired claims remain disclosed in the result JSON.", ""]
Path("audit/peer_review/capital_fixed_budget_results.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

plt.rcParams.update({"svg.hashsalt": "spiral-fixed-budget-v1", "font.size": 10})
fig, axes = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1, 1.15]}, layout="constrained")
delivery = np.array(delivery_image); ratios = np.array(ratio_image)
im = axes[0].imshow(delivery, vmin=0, vmax=100, cmap="YlGnBu", aspect="auto")
axes[0].set_title("Achieved value delivery (%) — all 24 seeds", pad=14)
axes[0].set_xticks(range(4), ["Ark +6", "Ark +144", "Direct", "Fully pooled"])
axes[0].set_yticks(range(8), labels)
for i in range(8):
    for j in range(4):
        axes[0].text(j, i, f"{delivery[i,j]:.1f}%", ha="center", va="center", color="white" if delivery[i,j] > 65 else "black")
fig.colorbar(im, ax=axes[0], shrink=.65, label="Gross invoice value delivered")
cmap = plt.get_cmap("YlOrRd").copy(); cmap.set_bad("#e7e9ee")
im2 = axes[1].imshow(ratios, cmap=cmap, aspect="auto", vmin=1, vmax=max(2, float(np.nanmax(ratios))) if np.any(np.isfinite(ratios)) else 2)
axes[1].set_title("Funding per delivered sat: Ark / comparator", pad=14)
axes[1].set_xticks(range(4), ["+6 / direct", "+6 / pool", "+144 / direct", "+144 / pool"])
axes[1].set_yticks(range(8), labels)
for i in range(8):
    for j in range(4):
        label = f"{ratios[i,j]:.2f}×\nn={ratio_n[i][j]}" if math.isfinite(ratios[i,j]) else "target\nnot met"
        axes[1].text(j, i, label, ha="center", va="center", fontsize=9,
                     color="white" if math.isfinite(ratios[i,j]) and ratios[i,j] >= 5 else "black")
fig.colorbar(im2, ax=axes[1], shrink=.65, label="Both mechanisms meet 99% on retained pairs")
fig.suptitle("Frozen pilot budgets • single-participant transaction-cost scenario", fontsize=16)
fig.savefig(root / "fixed-budget-comparison.png", dpi=160)
fig.savefig(root / "fixed-budget-comparison.svg", metadata={"Date": None})
svg = root / "fixed-budget-comparison.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"ark_cells": len(summary), "channel_cells": len(channel_summary), "comparisons": len(comparisons),
                  "ark_target_passes": sum(s["target_passes"] for s in summary), "ark_runs": 24 * len(summary)}))
