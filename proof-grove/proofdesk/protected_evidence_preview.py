"""Serve pinned issuance and refusal evidence from the local recovery demo."""

import hashlib
from io import BytesIO
import json
from typing import NamedTuple
from zipfile import BadZipFile, ZipFile

from .domain import Refused, hash32, positive
from .protected_funded_preview import local_artifact
from .verifier import read_bounded


RECEIPTS = {'issuance': 'verification.json', 'refusal': 'refusal-receipt.json'}
REFUSAL_STATEMENT = 'withdrawal/final-statement.json'


class CheckedEvidence(NamedTuple):
    summary: dict
    archive: bytes
    verification: bytes | None


def issuance_summary(receipt, claim, txid, wtxid):
    issuance, nova, payout = (receipt[key] for key in ('issuance', 'nova', 'bitcoin_payout'))
    issuer = issuance['independent_verifier']
    if (receipt['schema'] != 'proof-grove/protected-withdrawal-issuance-audit/v1'
            or issuance['claim'] != claim or payout['claim_id'] != claim or payout['network'] != 'regtest'
            or (payout['payout_txid'], payout['payout_wtxid']) != (txid, wtxid)
            or not all(issuer[flag] is True for flag in ('dleq_verified', 'batch_bound', 'offline_keyset_audit'))
            or nova['verified'] is not True or nova['operations'] != ['register', 'issue', 'redeem']
            or nova['declared_reserve_sats'] != 0 or nova['outstanding_claims_sats'] != 0
            or payout['holder_signature_verified'] is not True or payout['witness_inclusion_verified'] is not True
            or not issuance['amount_sats'] == issuer['amount_sats'] == payout['reserve_sats']):
        raise Refused('recovery_evidence_unverified')
    return {'issued_sats': positive(issuance['amount_sats'], 'issuance'),
            'proof_count': positive(issuer['proof_count'], 'Cashu proofs'),
            'holder_sats': positive(payout['payout_sats'], 'payout'),
            'nova_proof_sha256': hash32(nova['proof_sha256'], 'Nova proof'),
            'nova_verifier_key_sha256': hash32(nova['verifier_key_sha256'], 'Nova verifier')}


def refusal_summary(receipt, claim, txid, wtxid):
    holder, timeout, collateral, replay, chain, controls = (receipt[key] for key in (
        'holder_payout', 'collateral_timeout', 'collateral', 'independent_chain_replay', 'published_chain', 'controls'))
    authorization = receipt['joint_package']['authorization']
    delay = positive(authorization['timeout_blocks'], 'collateral delay', 65535)
    if (receipt['schema'] != 'proof-grove/m14/funded-withdrawal-refusal/v1'
            or authorization['cashu_claim_id'] != claim or (holder['txid'], holder['wtxid']) != (txid, wtxid)
            or receipt['verdict_supplied'] is not False or type(receipt['wallets_loaded_during_settlement']) is not int
            or receipt['wallets_loaded_during_settlement'] != 0 or replay['network'] != 'regtest'
            or (replay['height'], replay['anchor'], replay['archive_sha256']) != (
                chain['height'], chain['anchor'], chain['archive_sha256'])
            or (timeout['height'], timeout['block']) != (chain['height'], chain['anchor'])
            or timeout['height'] != collateral['height'] + delay or holder['height'] >= timeout['height']
            or controls['early_timeout']['allowed'] is not False
            or controls['substituted_timeout_beneficiary']['allowed'] is not False
            or controls['timeout_reorg_restored_only_collateral'] is not True):
        raise Refused('recovery_evidence_unverified')
    return {'holder_sats': positive(holder['sats'], 'holder payout'),
            'challenger_sats': positive(timeout['sats'], 'challenger payout'), 'timeout_blocks': delay,
            'holder_fee_sats': positive(holder['fee_sats'], 'holder fee'),
            'challenger_fee_sats': positive(timeout['fee_sats'], 'challenger fee'),
            'challenger_txid': hash32(timeout['txid'], 'challenger transaction'),
            'chain_sha256': hash32(chain['archive_sha256'], 'refusal block archive')}


def refusal_verification(manifest, descriptor, archive_pin, statement, claim, producer):
    pin = hash32(descriptor['verification_sha256'], 'refusal verification receipt')
    path = local_artifact(manifest, descriptor['verification'], '.json')
    raw = read_bounded(path, 128 * 1024)
    if hashlib.sha256(raw).hexdigest() != pin:
        raise Refused('recovery_evidence_verification_changed')
    result = json.loads(raw)
    bitcoin, chain = result['bitcoin'], producer['published_chain']
    if (result['schema'] != 'proof-grove/m14/independent-refusal-verification/v1'
            or result['network'] != 'regtest' or result['claim_id'] != claim or result['archive_sha256'] != archive_pin
            or result['statement_sha256'] != hashlib.sha256(statement).hexdigest()
            or type(result['wallets_loaded']) is not int or result['wallets_loaded'] != 0
            or result['verdict_supplied'] is not False
            or bitcoin['schema'] != 'proof-grove/protected-regtest-block-replay/v1' or bitcoin['network'] != 'regtest'
            or (bitcoin['height'], bitcoin['anchor'], bitcoin['archive_sha256'], bitcoin['blocks_submitted']) != (
                chain['height'], chain['anchor'], chain['archive_sha256'], chain['height'])
            or result['holder_payout'] != producer['holder_payout']
            or result['collateral_timeout'] != producer['collateral_timeout']
            or any(result[key] is not True for key in ('early_timeout_rejected', 'substituted_beneficiary_rejected',
                                                       'timeout_reorg_restored_only_collateral'))):
        raise Refused('recovery_evidence_unverified')
    return raw, {'independent_replay_verified': True, 'verification_sha256': pin,
                 'blocks_replayed': positive(bitcoin['blocks_submitted'], 'replayed blocks', 4096),
                 'refusal_holder_height': positive(result['holder_payout']['height'], 'holder payout height', 4096),
                 'refusal_timeout_height': positive(bitcoin['height'], 'timeout height', 4096)}


def checked_archive(manifest, case):
    if manifest is None:
        raise Refused('recovery_evidence_not_configured')
    if case not in RECEIPTS:
        raise Refused('recovery_evidence_unknown_case')
    try:
        publication = json.loads(read_bounded(manifest, 4096))
        if publication['schema'] != 'proof-grove/protected-recovery-evidence/v1':
            raise Refused('recovery_evidence_invalid_publication')
        claim, txid, wtxid = (hash32(publication[field], field) for field in ('claim_id', 'holder_txid', 'holder_wtxid'))
        archive = publication[case]
        pin = hash32(archive['sha256'], 'evidence archive')
        path = local_artifact(manifest, archive['file'], '.zip')
        raw = read_bounded(path, 256 * 1024)
        if hashlib.sha256(raw).hexdigest() != pin:
            raise Refused('recovery_evidence_archive_changed')
        verification_fields = {'verification', 'verification_sha256'} & archive.keys()
        if verification_fields and (len(verification_fields) != 2 or case != 'refusal'):
            raise Refused('recovery_evidence_invalid_publication')
        with ZipFile(BytesIO(raw)) as source:
            with source.open(RECEIPTS[case]) as member:
                receipt = member.read(128 * 1024 + 1)
            if verification_fields:
                with source.open(REFUSAL_STATEMENT) as member:
                    statement = member.read(64 * 1024 + 1)
                if not 0 < len(statement) <= 64 * 1024:
                    raise Refused('recovery_evidence_invalid_publication')
        if len(receipt) > 128 * 1024:
            raise Refused('recovery_evidence_invalid_publication')
        report = json.loads(receipt)
        summarize = issuance_summary if case == 'issuance' else refusal_summary
        summary = {'network': 'regtest', 'holder_txid': txid, 'archive_sha256': pin, **summarize(report, claim, txid, wtxid)}
        verification = None
        if verification_fields:
            verification, checked = refusal_verification(manifest, archive, pin, statement, claim, report)
            summary.update(checked)
        return CheckedEvidence(summary, raw, verification)
    except Refused:
        raise
    except (OSError, TypeError, KeyError, ValueError, AttributeError, BadZipFile) as error:
        raise Refused('recovery_evidence_invalid_publication') from error
