from __future__ import annotations

import argparse
import json
from pathlib import Path

from .testnet import endpoints, fund, make_plan, refute, signing_check


def main():
    parser = argparse.ArgumentParser(description='Stock Testnet4 BitVM primitives and Nova/BitVM3 verifier demos')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('plan', help='prepare fresh private keys and public fixed-claim contracts')
    init.add_argument('--private-dir', type=Path, required=True)
    init.add_argument('--output', type=Path, required=True)
    for name in ['status', 'signing-check', 'fund', 'refute']:
        command = commands.add_parser(name)
        command.add_argument('--cli', type=Path, required=True)
        command.add_argument('--observer-data', type=Path, required=True)
        command.add_argument('--signer-owner', type=Path, required=True)
        if name == 'status':
            continue
        if name == 'signing-check':
            command.add_argument('--wallet-setup', type=Path, required=True)
            continue
        command.add_argument('--private-dir', type=Path, required=True)
        command.add_argument('--output', type=Path, required=True)
        command.add_argument('--broadcast', action='store_true')
        if name == 'fund':
            command.add_argument('--wallet-setup', type=Path, required=True)
            command.add_argument('--nova-receipt', type=Path)
        else:
            command.add_argument('--funding', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            result = make_plan(args.private_dir, args.output)
        else:
            observer, signer = endpoints(args.cli, args.observer_data, args.signer_owner)
            if args.command == 'status':
                result = {'observer': observer.verify_testnet4(True), 'signer': signer.verify_testnet4(),
                          'scope': 'observer is public-network capable; dedicated signer has zero peers'}
            elif args.command == 'signing-check':
                result = signing_check(signer, json.loads(args.wallet_setup.read_text(encoding='utf-8-sig')))
            elif args.command == 'fund':
                result = fund(observer, signer, json.loads(args.wallet_setup.read_text(encoding='utf-8-sig')),
                              args.private_dir, args.output, args.nova_receipt, args.broadcast)
            else:
                result = refute(observer, signer, json.loads(args.funding.read_text()), args.private_dir, args.output, args.broadcast)
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
