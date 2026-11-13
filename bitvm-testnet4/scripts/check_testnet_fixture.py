"""Compare the Nova demo's genesis-to-height-4 headers against a synced Testnet4 node."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bitvm_demo.bitcoin import btc, TESTNET4_GENESIS
from bitvm_demo.testnet import CoreCLI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['cli', 'observer-data', 'gsv-source', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('use a fresh receipt path')
    observer = CoreCLI(args.cli, args.observer_data)
    info = observer.verify_testnet4(True)
    fixture = args.gsv_source / 'nova-bitvm3/m12/fixtures/testnet4-headers-0-80.bin'
    data = fixture.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != '86c91459b1d6622b39e4511b10374b4359fb5675ec24717b5778d17dd974df9f':
        raise ValueError('Testnet4 header fixture differs')
    checks = []
    for height in range(5):
        blockhash = observer.call('getblockhash', height)
        header = data[height * 80:(height + 1) * 80]
        if header.hex() != observer.call('getblockheader', blockhash, False) or btc.sha256d(header)[::-1].hex() != blockhash:
            raise ValueError(f'header mismatch at height {height}')
        details = observer.call('getblockheader', blockhash)
        checks.append({'height': height, 'hash': blockhash, 'chainwork': details['chainwork']})
    if checks[-1]['hash'] != '000000008f5794caa45c418a0184303e848e9d6756e4d77234c9aada983b4265' or int(checks[-1]['chainwork'], 16) != 0x500050005:
        raise ValueError('Nova statement tip or chainwork differs')
    receipt = {'status': 'passed', 'network': 'testnet4', 'genesis': TESTNET4_GENESIS,
               'at': datetime.now(timezone.utc).isoformat(), 'observer': info, 'fixture_sha256': digest,
               'verified_headers': checks, 'broadcast': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'verified_headers': 5, 'receipt': str(args.output)}))


if __name__ == '__main__': main()
