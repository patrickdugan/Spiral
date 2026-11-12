#!/usr/bin/env python3
"""Replay real Circle-STARK stages with Script-computed transaction effects.

The verifier's state result becomes an actual OP_RETURN output. Script checks
one of two recipient openings and reconstructs TapSighash from those outputs.
Stages remain independent: cross-stage state authorization is not implemented.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

MAX_BLOCK_WEIGHT = 4_000_000
RECIPIENTS = (bytes.fromhex('79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'),
              bytes.fromhex('c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5'))
TXCOMMIT = b'\x02' + hashlib.sha256(b'BIPSpace/Keyless-CHECKSIG/TXCOMMIT-draft').digest()
OP_SUCCESS = {80, 98, *range(126, 130), *range(131, 135), *range(137, 139),
              *range(141, 143), *range(149, 154), *range(187, 255)}


def h(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def tagged(tag: str, value: bytes) -> bytes:
    prefix = h(tag.encode('ascii'))
    return h(prefix + prefix + value)


def compact(n: int) -> bytes:
    if not 0 <= n < 2**64:
        raise ValueError('CompactSize out of range')
    if n < 253:
        return bytes([n])
    if n <= 0xffff:
        return b'\xfd' + struct.pack('<H', n)
    if n <= 0xffffffff:
        return b'\xfe' + struct.pack('<I', n)
    return b'\xff' + struct.pack('<Q', n)


def push(value: bytes) -> bytes:
    """MINIMALDATA-compatible push, including canonical numeric bytes."""
    if not value:
        return b'\x00'
    if len(value) == 1 and 1 <= value[0] <= 16:
        return bytes([0x50 + value[0]])
    if value == b'\x81':
        return b'\x4f'
    if len(value) <= 75:
        return bytes([len(value)]) + value
    if len(value) <= 255:
        return b'\x4c' + bytes([len(value)]) + value
    if len(value) <= 520:
        return b'\x4d' + struct.pack('<H', len(value)) + value
    raise ValueError('Expected output exceeds a Script stack element')


def scan(script: bytes) -> list[int]:
    """Decode pushes before testing opcode bytes; never scan pushed data."""
    pos, codes = 0, []
    while pos < len(script):
        code = script[pos]
        pos += 1
        codes.append(code)
        length = 0
        if 1 <= code <= 75:
            length = code
        elif code in (76, 77, 78):
            size = {76: 1, 77: 2, 78: 4}[code]
            if pos + size > len(script):
                raise ValueError('Truncated PUSHDATA length')
            length = int.from_bytes(script[pos:pos + size], 'little')
            pos += size
        if pos + length > len(script):
            raise ValueError('Truncated push payload')
        pos += length
    return codes


def tapleaf(script: bytes) -> bytes:
    return tagged('TapLeaf', b'\xc0' + compact(len(script)) + script)


def out(value: int, script: bytes) -> bytes:
    return struct.pack('<Q', value) + compact(len(script)) + script


def fixture(stage: int, script: bytes, stack: list[bytes], state: bytes, recipient: int = 0) -> dict:
    """Synthetic serialized one-input transaction. No funds are broadcast."""
    leaf = tapleaf(script)
    sibling = tapleaf(b'\x6a')
    root = tagged('TapBranch', min(leaf, sibling) + max(leaf, sibling))
    spk = b'\x52\x20' + root
    control = b'\xc0' + sibling
    prevout = h(b'Circle-Core/research-only' + struct.pack('<I', stage)) + bytes(4)
    sequence = struct.pack('<I', 0xfffffffd)
    header = struct.pack('<i', 2)
    locktime = bytes(4)
    outputs = out(948400, b'\x51\x20' + RECIPIENTS[recipient]) + out(0, b'\x6a\x20' + state)
    spent_value = 949400
    message = (b'\x00\x00' + header + locktime + h(prevout)
               + h(struct.pack('<Q', spent_value)) + h(compact(len(spk)) + spk)
               + h(sequence) + h(outputs) + b'\x02' + bytes(4)
               + leaf + b'\x02' + b'\xff' * 4)
    assert len(message) == 212
    # The outputs-hash slot is omitted. Script computes it from its results.
    prefix, suffix = message[:138], message[170:]
    proof_stack = stack + [RECIPIENTS[recipient], h(RECIPIENTS[1-recipient]),
                           b'' if recipient == 0 else b'\x01', prefix, suffix]
    items = proof_stack + [script, control]
    witness = compact(len(items)) + b''.join(compact(len(i)) + i for i in items)
    ins = b'\x01' + prevout + b'\x00' + sequence
    outs = b'\x02' + outputs
    raw = header + b'\x00\x01' + ins + outs + witness + locktime
    base_bytes = len(header + ins + outs + locktime)
    weight = 4 * base_bytes + 2 + len(witness)
    value_offset = len(header + b'\x00\x01' + ins + b'\x01')
    mutated = bytearray(raw)
    mutated[value_offset] ^= 1
    return {'name': f'circle-stage-{stage:03}-recipient-{recipient}', 'tx_hex': raw.hex(),
            'spent_value': spent_value, 'spent_script': spk.hex(), 'expected': True,
            'output_mutation_hex': bytes(mutated).hex(), 'weight': weight,
            'witness_stack_items': len(proof_stack),
            'max_witness_item_bytes': max(len(i) for i in proof_stack)}


def convert(records: list[dict]) -> tuple[list[dict], dict]:
    if not records or [r['stage'] for r in records] != list(range(len(records))):
        raise ValueError('Stages must be nonempty, contiguous and sorted from zero')
    vectors, measurements = [], []
    for record in records:
        if record.get('format') != 'circle-stage-v1':
            raise ValueError('Unsupported or missing exporter format')
        program = bytes.fromhex(record['script_hex'])
        codes = scan(program)
        forbidden = sorted(set(codes) & (OP_SUCCESS - {126}))
        if forbidden:
            raise ValueError(f"Stage {record['stage']} uses unsupported OP_SUCCESS: {forbidden}")
        if set(codes) & {171, 172, 173, 174, 175, 186}:
            raise ValueError('Unexpected code separator or signature opcode in proof stage')
        stack = [bytes.fromhex(v) for v in record['hint_hex'] + record['input_hex']]
        expected = [bytes.fromhex(v) for v in record['expected_output_hex']]
        if len(expected) != 1 or len(expected[0]) != 32:
            raise ValueError('Each stage must produce one 32-byte state commitment')
        # Protect policy/context fields beneath the stage's temporary altstack.
        # Expected state bytes are used ONLY to construct fixtures, never embedded
        # in the verifier script. The output-state hash comes from execution.
        script = (b'\x6b' * 5 + program
                  + b'\x82' + push(b'\x20') + b'\x88'
                  + b'\x6c' * 3
                  + bytes([107,107,118,168,108,108,99,124,104,126,168])
                  + push(h(h(RECIPIENTS[0]) + h(RECIPIENTS[1]))) + b'\x88'
                  + push(b'\x51\x20') + b'\x7c\x7e'
                  + push(struct.pack('<Q',948400)+b'\x22') + b'\x7c\x7e'
                  + b'\x7c' + push(bytes(8)+b'\x22\x6a\x20') + b'\x7c\x7e'
                  + b'\x7e\xa8'
                  + b'\x6c\x7c\x7e\x6c\x7e'
                  + push(h(b'TapSighash')*2) + b'\x7c\x7e\xa8'
                  + push(TXCOMMIT) + b'\xad\x51')
        good = fixture(record['stage'], script, stack, expected[0])
        alternate = fixture(record['stage'], script, stack, expected[0], 1)
        initial_resource_ok = good['witness_stack_items'] <= 1000 and good['max_witness_item_bytes'] <= 520
        good['expected'] = alternate['expected'] = initial_resource_ok
        bad = dict(good, name=good['name'] + '-changed-amount',
                   tx_hex=good['output_mutation_hex'], expected=False)
        # Preserve the context preimage while changing the actual state output.
        raw = bytearray.fromhex(good['tx_hex'])
        state_offset = 4+2+1+36+1+4+1+43+8+1+2
        raw[state_offset] ^= 1
        bad_state = dict(good, name=good['name']+'-changed-state',
                         tx_hex=bytes(raw).hex(), expected=False)
        vectors.extend([good, alternate, bad, bad_state])
        if initial_resource_ok:
            vectors.append(dict(bad, name=good['name'] + '-old-key-type-control',
                                disable_txcommit=True, expected=True))
        measurements.append({'stage': record['stage'], 'compiled_script_bytes': len(program),
                             'replay_script_bytes': len(script), 'weight_units': good['weight'],
                             'initial_resource_ok': initial_resource_ok,
                             'witness_stack_items': good['witness_stack_items'],
                             'max_witness_item_bytes': good['max_witness_item_bytes'],
                             'program_sha256': h(program).hex()})
    for vector in vectors:
        vector.pop('output_mutation_hex', None)
    report = {'format': 'circle-core-effects-v1', 'stages': measurements,
              'stage_count': len(records), 'vector_count': len(vectors),
              'sum_compiled_script_bytes': sum(m['compiled_script_bytes'] for m in measurements),
              'sum_independent_transaction_weight': sum(m['weight_units'] for m in measurements),
              'block_weight_limit': MAX_BLOCK_WEIGHT,
              'all_initial_stacks_fit': all(m['initial_resource_ok'] for m in measurements),
              'composed_verifier': False, 'payout_relation_proved': False,
              'scope': 'Independent real-proof stage replays: Script computes the output-state commitment and enforces a two-recipient policy, then reconstructs and checks TapSighash. Cross-stage state inputs and full L1 settlement are not enforced.'}
    return vectors, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage_directory', type=Path)
    ap.add_argument('output_vectors', type=Path)
    ap.add_argument('output_report', type=Path)
    args = ap.parse_args()
    records = [json.loads(p.read_text()) for p in sorted(args.stage_directory.glob('stage-*.json'))]
    vectors, report = convert(records)
    args.output_vectors.write_text(json.dumps(vectors, indent=2) + '\n')
    args.output_report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
