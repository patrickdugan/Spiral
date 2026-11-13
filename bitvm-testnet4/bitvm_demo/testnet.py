"""Testnet4-only observation, isolated wallet signing, and bounded demo transactions."""
from __future__ import annotations

import base64
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

from .bitcoin import ROOT, TESTNET4_GENESIS, btc, keypath_sighash, verify
from .circuits import Circuit

NOVA_SOURCE = 'fcddd4d773f52953387eed4b55beaab47c84155a'
NOVA_PROOF = '79c4af1113506bba24415d058557bba93583d5177ec074f13ba30f705c85daad'
NOVA_STATEMENT = '06fa3156d86ffb98f0a853cbd350b144f81d1586c6eda7d70c436267f821b007'


class CoreCLI:
    def __init__(self, executable: Path, datadir: Path, port: int | None = None, wallet: str | None = None):
        self.argv = [str(executable), '-testnet4', f'-datadir={datadir}', '-rpcclienttimeout=30']
        if port is not None: self.argv.append(f'-rpcport={port}')
        if wallet is not None: self.argv.append('-rpcwallet=' + wallet)

    def call(self, method: str, *params):
        arguments = [arg if isinstance(arg, str) else json.dumps(arg, separators=(',', ':')) for arg in params]
        result = subprocess.run(self.argv + [method] + arguments, capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise RuntimeError(f'{method}: bitcoin-cli returned exit {result.returncode}; no credentials are included in this error')
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout.strip()

    def verify_testnet4(self, synced: bool = False):
        info = self.call('getblockchaininfo')
        if info.get('chain') != 'testnet4' or self.call('getblockhash', 0) != TESTNET4_GENESIS:
            raise ValueError('RPC endpoint is not genuine Testnet4')
        if synced and info.get('initialblockdownload') is not False:
            raise ValueError('public observer is still synchronizing')
        return info


def endpoints(cli: Path, observer_data: Path, owner_path: Path):
    owner = json.loads(owner_path.read_text(encoding='utf-8-sig'))
    if owner.get('network') != 'testnet4' or owner.get('wallet') != 'bitvm-demo':
        raise ValueError('signer owner record is not the dedicated Testnet4 demo wallet')
    observer = CoreCLI(cli, observer_data)
    signer = CoreCLI(cli, Path(owner['datadir']), int(owner['rpcport']), owner['wallet'])
    observer.verify_testnet4(synced=True)
    signer.verify_testnet4()
    if signer.call('getconnectioncount') != 0:
        raise ValueError('the dedicated signing node must remain offline')
    return observer, signer


def utxos(address: str) -> list:
    base = 'https://mempool.space/testnet4/api'
    def fetch(path):
        request = urllib.request.Request(base + path, headers={'User-Agent': 'BitVM-Testnet4-Demos/1'})
        with urllib.request.urlopen(request, timeout=30) as stream:
            data = stream.read(128 * 1024 + 1)
        if len(data) > 128 * 1024:
            raise ValueError('public API response exceeds the demo bound')
        return data
    if fetch('/block-height/0').decode().strip() != TESTNET4_GENESIS:
        raise ValueError('public API has a different network genesis')
    return json.loads(fetch('/address/' + address + '/utxo'))


def _kv(key: bytes, value: bytes) -> bytes:
    return btc.ser_compact(len(key)) + key + btc.ser_compact(len(value)) + value


def psbt(tx: btc.Tx, value: int, spent_script: bytes) -> str:
    if len(tx.inputs) != 1:
        raise ValueError('funding uses one input')
    coin = value.to_bytes(8, 'little') + btc.ser_compact(len(spent_script)) + spent_script
    data = b'psbt\xff' + _kv(b'\x00', tx.stripped()) + b'\x00' + _kv(b'\x01', coin) + b'\x00' + b'\x00' * len(tx.outputs)
    return base64.b64encode(data).decode()


def signing_check(signer: CoreCLI, setup: dict):
    """Sign a synthetic coin offline; no observation or broadcast of this transaction."""
    info = signer.verify_testnet4()
    if signer.call('getconnectioncount') != 0:
        raise ValueError('signer must be offline')
    if setup.get('network') != 'testnet4' or setup.get('genesis') != TESTNET4_GENESIS:
        raise ValueError('setup belongs to another network')
    script = bytes.fromhex(setup['script_pubkey'])
    owned = signer.call('getaddressinfo', setup['address'])
    if not owned.get('ismine') or owned.get('scriptPubKey') != script.hex() or not script.startswith(b'\x51\x20') or len(script) != 34:
        raise ValueError('setup is not the owned P2TR signing address')
    tx = btc.Tx(2, [btc.TxIn(bytes.fromhex('42' * 32), 0, b'', 0xfffffffd)], [btc.TxOut(98000, script)], 0)
    signed = signer.call('walletprocesspsbt', psbt(tx, 100000, script))
    final = signer.call('finalizepsbt', signed['psbt'])
    if not signed.get('complete') or not final.get('complete'):
        raise ValueError('offline wallet did not complete the synthetic PSBT')
    result = btc.parse_tx(bytes.fromhex(final['hex']))
    if result.stripped() != tx.stripped() or len(result.inputs[0].witness) != 1:
        raise ValueError('wallet changed the transaction or did not use the key path')
    signature = result.inputs[0].witness[0]
    digest = keypath_sighash(tx, 100000, script)
    if not verify(digest, script[2:], signature):
        raise ValueError('independent BIP340 verification rejected the wallet signature')
    tx.outputs[0].value -= 1
    if verify(keypath_sighash(tx, 100000, script), script[2:], signature):
        raise ValueError('wallet signature failed to bind the output amount')
    return {'status': 'passed', 'network': 'testnet4', 'genesis': TESTNET4_GENESIS,
            'signer_height': info['blocks'], 'signer_peers': 0, 'synthetic_prevout': True,
            'broadcast': False, 'sighash': digest.hex(), 'raw': final['hex'],
            'independent_signature_verification': True, 'changed_output_rejected': True}


def nova_anchor(path: Path | None):
    if path is None:
        return None
    receipt = json.loads(path.read_text())
    if receipt.get('status') != 'passed' or len(receipt.get('cases', [])) != 3:
        raise ValueError('Nova/BitVM3 verifier receipt is incomplete')
    if (receipt.get('source') != NOVA_SOURCE or receipt.get('proof_sha256') != NOVA_PROOF or
            receipt.get('statement_sha256') != NOVA_STATEMENT):
        raise ValueError('Nova source, proof or statement does not match the pinned Testnet4 fixture')
    if (len(receipt.get('binary_sha256', '')) != 64 or
            {item['name'] for item in receipt.get('steps', []) if item.get('exit_code') == 0} != {'rustc', 'cargo', 'build', 'run'}):
        raise ValueError('Nova binary identity or successful execution steps are missing')
    cases = {item['case']: item for item in receipt['cases']}
    if set(cases) != {'real-nova-proof', 'tampered-proof-input', 'wrong-statement'}:
        raise ValueError('Nova verifier cases differ')
    if any(item['ciphertexts'] != 785442492 or item['input_bits'] != 8635080 for item in cases.values()):
        raise ValueError('receipt is not the complete M14 verifier')
    if not cases['real-nova-proof']['accepted'] or cases['real-nova-proof']['rejected']:
        raise ValueError('Nova proof was not accepted')
    if any(cases[name]['accepted'] or not cases[name]['rejected'] for name in ['tampered-proof-input', 'wrong-statement']):
        raise ValueError('negative verifier cases did not reject')
    encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()
    return b'BVM3\x01' + hashlib.sha256(encoded).digest()


def make_plan(private: Path, output: Path):
    private, output = private.resolve(), output.resolve()
    if private.is_relative_to(ROOT):
        raise ValueError('private demo keys must be outside the source checkout')
    if private.exists() or output.exists():
        raise ValueError('use fresh private-state and public-plan directories')
    private.mkdir(parents=True)
    output.mkdir(parents=True)
    circuits = [Circuit.create('nand'), Circuit.create('half-adder')]
    for index, circuit in enumerate(circuits):
        circuit.save_private(private / f'circuit-{index}.json')
    result = {'status': 'prepared', 'network': 'testnet4', 'genesis': TESTNET4_GENESIS,
              'contracts': [{'vout': i, 'value_sats': 20000, 'circuit': c.public()} for i, c in enumerate(circuits)],
              'scope': 'Fixed-claim NAND and half-adder fraud-proof primitives on stock Tapscript',
              'funding': 'Use the dedicated wallet funding workflow, not public example private keys'}
    (output / 'plan.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def fund(observer: CoreCLI, signer: CoreCLI, setup: dict, private: Path, output: Path,
         nova_receipt: Path | None = None, broadcast: bool = False):
    observer.verify_testnet4(synced=True)
    signer.verify_testnet4()
    if setup.get('network') != 'testnet4' or setup.get('genesis') != TESTNET4_GENESIS:
        raise ValueError('funding setup is not Testnet4')
    address, source_script = setup['address'], bytes.fromhex(setup['script_pubkey'])
    if not signer.call('getaddressinfo', address).get('ismine'):
        raise ValueError('funding address is not owned by the dedicated wallet')
    candidates = sorted((item for item in utxos(address) if item.get('status', {}).get('confirmed') and
                         60000 <= item.get('value', 0) <= 1_000_000), key=lambda item: item['value'])
    if not candidates:
        return {'status': 'needs_funding', 'address': address, 'required_sats': 100000, 'network': 'testnet4'}
    coin = candidates[0]
    actual = observer.call('gettxout', coin['txid'], coin['vout'])
    if (actual is None or actual['scriptPubKey']['hex'] != source_script.hex() or
            Decimal(str(actual['value'])) * 100_000_000 != coin['value'] or actual['confirmations'] < 1):
        raise ValueError('public API funding record disagrees with the verified node')
    anchor = nova_anchor(nova_receipt)
    if output.exists():
        raise ValueError('use a fresh funding output directory')
    if private.resolve().is_relative_to(ROOT):
        raise ValueError('private demo keys must be outside the source checkout')
    circuits = [Circuit.load_private(private / f'circuit-{index}.json') for index in range(2)]
    output.mkdir(parents=True)
    destination = signer.call('getrawchangeaddress', 'bech32m')
    change = signer.call('getaddressinfo', destination)
    if change.get('ismine') is not True:
        raise ValueError('change address is not owned')
    outputs = [btc.TxOut(20000, circuit.taproot().script_pubkey) for circuit in circuits]
    if anchor is not None: outputs.append(btc.TxOut(0, b'\x6a' + btc.push(anchor)))
    outputs.append(btc.TxOut(coin['value'] - 40000 - 2000, bytes.fromhex(change['scriptPubKey'])))
    tx = btc.Tx(2, [btc.TxIn(bytes.fromhex(coin['txid'])[::-1], coin['vout'], b'', 0xfffffffd)], outputs, 0)
    signed = signer.call('walletprocesspsbt', psbt(tx, coin['value'], source_script))
    final = signer.call('finalizepsbt', signed['psbt'])
    if not signed.get('complete') or not final.get('complete'):
        raise ValueError('dedicated wallet could not sign the funding input')
    raw = final['hex']
    if btc.parse_tx(bytes.fromhex(raw)).stripped() != tx.stripped():
        raise ValueError('signer changed funding outputs')
    admission = observer.call('testmempoolaccept', [raw])[0]
    if admission.get('allowed') is not True:
        raise ValueError('funding transaction was refused by stock Testnet4 relay policy')
    txid = tx.txid()[::-1].hex()
    manifest = {'status': 'signed_not_broadcast', 'network': 'testnet4', 'genesis': TESTNET4_GENESIS,
                'funding_txid': txid, 'raw': raw, 'funding_input': coin, 'fee_sats': 2000,
                'contracts': [{'vout': index, 'value_sats': 20000, 'circuit': circuit.public()} for index, circuit in enumerate(circuits)],
                'nova_anchor': anchor.hex() if anchor else None, 'admission': admission,
                'anchor_scope': 'Receipt commitment only; Bitcoin does not execute the Nova/BitVM3 verifier'}
    (output / 'funding.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if broadcast:
        if observer.call('sendrawtransaction', raw) != txid:
            raise ValueError('broadcast returned a different txid')
        manifest['status'] = 'broadcast'
        (output / 'funding.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def refute(observer: CoreCLI, signer: CoreCLI, funding: dict, private: Path, output: Path,
           broadcast: bool = False):
    observer.verify_testnet4(synced=True)
    signer.verify_testnet4()
    if funding.get('network') != 'testnet4' or funding.get('genesis') != TESTNET4_GENESIS:
        raise ValueError('funding manifest belongs to another network')
    output.mkdir(parents=True, exist_ok=False)
    receipt = {'network': 'testnet4', 'status': 'prepared', 'spends': []}
    for index, item in enumerate(funding['contracts']):
        coin = observer.call('gettxout', funding['funding_txid'], item['vout'])
        if coin is None or coin['confirmations'] < 1:
            raise ValueError('contract is spent or not yet confirmed')
        circuit = Circuit.load_private(private / f'circuit-{index}.json')
        if coin['scriptPubKey']['hex'] != circuit.taproot().script_pubkey.hex() or Decimal(str(coin['value'])) * 100000000 != 20000:
            raise ValueError('contract UTXO differs from private demo state')
        address = signer.call('getnewaddress', 'bitvm-demo-return', 'bech32m')
        info = signer.call('getaddressinfo', address)
        if info.get('ismine') is not True:
            raise ValueError('return address is not owned')
        tx = circuit.spend(funding['funding_txid'], item['vout'], 20000, bytes.fromhex(info['scriptPubKey']), gate=circuit.bad_gates()[0])
        raw = tx.serialize().hex()
        admission = observer.call('testmempoolaccept', [raw])[0]
        if admission.get('allowed') is not True:
            raise ValueError('refutation was refused by the stock Testnet4 node')
        txid = tx.txid()[::-1].hex()
        result = {'kind': circuit.kind, 'gate': circuit.bad_gates()[0], 'raw': raw, 'txid': txid,
                  'return_address': address, 'return_sats': 18000, 'fee_sats': 2000, 'admission': admission, 'broadcast': False}
        receipt['spends'].append(result)
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if broadcast:
            if observer.call('sendrawtransaction', raw) != txid:
                raise ValueError('refutation broadcast returned another txid')
            result['broadcast'] = True
            (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    receipt['status'] = 'broadcast' if broadcast else 'signed_not_broadcast'
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt
