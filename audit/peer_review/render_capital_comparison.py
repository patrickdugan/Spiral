"""Render the completed paired sensitivity without promoting it to final acceptance."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['svg.hashsalt'] = 'spiral-retained-sensitivity-v1'
import matplotlib.pyplot as plt

root = Path(__file__).parent
cells = ['zero', 'drain', 'accumulate', 'steady']
data = [json.loads((root / 'capital' / f'structural-comparison-{cell}.json').read_text(encoding='utf-8')) for cell in cells]
lines = ['# Retained-backing structural sensitivity', '',
         'Evidence class: implementation-informed, fee-free forecast. This is a completed paired sensitivity, **not the final fixed-budget capital-efficiency comparison**.', '',
         'The 34-event regtest reconstruction establishes retained payment change and recovery after an original-board sweep. This rerun applies those structural findings to the four existing demand families, using 24 paired seeds (101–124), a 4,320-block lifetime, eight lifetimes, and the same offered sequences for every mechanism. The six-block scenario uses the recorded expiry-to-reuse detection gap; it is not a production latency estimate. The 144-block scenario is a declared stress assumption.', '',
         '| Workload | Delivered / offered | Fronting CT / old model, +6 blocks | Fronting CT / old model, +144 blocks | Seeds meeting 99% |',
         '|---|---:|---:|---:|---:|']
for d in data:
    a, b = d['summaries']
    lines.append(f"| {d['cell']} | {a['delivery_rate']['mean']:.2%} | {a['retained_over_legacy_fronting']['mean']:.3f} | {b['retained_over_legacy_fronting']['mean']:.3f} | {a['target_passes']}/24 |")
lines += ['', 'Both policies deliver the same value on every paired seed. Channel and pooled-channel results are unchanged, and their failure counts match the holder-affordability failures. At the six-block delay, retained change reduces fronting in all four families. At 144 blocks, the accumulating case exceeds the old model by about 24%; retained expiry causes earlier refreshes while longer recovery keeps them outstanding. Low initial balances prevent several families from meeting the delivery target even under oracle sizing. Those failures remain in the offered denominator.', '',
          'Each JSON artifact publishes fronting, channel and pooled-channel capital-time over both offered and delivered volume, the delivery rate, F/C/W at the horizon, and a grouped future recovery schedule. Outstanding recovery is right-censored at the horizon; its later schedule is explicitly a forecast. The old duration index is retained only as a diagnostic and is flagged as **not a deduplicated unique-capital total**.', '',
          'A separate physical-resource estimate partitions each fee-free onchain root into live and forfeited principal, then adds the separately provisioned server Lightning channel once. It also charges idle onchain reserve up to the oracle peak backing budget. This boundary includes both sides of the Lightning channel and is not the operator-only economic A ledger or a market funding-cost estimate. The estimate is rejected if a live claim reaches expiry without a timely refresh. These partition assumptions still require fee-aware extension and live receipt validation.', '',
          '![Paired fronting sensitivity](capital/structural-comparison.png)', '',
          '## Remaining comparison work', '',
          'The final acceptance run must include the observed service/miner fees and 330-sat round backing overhead, explicit underlying-asset coverage, frozen budgets chosen on disjoint pilot seeds, the predeclared 99% service target, and pre-existing-balance as well as zero-balance cases. Receipt and automatic-refresh behavior remain aggregate assumptions here. No overall Ark-versus-channel efficiency ranking follows from this fee-free component experiment.', '',
          'Reproduce each cell from the repository root:', '', '```text',
          'node --experimental-strip-types audit/peer_review/capital_comparison.ts zero',
          'node --experimental-strip-types audit/peer_review/capital_comparison.ts drain',
          'node --experimental-strip-types audit/peer_review/capital_comparison.ts accumulate',
          'node --experimental-strip-types audit/peer_review/capital_comparison.ts steady', '```', '',
          'The four cells have a 30-minute per-process guard, within the two-hour exploratory campaign cap. The completed runs took about one minute at most per cell on this host. Monte Carlo intervals describe variation conditional on this generator, not mainnet uncertainty.', '']
(root / 'capital_comparison.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
fig, ax = plt.subplots(figsize=(9, 4.5), layout='constrained')
for j, (label, color) in enumerate([('+6 blocks (recorded detection gap)', '#17608b'), ('+144 blocks (stress assumption)', '#bc6b26')]):
    means, low, high = [], [], []
    for d in data:
        s = d['summaries'][j]['retained_over_legacy_fronting']; means.append(s['mean']); low.append(s['mean'] - s['mc95'][0]); high.append(s['mc95'][1] - s['mean'])
    x = [i + (j - .5) * .22 for i in range(4)]
    ax.errorbar(x, means, yerr=[low, high], fmt='o', capsize=4, color=color, label=label)
ax.axhline(1, color='#777777', linestyle='--', linewidth=1)
ax.set_xticks(range(4), ['Balanced', 'Draining', 'Accumulating', 'Few steady'])
ax.set_ylabel('Retained / original fronting sat-blocks'); ax.set_ylim(.4, 1.4)
ax.set_title('Fronting sensitivity depends on workload and recovery delay', weight='bold')
ax.legend(frameon=False, loc='lower right'); ax.grid(axis='y', alpha=.2); ax.spines[['top', 'right']].set_visible(False)
fig.supxlabel('24 paired seeds • 95% Monte Carlo intervals • Same offered and delivered value\nExcludes fees and round overhead; not total unique capital or a fixed-budget service-target result', fontsize=9)
for ext in ['png', 'svg']:
    p = root / 'capital' / f'structural-comparison.{ext}'
    fig.savefig(p, dpi=160, **({'metadata': {'Date': None}} if ext == 'svg' else {}))
    if ext == 'svg': p.write_text('\n'.join(line.rstrip() for line in p.read_text(encoding='utf-8').splitlines()) + '\n', encoding='utf-8', newline='\n')
plt.close(fig)
print('Wrote capital_comparison.md and paired sensitivity figures')
