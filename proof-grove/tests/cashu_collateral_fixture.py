"""Regtest settlement-record disclosure and timeout bond.

The setup signatures fix the transaction graph. Bitcoin checks its signatures,
record opening and CSV windows. M14 and Nova verification run outside Bitcoin.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils

from proofdesk.protected_reserve import _script_number

BOND = 50_000
FEE = 500
CHALLENGE_WINDOW = 144
RESPONSE_WINDOW = 24
OPEN_SEQUENCE = 0xfffffffd
OPENING_CHUNK_BYTES = 80
SECP256K1_ORDER = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141


def sha256(value):
    return hashlib.sha256(value).digest()


def hash256(value):
    return sha256(sha256(value))


def uint32(value):
    return value.to_bytes(4, 'little')


def uint64(value):
    return value.to_bytes(8, 'little')


def sized(raw):
    size = len(raw)
    prefix = bytes([size]) if size < 253 else b'\xfd' + size.to_bytes(2, 'little')
    return prefix + raw


def p2wsh(witness_script):
    return b'\x00\x20' + sha256(witness_script)


def csv(delay):
    return _script_number(delay) + b'\xb2\x75'


def opening_chunks(record):
    return tuple(record[start:start + OPENING_CHUNK_BYTES]
                 for start in range(0, len(record), OPENING_CHUNK_BYTES))


def witnesses(pin, record, public_keys):
    # OP_IF selects challenge/reveal. OP_ELSE selects the corresponding CSV
    # timeout. Each spend has two prior SIGHASH_ALL setup authorizations.
    commitment = b'\x20' + pin + b'\x75'
    quorum = b'\x52' + b''.join(b'\x21' + key for key in public_keys) + b'\x52\xae'
    record_opening = b''.join(b'\x82' + _script_number(len(chunk)) + b'\x88\xa8\x20' + sha256(chunk) + b'\x88'
                              for chunk in opening_chunks(record))
    return (
        commitment + b'\x63\x67' + csv(CHALLENGE_WINDOW) + b'\x68' + quorum,
        commitment + b'\x63' + record_opening + b'\x67' + csv(RESPONSE_WINDOW) + b'\x68' + quorum,
    )


@dataclass(frozen=True)
class Spend:
    body: bytes
    witness_script: bytes
    signatures: tuple

    @property
    def txid(self):
        return hash256(b'\x02\0\0\0' + self.body + b'\0' * 4)[::-1].hex()

    def raw(self, selector, opening=None):
        chunks = reversed(opening_chunks(opening)) if opening is not None else ()
        stack = (b'', *self.signatures, *chunks, selector, self.witness_script)
        return (b'\x02\0\0\0\x00\x01' + self.body + bytes([len(stack)])
                + b''.join(sized(item) for item in stack) + b'\0' * 4).hex()


def authorize(txid, vout, amount, script, sequence, destination, keys):
    outpoint = bytes.fromhex(txid)[::-1] + uint32(vout)
    nsequence = uint32(sequence)
    output = uint64(amount - FEE) + sized(destination)
    version = uint32(2)
    locktime = uint32(0)
    sighash_all = uint32(1)
    message = version + hash256(outpoint) + hash256(nsequence) + outpoint + sized(script)
    message += uint64(amount) + nsequence + hash256(output) + locktime + sighash_all
    sighash = hash256(message)
    method = ec.ECDSA(utils.Prehashed(hashes.SHA256()))
    signatures = []
    for key in keys:
        r, s = utils.decode_dss_signature(key.sign(sighash, method))
        der = utils.encode_dss_signature(r, min(s, SECP256K1_ORDER - s))
        key.public_key().verify(der, sighash, method)
        signatures.append(der + b'\x01')
    body = b'\x01' + outpoint + b'\x00' + nsequence + b'\x01' + output
    return Spend(body, script, tuple(signatures))


def setup(core, rpc, record, expected, operator, challenger):
    # The two setup keys are distinct from the two beneficiary wallets. The
    # fixture signs all four spends before any collateral is broadcast.
    keys = tuple(ec.generate_private_key(ec.SECP256K1()) for _ in range(2))
    public_keys = [key.public_key().public_bytes(serialization.Encoding.X962,
                                                serialization.PublicFormat.CompressedPoint) for key in keys]
    nonce = uuid4().bytes
    record_sha = sha256(record)
    pin = sha256(b'proof-grove/cashu-record-disclosure-bond/v1\0' + nonce + expected + record_sha
                 + b''.join(public_keys) + sized(operator) + sized(challenger)
                 + uint32(CHALLENGE_WINDOW) + uint32(RESPONSE_WINDOW) + uint64(BOND) + uint64(FEE))
    bond_script, challenge_script = witnesses(pin, record, public_keys)
    bond_output = p2wsh(bond_script)
    address = rpc('decodescript', [bond_script.hex()])['segwit']['address']
    unsigned = rpc('walletcreatefundedpsbt', [[], [{address: BOND / 100_000_000}], 0,
                                                {'lockUnspents': True}], wallet=True)
    funding = rpc('walletprocesspsbt', [unsigned['psbt'], True, 'ALL'], wallet=True)
    assert funding['complete']
    tx = core.rpc('decoderawtransaction', [funding['hex']])
    bond = next(output for output in tx['vout'] if output['scriptPubKey']['hex'] == bond_output.hex())
    assert round(bond['value'] * 100_000_000) == BOND
    challenge = authorize(tx['txid'], bond['n'], BOND, bond_script, OPEN_SEQUENCE, p2wsh(challenge_script), keys)
    reclaim = authorize(tx['txid'], bond['n'], BOND, bond_script, CHALLENGE_WINDOW, operator, keys)
    reveal = authorize(challenge.txid, 0, BOND - FEE, challenge_script, OPEN_SEQUENCE, operator, keys)
    slash = authorize(challenge.txid, 0, BOND - FEE, challenge_script, RESPONSE_WINDOW, challenger, keys)
    return {'funding':funding['hex'], 'funding_txid':tx['txid'], 'funding_vout':bond['n'],
            'bond_script':bond_script.hex(), 'challenge_script':challenge_script.hex(),
            'setup_public_keys':[key.hex() for key in public_keys], 'pin':pin.hex(), 'nonce':nonce.hex(),
            'candidates':{'challenge':challenge.raw(b'\x01'), 'reclaim':reclaim.raw(b''),
                          'reveal':reveal.raw(b'\x01', record), 'slash':slash.raw(b'')},
            'txids':{'challenge':challenge.txid, 'reclaim':reclaim.txid, 'reveal':reveal.txid, 'slash':slash.txid},
            'reveal_template':reveal}


def refuse(rpc, raw, *, reason=None):
    checked = rpc('testmempoolaccept', [[raw]])[0]
    assert checked['allowed'] is False, checked
    rejected = checked['reject-reason']
    if reason is not None:
        assert rejected == reason, checked
    return rejected


def confirm(rpc, raw, expected, mining_address, script=None, sats=None):
    assert rpc('sendrawtransaction', [raw]) == expected
    block = rpc('generatetoaddress', [1, mining_address], wallet=True)[0]
    tx = rpc('getrawtransaction', [expected, True, block])
    if script is not None:
        vout, = tx['vout']
        assert vout['scriptPubKey']['hex'] == script.hex() and round(vout['value'] * 100_000_000) == sats
    proof = rpc('gettxoutproof', [[expected], block])
    assert rpc('verifytxoutproof', [proof]) == [expected]
    height = rpc('getblockheader', [block])['height']
    return {'txid':expected, 'block':block, 'height':height, 'sats':sats, 'inclusion':proof}


def exercise(core, rpc, mining_address, record, expected, reserve_outpoint):
    wallets = ('cashu-bond-operator', 'cashu-bond-challenger')
    for wallet in wallets:
        rpc('createwallet', [wallet])
    addresses = [rpc('getnewaddress', [], wallet=wallet) for wallet in wallets]
    for index, wallet in enumerate(wallets):
        assert rpc('getaddressinfo', [addresses[index]], wallet=wallet)['ismine'] is True
        assert rpc('getaddressinfo', [addresses[1-index]], wallet=wallet)['ismine'] is False
    operator, challenger = (bytes.fromhex(core.rpc('validateaddress', [address])['scriptPubKey']) for address in addresses)
    fixtures = {}
    for mode in ('uncontested', 'withheld', 'disclosed'):
        graph = setup(core, rpc, record, expected, operator, challenger)
        template = graph.pop('reveal_template')
        candidates, txids = graph['candidates'], graph['txids']
        before = confirm(rpc, graph['funding'], graph['funding_txid'], mining_address)
        assert (graph['funding_txid'], graph['funding_vout']) != (reserve_outpoint['txid'], reserve_outpoint['vout'])
        early_reclaim = refuse(rpc, candidates['reclaim'], reason='non-BIP68-final')
        graph['funded'] = before
        graph['early_reclaim'] = early_reclaim
        if mode == 'uncontested':
            rpc('generatetoaddress', [CHALLENGE_WINDOW - 1, mining_address], wallet=True)
            result = confirm(rpc, candidates['reclaim'], txids['reclaim'], mining_address, operator, BOND - FEE)
            assert result['height'] == before['height'] + CHALLENGE_WINDOW
            graph.update(paid=result, conflicting_challenge=refuse(rpc, candidates['challenge']))
        else:
            challenge = confirm(rpc, candidates['challenge'], txids['challenge'], mining_address, p2wsh(bytes.fromhex(graph['challenge_script'])), BOND - FEE)
            assert challenge['height'] < before['height'] + CHALLENGE_WINDOW
            graph.update(challenge=challenge, early_slash=refuse(rpc, candidates['slash'], reason='non-BIP68-final'))
            if mode == 'withheld':
                first_block = challenge['block']
                rpc('invalidateblock', [first_block])
                rpc('generateblock', [mining_address, []])
                challenge = confirm(rpc, candidates['challenge'], txids['challenge'], mining_address)
                assert challenge['block'] != first_block and challenge['height'] == graph['challenge']['height'] + 1
                rpc('generatetoaddress', [RESPONSE_WINDOW - 2, mining_address], wallet=True)
                graph['old_deadline_rejected'] = refuse(rpc, candidates['slash'], reason='non-BIP68-final')
                rpc('generatetoaddress', [1, mining_address], wallet=True)
                # A different beneficiary or amount with the old signatures is invalid.
                redirect = candidates['slash'].replace(challenger.hex(), operator.hex(), 1)
                assert redirect != candidates['slash']
                graph['substituted_timeout_beneficiary'] = refuse(rpc, redirect)
                result = confirm(rpc, candidates['slash'], txids['slash'], mining_address, challenger, BOND - 2 * FEE)
                assert result['height'] == challenge['height'] + RESPONSE_WINDOW
                graph.update(reconfirmed_challenge=challenge, paid=result, conflicting_reveal=refuse(rpc, candidates['reveal']))
            else:
                changed = record[:72] + bytes([record[72] ^ 1]) + record[73:]
                graph['wrong_parent_root'] = refuse(rpc, template.raw(b'\x01', changed))
                graph['short_record'] = refuse(rpc, template.raw(b'\x01', record[:-1]))
                first, second, *rest = opening_chunks(record)
                graph['reordered_opening'] = refuse(rpc, template.raw(b'\x01', b''.join((second, first, *rest))))
                result = confirm(rpc, candidates['reveal'], txids['reveal'], mining_address, operator, BOND - 2 * FEE)
                assert result['height'] < challenge['height'] + RESPONSE_WINDOW
                graph.update(paid=result, conflicting_slash=refuse(rpc, candidates['slash']))
        assert core.rpc('gettxout', [reserve_outpoint['txid'], reserve_outpoint['vout'], False]) is None
        fixtures[mode] = graph
    return {'operator_script':operator.hex(), 'challenger_script':challenger.hex(),
            'independent_beneficiary_wallets':True, 'fixtures':fixtures}


def run(core, rpc, mining_address, receipt, certificate, directory, nova, m14):
    root = Path(__file__).resolve().parents[1]
    builder = [sys.executable, str(root/'scripts/protected-fixture-evidence.py')]
    directory.mkdir()
    admission = directory/'holder-receipt.json'
    admission.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    work = directory/'accounting'
    cert = ('--issuance-certificate', str(certificate))
    journal_sha = subprocess.check_output([*builder, 'journal', admission, work, *cert], text=True, timeout=30).strip()
    proof, journal = work/'proof', work/'journal.json'
    with (work/'prover.json').open('w', encoding='utf-8') as stream:
        subprocess.run([nova, 'prove-journal', proof, journal], stdout=stream, check=True, timeout=100)
    independent = work/'independent-verifier.json'
    with independent.open('w', encoding='utf-8') as stream:
        subprocess.run([nova, 'verify-journal', proof, journal, journal_sha], stdout=stream, check=True, timeout=100)
    record_path = work/'settlement.bin'
    subprocess.run([*builder, 'settlement', admission, record_path, independent, *cert], check=True, timeout=30)
    expected = subprocess.check_output([m14, '--digest', record_path], text=True, timeout=30).strip()
    (work/'settlement.blake3').write_text(expected + '\n', encoding='ascii')
    evaluation = subprocess.check_output([m14, record_path, expected], timeout=30)
    (work/'settlement-evaluation.json').write_bytes(evaluation)
    evaluated = json.loads(evaluation)
    assert evaluated['record_source'] == 'pinned-record' and len(evaluated['public_field_mutations_rejected']) == 20
    record = record_path.read_bytes()
    anchor, payout = record[40:72].hex(), receipt['payout']
    assert core.rpc('getblockhash', [payout['height']]) == anchor == payout['block']
    assert rpc('getrawtransaction', [payout['txid'], True, anchor])['txid'] == record[268:300].hex()
    print(json.dumps({'stage':'collateral-statement-verified','m14_non_free_gates':evaluated['non_free_gates']}), flush=True)
    results = exercise(core, rpc, mining_address, record, bytes.fromhex(expected), receipt['reserve'])
    return results | {'schema':'proof-grove/cashu-record-disclosure-bond-regtest/v1', 'network':'regtest',
                      'genesis':record[8:40].hex(), 'settlement_anchor':anchor, 'expected_record_blake3':expected,
                      'record_sha256':sha256(record).hex(), 'parent_root':record[72:104].hex(),
                      'opening_chunk_bytes':[len(chunk) for chunk in opening_chunks(record)],
                      'next_root':record[104:136].hex(), 'holder_claim':record[136:168].hex(),
                      'holder_outpoint':receipt['reserve'], 'holder_payout':payout,
                      'challenge_blocks':CHALLENGE_WINDOW, 'response_blocks':RESPONSE_WINDOW,
                      'bond_sats':BOND, 'per_spend_fee_sats':FEE, 'm14_non_free_gates':evaluated['non_free_gates'],
                      'consensus_scope':'pre-signed destinations, exact record opening and block-based timeout',
                      'offchain_verification':['Nova accounting proof', 'M14 settlement binding circuit']}
