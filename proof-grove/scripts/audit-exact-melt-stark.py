"""Preflight and independently verify the archived 23,750-sat Shinigami case.

Use the exact case directory with the pinned proving kit or stock verifier.
A fixture with different transaction IDs has a different public statement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ARCHIVE = Path(__file__).resolve().parents[2] / 'codex-campaign-2026-11-23' / 'outputs'
EXECUTION = ARCHIVE / 'Cashu-Melt-Redemption-Cairo-Execution.json'
EXECUTION_SHA256 = 'e9d3b0747e3d97587f4613db6508e6f18aa9f5144bc211459eb60e4c4331191b'
MAX_PROOF = 32 * 1024 * 1024
MAX_RAW_PROOF = 64 * 1024 * 1024
FIELD_PRIME = 2**251 + 17 * 2**192 + 1
FELT_HEX = re.compile(r'0x(?:0|[1-9a-f][0-9a-f]{0,62})')


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


def expected_public_output(receipt, statement):
    count = receipt['public_output_words_matched']
    if not isinstance(statement, list) or len(statement) != count - 3:
        raise ValueError('archived statement has the wrong number of public words')
    words = [receipt['program']['program_hash'], *statement]
    if any(not isinstance(word, str) or not FELT_HEX.fullmatch(word) for word in words):
        raise ValueError('archived statement has a noncanonical felt')
    values = [int(word, 16) for word in words]
    if any(value >= FIELD_PRIME for value in values):
        raise ValueError('archived statement has a felt outside the Cairo field')
    return [1, count - 1, *values]


def pinned_case(case, profile_path):
    evidence = read(EXECUTION, 64 * 1024)
    if hashlib.sha256(evidence).hexdigest() != EXECUTION_SHA256:
        raise ValueError('historical execution receipt differs from the archived pin')
    receipt = json.loads(evidence)
    pins = receipt['input_sha256']
    check(case / 'honest.args.json', pins['redemption_arguments'])
    statement = read(case / 'statement.json', 64 * 1024)
    parsed = json.loads(statement)
    canonical = json.dumps(parsed, sort_keys=True, separators=(',', ':')).encode()
    if receipt['statement_sha256'] not in {
        hashlib.sha256(statement).hexdigest(), hashlib.sha256(canonical).hexdigest()
    }:
        raise ValueError('statement is not the archived melt-funded case')
    profile = read(profile_path, 4096)
    if hashlib.sha256(profile).hexdigest() != pins['profile.json']:
        raise ValueError(f'SHA-256 mismatch for {profile_path}')
    return receipt, expected_public_output(receipt, parsed), json.loads(profile)


def preflight(runner, case):
    receipt, expected, profile = pinned_case(case, runner.parent / 'profile.json')
    pins = receipt['input_sha256']
    for name, key in (
        ('bin/scarb', 'bin/scarb'), ('bin/scarb-execute', 'bin/scarb-execute'),
        ('bin/scarb-verify', 'bin/scarb-verify'), ('bin/prove-clean', 'bin/prove-clean'),
        ('redemption/main.executable.json', 'redemption_executable'),
    ):
        check(runner.parent / name, pins[key])
    if not runner.is_file():
        raise FileNotFoundError(runner)
    return receipt, expected, profile


def verify_one(verifier, proof, cwd, timeout):
    start = time.monotonic()
    result = subprocess.run([str(verifier), '--proof-file', str(proof)], cwd=cwd,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout, check=False)
    return result.returncode, round(time.monotonic() - start, 4), result.stdout


def pinned_proof_output(document, expected):
    outputs = document['claim']['public_data']['public_memory']['output']
    if not isinstance(outputs, list) or len(outputs) != len(expected):
        raise ValueError('unexpected public memory for redemption')
    values = []
    for cell in outputs:
        if not isinstance(cell, list) or len(cell) != 2:
            raise ValueError('invalid Cairo public output cell')
        value_id, limbs = cell
        if (type(value_id) is not int or not 0 <= value_id < 2**32
                or not isinstance(limbs, list) or len(limbs) != 8
                or any(type(word) is not int or not 0 <= word < 2**32 for word in limbs)):
            raise ValueError('invalid Cairo public output cell')
        values.append(sum(word << (32 * idx) for idx, word in enumerate(limbs)))
    if values != expected:
        raise ValueError('proof public output differs from the pinned melt-funded statement')
    return outputs, values


def pinned_proof_profile(document, profile):
    """Check the pinned Stwo proof metadata before invoking its verifier."""
    if not isinstance(document, dict) or ('stark_proof' in document and 'extended_stark_proof' in document):
        raise ValueError('ambiguous or invalid Cairo proof format')
    stark = document.get('stark_proof')
    if 'extended_stark_proof' in document and isinstance(document['extended_stark_proof'], dict):
        stark = document['extended_stark_proof'].get('proof')
    # The pinned Scarb verifier selects plain Blake2s. The proof carries its
    # own PCS config, salt and preprocessed-trace variant.
    accepted = {
        'channel_hash': 'blake2s',
        'channel_salt': document.get('channel_salt'),
        'pcs_config': stark.get('config') if isinstance(stark, dict) else None,
        'preprocessed_trace': document.get('preprocessed_trace_variant'),
    }
    expected = {name: profile[name] for name in accepted}
    # JSON equality preserves numeric types (True and 1 otherwise compare equal).
    if json.dumps(accepted, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError('proof metadata differs from the pinned Shinigami security profile')
    return accepted


def independent_verify(verifier, proof, cwd, expected, profile, timeout, transcript):
    raw = read(proof, MAX_PROOF)
    document = json.loads(raw)
    verified_profile = pinned_proof_profile(document, profile)
    outputs, values = pinned_proof_output(document, expected)

    code, seconds, log = verify_one(verifier, proof, cwd, timeout)
    transcript.write(b'honest public statement\n' + log)
    if code != 0 or b'Verified proof successfully' not in log:
        raise ValueError(f'independent verifier refused the honest proof (exit {code})')
    controls = []
    with tempfile.TemporaryDirectory(prefix='cashu-melt-word-controls-') as directory:
        mutant = Path(directory) / 'mutated-proof.json'
        for index, cell in enumerate(outputs):
            cell[1][0] ^= 1
            mutant.write_text(json.dumps(document, separators=(',', ':')), encoding='utf-8')
            cell[1][0] ^= 1
            exit_code, elapsed, log = verify_one(verifier, mutant, cwd, timeout)
            transcript.write(f'\npublic output cell {index} (value ID {cell[0]})\n'.encode() + log)
            if exit_code != 1 or b'verification failed' not in log.lower():
                raise ValueError(f'expected verifier rejection for public cell {index}, got {exit_code}')
            controls.append({'index': index, 'value_id': cell[0], 'exit_code': exit_code, 'seconds': elapsed})
    return hashlib.sha256(raw).hexdigest(), values, seconds, controls, verified_profile


def run_kit(runner, case, result, args, expected):
    timing = result / 'runner'
    command = [sys.executable, '-B', str(runner), str(timing), '--redemption-case', str(case),
               '--threads', str(args.threads), '--max-seconds', str(args.max_seconds)]
    if args.existing_proof:
        command.extend(('--audit-proof', str(args.existing_proof.resolve())))
    elif args.execute_only:
        command.append('--execute-only')
    with (result / 'runner.log').open('xb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=args.max_seconds + 30)
    report = json.loads(read(timing / 'report.json', 512 * 1024))
    expected_status = ('existing_proof_audited' if args.existing_proof else
                       'fixture_executed' if args.execute_only else 'fresh_proof_independently_verified')
    if (report.get('status') != expected_status or report.get('case') != 'fresh_cashu_redemption'
            or (not args.existing_proof and report.get('public_words_matched') != len(expected))):
        raise ValueError('runner did not validate the historical public statement')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    tools = parser.add_mutually_exclusive_group(required=True)
    tools.add_argument('--runner', type=Path, help='pinned benchmarks/shinigami/run.py')
    tools.add_argument('--verifier', type=Path, help='pinned stock Scarb verifier for a downloaded compact proof')
    parser.add_argument('--profile', type=Path, help='pinned profile for standalone verification')
    parser.add_argument('--case', type=Path, required=True, help='exact honest.args.json and statement.json')
    parser.add_argument('--out', type=Path, help='new archive directory')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--existing-proof', type=Path, help='audit existing bytes instead of proving')
    mode.add_argument('--check-only', action='store_true')
    mode.add_argument('--execute-only', action='store_true', help='replay Cairo without starting the prover')
    parser.add_argument('--verifier-cwd', type=Path)
    chain_source = parser.add_mutually_exclusive_group()
    chain_source.add_argument('--core-config', type=Path, help='Proof Grove config for a separate local Core observer')
    chain_source.add_argument('--chain-context', type=Path, help='archived Bitcoin witness context to verify offline')
    parser.add_argument('--anchor-height', type=int, help='height of an independently pinned block at or after payout')
    parser.add_argument('--anchor-hash', help='hash of the independently pinned block')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--max-seconds', type=int, default=900)
    args = parser.parse_args()
    if args.verifier and (not args.profile or not (args.existing_proof or args.check_only)):
        parser.error('--verifier requires --profile and either --existing-proof or --check-only')
    if args.runner and args.profile:
        parser.error('--runner reads its profile from the pinned kit')
    if not args.check_only and args.out is None:
        parser.error('--out is required except with --check-only')
    if args.threads < 1 or args.max_seconds < 1:
        parser.error('threads and time limit must be positive')
    chain_options = (args.core_config or args.chain_context, args.anchor_height, args.anchor_hash)
    if any(option is not None for option in chain_options) and any(option is None for option in chain_options):
        parser.error('Bitcoin chain verification requires a chain source, --anchor-height and --anchor-hash')
    case = args.case.resolve()
    runner = args.runner.resolve() if args.runner else None
    if runner:
        receipt, expected, profile = preflight(runner, case)
        verifier = runner.parent / 'bin/scarb-verify'
    else:
        receipt, expected, profile = pinned_case(case, args.profile)
        verifier = args.verifier.resolve()
        check(verifier, receipt['input_sha256']['bin/scarb-verify'])
    if args.existing_proof:
        pinned_proof_profile(json.loads(read(args.existing_proof, MAX_RAW_PROOF)), profile)
    chain_observation = None
    if args.core_config or args.chain_context:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from proofdesk.exact_melt_chain import observe_witness_context, verify_witness_context

        if args.core_config:
            from proofdesk.adapters import CoreClient

            core = CoreClient.from_config(json.loads(read(args.core_config, 32768))['core'])
            chain_observation = observe_witness_context(core, receipt, expected, args.anchor_height, args.anchor_hash)
        else:
            chain_observation = json.loads(read(args.chain_context, 2 * 1024 * 1024))
            chain_observation['witness_verification'] = verify_witness_context(
                chain_observation, receipt, expected, args.anchor_height, args.anchor_hash)
    chain_status = {'chain_context_observed': bool(args.core_config),
                    'chain_context_witness_verified': chain_observation is not None}
    if args.check_only:
        print(json.dumps({'status': 'exact_case_available', 'outpoint': receipt['funding_outpoint'],
                          'expected_public_output_words': len(expected), **chain_status}))
        return

    result = args.out.resolve()
    result.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(case / 'statement.json', result / 'statement.json')
    report = run_kit(runner, case, result, args, expected) if runner else {'phases': {}}
    if args.execute_only:
        if chain_observation is not None:
            (result / 'chain-context.json').write_text(json.dumps(chain_observation, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': report['status'], 'public_words_matched': len(expected), **chain_status,
                          'execution': report['phases']['execute']}))
        return
    proof = result / 'redemption-proof.json'
    if runner:
        shutil.copyfile(result / 'runner' / 'verifier-input.json', proof)
        check(proof, report['verifier_input_sha256'])
    else:
        proof.write_bytes(read(args.existing_proof, MAX_PROOF))
    with (result / 'independent-verifier.log').open('xb') as log:
        digest, output, seconds, controls, verified_profile = independent_verify(
            verifier, proof, args.verifier_cwd or (runner.parent if runner else verifier.parent),
            expected, profile, min(60, args.max_seconds), log,
        )
    verification = {
        'schema': 'rbzk/cashu-independent-verification/v1',
        'verified': True, 'proof_sha256': digest, 'statement_sha256': receipt['statement_sha256'],
        **chain_status,
        'verifier_id': receipt['input_sha256']['bin/scarb-verify'], 'program': receipt['program'],
        'proof_profile_sha256': receipt['input_sha256']['profile.json'], 'verified_proof_profile': verified_profile,
        'funding_outpoint': receipt['funding_outpoint'], 'payout_txid': receipt['confirmed_spend'],
        'cairo_public_memory_output': [hex(value) for value in output],
        'verified_mutated_cells': controls, 'verify_seconds': seconds, 'stages': report['phases'],
    }
    if args.core_config:
        latest = observe_witness_context(core, receipt, expected, args.anchor_height, args.anchor_hash)
        if any(chain_observation[name] != latest[name] for name in ('funding', 'payout')):
            raise ValueError('Core changed the exact settlement blocks during proof verification')
        chain_observation = latest
    if chain_observation is not None:
        chain_file = result / 'chain-context.json'
        chain_file.write_text(json.dumps(chain_observation, indent=2) + '\n', encoding='utf-8')
        verification['chain_context_sha256'] = sha256(chain_file)
    (result / 'verification.json').write_text(json.dumps(verification, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
