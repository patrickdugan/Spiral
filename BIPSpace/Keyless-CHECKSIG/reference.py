"""Experimental Keyless CHECKSIG reference model. NOT Bitcoin Core consensus.

Uses BIP341 transaction hashing, BIP342 unknown-key behavior, proposed CAT,
draft P2MR two-leaf authorization and an UNALLOCATED hash-only CHECKSIG mode.
The executed proof is a SHA256 Merkle membership path, NOT a STARK or ZK proof.
"""
from dataclasses import dataclass
from hashlib import sha256
import struct

TXCOMMIT_KEY = b"\x02" + sha256(b"BIPSpace/Keyless-CHECKSIG/TXCOMMIT-draft").digest()
TXCOMMIT_KEY_VERSION = 2  # unallocated; BIP118 currently proposes 1
MAX_ELEMENT = 520
# Bitcoin Tapscript opcode bytes.
IF, ENDIF, RETURN, TOALT, FROMALT = 0x63, 0x68, 0x6a, 0x6b, 0x6c
DUP, ROT, SWAP, CAT, EQUALVERIFY = 0x76, 0x7b, 0x7c, 0x7e, 0x88
SHA256, CHECKSIGVERIFY, TRUE = 0xa8, 0xad, 0x51
PUBKEYS = (
    bytes.fromhex("79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"),
    bytes.fromhex("c6047f9441ed7d6d3045406e95c07cd85a2d7c5d9b5f862d6bc79f1c1e74d"),
)

class Reject(ValueError):
    pass

def need(test, reason):
    if not test:
        raise Reject(reason)

def H(b):
    return sha256(b).digest()

def th(tag, data):
    t = H(tag.encode("ascii"))
    return H(t + t + data)

def compact_size(n):
    need(0 <= n < 2**64, "compactsize")
    if n < 253: return bytes([n])
    if n <= 0xffff: return b"\xfd" + struct.pack("<H", n)
    if n <= 0xffffffff: return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)

def push(b):
    need(0 < len(b) <= 75, "push_length")
    return bytes([len(b)]) + b

@dataclass(frozen=True)
class Input:
    txid: bytes   # bytes in Bitcoin serialization order
    index: int
    value: int
    spent_script: bytes
    sequence: int = 0xfffffffd
    def outpoint(self):
        need(len(self.txid) == 32 and 0 <= self.index < 2**32, "outpoint")
        return self.txid + struct.pack("<I", self.index)

@dataclass(frozen=True)
class Output:
    value: int
    script: bytes
    def serialize(self):
        need(0 <= self.value <= 21_000_000 * 100_000_000, "output_value")
        return struct.pack("<Q", self.value) + compact_size(len(self.script)) + self.script

@dataclass(frozen=True)
class Tx:
    inputs: tuple
    outputs: tuple
    version: int = 2
    locktime: int = 0

def sigmsg(tx, index, hash_type=0, ext_flag=1, leaf=None,
           key_version=TXCOMMIT_KEY_VERSION, codesep=0xffffffff, annex=None):
    """BIP341 SigMsg prefixed by the 0x00 epoch byte."""
    need(hash_type in (0, 1, 2, 3, 0x81, 0x82, 0x83), "hash_type")
    need(0 <= index < len(tx.inputs), "input_index")
    need(ext_flag in (0, 1), "ext_flag")
    mode, anyone = hash_type & 3, bool(hash_type & 0x80)
    b = bytearray([0, hash_type])
    b += struct.pack("<iI", tx.version, tx.locktime)
    if not anyone:
        b += H(b"".join(i.outpoint() for i in tx.inputs))
        b += H(b"".join(struct.pack("<Q", i.value) for i in tx.inputs))
        b += H(b"".join(compact_size(len(i.spent_script)) + i.spent_script for i in tx.inputs))
        b += H(b"".join(struct.pack("<I", i.sequence) for i in tx.inputs))
    if mode in (0, 1):
        b += H(b"".join(o.serialize() for o in tx.outputs))
    b.append(ext_flag * 2 + (annex is not None))
    if anyone:
        inp = tx.inputs[index]
        b += inp.outpoint() + struct.pack("<Q", inp.value)
        b += compact_size(len(inp.spent_script)) + inp.spent_script
        b += struct.pack("<I", inp.sequence)
    else:
        b += struct.pack("<I", index)
    if annex is not None:
        need(annex.startswith(b"\x50"), "annex")
        b += H(compact_size(len(annex)) + annex)
    if mode == 3:
        need(index < len(tx.outputs), "sighash_single_missing_output")
        b += H(tx.outputs[index].serialize())
    if ext_flag == 1:
        need(leaf is not None and len(leaf) == 32, "leaf_hash")
        need(0 <= key_version <= 255 and 0 <= codesep <= 0xffffffff, "extension")
        b += leaf + bytes([key_version]) + struct.pack("<I", codesep)
    return bytes(b)

def sighash(tx, index, **kw):
    return th("TapSighash", sigmsg(tx, index, **kw))

def tapleaf(script):
    return th("TapLeaf", b"\xc0" + compact_size(len(script)) + script)

def tapbranch(a, b):
    need(len(a) == len(b) == 32, "branch")
    return th("TapBranch", min(a, b) + max(a, b))

def p2mr(script, sibling):
    return b"\x52\x20" + tapbranch(tapleaf(script), tapleaf(sibling))

DUMMY = bytes([RETURN]) + push(b"unspendable KCS sibling")

def allowlist_root():
    return H(H(PUBKEYS[0]) + H(PUBKEYS[1]))

def compiled_script(amount=948400):
    """Merkle-authenticate recipient, rebuild sha_outputs and TapSighash.

    Witness order bottom to top: prefix, suffix, xonly_key, sibling_hash,
    direction. The proof binds one of two recipient keys known at funding.
    The final digest checks against the actual spending transaction.
    """
    tag = H(b"TapSighash")
    return b"".join((
        bytes([TOALT, TOALT, DUP, SHA256, FROMALT, FROMALT, IF, SWAP,
               ENDIF, CAT, SHA256]),
        push(allowlist_root()), bytes([EQUALVERIFY]),
        bytes([ROT, TOALT, SWAP, TOALT]),
        push(b"\x51\x20"), bytes([SWAP, CAT]),
        push(struct.pack("<Q", amount) + b"\x22"),
        bytes([SWAP, CAT, SHA256]),
        bytes([FROMALT, FROMALT, ROT, ROT, CAT, CAT]),
        push(tag + tag), bytes([SWAP, CAT, SHA256]),
        push(TXCOMMIT_KEY), bytes([CHECKSIGVERIFY, TRUE])
    ))

def fixture(recipient=0, prevout=None, amount=948400):
    need(recipient in (0, 1), "recipient_index")
    script = compiled_script(amount)
    funding_script = p2mr(script, DUMMY)
    i = Input(prevout if prevout is not None else H(b"funded reserve"), 0,
              amount + 1000, funding_script)
    tx = Tx((i,), (Output(amount, b"\x51\x20" + PUBKEYS[recipient]),))
    msg = sigmsg(tx, 0, leaf=tapleaf(script))
    need(len(msg) == 212, "message_size")
    # Script independently computes sha_outputs of the one serialized output.
    witness = [msg[:138], msg[170:], PUBKEYS[recipient],
               H(PUBKEYS[1-recipient]), b"" if recipient == 0 else b"\x01"]
    control = b"\xc0" + tapleaf(DUMMY)
    return tx, script, control, witness

def ops(script):
    pos = 0
    while pos < len(script):
        code = script[pos]
        pos += 1
        if 1 <= code <= 75:
            need(pos + code <= len(script), "truncated_push")
            data = script[pos:pos+code]
            pos += code
            yield code, data
        else:
            yield code, None

def execute(tx, script, control, witness, *, upgraded=True, cat_active=True):
    """Deliberately small Script interpreter. It only handles fixture opcodes."""
    need(len(control) == 33 and control[0] == 0xc0, "control")
    need(tx.inputs[0].spent_script == b"\x52\x20" +
         tapbranch(tapleaf(script), control[1:]), "p2mr_commitment")
    stack, alt = list(witness), []
    need(all(len(x) <= MAX_ELEMENT for x in stack), "witness_element")
    witness_items = stack + [script, control]
    witness_size = len(compact_size(len(witness_items))) + sum(
        len(compact_size(len(x))) + len(x) for x in witness_items)
    budget = 50 + witness_size
    conditional = [True]
    def pop():
        need(bool(stack), "underflow")
        return stack.pop()
    for code, data in ops(script):
        if code == IF:
            if all(conditional):
                flag = pop()
                need(flag in (b"", b"\x01"), "minimalif")
                conditional.append(flag == b"\x01")
            else:
                conditional.append(False)
            continue
        if code == ENDIF:
            need(len(conditional) > 1, "endif")
            conditional.pop()
            continue
        if not all(conditional):
            continue
        if data is not None:
            stack.append(data)
        elif code == TOALT: alt.append(pop())
        elif code == FROMALT:
            need(bool(alt), "alt_underflow")
            stack.append(alt.pop())
        elif code == DUP:
            a = pop()
            stack.extend((a, a))
        elif code == ROT:
            need(len(stack) >= 3, "rot")
            stack[-3:] = stack[-2:] + stack[-3:-2]
        elif code == SWAP:
            need(len(stack) >= 2, "swap")
            stack[-2:] = stack[-2:][::-1]
        elif code == CAT:
            need(cat_active, "cat_not_enabled_in_model")
            b, a = pop(), pop()
            need(len(a) + len(b) <= MAX_ELEMENT, "cat_overflow")
            stack.append(a+b)
        elif code == SHA256: stack.append(H(pop()))
        elif code == EQUALVERIFY:
            need(pop() == pop(), "merkle_membership")
        elif code == CHECKSIGVERIFY:
            key, candidate = pop(), pop()
            need(bool(candidate), "empty_sig")
            budget -= 50
            need(budget >= 0, "sigops_budget")
            if upgraded and key == TXCOMMIT_KEY:
                need(len(candidate) == 32, "digest_size")
                actual = sighash(tx, 0, leaf=tapleaf(script))
                need(candidate == actual, "txcommit_mismatch")
            else:
                need(len(key) not in (0, 32), "unsupported_key_type")
        elif code == TRUE: stack.append(b"\x01")
        elif code == RETURN: raise Reject("op_return")
        else: raise Reject("unsupported_opcode_" + hex(code))
        need(len(stack) + len(alt) <= 1000, "stack_limit")
        need(all(len(x) <= MAX_ELEMENT for x in stack+alt), "element_limit")
    need(len(conditional) == 1, "unterminated_if")
    need(stack == [b"\x01"] and not alt, "cleanstack")
    return True

if __name__ == "__main__":
    for recipient in range(2):
        tx, script, control, witness = fixture(recipient)
        print({"recipient":recipient, "script_bytes":len(script),
               "txdigest":sighash(tx,0,leaf=tapleaf(script)).hex(),
               "accepted":execute(tx,script,control,witness)})
