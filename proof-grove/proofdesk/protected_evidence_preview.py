"""Serve pinned issuance and refusal evidence from the local recovery demo."""

import hashlib
from io import BytesIO
import json
from zipfile import BadZipFile, ZipFile

from .domain import Refused, hash32, positive
from .protected_funded_preview import local_artifact
from .verifier import read_bounded


RECEIPTS = {'issuance': 'verification.json', 'refusal': 'refusal-receipt.json'}


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
        with ZipFile(BytesIO(raw)) as source:
            with source.open(RECEIPTS[case]) as member:
                receipt = member.read(128 * 1024 + 1)
        if len(receipt) > 128 * 1024:
            raise Refused('recovery_evidence_invalid_publication')
        summary = issuance_summary if case == 'issuance' else refusal_summary
        return ({'network': 'regtest', 'holder_txid': txid, 'archive_sha256': pin,
                 **summary(json.loads(receipt), claim, txid, wtxid)}, raw)
    except Refused:
        raise
    except (OSError, TypeError, KeyError, ValueError, AttributeError, BadZipFile) as error:
        raise Refused('recovery_evidence_invalid_publication') from error
