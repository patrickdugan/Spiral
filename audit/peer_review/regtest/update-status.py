"""Publish acceptance status without promoting transaction evidence to reducer proof."""
from pathlib import Path
import json

root = Path(__file__).parent
runtime = json.loads((root / 'evidence/runtime-identity.json').read_text())
proof = json.loads((root / 'evidence/reuse-proof.json').read_text())
audit = json.loads((root / 'evidence/economic-reconciliation.json').read_text())
result = {
    'inspection_date': '2026-10-21', 'evidence_class': 'observed-regtest',
    'regtest_status': 'transaction_lifecycle_verified_reducer_normalization_pending',
    'testnet4_status': 'not_attempted_reducer_prerequisite_unsatisfied',
    'actual_genesis_hash': runtime['genesis'], 'best_block_hash': runtime['chain']['bestblockhash'],
    'binary_digests': runtime['executables'], 'container_digests': runtime['images'],
    'effective_configuration': '../regtest/evidence/runtime-identity.json',
    'initial_state_snapshots': ['../regtest/evidence/initial-funding.json', '../regtest/evidence/initial-funded-state.json'],
    'owned_regtest_endpoint': '127.0.0.1:18483 (WSL, regtest only)',
    'noncoinbase_transactions_in_reconciled_fixture': len(audit['transaction_events']) + 1,
    'exclusive_reuse_proof': '../regtest/evidence/reuse-proof.json',
    'economic_reconciliation': '../regtest/evidence/economic-reconciliation.json',
    'fixture_initial_sat': audit['initial_fixture_sat'], 'recovered_output_sat': proof['recovered_output_sat'],
    'clock_caveat': 'Accelerated blocks and manually triggered sweeps; no production latency inference.',
    'remaining': ['Extend reducer and adapter for retained backing, actual gross reserve, round overhead and fees',
                  'Replay observed events through all machine invariants',
                  'Complete live failure/timeout/receive/exit/reorg branches',
                  'Rerun matched-service comparisons with normalized observed semantics',
                  'Only then execute the bounded testnet4 operational-clock protocol']}
(root.parent / 'capital/execution-status.json').write_text(json.dumps(result, indent=2) + '\n', newline='\n')
print(result['regtest_status'])
