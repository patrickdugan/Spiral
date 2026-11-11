"""Exact Bitcoin transaction serialization-weight tally for the toy AIR spend.

Uses the research P2MR and Script bytes from stark_trace.py; does not
execute Bitcoin Core or model economic/standardness policy.
"""
import json
import struct
from stark_trace import fixture
from reference import compact_size

def serialize_stripped(tx):
    result=bytearray(struct.pack("<i",tx.version))
    result+=compact_size(len(tx.inputs))
    for item in tx.inputs:
        result+=item.outpoint()
        result+=b"\x00"              # empty scriptSig
        result+=struct.pack("<I",item.sequence)
    result+=compact_size(len(tx.outputs))
    result+=b"".join(o.serialize() for o in tx.outputs)
    result+=struct.pack("<I",tx.locktime)
    return bytes(result)

def witness_bytes(wit, script, control):
    items=wit+[script,control]
    return (compact_size(len(items)) +
            b"".join(compact_size(len(x))+x for x in items))

def weight(tx, wit, script, control):
    stripped=serialize_stripped(tx)
    witness=witness_bytes(wit,script,control)
    # SegWit marker + flag are included in witness serialization.
    return {"stripped_bytes":len(stripped),
            "witness_bytes":len(witness)+2,
            "script_bytes":len(script),
            "control_bytes":len(control),
            "weight_units":4*len(stripped)+2+len(witness),
            "virtual_bytes":(4*len(stripped)+2+len(witness)+3)//4,
            "witness_items":len(wit)+2}

if __name__=="__main__":
    tx,script,control,witness=fixture()
    print(json.dumps(weight(tx,witness,script,control),indent=2))
