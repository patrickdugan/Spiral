"""Build and verify accounting and settlement evidence for protected Cashu fixtures."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


GENESIS = '0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206'
SCHEMA = 'proof-grove/protected-reserve-regtest/v1'
V3_PLAN = 'proof-grove/protected-reserve-plan/v3'


def read_bounded(path, limit):
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError('unexpected evidence file length')
    return data


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_receipt(path):
    value = json.loads(read_bounded(path, 256 * 1024))
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


def verify_v3_admission(receipt, portable_path, bundle_path, bundle_id, mint_pin_path, node, wallet_cli=None):
    """Rerun offline note verification against the observer's independent pins."""
    hex_bytes(bundle_id, 32)
    bundle_raw = read_bounded(bundle_path, 32768)
    bundle = json.loads(bundle_raw)
    reserve = receipt['reserve']
    funding = {key: reserve[key] for key in ('txid', 'vout', 'block')}
    if (bundle != receipt['app_bundle'] or bundle['bundle_id'] != bundle_id
            or bundle['plan']['schema'] != V3_PLAN or bundle['funding'] != funding
            or bundle['plan']['genesis'] != GENESIS):
        raise ValueError('V3 funding receipt differs from the independently pinned bundle')
    claim = hashlib.sha256(b'proof-grove/protected-reserve/v1\0' + hex_bytes(GENESIS, 32)
                           + hex_bytes(funding['txid'], 32) + funding['vout'].to_bytes(4, 'big')).hexdigest()
    if claim != receipt['claim_id']:
        raise ValueError('V3 claim is not the canonical reserve outpoint claim')
    pin = json.loads(read_bounded(mint_pin_path, 32768))
    hex_bytes(pin['keysets_sha256'], 32)
    portable = read_bounded(portable_path, 2 * 1024 * 1024)
    cli = wallet_cli or (Path(__file__).resolve().parents[1] / 'wallet/cli.mjs')
    with tempfile.TemporaryDirectory(prefix='proof-grove-v3-admission-') as scratch:
        checked_receipt, checked_bundle = (Path(scratch) / name for name in ('receipt.json', 'bundle.json'))
        checked_receipt.write_bytes(portable)
        checked_bundle.write_bytes(bundle_raw)
        run = subprocess.run([node, str(cli), 'protected-verify-receipt', '--receipt', str(checked_receipt),
                              '--mint', pin['mint'], '--keysets-sha256', pin['keysets_sha256'],
                              '--bundle', str(checked_bundle), '--bundle-id', bundle_id,
                              '--amount', str(reserve['sats'])],
                             stdin=subprocess.DEVNULL, capture_output=True, check=False, timeout=30)
    try:
        verification = json.loads(run.stdout)
    except json.JSONDecodeError:
        raise ValueError(f'V3 wallet verifier did not return JSON (exit {run.returncode})') from None
    if run.returncode:
        raise ValueError(f'V3 offline issuer verification refused the receipt: {verification.get("error")}')
    if (verification.get('batch_bound') is not True or verification.get('dleq_verified') is not True
            or verification.get('offline_keyset_audit') is not True
            or verification.get('bundle_id') != bundle_id or verification.get('amount_sats') != reserve['sats']
            or verification.get('keysets_sha256') != pin['keysets_sha256']
            or verification.get('keyset_ids') != pin['keyset_ids']):
        raise ValueError('V3 issuer verification did not establish the expected exact batch')
    intent = json.loads(portable)['operation']['protection']['batch']['intent_id']
    return {'kind': 'verified-cdk-protected-v3-batch', 'real_cdk_issuance': True,
            'bundle_id': bundle_id, 'claim': claim, 'amount_sats': reserve['sats'],
            'intent_id': intent, 'issuance_batch_sha256': bundle['plan']['claim_commitment'],
            'issuance_receipt_sha256': hashlib.sha256(portable).hexdigest(), 'independent_verifier': verification}


def issuance_evidence(receipt, certificate, note):
    bundle, reserve = receipt['app_bundle'], receipt['reserve']
    common = {'bundle_id': bundle['bundle_id'], 'claim': note, 'amount_sats': reserve['sats']}
    if certificate is None and 'cdk_issuance' not in receipt:
        return common | {'kind': 'declared-fixture-issuance', 'real_cdk_issuance': False}
    if certificate is None:
        raise ValueError('the observed CDK receipt requires its issuance certificate')
    independent, control = receipt['cdk_issuance'], receipt['legacy_cdk_melt']
    certificate_sha = hashlib.sha256(certificate).hexdigest()
    envelope = json.loads(certificate)
    operation = envelope['operation']
    proof_hash = hashlib.sha256(json.dumps(
        operation['proofs'], ensure_ascii=False, separators=(',', ':'), allow_nan=False
    ).encode()).hexdigest()
    if (envelope.get('schema') != 'proof-grove/protected-cdk-issuance-fixture/v1'
            or digest({key: value for key, value in bundle.items() if key != 'bundle_id'}) != bundle['bundle_id']
            or operation['protection']['bundle_id'] != bundle['bundle_id']
            or operation['protection']['lock_key'] != independent['lock_key']
            or independent['bundle_id'] != bundle['bundle_id']
            or independent['amount_sats'] != reserve['sats'] or operation['amount_sats'] != reserve['sats']
            or independent['proofs_sha256'] != proof_hash
            or independent['request_sha256'] != operation['request_sha256']
            or independent['certificate_sha256'] != certificate_sha or control['certificate_sha256'] != certificate_sha
            or not all(independent[field] is True for field in (
                'dleq_verified', 'offline_keyset_audit', 'changed_secret_rejected'
            )) or control['refused_protected_inputs'] is not True or control['unspent_after_rejection'] is not True):
        raise ValueError('CDK certificate does not match the protected fixture audits')
    return common | {'kind': 'observed-cdk-protected-issuance', 'real_cdk_issuance': True,
                     'certificate_sha256': certificate_sha, 'independent_verifier': independent}


def journal(receipt, certificate=None, v3=None):
    bundle, reserve, payout = (receipt[key] for key in ('app_bundle', 'reserve', 'payout'))
    plan = bundle['plan']
    if plan['schema'] == V3_PLAN:
        if v3 is None or certificate is not None:
            raise ValueError('V3 journal requires independently verified batch evidence')
        mint = digest({'schema': 'proof-grove/protected-accounting-mint/v3',
                       'mint_url': v3['independent_verifier']['mint']})
        namespace, _, quote = v3['intent_id'].partition(':')
        if namespace != 'cashu':
            raise ValueError('V3 issuance intent must identify a Cashu quote')
        intent = hashlib.sha256(b'proof-grove/protected-issuance-intent/v1\0'
                                + hex_bytes(quote, 32)).hexdigest()
        note, issuance = v3['claim'], v3
    else:
        if v3 is not None:
            raise ValueError('V3 evidence requires a V3 reserve plan')
        mint = digest({'schema': plan['schema'], 'mint_pubkey': plan['mint_pubkey']})
        intent = plan['claim_commitment'] if certificate is not None else digest({
            'kind': 'protected-fixture-intent', 'plan_id': plan['plan_id'],
        })
        note = receipt['claim_id'] if certificate is not None else digest({
            'kind': 'fixture-note', 'claim_commitment': plan['claim_commitment'], 'bundle_id': bundle['bundle_id'],
        })
        issuance = issuance_evidence(receipt, certificate, note)
    actions = [
        {'kind': 'register', 'intent': intent},
        {'kind': 'issue', 'intent': intent, 'claim': note},
        {'kind': 'redeem', 'input': note, 'reserve_before_sats': reserve['sats']},
    ]
    evidence = [
        {'kind': 'observed-regtest-reserve', 'funding': reserve, 'bundle_id': bundle['bundle_id']},
        issuance,
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


def settlement(receipt, verifier, certificate=None, v3=None):
    expected, evidence = journal(receipt, certificate, v3)
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


def audit_v3(args, receipt, v3):
    """Verify the archived issuance, Nova proof and mined payout against separate pins."""
    if args.output.exists():
        raise ValueError('the V3 audit requires a new output directory')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from proofdesk.protected_payout_evidence import verify as verify_payout

    statement, records = journal(receipt, v3=v3)
    encoded = canonical(statement)
    journal_sha256 = hashlib.sha256(encoded).hexdigest()
    hex_bytes(args.journal_sha256, 32)
    hex_bytes(args.nova_key_sha256, 32)
    if journal_sha256 != args.journal_sha256:
        raise ValueError('rebuilt V3 journal differs from the independent pin')
    payout = verify_payout(receipt, args.v3_bundle_id, args.anchor_height, args.anchor_hash, openssl=args.openssl)
    if (payout['claim_id'] != v3['claim'] or payout['reserve_sats'] != v3['amount_sats']
            or payout['funding_txid'] != statement['events'][0]['funding_txid']):
        raise ValueError('V3 payout differs from the admitted issuance claim')

    proof_file = args.proof_dir / 'nova-proof.bin'
    proof_sha256 = hashlib.sha256(read_bounded(proof_file, 4 * 1024 * 1024)).hexdigest()
    with tempfile.TemporaryDirectory(prefix='proof-grove-v3-journal-') as scratch:
        journal_path = Path(scratch) / 'journal.json'
        journal_path.write_bytes(encoded)
        checked = subprocess.run([str(args.nova_verifier.resolve()), 'verify-journal', str(args.proof_dir.resolve()),
                                  str(journal_path), journal_sha256], stdin=subprocess.DEVNULL,
                                 capture_output=True, check=True, timeout=180)
    nova = json.loads(checked.stdout)
    if (nova.get('verifier_key_sha256') != args.nova_key_sha256 or nova.get('proof_sha256') != proof_sha256
            or nova.get('steps') != len(records)):
        raise ValueError('Nova verification differs from the pinned key, proof, or journal length')
    record = settlement(receipt, nova, v3=v3)
    result = {'schema': 'proof-grove/protected-v3-archived-audit/v1', 'journal_sha256': journal_sha256,
              'settlement_record_sha256': hashlib.sha256(record).hexdigest(),
              'issuance': v3, 'nova': nova, 'bitcoin_payout': payout}
    args.output.mkdir()
    (args.output / 'journal.json').write_bytes(encoded)
    (args.output / 'admission-evidence.json').write_bytes(canonical(records))
    (args.output / 'settlement.bin').write_bytes(record)
    (args.output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    generate = subparsers.add_parser('journal')
    make_record = subparsers.add_parser('settlement')
    combined = subparsers.add_parser('audit-v3')
    for command in (generate, make_record, combined):
        command.add_argument('receipt', type=Path)
        command.add_argument('output', type=Path)
        command.add_argument('--issuance-certificate', type=Path)
        command.add_argument('--v3-receipt', type=Path)
        command.add_argument('--v3-bundle', type=Path)
        command.add_argument('--v3-bundle-id')
        command.add_argument('--v3-mint-pin', type=Path)
        command.add_argument('--node', default='node')
        command.add_argument('--wallet-cli', type=Path)
    make_record.add_argument('nova_verifier', type=Path)
    combined.add_argument('--proof-dir', required=True, type=Path)
    combined.add_argument('--nova-verifier', required=True, type=Path)
    combined.add_argument('--journal-sha256', required=True)
    combined.add_argument('--nova-key-sha256', required=True)
    combined.add_argument('--anchor-height', required=True, type=int)
    combined.add_argument('--anchor-hash', required=True)
    combined.add_argument('--openssl', default='openssl')
    args = parser.parse_args()
    receipt = read_receipt(args.receipt)
    v3_inputs = (args.v3_receipt, args.v3_bundle, args.v3_bundle_id, args.v3_mint_pin)
    if any(v3_inputs) and (not all(v3_inputs) or args.issuance_certificate):
        parser.error('all four V3 admission arguments are required together')
    if args.command == 'audit-v3' and not all(v3_inputs):
        parser.error('audit-v3 requires independently pinned V3 admission inputs')
    certificate = read_bounded(args.issuance_certificate, 2 * 1024 * 1024) if args.issuance_certificate else None
    v3 = verify_v3_admission(receipt, *v3_inputs, args.node, args.wallet_cli) if all(v3_inputs) else None
    if args.command == 'journal':
        statement, records = journal(receipt, certificate, v3)
        args.output.mkdir()
        (args.output / 'journal.json').write_bytes(canonical(statement))
        (args.output / 'admission-evidence.json').write_bytes(canonical(records))
        print(hashlib.sha256(canonical(statement)).hexdigest())
    elif args.command == 'settlement':
        verification = json.loads(read_bounded(args.nova_verifier, 256 * 1024))
        record = settlement(receipt, verification, certificate, v3)
        with args.output.open('xb') as stream:
            stream.write(record)
    else:
        audit_v3(args, receipt, v3)


if __name__ == '__main__':
    main()
