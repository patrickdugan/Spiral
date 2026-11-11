"""Compiler for a 4-row transparent AIR trace checked in research Tapscript.

This is an executable complete-trace proof, NOT a scalable STARK or FRI proof.
It compiles a simple F_17 transition and SHA-256 trace commitment into
Script and composes the result with the TXCOMMIT mode from reference.py.
Because it opens EVERY row, it is pedagogical feasibility work only.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import sys
import struct

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import reference as K

# Standard Bitcoin opcode bytes, plus BIP347 OP_CAT (not activated).
DROP, PICK, ROLL, ADD, SUB = 0x75, 0x79, 0x7a, 0x93, 0x94
NUMEQUALVERIFY, GE, WITHIN, VERIFY = 0x9d, 0xa2, 0xa5, 0x69

def small(n):
    K.need(0 <= n <= 16, "small")
    return bytes([0x50+n]) if n else b"\x00"

def pushnum(n):
    if n <= 16: return small(n)
    K.need(16 < n < 128, "script_num")
    return K.push(bytes([n]))

def trace_bytes(rows):
    K.need(len(rows)==4 and all(type(v) is int and 1 <= v < 17 for v in rows), "trace_range")
    return bytes(rows)

def prove_trace(start: int):
    # No witness makes a truncated trace sufficient. All four steps are opened.
    rows=[start]
    for _ in range(3):
        rows.append((rows[-1]+2)%17)
    trace_bytes(rows) # reject zero and out-of-domain Script-number encodings
    return tuple(rows)

def compile_air(amount=948400):
    """Witness: prefix suffix receiver sibling direction v0 v1 v2 v3."""
    p=[]
    def emit(x): p.append(x if isinstance(x,bytes) else bytes([x]))
    # Ensure every field element has a single canonical nonzero byte encoding.
    for idx in (3,2,1,0):
        emit(small(idx));emit(PICK);emit(small(1));emit(pushnum(17))
        emit(WITHIN);emit(VERIFY)
    # Three field transitions: v[i+1] == (v[i]+2) mod 17.
    # OP_MUL and OP_MOD are disabled, so only addition and a bounded reduction.
    for idx in (3,2,1):
        emit(small(idx));emit(PICK);emit(small(2));emit(ADD)
        emit(K.DUP);emit(pushnum(17));emit(GE);emit(K.IF)
        emit(pushnum(17));emit(SUB);emit(K.ENDIF)
        emit(small(idx));emit(PICK);emit(NUMEQUALVERIFY)
    # Duplicate four original 1-byte rows without altering them.
    for _ in range(4):
        emit(small(3));emit(PICK)
    emit(K.CAT);emit(K.CAT);emit(K.CAT);emit(K.SHA256)
    emit(K.TOALT)
    for _ in range(4): emit(DROP)
    emit(K.FROMALT)
    # Rotate root below receiver,sibling,direction.
    for _ in range(3):
        emit(small(3));emit(ROLL)
    # SHA256 two-key allowlist membership, with a keyed recipient chosen at spend.
    emit(bytes([K.TOALT,K.TOALT,K.DUP,K.SHA256,
                K.FROMALT,K.FROMALT,K.IF,K.SWAP,K.ENDIF,
                K.CAT,K.SHA256]))
    emit(K.push(K.allowlist_root()));emit(K.EQUALVERIFY)
    # Reorder prefix, suffix, root into alt stack, keeping recipient.
    emit(small(3));emit(ROLL);emit(K.TOALT)
    emit(K.ROT);emit(K.TOALT)
    emit(K.SWAP);emit(K.TOALT)
    # Output 0 is a dynamic P2TR recipient with policy-fixed sats.
    emit(K.push(b"\x51\x20"));emit(K.SWAP);emit(K.CAT)
    emit(K.push(struct.pack("<Q",amount)+b"\x22"));emit(K.SWAP);emit(K.CAT)
    # Output 1 reveals the trace SHA256 as OP_RETURN data.
    emit(K.FROMALT)
    emit(K.push(bytes(8)+b"\x22\x6a\x20"))
    emit(K.SWAP);emit(K.CAT)
    emit(K.CAT);emit(K.SHA256)
    emit(bytes([K.FROMALT,K.FROMALT,K.ROT,K.ROT,K.CAT,K.CAT]))
    tag=K.H(b"TapSighash")
    emit(K.push(tag+tag));emit(K.SWAP);emit(K.CAT);emit(K.SHA256)
    emit(K.push(K.TXCOMMIT_KEY));emit(K.CHECKSIGVERIFY);emit(K.TRUE)
    return b"".join(p)

def fixture(start=3, recipient=0, amount=948400):
    rows=prove_trace(start)
    script=compile_air(amount)
    inp=K.Input(K.H(b"newly funded transparent AIR reserve"),0,
                amount+1000,K.p2mr(script,K.DUMMY))
    out0=K.Output(amount,b"\x51\x20"+K.PUBKEYS[recipient])
    out1=K.Output(0,b"\x6a\x20"+K.H(trace_bytes(rows)))
    tx=K.Tx((inp,),(out0,out1))
    msg=K.sigmsg(tx,0,leaf=K.tapleaf(script))
    K.need(len(msg)==212,"msg_size")
    witness=[msg[:138],msg[170:],K.PUBKEYS[recipient],
             K.H(K.PUBKEYS[1-recipient]),b"" if recipient==0 else b"\x01"]
    witness.extend(bytes([v]) for v in rows)
    control=b"\xc0"+K.tapleaf(K.DUMMY)
    return tx,script,control,witness

def num(raw):
    K.need(len(raw) <= 4,"numeric_size")
    if not raw: return 0
    K.need(raw[-1]&0x7f or len(raw)==1,"number_format")
    n=int.from_bytes(raw,"little")
    if raw[-1]&0x80: n=-(n & ~(0x80 << ((len(raw)-1)*8)))
    return n

def vnum(v):
    K.need(-2147483647 <= v <= 2147483647,"numeric_overflow")
    if v==0: return b""
    b=bytearray(abs(v).to_bytes((abs(v).bit_length()+7)//8,"little"))
    if b[-1]&0x80: b+=b"\x80" if v < 0 else b"\x00"
    elif v < 0: b[-1] |= 0x80
    return bytes(b)

def run(tx,script,control,witness,*,upgraded=True,cat_active=True):
    """Limited Script VM with only the selected opcodes; not Bitcoin Core."""
    K.need(tx.inputs[0].spent_script==K.p2mr(script,K.DUMMY),"funding_commitment")
    K.need(control==b"\xc0"+K.tapleaf(K.DUMMY),"control")
    stack=list(witness);alt=[];conds=[True]
    wit=stack+[script,control]
    cost=50+len(K.compact_size(len(wit)))+sum(
        len(K.compact_size(len(v)))+len(v) for v in wit)
    def pop():
        K.need(bool(stack),"stack_empty")
        return stack.pop()
    def push(v):
        K.need(len(v) <= 520,"element_limit")
        stack.append(v)
    for code,data in K.ops(script):
        if code==K.IF:
            if all(conds):
                f=pop()
                K.need(f in (b"",b"\x01"),"minimalif")
                conds.append(f==b"\x01")
            else: conds.append(False)
            continue
        if code==K.ENDIF:
            K.need(len(conds)>1,"endif")
            conds.pop();continue
        if not all(conds): continue
        if data is not None: push(data)
        elif 0x51 <= code <= 0x60: push(vnum(code-0x50))
        elif code==0: push(b"")
        elif code==K.TOALT: alt.append(pop())
        elif code==K.FROMALT:
            K.need(bool(alt),"alt_empty")
            push(alt.pop())
        elif code==K.DUP:
            v=pop();push(v);push(v)
        elif code==K.ROT:
            K.need(len(stack)>=3,"rot")
            stack[-3:]=stack[-2:]+stack[-3:-2]
        elif code==K.SWAP:
            K.need(len(stack)>=2,"swap")
            stack[-2:]=stack[-2:][::-1]
        elif code in (PICK,ROLL):
            i=num(pop())
            K.need(0 <= i < len(stack),"pick_roll_index")
            v=stack[-i-1] if code==PICK else stack.pop(-i-1)
            push(v)
        elif code==K.CAT:
            K.need(cat_active,"cat_unactivated")
            b,a=pop(),pop();push(a+b)
        elif code==K.SHA256: push(K.H(pop()))
        elif code==K.EQUALVERIFY:
            K.need(pop()==pop(),"merkle_membership")
        elif code==NUMEQUALVERIFY:
            K.need(num(pop())==num(pop()),"air_transition")
        elif code in (ADD,SUB,GE,WITHIN):
            if code==WITHIN:
                top=num(pop());bottom=num(pop());a=num(pop())
                push(vnum(int(bottom<=a<top)))
            else:
                b=num(pop());a=num(pop())
                push(vnum(a+b if code==ADD else a-b if code==SUB else int(a>=b)))
        elif code==VERIFY:
            K.need(num(pop()) != 0,"air_bounds")
        elif code==DROP: pop()
        elif code==K.CHECKSIGVERIFY:
            key,candidate=pop(),pop()
            K.need(candidate!=b"","empty_digest")
            cost -= 50
            K.need(cost>=0,"sigops_budget")
            if upgraded and key==K.TXCOMMIT_KEY:
                K.need(len(candidate)==32,"digest_size")
                K.need(candidate==K.sighash(tx,0,leaf=K.tapleaf(script)),
                       "txcommit_mismatch")
            else: K.need(len(key) not in (0,32),"unknown_pubkey_type")
        elif code==K.TRUE: push(b"\x01")
        else: raise K.Reject("unsupported_"+hex(code))
        K.need(len(stack)+len(alt)<=1000,"stack_budget")
        K.need(all(len(x)<=520 for x in stack+alt),"element_budget")
    K.need(len(conds)==1,"conditional_unclosed")
    K.need(stack==[b"\x01"] and not alt,"cleanstack")
    return True

if __name__=="__main__":
    for start,recipient in ((3,0),(5,1)):
        tx,script,control,wit=fixture(start,recipient)
        print({"scheme":"full-trace AIR (NOT STARK)","rows":list(prove_trace(start)),
               "script_bytes":len(script),"witness_items":len(wit),
               "valid":run(tx,script,control,wit)})
