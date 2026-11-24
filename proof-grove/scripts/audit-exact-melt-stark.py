"""Preflight and independently verify the archived 23,750-sat Shinigami case.

Requires the original pinned proving bundle and the exact case directory. A
regenerated fixture with different transaction IDs is a different statement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ARCHIVE = Path(__file__).resolve().parents[2] / 'codex-campaign-2026-11-23' / 'outputs'
EXECUTION = ARCHIVE / 'Cashu-Melt-Redemption-Cairo-Execution.json'
MAX_PROOF = 32 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path, limit):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError(f'invalid file size for {path.name}')
    return data


def check(path, expected):
    if sha256(path) != expected:
        raise ValueError(f'SHA-256 mismatch for {path}')


def preflight(runner, case):
    receipt = json.loads(EXECUTION.read_bytes())
    pins = receipt['input_sha256']
    for name, key in (
        ('bin/scarb', 'bin/scarb'), ('bin/scarb-execute', 'bin/scarb-execute'),
        ('bin/scarb-verify', 'bin/scarb-verify'), ('bin/prove-clean', 'bin/prove-clean'),
        ('profile.json', 'profile.json'), ('redemption/main.executable.json', 'redemption_executable'),
    ):
        check(runner.parent / name, pins[key])
    if not runner.is_file():
        raise FileNotFoundError(runner)
    check(case / 'honest.args.json', pins['redemption_arguments'])
    statement = read(case / 'statement.json', 64 * 1024)
    parsed = json.loads(statement)
    canonical = json.dumps(parsed, sort_keys=True, separators=(',', ':')).encode()
    if receipt['statement_sha256'] not in {
        hashlib.sha256(statement).hexdigest(), hashlib.sha256(canonical).hexdigest()
    }:
        raise ValueError('statement is not the archived melt-funded case')
    return receipt


def verify_one(verifier, proof, cwd, timeout):
    start = time.monotonic()
    result = subprocess.run([str(verifier), '--proof-file', str(proof)], cwd=cwd,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout, check=False)
    return result.returncode, round(time.monotonic() - start, 4), result.stdout


def independent_verify(verifier, proof, cwd, expected_program, timeout, transcript):
    raw = read(proof, MAX_PROOF)
    document = json.loads(raw)
    outputs = document['claim']['public_data']['public_memory']['output']
    if not isinstance(outputs, list) or not 24 <= len(outputs) <= 27:
        raise ValueError('unexpected public memory for redemption')
    values = []
    for cell in outputs:
        offset, limbs = cell
        if type(offset) is not int or len(limbs) != 8 or any(
                type(word) is not int or not 0 <= word < 2**32 for word in limbs):
            raise ValueError('invalid Cairo public output cell')
        values.append(sum(word << (32 * idx) for idx, word in enumerate(limbs)))
    if values[:3] != [1, len(outputs) - 1, int(expected_program, 16)]:
        raise ValueError('redemption program binding mismatch')

    code, seconds, log = verify_one(verifier, proof, cwd, timeout)
    transcript.write(b'honest public statement\n' + log)
    if code != 0:
        raise ValueError(f'independent verifier refused the honest proof (exit {code})')
    controls = []
    with tempfile.TemporaryDirectory(prefix='cashu-melt-word-controls-') as directory:
        mutant = Path(directory) / 'mutated-proof.json'
        for index, cell in enumerate(outputs):
            cell[1][0] ^= 1
            mutant.write_text(json.dumps(document, separators=(',', ':')), encoding='utf-8')
            cell[1][0] ^= 1
            exit_code, elapsed, log = verify_one(verifier, mutant, cwd, timeout)
            transcript.write(f'\npublic output cell {index} (address {cell[0]})\n'.encode() + log)
            if exit_code != 1:
                raise ValueError(f'expected verifier rejection for public cell {index}, got {exit_code}')
            controls.append({'index': index, 'address': cell[0], 'exit_code': exit_code, 'seconds': elapsed})
    return hashlib.sha256(raw).hexdigest(), values, seconds, controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True, help='pinned benchmarks/shinigami/run.py')
    parser.add_argument('--case', type=Path, required=True, help='exact honest.args.json and statement.json')
    parser.add_argument('--out', type=Path, help='new archive directory')
    parser.add_argument('--existing-proof', type=Path, help='audit existing bytes instead of proving')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--verifier-cwd', type=Path)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--max-seconds', type=int, default=900)
    args = parser.parse_args()
    if not args.check_only and args.out is None:
        parser.error('--out is required for generation or verification')
    if args.threads < 1 or args.max_seconds < 1:
        parser.error('threads and time limit must be positive')
    runner, case = args.runner.resolve(), args.case.resolve()
    receipt = preflight(runner, case)
    if args.check_only:
        print(json.dumps({'status': 'exact_case_available', 'outpoint': receipt['funding_outpoint']}))
        return

    result = args.out.resolve()
    result.mkdir(parents=True, exist_ok=False)
    timing = result / 'runner'
    command = [sys.executable, '-B', str(runner), str(timing), '--redemption-case', str(case),
               '--threads', str(args.threads), '--max-seconds', str(args.max_seconds)]
    if args.existing_proof:
        command.extend(('--audit-proof', str(args.existing_proof.resolve())))
    with (result / 'runner.log').open('xb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=args.max_seconds + 30)
    report = json.loads(read(timing / 'report.json', 512 * 1024))
    expected_status = 'existing_proof_audited' if args.existing_proof else 'fresh_proof_independently_verified'
    if (report.get('status') != expected_status or report.get('case') != 'fresh_cashu_redemption'
            or report.get('public_words_matched') != receipt['public_output_words_matched']):
        raise ValueError('runner did not validate the historical public statement')
    proof = result / 'redemption-proof.json'
    shutil.copyfile(args.existing_proof or timing / 'verifier-input.json', proof)
    check(proof, report['verifier_input_sha256'])
    verifier = runner.parent / 'bin/scarb-verify'
    with (result / 'independent-verifier.log').open('xb') as log:
        digest, output, seconds, controls = independent_verify(
            verifier, proof, args.verifier_cwd or runner.parent,
            receipt['program']['program_hash'], min(60, args.max_seconds), log,
        )
    shutil.copyfile(case / 'statement.json', result / 'statement.json')
    verification = {
        'schema': 'rbzk/cashu-independent-verification/v1',
        'verified': True, 'proof_sha256': digest, 'statement_sha256': receipt['statement_sha256'],
        'verifier_id': receipt['input_sha256']['bin/scarb-verify'], 'program': receipt['program'],
        'funding_outpoint': receipt['funding_outpoint'], 'payout_txid': receipt['confirmed_spend'],
        'cairo_public_memory_output': [hex(value) for value in output],
        'verified_mutated_cells': controls, 'verify_seconds': seconds, 'stages': report['phases'],
    }
    (result / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
