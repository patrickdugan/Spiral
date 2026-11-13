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
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'fcddd4d773f52953387eed4b55beaab47c84155a'
PROOF = '79c4af1113506bba24415d058557bba93583d5177ec074f13ba30f705c85daad'
STATEMENT = '06fa3156d86ffb98f0a853cbd350b144f81d1586c6eda7d70c436267f821b007'
TEST = 'nova-bitvm3/m14/e2e/tests/garbled.rs'
NAME = 'testnet4_nova_demo_accepts_and_rejects'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def statement_sha(path):
    # Git's Windows checkout may replace LF by CRLF. Accept only that conversion.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def git(source, *arguments):
    return subprocess.check_output(['git', '-C', str(source), *arguments], timeout=90)


def prepare(source):
    if git(source, 'rev-parse', 'HEAD').decode().strip() != SOURCE:
        raise ValueError('GSV source revision differs from the pinned fixture source')
    # Only the exact supplied overlay may change; preserve any other worker's files.
    original = git(source, 'show', 'HEAD:' + TEST).decode().replace('\r\n', '\n')
    addition = (ROOT / 'nova/disk_transport.rs.inc').read_text() + (ROOT / 'nova/testnet4_garbled.rs.inc').read_text()
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
    if statement_sha(source / 'nova-bitvm3/m13/fixtures/a-statement.json') != STATEMENT:
        raise ValueError('Testnet4 statement fixture differs')


def run(args):
    source, output = args.source.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
              'source': SOURCE, 'proof_sha256': PROOF, 'statement_sha256': STATEMENT,
              'offline': True, 'gpu_proving': False, 'steps': [],
              'scope': 'Actual M14 functional garbling/evaluation; no OT, cut-and-choose or Bitcoin dispute transaction graph'}
    def save():
        temporary = output / 'report.tmp.json'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')
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
                                'selected_case': env.get('BITVM_DEMO_CASE'),
                                'log_sha256': sha(log)})
        save()
        if code or timed_out:
            raise RuntimeError(f'{name} failed; inspect {log.name}; cached build artifacts can be reused in a fresh run')
    save()
    try:
        prepare(source)
        report['statement_file_sha256'] = sha(source / 'nova-bitvm3/m13/fixtures/a-statement.json')
        report['statement_hash_encoding'] = 'CRLF normalized to LF; otherwise exact pinned bytes'
        report['diff_sha256'] = hashlib.sha256(git(source, 'diff', '--binary')).hexdigest()
        report['overlay_sha256'] = sha(ROOT / 'nova/testnet4_garbled.rs.inc')
        toolchain = args.toolchain.resolve()
        env = dict(os.environ)
        env.update(PATH=str(toolchain) + os.pathsep + env.get('PATH', ''),
                   RUSTC=str(toolchain / 'rustc'), RUSTDOC=str(toolchain / 'rustdoc'),
                   CARGO_PROFILE_TEST_DEBUG='0', CARGO_INCREMENTAL='0', CARGO_HUSKY_DONT_INSTALL_HOOKS='true',
                   RAYON_NUM_THREADS=str(args.jobs), CARGO_TERM_COLOR='never')
        if args.aesni:
            env.pop('CARGO_ENCODED_RUSTFLAGS', None)
            env['RUSTFLAGS'] = '-C target-feature=+aes,+sse2'
        report['rustflags'] = env.get('RUSTFLAGS', '')
        report['aesni_requested'] = args.aesni
        scratch = args.target.resolve() / 'demo-ciphertexts'
        scratch.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(scratch).free < 13_000_000_000:
            raise ValueError('sequential full garbling needs at least 13 GB of free scratch space')
        env['BITVM_DEMO_CIPHERTEXT_DIR'] = str(scratch)
        report.update(transport='temporary-file-sequential', scratch_bytes_per_case=785442492 * 16,
                      transport_overlay_sha256=sha(ROOT / 'nova/disk_transport.rs.inc'))
        step('rustc', [str(toolchain / 'rustc'), '-Vv'], 30)
        step('cargo', [str(toolchain / 'cargo'), '-V'], 30)
        if args.aesni:
            probe = output / 'cpu_probe.rs'
            probe.write_text('fn main() {\n'
                '#[cfg(target_arch="x86_64")] { let a=std::is_x86_feature_detected!("aes"); '
                'let s=std::is_x86_feature_detected!("sse2"); println!("aes={a} sse2={s}"); '
                'assert!(a && s, "AES-NI/SSE2 unavailable"); }\n'
                '#[cfg(not(target_arch="x86_64"))] panic!("AES-NI requires x86_64");\n}\n')
            executable = output / ('cpu_probe.exe' if os.name == 'nt' else 'cpu_probe')
            step('cpu_probe_build', [str(toolchain / 'rustc'), '--edition=2021', str(probe), '-o', str(executable)], 60)
            step('cpu_probe', [str(executable)], 30)
            step('cpu_cfg', [str(toolchain / 'rustc'), '--print', 'cfg', '-C', 'target-feature=+aes,+sse2'], 30)
            configured = (output / 'cpu_cfg.log').read_text()
            if 'target_feature="aes"' not in configured or 'target_feature="sse2"' not in configured:
                raise ValueError('compiler did not enable the verified CPU AES target features')
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
        if args.build_only:
            report.update(status='built_not_verified', cases=[], finished_at=datetime.now(timezone.utc).isoformat())
            save()
            print(json.dumps({'status': report['status'], 'report': str(output / 'report.json')}))
            return 0
        step('transport', [str(binary), '--exact', 'testnet4_disk_transport_roundtrip_and_truncation', '--nocapture'], 60)
        cases = []
        case_order = ['wrong-statement', 'real-nova-proof', 'tampered-proof-input']
        report.update(case_isolation='fresh process per full evaluation', timeout_seconds_per_case=args.timeout)
        for case in case_order:
            env['BITVM_DEMO_CASE'] = case
            step('run-' + case, [str(binary), '--exact', NAME, '--nocapture', '--test-threads=1'], args.timeout)
            observed = [json.loads(line.split('BITVM3_DEMO ', 1)[1])
                        for line in (output / ('run-' + case + '.log')).read_text().splitlines() if 'BITVM3_DEMO ' in line]
            if len(observed) != 1 or observed[0]['case'] != case:
                raise ValueError('isolated process did not execute exactly the requested full case')
            cases += observed
            report['cases'] = cases
            save()
        if len(cases) != 3 or {item['case'] for item in cases} != {'real-nova-proof', 'tampered-proof-input', 'wrong-statement'}:
            raise ValueError('missing verifier cases')
        for item in cases:
            wanted = item['case'] == 'real-nova-proof'
            if (item['accepted'] is not wanted or item['rejected'] is wanted or
                    item['ciphertexts'] != 785442492 or item['input_bits'] != 8635080):
                raise ValueError('verifier result or circuit dimensions differ')
        report['steps'].append({'name': 'run', 'exit_code': 0, 'scope': 'Aggregate of three successful isolated case processes; see run-* steps for commands'})
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
    parser.add_argument('--timeout', type=int, default=3600)
    parser.add_argument('--aesni', action='store_true', help='verify x86 CPU support and enable the upstream AES-NI backend')
    parser.add_argument('--build-only', action='store_true', help='precompile only; produces built_not_verified, never a passed receipt')
    return run(parser.parse_args())


if __name__ == '__main__':
    sys.exit(main())
