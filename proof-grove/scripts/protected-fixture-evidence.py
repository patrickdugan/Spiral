"""Build Nova and BitVM3 fixture inputs from the protected holder regtest receipt."""

import argparse
import hashlib
import json
from pathlib import Path


GENESIS = '0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206'
SCHEMA = 'proof-grove/protected-reserve-regtest/v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_receipt(path):
    value = json.loads(path.read_bytes())
    if value.get('schema') != SCHEMA or value.get('genesis') != GENESIS:
        raise ValueError('expected the protected holder regtest receipt')
    if value.get('evidence') != 'bitcoin-core-regtest-consensus':
        raise ValueError('expected a completed Bitcoin Core fixture')
    plan = value['app_bundle']['plan']
    reserve = value['reserve']
    payout = value['payout']
    if (plan['reserve_sats'] != reserve['sats'] or plan['funding_script'] != reserve['script']
            or plan['payout_sats'] != payout['sats'] or plan['payout_script'] != payout['script']
            or plan['fee_sats'] != payout['fee_sats']
            or payout['sats'] + payout['fee_sats'] + plan['change_sats'] != reserve['sats']
            or value['mature_holder_check']['mempool_eligible'] is not True
            or value['mature_holder_check']['txid'] != payout['txid']):
        raise ValueError('reserve and settlement disagree with the saved plan')
    return value


def journal(receipt):
    bundle, reserve, payout = (receipt[key] for key in ('app_bundle', 'reserve', 'payout'))
    plan = bundle['plan']
    mint = digest({'schema': plan['schema'], 'mint_pubkey': plan['mint_pubkey']})
    intent = digest({'kind': 'protected-fixture-intent', 'plan_id': plan['plan_id']})
    note = digest({'kind': 'fixture-note', 'claim_commitment': plan['claim_commitment'],
                   'bundle_id': bundle['bundle_id']})
    actions = [
        {'kind': 'register', 'intent': intent},
        {'kind': 'issue', 'intent': intent, 'claim': note},
        {'kind': 'redeem', 'input': note, 'reserve_before_sats': reserve['sats']},
    ]
    evidence = [
        {'kind': 'observed-regtest-reserve', 'funding': reserve, 'bundle_id': bundle['bundle_id']},
        {'kind': 'declared-fixture-issuance', 'real_cdk_issuance': False,
         'bundle_id': bundle['bundle_id'], 'claim': note, 'amount_sats': reserve['sats']},
        {'kind': 'observed-regtest-payout', 'payout': payout, 'bundle_id': bundle['bundle_id']},
    ]
    events = [
        {'funding_txid': reserve['txid'], 'funding_vout': reserve['vout'], 'amount_sats': reserve['sats'],
         'action': action, 'evidence_sha256': digest(record)}
        for action, record in zip(actions, evidence, strict=True)
    ]
    return {'schema': 'proof-grove/cashu-nova-journal/v1', 'genesis': GENESIS,
            'mint_profile_sha256': mint, 'events': events}, evidence


def hex_bytes(value, count):
    raw = bytes.fromhex(value)
    if len(raw) != count or value != raw.hex():
        raise ValueError('invalid canonical hexadecimal field')
    return raw


def settlement(receipt, verifier):
    expected, evidence = journal(receipt)
    expected_hash = hashlib.sha256(canonical(expected)).hexdigest()
    if (verifier.get('schema') != 'proof-grove/cashu-nova-regtest-accounting/v1'
            or verifier.get('mode') != 'verify-journal' or verifier.get('verified') is not True
            or verifier.get('journal_sha256') != expected_hash
            or verifier.get('operations') != ['register', 'issue', 'redeem']
            or verifier.get('declared_reserve_sats') != 0 or verifier.get('outstanding_claims_sats') != 0):
        raise ValueError('independent verifier receipt does not match the protected fixture journal')
    reserve, payout = receipt['reserve'], receipt['payout']
    plan = receipt['app_bundle']['plan']
    if payout['height'] - payout['delay_blocks'] != receipt['mature_holder_check']['observation']['funding_height']:
        raise ValueError('wrong settlement height')
    halves = [
        b'PGCSET01', hex_bytes(GENESIS, 32), hex_bytes(payout['block'], 32),
        hex_bytes(verifier['before_final_journal_root'], 32), hex_bytes(verifier['zn'][8], 32),
        hex_bytes(receipt['claim_id'], 32), hex_bytes(reserve['txid'], 32),
        reserve['vout'].to_bytes(4, 'little'),
        hashlib.sha256(hex_bytes(reserve['script'], 34)).digest(),
        bytes.fromhex(digest({
            'kind': 'holder-bitcoin-signature-observation',
            'holder_pubkey': plan['holder_pubkey'], 'payout_wtxid': payout['wtxid'],
            'evidence_sha256': digest(evidence[-1]),
        })),
        hex_bytes(payout['txid'], 32), hex_bytes(payout['wtxid'], 32),
        hashlib.sha256(bytes.fromhex(payout['script'])).digest(),
        (payout['height'] - payout['delay_blocks']).to_bytes(4, 'little'),
        payout['height'].to_bytes(4, 'little'), payout['delay_blocks'].to_bytes(4, 'little'),
        *(value.to_bytes(7, 'little') for value in (
            reserve['sats'], payout['sats'], plan['change_sats'], payout['fee_sats']
        )),
    ]
    result = b''.join(halves)
    if len(result) != 404:
        raise ValueError('settlement record length mismatch')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    generate = subparsers.add_parser('journal')
    make_record = subparsers.add_parser('settlement')
    for command in (generate, make_record):
        command.add_argument('receipt', type=Path)
        command.add_argument('output', type=Path)
    make_record.add_argument('nova_verifier', type=Path)
    args = parser.parse_args()
    receipt = read_receipt(args.receipt)
    if args.command == 'journal':
        statement, records = journal(receipt)
        args.output.mkdir()
        (args.output / 'journal.json').write_bytes(canonical(statement))
        (args.output / 'admission-evidence.json').write_bytes(canonical(records))
        print(hashlib.sha256(canonical(statement)).hexdigest())
    else:
        verification = json.loads(args.nova_verifier.read_bytes())
        with args.output.open('xb') as stream:
            stream.write(settlement(receipt, verification))


if __name__ == '__main__':
    main()
