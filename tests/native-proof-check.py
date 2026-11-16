"""Explicit local integration check; requires an existing verifier and public proof.

python tests/native-proof-check.py --config config.local.json --proof /path/to/proof.bin
The actual proof is never committed. This check cannot invoke a wallet.
"""
import argparse
import dataclasses
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from proofdesk.__main__ import gate_from, load_config
from proofdesk.domain import Refused
from proofdesk.verifier import PROOF_LIMIT, read_bounded

parser = argparse.ArgumentParser()
parser.add_argument('--config', required=True)
parser.add_argument('--proof', required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
statement = (root/'fixtures/m16-mainnet-statement.bin').read_bytes()
proof = read_bounded(args.proof, PROOF_LIMIT)
gate = gate_from(load_config(args.config))
cases = []
start = time.monotonic()
evidence = gate.verify(statement, proof)
cases.append({'name':'historical-mainnet-proof','outcome':'proof-verified','seconds':round(time.monotonic()-start,3)})
flipped = bytearray(proof); flipped[len(flipped)//2] ^= 1
changed = bytearray(statement); changed[1248] ^= 1  # PAY1 amount, leaves chain/confirmation encoding intact.
for name, submitted_statement, submitted_proof in (
    ('flipped-proof-byte',statement,bytes(flipped)),
    ('truncated-proof',statement,proof[:-1]),
    ('changed-payment-amount',bytes(changed),proof),
):
    start=time.monotonic()
    try:
        gate.verify(submitted_statement,submitted_proof)
    except Refused as exc:
        if exc.code != 'proof_rejected':
            raise AssertionError(f'{name} failed before cryptographic rejection: {exc.code}')
        cases.append({'name':name,'outcome':exc.code,'seconds':round(time.monotonic()-start,3)})
    else:
        raise AssertionError(f'{name} was accepted')
report={'status':'passed','cases':cases,'binary_sha256':gate.expected_hash,
        'statement_sha256':evidence.statement_sha256,'proof_sha256':evidence.proof_sha256,
        'evidence':dataclasses.asdict(evidence),'settlement':'not executed',
        'meaning':'Historical public mainnet proof verified with the actual native gate. No live payment reserved.'}
output=root/'.runtime'/'native-proof-report.json'
output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
