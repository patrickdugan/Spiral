"""Owner-operated exit preparation/export and an independent Core broadcaster."""
import json
import os
from pathlib import Path
import time

from .adapters import BarkClient, CoreClient
from .ark import ArkCaretaker
from .domain import Ledger, Refused, canonical
from .exits import ExitRecovery


def configure(parser):
    for name in ('exit-prepare', 'exit-export', 'exit-import', 'exit-advance', 'exit-watch'):
        command = parser.add_parser(name)
        command.add_argument('--config', required=True)
        if name == 'exit-prepare':
            command.add_argument('--vtxo', action='append', required=True)
            command.add_argument('--fee-rate', type=int, default=5, help='sat/vB for saved CPFP transactions')
            command.add_argument('--max-fee', type=int, required=True, help='Total saved CPFP fee budget in sats; final claim is separate')
        elif name == 'exit-import':
            command.add_argument('--bundle', required=True)
            command.add_argument('--expected-id', required=True, help='Bundle ID obtained independently from its owner')
        else:
            command.add_argument('--id', required=True)
            if name == 'exit-export':command.add_argument('--output', required=True)
            if name in ('exit-advance', 'exit-watch'):command.add_argument('--broadcast', action='store_true')
            if name == 'exit-watch':command.add_argument('--interval', type=int, default=5)


def run(args):
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if config.get('mode') != 'regtest':raise Refused('exit_regtest_required')
    settings = config['core']
    core = CoreClient(settings['url'], settings['username'], os.environ[settings['password_env']])
    database = config_path.parent / config.get('database', '.runtime/regtest.sqlite')
    database.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(database, 'regtest')
    try:
        recovery = ExitRecovery(ledger, core, broadcaster=config.get('ark_regtest_exit_broadcast') is True)
        if args.command == 'exit-prepare':
            bark = BarkClient(config['bark_url'], os.environ[config['bark_bearer_env']] if config.get('bark_bearer_env') else '')
            caretaker = ArkCaretaker(ledger, bark, core, allow_regtest=config.get('ark_regtest_execution') is True)
            return recovery.prepare(caretaker, args.vtxo, args.fee_rate, args.max_fee)
        if args.command == 'exit-export':
            body = recovery.bundle(args.id)
            # New file only; a private recovery package can advance signed spends.
            with open(args.output, 'xb') as target:
                os.chmod(args.output, 0o600)
                target.write(canonical(body))
            return {'id': args.id, 'exported': True, 'meaning': 'Private signed recovery data. Keep the bundle ID through a separate trusted channel.'}
        if args.command == 'exit-import':
            with open(args.bundle, 'rb') as source:raw = source.read(1500001)
            if len(raw) > 1500000:raise Refused('exit_plan_too_large')
            return recovery.store(json.loads(raw), args.expected_id)
        if args.command == 'exit-advance':return recovery.advance(args.id, broadcast=args.broadcast)
        if not 1 <= args.interval <= 60:raise Refused('invalid_watch_interval')
        previous = None
        while True:
            try:
                result = recovery.advance(args.id, broadcast=args.broadcast)
            except Refused as error:
                if error.code not in ('chain_changed_retry', 'core_rpc_error', 'upstream_unavailable'):
                    raise
                result = {'id': args.id, 'state': 'observer_retry', 'reason': error.code}
            encoded = canonical(result)
            if encoded != previous:print(encoded.decode(), flush=True);previous = encoded
            if result['state'] not in ('awaiting_confirmations', 'exit_confirmed', 'submitting', 'submission_uncertain', 'observer_retry', 'timelock_wait'):
                return {'watch_stopped': True, 'id': args.id, 'state': result['state']}
            time.sleep(args.interval)
    finally:
        ledger.close()
