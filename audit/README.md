# Liquidity on Trial: reproducible adversarial audit

Baseline: the untouched C:/projects/Spiral repository at a0a3140. Date:
2026-09-11. This is an exploratory follow-up, not a new preregistered campaign.

Start with paper/liquidity_on_trial.md and paper/connector_calculus_critique.md,
or the corresponding PDFs under output/pdf. SWARM_ARENA.md documents actual
reviewer objections, concessions, and cross-examination. The original paper
and results are not overwritten. The C: repository is the handoff destination;
E: paths in historical receipts identify where the audit scripts were staged.

## Evidence classes

| Directory/file | Kind of evidence |
|---|---|
| algebra | Exact witnesses, finite grids, simple-path controls, independent cross-checks |
| inference | Original CSV integrity, 37 sample reconstructions, 126 bounded episodes, hash-order controls |
| incentives | Exact accounting witnesses, 20 Markov sensitivity cells, D-header-backed toy depth scenarios |
| testnet4/results | 512 public historical headers and source receipts; no wallet records |
| resource_model.py | New local gross-reservation reference; not a Lightning implementation |
| validation.json | Tests, source/receipt integrity, and post-review ledger regression |

## Quick validation

Run in C:/projects/Spiral with its existing environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONHASHSEED='1'
$env:PYTHONPATH='C:\projects\Spiral\src'
& '.\.venv\Scripts\python.exe' audit/validate_bundle.py
```

This runs the original tests plus 32 new audit/reference tests and verifies
retained source/input hashes. No node or wallet is touched. validation.json is
regenerated; preserve the delivered file if comparing receipts byte-for-byte.

## Re-run selected experiments

```powershell
& '.\.venv\Scripts\python.exe' audit/algebra/challenge.py
& '.\.venv\Scripts\python.exe' audit/incentives/run_audit.py --source-root 'C:\projects\Spiral'
& '.\.venv\Scripts\python.exe' audit/inference/run_audit.py --repo 'C:\projects\Spiral'
```

See each lane report for exact commands and dependencies. Inference rebuilds
37 graph samples and 126 episodes from the retained 32.9 MB public snapshot. The
final delivered diagnostic pins PYTHONHASHSEED=1. Changing that environment
variable after Python has started does not alter that process's hash seed.
Hash-order controls therefore run in separate Python processes; see
inference/hash_order_witness.py and its two saved JSON outputs.

Re-running writes results and timestamps in the selected lane, so a delivered
bundle manifest will no longer match. Keep the delivered evidence separate if
you need both histories. The reports distinguish original simulator behavior
from the separate canonical/transactional references.

## Historical D-drive replay

```powershell
& '.\.venv\Scripts\python.exe' audit/testnet4/replay.py --datadir 'D:\BitcoinTestnet\testnet4'
```

This seeks public block records and reads public UpdateTip log entries. It
does not read wallets, cookies, keys, or transaction bodies. It checks network
framing, header hashes, encoded proof-of-work targets and parent links, but is
not a complete consensus validator. It can take several minutes on a slow D:
disk. Its result is the last locally logged HISTORICAL branch, not a query of
the current chain. Requiring actual current-node/Lightning execution is a
separate task: RPC 48332 was not responding during this audit.

The delivered 512-header CSV can be validated without D:. The independent
algebra cross-review additionally reread three exact D: offsets. No processes
were restarted and no test funds were spent. Block-depth service, funding
inclusion, prices and profit scenarios are explicit assumptions, not measured
transactions. Miner timestamps are not observed arrival times.

## Preserve the dispute history

algebra/cross_examination.json binds the coordinator's pre-fix reference and
shows the float-direction bug. Do not overwrite it by rerunning its historical
script against the corrected model. The parent response documents the one-line
fix and validation.json verifies the post-fix rejection. The historical testnet
summary's prose says 512 links; the correct count is 511 internal links. It is
retained for byte identity and corrected explicitly in the delivered documents.

incentives/CROSS_EXAM.md records an earlier unpinned diagnostic at 85.7576%
retry8/oracle8 success and 519 retry failures. The final pinned inference results
are 84.79798% and 522. This difference is disclosed rather than silently editing
the historical exchange.

## Build the documents

```powershell
& '.\.venv\Scripts\python.exe' audit/build_documents.py
```

The builder uses ReportLab and Matplotlib, creates two final PDFs and two
scientific plots, and leaves equation/render intermediates in tmp/pdfs. It
does not edit the original renderer, manuscript, or PDF. Final PDFs were rendered
and visually checked before handoff. The bundle manifest is a byte-integrity
index, not a proof of scientific truth or author approval.
