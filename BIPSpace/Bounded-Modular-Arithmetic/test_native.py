"""Independent C++ decoder/arithmetic under GCC and Clang UBSan."""
import itertools
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from muladdmod import ScriptError, muladdmod
from test_muladdmod import args

REPORT = {}
ROOT = Path(__file__).resolve().parent


def vectors():
    for m in range(2, 14):
        for a, b, c in itertools.product(range(m), repeat=3): yield args(a, b, c, m)
    rng = random.Random(20261112)
    for width in range(1, 33):
        for _ in range(64):
            m = rng.randrange(max(2, 1 << (8*(width-1))), 1 << (8*width))
            yield args(*(rng.randrange(m) for _ in range(3)), m)
    for width in range(1, 33):
        for m in sorted({max(2, 1 << (8*(width-1))), (1 << (8*width))-1}):
            for a, b, c in itertools.product(sorted({0, 1, m-1}), repeat=3):
                yield args(a, b, c, m)


def invalid_vectors():
    yield (b'', b'', b'', b'')
    for m in (b'\x00', b'\x01', b'\x11\x00', bytes([1])*33):
        yield (bytes(len(m)),)*3 + (m,)
    for width in range(1, 33):
        m = (1 << (8*width))-1
        good = list(args(1, 1, 1, m))
        for position in range(3):
            for bad in (bytes(width-1), bytes(width+1), m.to_bytes(width, 'little')):
                changed = good.copy(); changed[position] = bad
                yield tuple(changed)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = [c for c in ('g++', 'clang++') if shutil.which(c)]
        if len(compilers) != 2:
            if os.getenv('BMA_REQUIRE_NATIVE') == '1':
                raise RuntimeError('GCC and Clang are both required for this verification run')
            raise unittest.SkipTest('GCC and Clang required for native differential suite')
        cls.temp = tempfile.TemporaryDirectory()
        cls.binaries = []
        for compiler in compilers:
            out = Path(cls.temp.name) / compiler.replace('+', 'p')
            cmd = [compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-pedantic', '-fsanitize=undefined', '-fno-sanitize-recover=all',
                   str(ROOT/'native/muladdmod.cpp'), '-o', str(out)]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            version = subprocess.check_output([compiler, '--version'], text=True).splitlines()[0]
            cls.binaries.append((compiler, str(out)))
            REPORT[compiler] = {'compiler': version, 'flags': cmd[1:-3],
                                'sanitizer': 'undefined; no recovery'}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check_cases(self, cases, label):
        cases = list(cases)
        expected = []
        for case in cases:
            try: expected.append('OK ' + muladdmod(*case).hex())
            except ScriptError: expected.append('ERR')
        data = ''.join(' '.join(x.hex() or '-' for x in case)+'\n' for case in cases)
        for compiler, binary in self.binaries:
            result = subprocess.run([binary], input=data, capture_output=True, text=True,
                                    check=True, timeout=60)
            self.assertEqual(result.stderr, '')
            self.assertEqual(result.stdout.splitlines(), expected)
            REPORT[compiler][label] = len(cases)

    def test_valid_all_widths(self):
        self.check_cases(vectors(), 'valid_vectors')

    def test_independent_decoder_rejections(self):
        self.check_cases(invalid_vectors(), 'rejection_vectors')

    def test_transport_parser_rejections(self):
        lines = ['','00 00 00','zz 00 00 11','0 00 00 11','00 00 00 11 extra']
        for _, binary in self.binaries:
            r = subprocess.run([binary], input='\n'.join(lines)+'\n',
                               capture_output=True, text=True, check=True, timeout=10)
            self.assertEqual(r.stdout.splitlines(), ['ERR']*len(lines))
            self.assertEqual(r.stderr, '')


if __name__ == '__main__':
    unittest.main()
