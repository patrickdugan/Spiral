"""Run every test, save receipts, and optionally collect local microbenchmarks."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'results')
    parser.add_argument('--benchmark', action='store_true')
    options = parser.parse_args()
    os.environ['BMA_REQUIRE_NATIVE'] = '1'
    start = time.perf_counter()
    log = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern='test_*.py')
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    import test_muladdmod, test_dispute, test_native
    report = {
        'status': 'pass' if result.wasSuccessful() and not result.skipped else 'fail',
        'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'elapsed_seconds': time.perf_counter()-start,
        'python': sys.version, 'platform': platform.platform(),
        'original_python_vectors': test_muladdmod.COUNTS,
        'trace_exhaustion': test_dispute.COUNTS, 'native': test_native.REPORT,
        'scope': 'Host models and standalone C++ only; Bitcoin Core and live BitVM execution untested.',
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(ROOT.rglob('*')) if p.suffix in ('.py', '.cpp')
                          and '__pycache__' not in p.parts},
    }
    if options.benchmark and report['status'] == 'pass':
        with tempfile.TemporaryDirectory() as temp:
            binary = str(Path(temp)/'benchmark')
            cmd = ['g++','-std=c++17','-O2','-DNDEBUG',str(ROOT/'native/muladdmod.cpp'),'-o',binary]
            subprocess.run(cmd, check=True, timeout=60)
            measurements = {}
            for _ in range(5):
                output = subprocess.check_output([binary,'--bench'], text=True, timeout=60)
                for line in output.splitlines():
                    width, ns, checksum = line.split()
                    row = measurements.setdefault(width, {'nanoseconds_per_call': [], 'checksums': []})
                    row['nanoseconds_per_call'].append(float(ns)); row['checksums'].append(int(checksum))
            for row in measurements.values():
                row['median_ns'] = statistics.median(row['nanoseconds_per_call'])
            report['microbenchmark'] = {
                'flags': '-std=c++17 -O2 -DNDEBUG', 'iterations_per_sample': 4000,
                'samples': 5, 'widths': measurements,
                'scope': 'Local dense-operand microbenchmark including decode and result allocation; no consensus price calibration.'}
    options.output.mkdir(parents=True, exist_ok=True)
    (options.output/'tests.txt').write_text(log.getvalue())
    (options.output/'verification.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(log.getvalue(), end='')
    print(json.dumps({k:report[k] for k in ('status','tests','failures','errors','skipped')}, indent=2))
    return 0 if report['status']=='pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
