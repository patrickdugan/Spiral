#!/usr/bin/env python3
"""Generate complete serialized transactions for the patched Core interpreter.
The tests inject known spent outputs; no node, wallet or coins are involved.
"""
from dataclasses import replace
import json
from pathlib import Path
import sys

base = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(base / 'verifiers'), str(base)]
import reference as K
import stark_trace as A
from weight import serialize_stripped, witness_bytes

vectors = []
def add(name, tx, script, control, witness, expected=True, disable=False):
    stripped = serialize_stripped(tx)
    raw = stripped[:4] + b'\x00\x01' + stripped[4:-4] + witness_bytes(witness, script, control) + stripped[-4:]
    vectors.append({'name':name, 'tx_hex':raw.hex(),
                    'spent_value':tx.inputs[0].value,
                    'spent_script':tx.inputs[0].spent_script.hex(),
                    'expected':expected, 'disable_txcommit':disable})

for recipient in (0,1):
    add(f'merkle_recipient_{recipient}', *K.fixture(recipient))
    add(f'air_recipient_{recipient}', *A.fixture(3+recipient*2,recipient))

tx, sc, ctrl, wit = A.fixture()
for name, bad_tx in [
    ('payout_amount', replace(tx, outputs=(replace(tx.outputs[0],value=948399),tx.outputs[1]))),
    ('payout_script', replace(tx, outputs=(replace(tx.outputs[0],script=b'\x51\x20'+bytes(32)),tx.outputs[1]))),
    ('trace_commitment', replace(tx, outputs=(tx.outputs[0],K.Output(0,b'\x6a\x20'+bytes(32))))),
    ('extra_output', replace(tx, outputs=tx.outputs+(K.Output(0,b'\x6a'),))),
    ('spent_amount', replace(tx, inputs=(replace(tx.inputs[0],value=tx.inputs[0].value+1),))),
    ('outpoint', replace(tx, inputs=(replace(tx.inputs[0],txid=K.H(b'other outpoint')),))),
    ('sequence', replace(tx, inputs=(replace(tx.inputs[0],sequence=0xffffffff),))),
    ('version', replace(tx,version=3)),
    ('locktime', replace(tx,locktime=42)),
]:
    add(name, bad_tx, sc, ctrl, wit, False)
for name, index, value in [('false_air_step',7,b'\x08'),('wrong_sibling',3,bytes(32)),('nonminimal_if',4,b'\x02'),('oversize_item',0,bytes(521))]:
    bad_wit = list(wit)
    bad_wit[index] = value
    add(name,tx,sc,ctrl,bad_wit,False)
add('wrong_control',tx,sc,b'\xc0'+bytes(32),wit,False)
add('old_key_semantics_do_not_bind_outputs',replace(tx,outputs=(K.Output(948400,b'\x51\x20'+bytes(32)),tx.outputs[1])),sc,ctrl,wit,True,True)

def simple(script, witness_fn, name, expected):
    tx = K.Tx((K.Input(K.H(b'core signature mode fixture'),0,100000,K.p2mr(script,K.DUMMY)),),
              (K.Output(99000,b'\x51\x20'+K.PUBKEYS[0]),))
    add(name,tx,script,b'\xc0'+K.tapleaf(K.DUMMY),witness_fn(tx,script),expected)

def digest(tx, script, **kw):
    return K.sighash(tx,0,leaf=K.tapleaf(script),**kw)
key = K.push(K.TXCOMMIT_KEY)
simple(key+b'\xac',lambda t,s:[digest(t,s)],'checksig_valid',True)
simple(key+b'\xac\x91',lambda t,s:[bytes(32)],'bad_digest_cannot_be_inverted_by_not',False)
simple(key+b'\xac\x91',lambda t,s:[b''],'empty_digest_retains_false_then_not',True)
simple(key+b'\xad\x51',lambda t,s:[digest(t,s)],'checksigverify_valid',True)
simple(key+b'\xad\x51',lambda t,s:[b''],'checksigverify_empty_rejects',False)
simple(key+b'\xba\x52\x87',lambda t,s:[digest(t,s),b'\x01'],'checksigadd_valid',True)
simple(key+b'\xba\x52\x87',lambda t,s:[bytes(32),b'\x01'],'checksigadd_invalid_aborts',False)
simple(key+b'\xba\x51\x87',lambda t,s:[b'',b'\x01'],'checksigadd_empty_retains_n',True)
simple(key+b'\xac',lambda t,s:[digest(t,s)[:-1]],'31_byte_digest_rejects',False)
simple(key+b'\xac',lambda t,s:[digest(t,s)+b'\x00'],'33_byte_digest_rejects',False)
simple(b'\xab'+key+b'\xac',lambda t,s:[digest(t,s,codesep=0)],'codeseparator_bound',True)
simple(b'\xab'+key+b'\xac',lambda t,s:[digest(t,s)],'wrong_codeseparator_rejects',False)
simple(b'\x7e\x75\x51',lambda t,s:[bytes(260),bytes(260)],'cat_520_bytes',True)
simple(b'\x7e\x75\x51',lambda t,s:[bytes(261),bytes(260)],'cat_521_bytes_rejects',False)
simple(K.push(b'\x02'+bytes(32))+b'\xac',lambda t,s:[b'\x01'],'other_unknown_key_unchanged',True)

out = Path(sys.argv[1])
out.write_text(json.dumps(vectors,indent=2)+'\n')
print(f'Generated {len(vectors)} complete Bitcoin transaction vectors: {out}')
