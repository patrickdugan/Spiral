"""Prove a candidate consumption while the actual V3 reserve remains unspent."""

import copy
import hashlib
import json
import os
import subprocess
import sys

from proofdesk import protected_accounting as accounting, protected_withdrawal as withdrawal
from proofdesk import protected_chain_archive
from proofdesk import protected_withdrawal_evidence as bitcoin_evidence
from proofdesk.domain import Refused, digest
from protected_rollover_fixture import v3_issuance_prefix


def _refusal(expected, operation, *args):
    try:
        operation(*args)
    except Refused as error:
        assert error.code == expected, error
        return error.code
    raise AssertionError(f'missing expected refusal {expected}')


def prove(core, rpc, root, runtime, handoff, node, nova, key_pin, bundle, raw):
    mint, entries = v3_issuance_prefix(root, handoff, node, bundle)
    tip = core.rpc('getblockchaininfo', [])
    catalog = {'schema': accounting.CATALOG_SCHEMA, 'genesis': bundle['plan']['genesis'], 'mint': mint,
               'tip_hash': tip['bestblockhash'], 'tip_height': tip['blocks'], 'bundles': [bundle]}
    journal = {'schema': accounting.JOURNAL_SCHEMA, 'genesis': catalog['genesis'],
               'mint_profile_sha256': digest({'schema': 'proof-grove/protected-accounting-mint/v3', 'mint_url': mint}),
               'events': [event for event, _ in entries]}
    records = [record for _, record in entries]
    args = (core, catalog, journal, records, bundle['bundle_id'], raw)
    live = accounting.audit(core, catalog, journal, records)
    assert live['declared_reserve_sats'] == live['outstanding_claims_sats'] == bundle['plan']['reserve_sats']

    directory = handoff/'withdrawal-authorization'
    directory.mkdir()

    def write(name, data):
        path = directory/name
        path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        return path

    def pin(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    tx_path = directory/'signed-payout.hex'
    tx_path.write_text(raw + '\n', encoding='ascii')
    command = [sys.executable, '-m', 'proofdesk', 'protected-withdrawal', '--config', runtime/'protected-core.json',
               '--bundle-id', bundle['bundle_id'], '--tx-file', tx_path]
    for name, data in (('catalog', catalog), ('journal', journal), ('records', records)):
        path = write(f'confirmed-{name}.json', data)
        command.extend((f'--{name}', path, f'--{name}-sha256', pin(path)))
    candidate_path = directory/'candidate.json'
    cli = json.loads(subprocess.check_output([*command, '--output', candidate_path], cwd=root, timeout=40))
    candidate = json.loads(candidate_path.read_bytes())
    assert cli['withdrawal_id'] == candidate['withdrawal_id'] and cli['steps'] == 3
    assert withdrawal.verify_candidate(*args, candidate) == candidate
    paid = candidate['admission']['statement']['withdrawal']
    witness = bitcoin_evidence.capture(rpc, bundle, candidate['admission'], raw)
    write('bitcoin-authorization-evidence.json', witness)
    verified_bitcoin = bitcoin_evidence.verify(witness, bundle['bundle_id'], candidate['withdrawal_id'],
                                              catalog['tip_height'], catalog['tip_hash'],
                                              openssl=os.environ.get('PROOF_GROVE_OPENSSL', 'openssl'))
    write('independent-bitcoin-authorization.json', verified_bitcoin)
    archive = protected_chain_archive.capture(rpc, directory/'checkpoint-blocks.hex', catalog['tip_height'], catalog['tip_hash'])
    write('checkpoint-blocks-manifest.json', archive)

    changed = copy.deepcopy(candidate)
    changed['admission']['statement']['withdrawal']['wtxid'] = '55' * 32
    changed['withdrawal_id'] = changed['journal']['events'][-1]['evidence_sha256'] = digest(changed['admission'])
    _refusal('protected_withdrawal_candidate_mismatch', withdrawal.verify_candidate, *args, changed)
    _refusal('protected_accounting_payout_mismatch', accounting.audit, core, catalog,
             candidate['journal'], [*records, candidate['admission']])

    candidate_journal = write('candidate-journal.json', candidate['journal'])
    proof_dir = directory/'proof'
    print(json.dumps({'stage': 'pre-withdrawal-nova-prove', 'steps': cli['steps']}), flush=True)
    with (directory/'prover.json').open('x', encoding='utf-8') as log:
        subprocess.run([nova, 'prove-journal', proof_dir, candidate_journal], stdout=log, timeout=300, check=True)
    transcript = subprocess.check_output([nova, 'verify-journal', proof_dir, candidate_journal, pin(candidate_journal)],
                                         timeout=180)
    (directory/'independent-verifier.json').write_bytes(transcript)
    verified = json.loads(transcript)
    assert (verified['verified'], verified['steps'], verified['verifier_key_sha256'], verified['journal_sha256']) == (
        True, 3, key_pin, pin(candidate_journal))
    assert verified['operations'] == ['register', 'issue', 'redeem']
    assert verified['zn'][8] != verified['before_final_journal_root']
    assert verified['declared_reserve_sats'] == verified['outstanding_claims_sats'] == 0
    assert accounting.audit(core, catalog, journal, records) == live
    assert paid['txid'] not in rpc('getrawmempool', [])
    assert core.rpc('gettxout', [bundle['funding']['txid'], bundle['funding']['vout'], True]) is not None

    rpc('invalidateblock', [catalog['tip_hash']])
    try:
        _refusal('protected_accounting_stale_catalog', withdrawal.verify_candidate, *args, candidate)
    finally:
        rpc('reconsiderblock', [catalog['tip_hash']])
    assert withdrawal.verify_candidate(*args, candidate) == candidate
    result = {'confirmed_prefix': live, 'candidate_withdrawal': paid, 'nova': verified,
              'proved_before_broadcast': True, 'anchor_invalidation_rejected': True,
              'substituted_witness_rejected': True, 'candidate_as_confirmed_rejected': True}
    write('pre-broadcast-verification.json', result)

    def after_broadcast():
        return _refusal('protected_accounting_reserve_unavailable', withdrawal.verify_candidate, *args, candidate)

    return result, after_broadcast
