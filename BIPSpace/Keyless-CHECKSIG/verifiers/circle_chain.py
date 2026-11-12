"""Research compiler for a keyless, state-linked Circle-STARK transaction chain.

Each transition authenticates its input state through the actual spent P2MR
script hash in TapSighash. It derives the successor P2MR root from its computed
result and a statically committed next program. The terminal stage pays one of
two fixed policy recipients. No signatures are created. No network activation.
"""
from __future__ import annotations
import argparse
import json
import struct
from pathlib import Path
from circle_core_vectors import h, tagged, tapleaf, compact, push, out, scan, OP_SUCCESS, TXCOMMIT, RECIPIENTS

START_VALUE = 10_000_000
FEE = 10_000
ZERO = bytes(32)


def snum(n: int) -> bytes:
    if n == 0:
        return b''
    result = bytearray(abs(n).to_bytes((abs(n).bit_length()+7)//8, 'little'))
    if result[-1] & 0x80:
        result.append(0x80 if n < 0 else 0)
    elif n < 0:
        result[-1] |= 0x80
    return bytes(result)


class Builder:
    """Track post-stage stack labels while emitting ordinary Script opcodes."""
    def __init__(self, stack=()):
        self.stack = list(stack)
        self.code = bytearray()

    def op(self, opcode: int, n: int = 0, result: str | None = None):
        if n > len(self.stack):
            raise ValueError('Compiler stack underflow')
        if n:
            del self.stack[-n:]
        self.code.append(opcode)
        if result is not None:
            self.stack.append(result)

    def const(self, value: bytes, label: str = ''):
        self.code.extend(push(value))
        self.stack.append(label)

    def number(self, n: int, label: str = ''):
        self.const(snum(n), label)

    def pick(self, name: str):
        distance = self.stack[::-1].index(name)
        self.number(distance)
        self.op(0x79, 1, name)

    def cat(self, result=''):
        self.op(0x7e, 2, result)

    def swap(self):
        self.code.append(0x7c)
        self.stack[-2:] = self.stack[-2:][::-1]

    def equal(self):
        self.op(0x88, 2)

    def length(self, name: str, expected: int):
        self.pick(name)
        self.op(0x82, 0, '')
        self.number(expected)
        self.equal()
        self.op(0x75, 1)

    def hash(self, result: str):
        self.op(0xa8, 1, result)

    def tag(self, name: str, result: str):
        self.const(h(name.encode('ascii')) * 2)
        self.swap()
        self.cat()
        self.hash(result)

    def conditional(self, left, right):
        self.stack.pop()
        a, b = Builder(self.stack), Builder(self.stack)
        left(a)
        right(b)
        if a.stack != b.stack:
            raise ValueError(f'Unbalanced compiler branches: {a.stack} != {b.stack}')
        self.code.extend(b'\x63' + a.code + b'\x67' + b.code + b'\x68')
        self.stack = a.stack

    def state_leaf(self, state: str, result: str):
        self.const(b'\xc0\x22\x6a\x20')
        self.pick(state)
        self.cat()
        self.tag('TapLeaf', result)

    def branch_hash(self, result: str):
        # Stack ends [left, right, swap_bit]. OP_IF enforces MINIMALIF.
        self.stack.pop()
        self.code.extend(b'\x63\x7c\x68')
        self.stack[-2:] = ['', '']
        self.cat()
        self.tag('TapBranch', result)


def compare_to_constant(b: Builder, constant: bytes) -> None:
    """Prove new_leaf < constant using its first differing byte.

    Witness fields cmp_pos, cmp_raw, cmp_tail, cmp_num reconstruct the entire
    computed hash. Numeric/byte consistency includes zero and bytes >=128.
    Equal hashes fail closed; this application uses distinct TapLeaf preimages.
    """
    if len(constant) != 32:
        raise ValueError('Expected 32-byte constant')
    b.length('cmp_raw', 1)
    b.pick('cmp_num'); b.number(0); b.number(256); b.op(0xa5, 3, ''); b.op(0x69, 1)
    b.pick('cmp_num'); b.number(128); b.op(0xa2, 2, '')

    def upper(t):
        t.pick('cmp_raw'); t.const(b'\x00'); t.cat(); t.pick('cmp_num'); t.equal()

    def lower(t):
        t.pick('cmp_num'); t.number(0); t.op(0x9c, 2, '')
        def zero(z):
            z.pick('cmp_raw'); z.const(b'\x00'); z.equal()
        def nonzero(z):
            z.pick('cmp_raw'); z.pick('cmp_num'); z.equal()
        t.conditional(zero, nonzero)

    b.conditional(upper, lower)

    def cases(t: Builder, index: int):
        if index == 32:
            t.op(0x6a)
            t.number(0, 'new_less')  # unreachable; balances compiler labels
            return
        t.pick('cmp_pos'); t.number(index); t.op(0x9c, 2, '')
        def chosen(c):
            c.length('cmp_tail', 31-index)
            c.const(constant[:index]); c.pick('cmp_raw'); c.cat()
            c.pick('cmp_tail'); c.cat(); c.pick('new_leaf'); c.equal()
            c.pick('cmp_num'); c.number(constant[index]); c.op(0x9e, 2, ''); c.op(0x69, 1)
            c.pick('cmp_num'); c.number(constant[index]); c.op(0x9f, 2, 'new_less')
        t.conditional(chosen, lambda c: cases(c, index+1))
    cases(b, 0)


def compile_transition(program: bytes, index: int, next_leaf: bytes | None) -> bytes:
    if set(scan(program)) & ((OP_SUCCESS - {126}) | {171, 172, 173, 174, 175, 186}):
        raise ValueError('Unsupported opcode in stage')
    terminal = next_leaf is None
    fields = (['self_leaf', 'old_order', 'recipient', 'prevouts_hash'] if terminal else
              ['self_leaf', 'old_order', 'cmp_pos', 'cmp_raw', 'cmp_tail', 'cmp_num', 'prevouts_hash'])
    # Context is above the stage stack. Preserve it below the stage's temporary
    # altstack. Preserve a copy of the old state before the stage consumes it.
    prologue = b'\x6b' * len(fields)
    if index == 0:
        prologue += push(ZERO) + b'\x6b'
    else:
        prologue += b'\x76\x6b'
    prologue += program + b'\x6c' * (len(fields)+1)
    b = Builder(['new_state', 'old_state'] + fields)
    for name in ('new_state', 'old_state', 'self_leaf', 'prevouts_hash'):
        b.length(name, 32)
    # Current P2MR root binds old state to the actual UTXO. The supplied self
    # leaf hash is also used in SigMsg's extension, authenticating it to Core.
    b.state_leaf('old_state', 'old_leaf')
    b.pick('self_leaf'); b.pick('old_leaf'); b.pick('old_order')
    b.branch_hash('old_root')
    b.const(b'\x22\x52\x20'); b.pick('old_root'); b.cat(); b.hash('spent_scripts_hash')
    value = START_VALUE - (index+1) * FEE
    if value <= 0:
        raise ValueError('Fee schedule exhausts reserve')
    if terminal:
        b.pick('recipient')
        def recipient(which):
            return lambda t: t.const(out(value, b'\x51\x20' + RECIPIENTS[which]), 'serialized_output')
        b.conditional(recipient(1), recipient(0))
        b.hash('outputs_hash')
    else:
        b.state_leaf('new_state', 'new_leaf')
        compare_to_constant(b, next_leaf)
        b.const(next_leaf); b.pick('new_leaf'); b.pick('new_less')
        b.branch_hash('new_root')
        b.const(struct.pack('<Q', value) + b'\x22\x52\x20')
        b.pick('new_root'); b.cat(); b.hash('outputs_hash')
    # Exact DEFAULT message for one fixed-value input and one output.
    b.const(b'\x00\x00' + struct.pack('<iI', 2, 0))
    b.pick('prevouts_hash'); b.cat()
    b.const(h(struct.pack('<Q', START_VALUE-index*FEE))); b.cat()
    b.pick('spent_scripts_hash'); b.cat()
    b.const(h(struct.pack('<I', 0xfffffffd))); b.cat()
    b.pick('outputs_hash'); b.cat()
    b.const(b'\x02' + bytes(4)); b.cat()
    b.pick('self_leaf'); b.cat()
    b.const(b'\x02' + b'\xff'*4); b.cat()
    b.tag('TapSighash', 'digest')
    b.op(0x6b, 1)
    while b.stack:
        b.op(0x75, 1)
    b.op(0x6c, 0, 'digest')
    b.const(TXCOMMIT); b.op(0xad, 2); b.op(0x51, 0, 'success')
    return prologue + b.code


def data_leaf(state: bytes) -> bytes:
    if len(state) != 32:
        raise ValueError('State must be a 32-byte commitment')
    return tapleaf(b'\x6a\x20'+state)


def lock(script: bytes, state: bytes) -> bytes:
    a, b = tapleaf(script), data_leaf(state)
    return b'\x52\x20' + tagged('TapBranch', min(a,b)+max(a,b))


def comparison_hint(value: bytes, constant: bytes) -> list[bytes]:
    if len(value) != 32 or len(constant) != 32 or value == constant:
        raise ValueError('Comparison requires different 32-byte hashes')
    index = next(i for i in range(32) if value[i] != constant[i])
    return [snum(index), value[index:index+1], value[index+1:], snum(value[index])]


def serialize(index: int, script: bytes, old_state: bytes, new_state: bytes,
              stage_stack: list[bytes], previous_txid: bytes,
              next_script: bytes | None, recipient: int = 0,
              *, actual_old_state: bytes | None = None) -> dict:
    actual_old_state = old_state if actual_old_state is None else actual_old_state
    spent_script = lock(script, actual_old_state)
    leaf = tapleaf(script)
    prevout = previous_txid + bytes(4)
    params = [leaf, b'\x01' if leaf > data_leaf(old_state) else b'']
    if next_script is None:
        params += [b'\x01' if recipient else b'']
        output_script = b'\x51\x20' + RECIPIENTS[recipient]
    else:
        params += comparison_hint(data_leaf(new_state), tapleaf(next_script))
        output_script = lock(next_script, new_state)
    params += [h(prevout)]
    control = b'\xc0' + data_leaf(actual_old_state)
    stack = stage_stack + params
    items = stack + [script, control]
    version, locktime, sequence = struct.pack('<i',2), bytes(4), struct.pack('<I',0xfffffffd)
    ins = b'\x01' + prevout + b'\x00' + sequence
    serialized_output = out(START_VALUE-(index+1)*FEE, output_script)
    outputs = b'\x01' + serialized_output
    stripped = version + ins + outputs + locktime
    witness = compact(len(items)) + b''.join(compact(len(x))+x for x in items)
    raw = version + b'\x00\x01' + ins + outputs + witness + locktime
    return {'name': f'circle-chain-stage-{index:03}', 'tx_hex': raw.hex(),
            'spent_value': START_VALUE-index*FEE, 'spent_script': spent_script.hex(),
            'expected': True, 'txid_internal': h(h(stripped)).hex(),
            'previous_txid_internal': previous_txid.hex(), 'output_script': output_script.hex(),
            'weight_units': 4*len(stripped)+len(witness)+2,
            'witness_stack_items': len(stack), 'stack': stack, 'control': control,
            'outputs_serialized': serialized_output,
            'max_witness_item_bytes': max(map(len,stack))}


def message_digest(record: dict, script: bytes) -> bytes:
    prevout = bytes.fromhex(record['previous_txid_internal']) + bytes(4)
    spent_script = bytes.fromhex(record['spent_script'])
    message = (b'\x00\x00' + struct.pack('<iI',2,0) + h(prevout)
               + h(struct.pack('<Q',record['spent_value']))
               + h(compact(len(spent_script))+spent_script)
               + h(struct.pack('<I',0xfffffffd)) + h(record['outputs_serialized'])
               + b'\x02' + bytes(4) + tapleaf(script) + b'\x02' + b'\xff'*4)
    assert len(message) == 212
    return tagged('TapSighash',message)


def binding_controls() -> list[dict]:
    """Small Core controls isolate covenant binding from STARK correctness."""
    middle = h(b'Circle-chain/core-binding-control')
    terminal = compile_transition(b'\xa8', 1, None)
    initial = compile_transition(push(middle), 0, tapleaf(terminal))
    parent = h(b'Circle-chain/core-binding-funding')
    first = serialize(0, initial, ZERO, middle, [], parent, terminal)
    second = serialize(1, terminal, middle, h(middle), [middle],
                       bytes.fromhex(first['txid_internal']), None)
    other = serialize(1, terminal, middle, h(middle), [middle],
                      bytes.fromhex(first['txid_internal']), None, 1)
    wrong = h(b'valid SHA256 computation on an unauthorized old state')
    wrong_old = serialize(1, terminal, wrong, h(wrong), [wrong],
                          bytes.fromhex(first['txid_internal']), None,
                          actual_old_state=middle)
    wrong_next = serialize(0, initial, ZERO, middle, [], parent,
                           compile_transition(b'\xa8', 2, None))
    wrong_new = serialize(0, initial, ZERO, h(b'false output state'), [], parent, terminal)
    cases = [('initial', first, True), ('terminal', second, True),
             ('other-recipient', other, True), ('wrong-old-state-fresh-witness', wrong_old, False),
             ('wrong-next-program', wrong_next, False), ('wrong-computed-state', wrong_new, False)]
    return [dict(record, name='binding-control-'+name, expected=expected)
            for name, record, expected in cases]


def build(records: list[dict]) -> tuple[list[dict], dict]:
    from audit_circle_continuity import audit
    audit_report = audit(records)
    scripts = [b''] * len(records)
    for i in reversed(range(len(records))):
        next_leaf = tapleaf(scripts[i+1]) if i+1 < len(scripts) else None
        scripts[i] = compile_transition(bytes.fromhex(records[i]['script_hex']), i, next_leaf)
    vectors, measurements = [], []
    parent = h(b'Circle-chain/synthetic-funding-outpoint/v1')
    old_state = ZERO
    prior_output_script = lock(scripts[0],old_state)
    for i, record in enumerate(records):
        new_state = bytes.fromhex(record['expected_output_hex'][0])
        stack = [bytes.fromhex(x) for x in record['hint_hex'] + record['input_hex']]
        nxt = scripts[i+1] if i+1 < len(scripts) else None
        good = serialize(i,scripts[i],old_state,new_state,stack,parent,nxt)
        if good['spent_script'] != prior_output_script.hex():
            raise ValueError(f'Linked output script mismatch before stage {i}')
        if good['witness_stack_items'] > 1000 or good['max_witness_item_bytes'] > 520:
            raise ValueError(f'Initial witness exceeds Core limits at stage {i}')
        vectors.append(good)
        amount = bytearray.fromhex(good['tx_hex']); amount[49] ^= 1
        successor = bytearray.fromhex(good['tx_hex']); successor[60] ^= 1
        vectors.append(dict(good,name=good['name']+'-wrong-value',tx_hex=bytes(amount).hex(),expected=False))
        vectors.append(dict(good,name=good['name']+'-wrong-successor',tx_hex=bytes(successor).hex(),expected=False))
        if nxt is None:
            alternate = serialize(i,scripts[i],old_state,new_state,stack,parent,nxt,recipient=1)
            vectors.append(dict(alternate,name=good['name']+'-other-recipient'))
        measurements.append({'stage': i,'contract_script_bytes':len(scripts[i]),
                             'program_bytes':record['script_bytes'],
                             'weight_units':good['weight_units'],
                             'initial_stack_items':good['witness_stack_items'],
                             'txid_internal':good['txid_internal'],
                             'previous_txid_internal':good['previous_txid_internal'],
                             'input_state_commitment':old_state.hex(),
                             'output_state_commitment':new_state.hex(),
                             'script_sha256':h(scripts[i]).hex()})
        parent = bytes.fromhex(good['txid_internal'])
        prior_output_script = bytes.fromhex(good['output_script'])
        old_state = new_state
    real_stage_vectors = len(vectors)
    controls = binding_controls()
    vectors.extend(controls)
    for vector in vectors:
        for key in ('stack','control','outputs_serialized'):
            vector.pop(key,None)
    report = {'format':'circle-keyless-chain-v1','stage_count':len(records),
              'vector_count':len(vectors),'real_stage_vector_count':real_stage_vectors,
              'binding_control_vector_count':len(controls),'root_spent_script':vectors[0]['spent_script'],
              'start_value_sats':START_VALUE,'fee_per_stage_sats':FEE,
              'terminal_value_sats':START_VALUE-len(records)*FEE,
              'sum_transaction_weight':sum(x['weight_units'] for x in measurements),
              'sum_contract_script_bytes':sum(x['contract_script_bytes'] for x in measurements),
              'maximum_initial_stack_items':max(x['initial_stack_items'] for x in measurements),
              'recorded_chain_edges_checked':len(records)-1,
              'program_manifest_sha256':audit_report['program_manifest_sha256'],
              'stages':measurements,
              'core_verified':False,'network_activated':False,'mined_or_broadcast':False,
              'application':'Upstream 32-row Fibonacci PLONK example, 8 query groups; no IOB or Nova verifier inside Script.'}
    return vectors,report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stages',type=Path); p.add_argument('vectors',type=Path); p.add_argument('report',type=Path)
    a=p.parse_args()
    records=[json.loads(f.read_text()) for f in sorted(a.stages.glob('stage-*.json'))]
    vectors,report=build(records)
    a.vectors.write_text(json.dumps(vectors,indent=2)+'\n')
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='stages'},indent=2))


if __name__=='__main__':
    main()
