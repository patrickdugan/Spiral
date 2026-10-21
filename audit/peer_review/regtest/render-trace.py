"""Plot reconstructed detection-height accounting; never label it a latency fit."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['svg.hashsalt'] = 'spiral-observed-capital-v1'
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

root = Path(__file__).parent / 'evidence'
rows = json.loads((root / 'machine-trace.json').read_text())
heights = [r['height'] for r in rows]
fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout='constrained')
colors = {'fronting': '#a65114', 'unique_committed': '#135d91', 'htlc': '#4c8b59'}
for key, label in [('fronting', 'Outstanding fronting F−C'), ('unique_committed', 'Unique committed assets')]:
    axes[0].step(heights, [r['report']['stocks'][key] / 1000 for r in rows], where='post', label=label, color=colors[key], linewidth=2)
    axes[1].plot(heights, [int(r['report']['integrals'][key]['msat_blocks']) / 1_000_000_000 for r in rows], label=label, color=colors[key], linewidth=2)
axes[0].set_ylabel('Satoshis'); axes[1].set_ylabel('Million sat-blocks')
axes[0].yaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
axes[0].legend(loc='upper right', frameon=False)
for ax in axes:
    ax.grid(axis='y', alpha=.2); ax.spines[['top', 'right']].set_visible(False)
    ax.axvline(4433, color='#777777', linewidth=.8, linestyle='--')
axes[0].annotate('Original board expiry: 4433\nSweep reuse observed: 4439', xy=(4433, 98982), xytext=(2950, 235000),
                 arrowprops={'arrowstyle': '->', 'color': '#777777'}, fontsize=9)
axes[1].set_xlabel('Canonical regtest height (snapshot detection times)')
fig.suptitle('Executed regtest: economic replay and detection-height capital accounting', fontsize=13, weight='bold')
fig.supxlabel('34 accepted events • Exact commitment intervals are censored • Seconds unavailable\nManual sweeps and accelerated blocks: no production latency inference', fontsize=9)
for extension in ['png', 'svg']:
    path = root / f'machine-trace.{extension}'
    fig.savefig(path, dpi=160, **({'metadata': {'Date': None}} if extension == 'svg' else {}))
    if extension == 'svg':
        path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n', newline='\n')
plt.close(fig)
print('Rendered machine-trace.png and machine-trace.svg')
