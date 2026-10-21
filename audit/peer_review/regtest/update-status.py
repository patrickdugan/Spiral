"""Publish acceptance status without promoting transaction evidence to reducer proof."""
from pathlib import Path
import json

root = Path(__file__).parent
runtime = json.loads((root / 'evidence/runtime-identity.json').read_text())
proof = json.loads((root / 'evidence/reuse-proof.json').read_text())
audit = json.loads((root / 'evidence/economic-reconciliation.json').read_text())
machine = json.loads((root / 'evidence/machine-reconciliation.json').read_text())
assert machine['economic_reconciliation'] and machine['replay_verified']
result = {
    'inspection_date': '2026-10-21', 'evidence_class': 'observed-regtest',
    'regtest_status': 'transaction_lifecycle_and_reducer_economic_replay_verified_timing_interval_censored',
    'testnet4_status': 'not_attempted_matched_service_calibration_pending',
    'actual_genesis_hash': runtime['genesis'], 'best_block_hash': runtime['chain']['bestblockhash'],
    'binary_digests': runtime['executables'], 'container_digests': runtime['images'],
    'effective_configuration': '../regtest/evidence/runtime-identity.json',
    'initial_state_snapshots': ['../regtest/evidence/initial-funding.json', '../regtest/evidence/initial-funded-state.json'],
    'owned_regtest_endpoint': '127.0.0.1:18483 (WSL, regtest only)',
    'noncoinbase_transactions_in_reconciled_fixture': len(audit['transaction_events']) + 1,
    'exclusive_reuse_proof': '../regtest/evidence/reuse-proof.json',
    'economic_reconciliation': '../regtest/evidence/economic-reconciliation.json',
    'machine_reconciliation': '../regtest/evidence/machine-reconciliation.json',
    'machine_state_hash': machine['report']['state_hash'],
    'structural_sensitivity': '../capital_comparison.md (completed; full fee-aware fixed-budget comparison remains pending)',
    'fixture_initial_sat': audit['initial_fixture_sat'], 'recovered_output_sat': proof['recovered_output_sat'],
    'clock_caveat': 'Accelerated blocks and manually triggered sweeps; no production latency inference.',
    'remaining': ['Instrument exact acceptance/commit timing; current journal uses snapshot detection heights and unknown seconds',
                  'Complete live failure/timeout/receive/exit/reorg branches',
                  'Rerun matched-service comparisons with normalized observed semantics',
                  'Only then execute the bounded testnet4 operational-clock protocol']}
(root.parent / 'capital/execution-status.json').write_text(json.dumps(result, indent=2) + '\n', newline='\n')
print(result['regtest_status'])
