"""Serve pinned protected Cashu evidence from the local recovery demo."""

import hashlib
from io import BytesIO
import json
from typing import NamedTuple
from zipfile import BadZipFile, ZipFile

from .domain import MAX_SATS, Refused, digest, hash32, positive
from .protected_accounting import JOURNAL_SCHEMA, MAX_EVENTS, REGISTRY_CATALOG_SCHEMA
from .protected_chain_archive import inspect_headers
from .protected_funded_preview import local_artifact
from .protected_registry import SCHEMA as REGISTRY_SCHEMA
from .protected_reserve import GENESIS
from .verifier import read_bounded


RECEIPTS = {'issuance': 'verification.json', 'refusal': 'refusal-receipt.json',
            'accounting': 'evidence/nova-registry-verification.json'}
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


def read_member(source, name, limit):
    with source.open(name) as member:
        raw = member.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise Refused('recovery_evidence_invalid_publication')
    return raw


def accounting_summary(source, receipt, descriptor):
    root = json.loads(read_member(source, 'evidence/registry-root.json', 4096))
    catalog_raw = read_member(source, 'evidence/catalog.json', 128 * 1024)
    journal_raw = read_member(source, 'evidence/journal.json', 128 * 1024)
    catalog, journal = json.loads(catalog_raw), json.loads(journal_raw)
    proof = read_member(source, 'evidence/nova-proof/nova-proof.bin', 128 * 1024)
    blocks = read_member(source, 'evidence/registry-blocks.hex', 1024 * 1024)
    registry, nova = receipt['registry'], receipt['nova']
    root_pin = hash32(descriptor['registry_sha256'], 'registry root')
    tip_hash = hash32(descriptor['tip_hash'], 'registry tip')
    tip_height = positive(descriptor['tip_height'], 'registry height', 4096)
    key_pin = hash32(descriptor['nova_verifier_key_sha256'], 'Nova verifier')
    blocks_pin = hash32(descriptor['blocks_sha256'], 'registry blocks')
    fields = ('declared_reserve_sats', 'outstanding_claims_sats', 'pending_issuance_sats')
    totals = tuple(receipt[field] for field in fields)
    if (receipt['schema'] != 'proof-grove/protected-ledger-audit/v1'
            or (receipt['tip_hash'], receipt['tip_height']) != (tip_hash, tip_height)
            or (root['schema'], root['genesis']) != (REGISTRY_SCHEMA, GENESIS)
            or (catalog['schema'], catalog['genesis'], catalog['tip_hash'], catalog['tip_height']) != (
                REGISTRY_CATALOG_SCHEMA, GENESIS, tip_hash, tip_height)
            or (journal['schema'], journal['genesis']) != (JOURNAL_SCHEMA, GENESIS)
            or not root_pin == digest(root) == catalog['registry_sha256'] == registry['root_sha256']
            or receipt['catalog_sha256'] != hashlib.sha256(catalog_raw).hexdigest()
            or not receipt['journal_sha256'] == hashlib.sha256(journal_raw).hexdigest() == nova['journal_sha256']
            or hashlib.sha256(blocks).hexdigest() != blocks_pin
            or nova['schema'] != 'proof-grove/cashu-nova-regtest-accounting/v1'
            or nova['mode'] != 'verify-journal' or nova['verified'] is not True
            or positive(nova['steps'], 'Nova steps', MAX_EVENTS) != len(journal['events'])
            or nova['proof_bytes'] != len(proof) or hashlib.sha256(proof).hexdigest() != nova['proof_sha256']
            or key_pin != nova['verifier_key_sha256']
            or any(type(value) is not int or not 0 <= value <= MAX_SATS for value in totals)
            or sum(totals[1:]) > totals[0]
            or totals[:2] != (nova['declared_reserve_sats'], nova['outstanding_claims_sats'])
            or len(nova['zn']) != 10 or totals != tuple(int(hash32(word, 'Nova total'), 16) for word in nova['zn'][4:7])
            or not receipt['catalog_reserves'] == registry['registered_reserves'] == len(catalog['bundles'])):
        raise Refused('recovery_evidence_unverified')
    inspect_headers(blocks, tip_height, tip_hash)
    return dict(zip(fields, totals, strict=True)) | {
        'tip_height': tip_height, 'tip_hash': tip_hash, 'registry_sha256': root_pin,
        'registered_reserves': positive(registry['registered_reserves'], 'enrolled reserves', MAX_EVENTS),
        'nova_proof_sha256': nova['proof_sha256'], 'nova_verifier_key_sha256': key_pin,
    }


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
        if case == 'accounting' and case not in publication:
            raise Refused('recovery_accounting_not_configured')
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
            receipt = read_member(source, RECEIPTS[case], 128 * 1024)
            report = json.loads(receipt)
            if case == 'accounting':
                summary = accounting_summary(source, report, archive)
                return CheckedEvidence({'network': 'regtest', 'archive_sha256': pin, **summary}, raw, receipt)
            statement = read_member(source, REFUSAL_STATEMENT, 64 * 1024) if verification_fields else None
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
