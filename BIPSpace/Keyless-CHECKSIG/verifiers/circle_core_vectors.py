#!/usr/bin/env python3
"""Replay exported real Circle-STARK stages in Core's VerifyScript.

Each fixture checks the expected stage output and an actual TapSighash. Stages
are independent; this is deliberately not a composed proof or payout circuit.
No network consensus flags are changed by this exporter.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

MAX_BLOCK_WEIGHT = 4_000_000
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


def fixture(stage: int, script: bytes, stack: list[bytes]) -> dict:
    """A synthetic, serialized one-input transaction. No funds are broadcast."""
    leaf = tapleaf(script)
    sibling = tapleaf(b'\x6a')
    root = tagged('TapBranch', min(leaf, sibling) + max(leaf, sibling))
    spk = b'\x52\x20' + root
    control = b'\xc0' + sibling
    prevout = h(b'Circle-Core/research-only' + struct.pack('<I', stage)) + bytes(4)
    sequence = struct.pack('<I', 0xfffffffd)
    header = struct.pack('<i', 2)
    locktime = bytes(4)
    recipient = bytes.fromhex('79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798')
    outputs = out(948400, b'\x51\x20' + recipient)
    spent_value = 949400
    message = (b'\x00\x00' + header + locktime + h(prevout)
               + h(struct.pack('<Q', spent_value)) + h(compact(len(spk)) + spk)
               + h(sequence) + h(outputs) + b'\x02' + bytes(4)
               + leaf + b'\x02' + b'\xff' * 4)
    digest = tagged('TapSighash', message)
    items = stack + [digest, script, control]
    witness = compact(len(items)) + b''.join(compact(len(i)) + i for i in items)
    ins = b'\x01' + prevout + b'\x00' + sequence
    outs = b'\x01' + outputs
    raw = header + b'\x00\x01' + ins + outs + witness + locktime
    base_bytes = len(header + ins + outs + locktime)
    weight = 4 * base_bytes + 2 + len(witness)
    value_offset = len(header + b'\x00\x01' + ins + b'\x01')
    mutated = bytearray(raw)
    mutated[value_offset] ^= 1
    return {'name': f'circle-stage-{stage:03}', 'tx_hex': raw.hex(),
            'spent_value': spent_value, 'spent_script': spk.hex(), 'expected': True,
            'output_mutation_hex': bytes(mutated).hex(), 'weight': weight,
            'witness_stack_items': len(stack) + 1,
            'max_witness_item_bytes': max([len(i) for i in stack] + [32])}


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
        script = (b'\x6b' + program
                  + b''.join(push(v) + b'\x88' for v in reversed(expected))
                  + b'\x6c' + push(TXCOMMIT) + b'\xad\x51')
        good = fixture(record['stage'], script, stack)
        initial_resource_ok = good['witness_stack_items'] <= 1000 and good['max_witness_item_bytes'] <= 520
        good['expected'] = initial_resource_ok
        bad = dict(good, name=good['name'] + '-changed-output',
                   tx_hex=good['output_mutation_hex'], expected=False)
        vectors.extend([good, bad])
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
    report = {'format': 'circle-core-replay-v1', 'stages': measurements,
              'stage_count': len(records), 'vector_count': len(vectors),
              'sum_compiled_script_bytes': sum(m['compiled_script_bytes'] for m in measurements),
              'sum_independent_transaction_weight': sum(m['weight_units'] for m in measurements),
              'block_weight_limit': MAX_BLOCK_WEIGHT,
              'all_initial_stacks_fit': all(m['initial_resource_ok'] for m in measurements),
              'composed_verifier': False, 'payout_relation_proved': False,
              'scope': 'Independent real-proof stage replays with fixed expected outputs and witness-supplied transaction digests. No cross-stage consistency or full L1 settlement claim.'}
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
