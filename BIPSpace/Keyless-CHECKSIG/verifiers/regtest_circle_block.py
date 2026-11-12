#!/usr/bin/env python3
"""Mine a state-linked real-proof chain in an isolated research regtest block.

No public peers or external funds. Requires disposable Core v30.0 with
patch_core.py and patch_core_regtest.py applied. Direct block submission
bypasses package relay while retaining block, UTXO and Script validation.
"""
from __future__ import annotations
import argparse
import base64
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from circle_core_vectors import h, compact, out, push, RECIPIENTS
from circle_chain import START_VALUE, FEE, ZERO, compile_transition, serialize, lock, tapleaf, snum
from audit_circle_continuity import audit


def dsha(data: bytes) -> bytes:
    return h(h(data))


@dataclass
class Transaction:
    raw: bytes
    stripped: bytes
    value_offsets: list[int]

    @property
    def txid(self) -> bytes:
        return dsha(self.stripped)

    @property
    def weight(self) -> int:
        return 3*len(self.stripped)+len(self.raw)


def parse_transaction(raw: bytes) -> Transaction:
    pos = 0
    def take(n: int) -> bytes:
        nonlocal pos
        if n < 0 or pos+n > len(raw):
            raise ValueError('Truncated transaction')
        b = raw[pos:pos+n]; pos += n
        return b
    def varint() -> int:
        first = take(1)[0]
        if first < 253:
            return first
        width = {253:2,254:4,255:8}[first]
        value = int.from_bytes(take(width),'little')
        if value < {253:253,254:65536,255:4294967296}[first]:
            raise ValueError('Noncanonical CompactSize')
        return value
    version = take(4)
    witness = raw[pos:pos+2] == b'\x00\x01'
    if witness:
        take(2)
    start = pos
    n_inputs = varint()
    if n_inputs == 0:
        raise ValueError('Zero-input transaction')
    for _ in range(n_inputs):
        take(36); take(varint()); take(4)
    n_outputs = varint()
    offsets = []
    for _ in range(n_outputs):
        offsets.append(pos); take(8); take(varint())
    body = raw[start:pos]
    if witness:
        for _ in range(n_inputs):
            for _ in range(varint()):
                take(varint())
    locktime = take(4)
    if pos != len(raw):
        raise ValueError('Trailing transaction bytes')
    return Transaction(raw,version+body+locktime,offsets)


def one_input(previous: bytes, index: int, outputs: list[bytes], witness: list[bytes],
              script_sig: bytes = b'', sequence: int = 0xfffffffd) -> Transaction:
    raw = (struct.pack('<i',2)+b'\x00\x01\x01'+previous+struct.pack('<I',index)
           +compact(len(script_sig))+script_sig+struct.pack('<I',sequence)
           +compact(len(outputs))+b''.join(outputs)+compact(len(witness))
           +b''.join(compact(len(x))+x for x in witness)+bytes(4))
    return parse_transaction(raw)


def merkle(leaves: list[bytes]) -> bytes:
    if not leaves or any(len(x)!=32 for x in leaves):
        raise ValueError('Merkle input')
    nodes = list(leaves)
    while len(nodes)>1:
        if len(nodes)%2:
            nodes.append(nodes[-1])
        nodes = [dsha(nodes[i]+nodes[i+1]) for i in range(0,len(nodes),2)]
    return nodes[0]


def witness_address(program: bytes) -> str:
    """BIP173 native v0 regtest address for the OP_TRUE test faucet."""
    if len(program)!=32:
        raise ValueError('Expected P2WSH program')
    alphabet='qpzry9x8gf2tvdw0s3jn54khce6mua7l'
    acc=0; bits=0; values=[0]
    for value in program:
        acc=(acc<<8)|value; bits+=8
        while bits>=5:
            bits-=5; values.append((acc>>bits)&31)
    if bits:
        values.append((acc<<(5-bits))&31)
    hrp='bcrt'
    expanded=[ord(c)>>5 for c in hrp]+[0]+[ord(c)&31 for c in hrp]
    chk=1
    for value in expanded+values+[0]*6:
        top=chk>>25; chk=((chk&0x1ffffff)<<5)^value
        for i,generator in enumerate((0x3b6a57b2,0x26508e6d,0x1ea119fa,0x3d4233dd,0x2a1462b3)):
            if (top>>i)&1:
                chk^=generator
    chk^=1
    check=[(chk>>(5*(5-i)))&31 for i in range(6)]
    return hrp+'1'+''.join(alphabet[v] for v in values+check)


def block(txs: list[Transaction], template: dict, faucet_script: bytes,
          fees: int) -> tuple[bytes, dict]:
    reserved=bytes(32)
    witness_root=merkle([bytes(32)]+[dsha(tx.raw) for tx in txs])
    commitment=dsha(witness_root+reserved)
    coinbase=one_input(bytes(32),0xffffffff,
        [out(int(template['coinbasevalue'])+fees,faucet_script),out(0,b'\x6a\x24\xaa\x21\xa9\xed'+commitment)],
        [reserved],push(snum(int(template['height'])))+push(b'KCS'),0xffffffff)
    transactions=[coinbase]+txs
    root=merkle([tx.txid for tx in transactions])
    bits=int(template['bits'],16)
    exponent=bits>>24; coefficient=bits&0x7fffff
    target=coefficient << (8*(exponent-3))
    prefix=(struct.pack('<i',int(template['version']))+bytes.fromhex(template['previousblockhash'])[::-1]
            +root+struct.pack('<II',int(template['curtime']),bits))
    for nonce in range(1_000_000):
        header=prefix+struct.pack('<I',nonce)
        digest=dsha(header)
        if int.from_bytes(digest,'little')<=target:
            break
    else:
        raise RuntimeError('Regtest PoW search exceeded bound')
    payload=header+compact(len(transactions))+b''.join(tx.raw for tx in transactions)
    base=80+len(compact(len(transactions)))+sum(len(tx.stripped) for tx in transactions)
    return payload, {'hash':digest[::-1].hex(),'weight':3*base+len(payload),
                     'size':len(payload),'transactions':len(transactions),
                     'witness_commitment':commitment.hex(),'nonce':nonce}


class Rpc:
    def __init__(self, port: int, cookie: Path):
        self.url=f'http://127.0.0.1:{port}/'
        self.cookie=cookie
    def __call__(self, method: str, *args):
        token=base64.b64encode(self.cookie.read_bytes().strip()).decode('ascii')
        data=json.dumps({'jsonrpc':'1.0','id':'keyless-regtest','method':method,'params':list(args)}).encode()
        request=urllib.request.Request(self.url,data,{'Authorization':'Basic '+token,'Content-Type':'application/json'})
        try:
            response=urllib.request.urlopen(request,timeout=180)
        except urllib.error.HTTPError as error:
            response=error
        body=json.loads(response.read())
        if body.get('error'):
            raise RuntimeError(f'{method}: {body["error"]}')
        return body['result']


def compile_scripts(records: list[dict]) -> list[bytes]:
    scripts=[b'']*len(records)
    for i in reversed(range(len(records))):
        scripts[i]=compile_transition(bytes.fromhex(records[i]['script_hex']),i,
                                      tapleaf(scripts[i+1]) if i+1<len(scripts) else None)
    return scripts


def run(bitcoind: Path, directory: Path, output: Path) -> dict:
    records=[json.loads(p.read_text()) for p in sorted(directory.glob('stage-*.json'))]
    continuity=audit(records)
    scripts=compile_scripts(records)
    output.mkdir(parents=True,exist_ok=True)
    faucet_program=h(b'\x51'); faucet_script=b'\x00\x20'+faucet_program
    address=witness_address(faucet_program)
    with tempfile.TemporaryDirectory(prefix='keyless-regtest-') as datadir:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        rpc=Rpc(port,Path(datadir)/'regtest/.cookie')
        log=(output/'regtest-node.log').open('wb')
        process=subprocess.Popen([str(bitcoind.resolve()),'-regtest=1','-keylessresearch=1',
            '-server=1','-listen=0','-connect=0','-dnsseed=0','-persistmempool=0',
            '-printtoconsole=1','-debug=validation','-datadir='+datadir,
            '-rpcport='+str(port),'-rpcbind=127.0.0.1','-rpcallowip=127.0.0.1'],stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(120):
                if process.poll() is not None:
                    raise RuntimeError('Regtest daemon exited; inspect regtest-node.log')
                try:
                    info=rpc('getblockchaininfo')
                    break
                except (OSError,RuntimeError,ValueError):
                    time.sleep(0.5)
            else:
                raise RuntimeError('Regtest RPC startup failed')
            assert info['chain']=='regtest' and rpc('getconnectioncount')==0
            assert rpc('validateaddress',address)['scriptPubKey']==faucet_script.hex()
            blocks=rpc('generatetoaddress',101,address)
            coinbase=rpc('getblock',blocks[0],2)['tx'][0]
            entry=next(v for v in coinbase['vout'] if v['scriptPubKey']['hex']==faucet_script.hex())
            value=int(Decimal(str(entry['value']))*100_000_000)
            root_script=lock(scripts[0],ZERO)
            funding=one_input(bytes.fromhex(coinbase['txid'])[::-1],entry['n'],
                [out(START_VALUE,root_script),out(value-START_VALUE-1000,faucet_script)],[b'\x51'])
            chain=[]; parent=funding.txid; old_state=ZERO
            for i,record in enumerate(records):
                state=bytes.fromhex(record['expected_output_hex'][0])
                hints=[bytes.fromhex(x) for x in record['hint_hex']+record['input_hex']]
                fixture=serialize(i,scripts[i],old_state,state,hints,parent,
                                  scripts[i+1] if i+1<len(scripts) else None)
                tx=parse_transaction(bytes.fromhex(fixture['tx_hex']))
                assert tx.txid.hex()==fixture['txid_internal']
                chain.append(tx); parent=tx.txid; old_state=state
            txs=[funding]+chain
            template=rpc('getblocktemplate',{'rules':['segwit']})
            assert template['height']==102
            total_fees=1000+len(chain)*FEE
            valid,valid_info=block(txs,template,faucet_script,total_fees)
            assert valid_info['weight']<4_000_000
            # Reduce the last payout by one sat and recompute all Merkle
            # commitments and proof of work. The extra fee remains unclaimed.
            wrong=bytearray(chain[-1].raw)
            offset=chain[-1].value_offsets[0]
            terminal_value=struct.unpack_from('<Q',wrong,offset)[0]
            struct.pack_into('<Q',wrong,offset,terminal_value-1)
            bad_txs=txs[:-1]+[parse_transaction(bytes(wrong))]
            invalid,invalid_info=block(bad_txs,template,faucet_script,total_fees)
            (output/'circle-chain-invalid-block.hex').write_text(invalid.hex()+'\n')
            (output/'circle-chain-valid-block.hex').write_text(valid.hex()+'\n')
            before=rpc('getbestblockhash')
            invalid_result=rpc('submitblock',invalid.hex())
            assert isinstance(invalid_result,str) and 'script' in invalid_result.lower(),invalid_result
            assert rpc('getbestblockhash')==before
            started=time.monotonic()
            valid_result=rpc('submitblock',valid.hex())
            elapsed=time.monotonic()-started
            assert valid_result is None,valid_result
            assert rpc('getbestblockhash')==valid_info['hash']
            accepted=rpc('getblock',valid_info['hash'],1)
            assert accepted['weight']==valid_info['weight'] and len(accepted['tx'])==74
            terminal=rpc('gettxout',chain[-1].txid[::-1].hex(),0,False)
            assert terminal['confirmations']==1
            assert int(Decimal(str(terminal['value']))*100_000_000)==START_VALUE-72*FEE
            assert terminal['scriptPubKey']['hex']==(b'\x51\x20'+RECIPIENTS[0]).hex()
            for spent in [funding]+chain[:-1]:
                assert rpc('gettxout',spent.txid[::-1].hex(),0,False) is None
            report={'format':'keyless-circle-regtest-block-v1','chain':'regtest',
                'block_height':accepted['height'],'block':valid_info,
                'proof_stage_count':len(chain),'linked_transaction_weight':sum(tx.weight for tx in chain),
                'funding_transaction_weight':funding.weight,'terminal_value_sats':START_VALUE-72*FEE,
                'total_fees_sats':total_fees,'valid_block_submit_result':valid_result,
                'invalid_block_rejection':invalid_result,'invalid_block_hash':invalid_info['hash'],
                'terminal_txid':chain[-1].txid[::-1].hex(),'terminal_utxo_confirmations':1,
                'all_intermediate_outputs_spent':True,'connected_peers':rpc('getconnectioncount'),
                'submit_valid_block_seconds':elapsed,'verifier_manifest_sha256':continuity['program_manifest_sha256'],
                'core_revision':'d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3',
                'circle_revision':'9540164f243b23e4ca995c153f70ec64744df28a',
                'activation':'Explicit -keylessresearch=1 on disposable regtest only.',
                'application':'32-row Fibonacci PLONK example with eight query groups.',
                'scope':'Actual Core ConnectBlock, witness commitments, PoW and UTXO changes. No public network, mempool/package-relay test, production soundness estimate, IOB statement or Nova-in-Script.'}
            (output/'regtest-circle-results.json').write_text(json.dumps(report,indent=2)+'\n')
            return report
        finally:
            try:
                rpc('stop')
            except (OSError,RuntimeError,ValueError):
                pass
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
            log.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bitcoind',type=Path)
    parser.add_argument('stages',type=Path)
    parser.add_argument('output_directory',type=Path)
    args=parser.parse_args()
    print(json.dumps(run(args.bitcoind,args.stages,args.output_directory),indent=2))


if __name__=='__main__':
    main()
