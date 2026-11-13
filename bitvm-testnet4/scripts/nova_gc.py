"""Run the real Testnet4 Nova proof through M14's complete garbled verifier.

Uses an existing, isolated GSV checkout and installed Rust toolchain. Offline only.
The overlay is a functional test, not a complete BitVM3 dispute protocol.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'fcddd4d773f52953387eed4b55beaab47c84155a'
PROOF = '79c4af1113506bba24415d058557bba93583d5177ec074f13ba30f705c85daad'
STATEMENT = 'ce268815e58635bb9cda91cbde3dce0fd438fd097dec1171c6df131e2d337701'
TEST = 'nova-bitvm3/m14/e2e/tests/garbled.rs'
NAME = 'testnet4_nova_demo_accepts_and_rejects'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(source, *arguments):
    return subprocess.check_output(['git', '-C', str(source), *arguments], timeout=90)


def prepare(source):
    if git(source, 'rev-parse', 'HEAD').decode().strip() != SOURCE:
        raise ValueError('GSV source revision differs from the pinned fixture source')
    # Only the exact supplied overlay may change; preserve any other worker's files.
    original = git(source, 'show', 'HEAD:' + TEST).decode().replace('\r\n', '\n')
    addition = (ROOT / 'nova/testnet4_garbled.rs.inc').read_text()
    current = (source / TEST).read_text()
    dirty = git(source, 'status', '--porcelain', '--untracked-files=all').decode().splitlines()
    if any(line[3:] != TEST for line in dirty):
        raise ValueError('use an isolated GSV checkout without unrelated changes')
    if current not in (original, original + addition):
        raise ValueError('GSV test has unrelated changes; refusing to overwrite it')
    if current == original:
        (source / TEST).write_bytes((original + addition).encode())
    if sha(source / 'nova-bitvm3/m13/fixtures/a-wrap-blake3-v2.bin') != PROOF:
        raise ValueError('real Nova proof fixture differs')
    if sha(source / 'nova-bitvm3/m13/fixtures/a-statement.json') != STATEMENT:
        raise ValueError('Testnet4 statement fixture differs')


def run(args):
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
              'source': SOURCE, 'proof_sha256': PROOF, 'statement_sha256': STATEMENT,
              'offline': True, 'gpu_proving': False, 'steps': [],
              'scope': 'Actual M14 functional garbling/evaluation; no OT, cut-and-choose or Bitcoin dispute transaction graph'}
    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    def step(name, argv, timeout):
        log = output / (name + '.log')
        start = time.monotonic()
        timed_out = False
        with log.open('wb') as stream:
            process = subprocess.Popen(argv, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=os.name == 'posix')
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == 'posix':
                    import signal
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    if os.name == 'posix': os.killpg(process.pid, signal.SIGKILL)
                    else: process.kill()
                    process.wait(timeout=15)
                code = process.returncode
        report['steps'].append({'name': name, 'command': argv, 'exit_code': code,
                                'timed_out': timed_out, 'seconds': time.monotonic() - start,
                                'log_sha256': sha(log)})
        save()
        if code or timed_out:
            raise RuntimeError(f'{name} failed; inspect {log.name}; cached build artifacts can be reused in a fresh run')
    save()
    try:
        prepare(source)
        report['diff_sha256'] = hashlib.sha256(git(source, 'diff', '--binary')).hexdigest()
        report['overlay_sha256'] = sha(ROOT / 'nova/testnet4_garbled.rs.inc')
        toolchain = args.toolchain.resolve()
        env = dict(os.environ)
        env.update(PATH=str(toolchain) + os.pathsep + env.get('PATH', ''),
                   RUSTC=str(toolchain / 'rustc'), RUSTDOC=str(toolchain / 'rustdoc'),
                   CARGO_PROFILE_TEST_DEBUG='0', CARGO_INCREMENTAL='0', CARGO_HUSKY_DONT_INSTALL_HOOKS='true',
                   RAYON_NUM_THREADS=str(args.jobs), CARGO_TERM_COLOR='never')
        step('rustc', [str(toolchain / 'rustc'), '-Vv'], 30)
        step('cargo', [str(toolchain / 'cargo'), '-V'], 30)
        step('build', [str(toolchain / 'cargo'), 'test', '--offline', '--locked', '--jobs', str(args.jobs),
                       '--manifest-path', str(source / 'nova-bitvm3/m14/e2e/Cargo.toml'),
                       '--target-dir', str(args.target.resolve()), '--test', 'garbled', '--no-run',
                       '--message-format=json'], args.build_timeout)
        binary = None
        for line in (output / 'build.log').read_text().splitlines():
            try: item = json.loads(line)
            except json.JSONDecodeError: continue
            if item.get('reason') == 'compiler-artifact' and item.get('target', {}).get('name') == 'garbled' and item.get('executable'):
                binary = Path(item['executable'])
        if binary is None or not binary.is_file():
            raise ValueError('cargo did not identify the actual test executable')
        report.update(binary=str(binary), binary_sha256=sha(binary))
        step('run', [str(binary), '--exact', NAME, '--nocapture', '--test-threads=1'], args.timeout)
        cases = [json.loads(line.split('BITVM3_DEMO ', 1)[1]) for line in (output / 'run.log').read_text().splitlines()
                 if 'BITVM3_DEMO ' in line]
        if len(cases) != 3 or {item['case'] for item in cases} != {'real-nova-proof', 'tampered-proof-input', 'wrong-statement'}:
            raise ValueError('missing verifier cases')
        for item in cases:
            wanted = item['case'] == 'real-nova-proof'
            if (item['accepted'] is not wanted or item['rejected'] is wanted or
                    item['ciphertexts'] != 785442492 or item['input_bits'] != 8635080):
                raise ValueError('verifier result or circuit dimensions differ')
        report.update(status='passed', cases=cases)
    except Exception as error:
        report.update(status='blocked_or_failed', error=f'{type(error).__name__}: {error}')
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({'status': report['status'], 'report': str(output / 'report.json')}))
    return 0 if report['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'output', 'toolchain', 'target']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=range(1, 5), default=2)
    parser.add_argument('--build-timeout', type=int, default=3600)
    parser.add_argument('--timeout', type=int, default=1800)
    return run(parser.parse_args())


if __name__ == '__main__':
    sys.exit(main())
