"""Independently verify the three holder signatures and amounts in a regtest rollover."""

import argparse
import hashlib
import json
from pathlib import Path

from .cashu import compressed_point
from .domain import digest, hash32, positive
from .protected_payout_evidence import _raw, _transaction, _verify_holder_witness
from .protected_reserve import (
    GENESIS, PLAN_FIELDS, SUCCESSOR_BUNDLE_SCHEMA, SUCCESSOR_PLAN_SCHEMA, V3_BUNDLE_SCHEMA, V3_PLAN_SCHEMA,
    _ISSUANCE_TERM_SCHEMAS, _witness_script,
)
from .protected_rollover import PLAN_SCHEMA, RECEIPT_SCHEMA, RECIPIENT_FIELDS
from .verifier import read_bounded


def _check_id(document, field, expected):
    if document.get(field) != expected or digest({key: value for key, value in document.items() if key != field}) != expected:
        raise ValueError(f'protected rollover {field} pin mismatch')


def _funding(bundle, schema, plan_schema, transaction):
    plan, outpoint = bundle['plan'], bundle['funding']
    if (bundle['schema'] != schema or plan['schema'] != plan_schema or plan['network'] != 'regtest'
            or plan['genesis'] != GENESIS or not compressed_point(plan['holder_pubkey'])
            or not compressed_point(plan['mint_pubkey']) or plan['holder_pubkey'] == plan['mint_pubkey']):
        raise ValueError('unexpected protected rollover bundle profile or keys')
    _check_id(bundle, 'bundle_id', hash32(bundle['bundle_id'], 'bundle_id'))
    _check_id(plan, 'plan_id', hash32(plan['plan_id'], 'plan_id'))
    terms = {key: plan[key] for key in (*PLAN_FIELDS, 'network', 'genesis', 'payout_script')}
    preimage = digest({'schema': _ISSUANCE_TERM_SCHEMAS[plan_schema]} | terms)
    commitment = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
    delay = positive(plan['delay_blocks'], 'delay_blocks', 65535)
    script = _witness_script(plan['holder_pubkey'], plan['mint_pubkey'], delay, commitment)
    destination = b'\x00\x20' + hashlib.sha256(script).digest()
    position = outpoint['vout']
    amount = positive(plan['reserve_sats'], 'reserve_sats')
    if (transaction.txid != outpoint['txid'] or type(position) is not int or not 0 <= position < len(transaction.outputs)
            or transaction.outputs[position] != (amount, destination) or plan['funding_script'] != destination.hex()
            or plan['witness_script'] != script.hex() or plan['issuance_preimage'] != preimage
            or plan['issuance_hash'] != commitment):
        raise ValueError('protected rollover funding script, amount or outpoint mismatch')
    return bytes.fromhex(transaction.txid)[::-1] + position.to_bytes(4, 'little')


def verify(receipt, parent_id, rollover_id, *, openssl='openssl'):
    """Authenticate the signed transactions under pinned terms from the regtest observer."""
    hash32(parent_id, 'parent_bundle_id')
    hash32(rollover_id, 'rollover_id')
    parent, plan, confirmed = receipt['parent_bundle'], receipt['plan'], receipt['rollover']
    if (receipt.get('schema'), receipt.get('network'), receipt.get('genesis'), plan['schema'], confirmed['schema']) != (
            'proof-grove/protected-rollover-regtest/v1', 'regtest', GENESIS, PLAN_SCHEMA, RECEIPT_SCHEMA):
        raise ValueError('unexpected protected rollover evidence schema')
    _check_id(parent, 'bundle_id', parent_id)
    _check_id(plan, 'rollover_id', rollover_id)
    _check_id(confirmed, 'receipt_id', hash32(confirmed['receipt_id'], 'receipt_id'))
    children, payouts, recipients = confirmed['successors'], receipt['payouts'], plan['recipients']
    if (confirmed['rollover_id'] != rollover_id or plan['parent_bundle_id'] != parent_id
            or confirmed['parent_bundle_id'] != parent_id or confirmed['parent_funding'] != parent['funding']
            or plan['parent_funding'] != parent['funding'] or not len(children) == len(payouts) == len(recipients) == 2
            or plan['children'] != [child['plan'] for child in children]):
        raise ValueError('rollover parent or successor set differs from the pinned plan')

    initial = _transaction(receipt['parent_funding_raw'])
    split = _transaction(receipt['split_raw'])
    previous = _funding(parent, V3_BUNDLE_SCHEMA, V3_PLAN_SCHEMA, initial)
    _verify_holder_witness(split, previous, parent['plan'], openssl)
    split_fee = positive(confirmed['split_fee_sats'], 'split_fee_sats')
    if (len(split.outputs) != 2 or (split.txid, split.wtxid) != (confirmed['txid'], confirmed['wtxid'])
            or parent['plan']['reserve_sats'] - sum(amount for amount, _ in split.outputs) != split_fee
            or split_fee != plan['split_fee_sats']):
        raise ValueError('protected rollover split amount or fee mismatch')

    payout_amounts = []
    for position, (child, paid, terms) in enumerate(zip(children, payouts, recipients, strict=True)):
        child_plan = child['plan']
        claim = digest({'schema': 'proof-grove/protected-successor-claim/v1',
                        'parent_bundle_id': parent_id, 'vout': position, 'recipient': terms})
        if (set(terms) != RECIPIENT_FIELDS or any(child_plan[key] != value for key, value in terms.items())
                or child_plan['claim_commitment'] != claim or child_plan['mint_pubkey'] != parent['plan']['mint_pubkey']
                or child['funding'] != {'txid': split.txid, 'vout': position, 'block': confirmed['block']}):
            raise ValueError('protected successor terms differ from the pinned split output')
        previous = _funding(child, SUCCESSOR_BUNDLE_SCHEMA, SUCCESSOR_PLAN_SCHEMA, split)
        tx = _transaction(paid['raw'])
        amount = positive(child_plan['payout_sats'], 'payout_sats')
        fee = positive(child_plan['fee_sats'], 'fee_sats')
        if ((tx.txid, tx.wtxid, amount, fee) != (paid['txid'], paid['wtxid'], paid['payout_sats'], paid['fee_sats'])
                or tx.outputs != [(amount, _raw(child_plan['payout_script'], 10000))]
                or child_plan['reserve_sats'] - amount != fee or child_plan['change_sats'] != 0):
            raise ValueError('protected successor payout output or fee mismatch')
        _verify_holder_witness(tx, previous, child_plan, openssl)
        payout_amounts.append(amount)

    if children[0]['plan']['holder_pubkey'] == children[1]['plan']['holder_pubkey']:
        raise ValueError('protected rollover requires two independent holder keys')
    return {'schema': 'proof-grove/protected-rollover-offline-signatures/v1', 'parent_bundle_id': parent_id,
            'rollover_id': rollover_id, 'split_txid': split.txid, 'split_fee_sats': split_fee,
            'payout_sats': payout_amounts, 'verified_holder_signatures': 3}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    parser.add_argument('--parent-bundle-id', required=True)
    parser.add_argument('--rollover-id', required=True)
    parser.add_argument('--openssl', default='openssl')
    args = parser.parse_args()
    result = verify(json.loads(read_bounded(args.receipt, 256 * 1024)), args.parent_bundle_id, args.rollover_id,
                    openssl=args.openssl)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
