#!/usr/bin/env python3
"""Audit exported proof-stage continuity as host-side evidence.

This checks fixture provenance and byte equality at stage boundaries. It does
not execute Script, prove a claim, or enforce on-chain state succession.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path


def audit(records: list[dict], expected_stages: int = 72,
          expected_program_manifest: str | None = None) -> dict:
    if expected_stages < 1 or len(records) != expected_stages:
        raise ValueError('Incomplete or unexpected stage count')
    if [record['stage'] for record in records] != list(range(expected_stages)):
        raise ValueError('Stage ordering or uniqueness failure')
    program_manifest = hashlib.sha256(b'Circle-stage-program-manifest-v1\x00'
                                     + struct.pack('<I', expected_stages))
    links = 0
    old_output = None
    hints = 0
    inputs = 0
    bytecode_bytes = 0
    for index, record in enumerate(records):
        if record.get('format') != 'circle-stage-v1':
            raise ValueError('Wrong export format')
        code = bytes.fromhex(record['script_hex'])
        stack_in = [bytes.fromhex(v) for v in record['input_hex']]
        stack_out = [bytes.fromhex(v) for v in record['expected_output_hex']]
        if len(stack_out) != 1 or len(stack_out[0]) != 32:
            raise ValueError(f'Stage {index} lacks a single 32-byte output state')
        if index == 0:
            if stack_in:
                raise ValueError('Initial stage unexpectedly consumes a prior state')
        elif stack_in != old_output:
            raise ValueError(f'Unmatched state boundary before stage {index}')
        else:
            links += 1
        old_output = stack_out
        program_manifest.update(struct.pack('<II', index, len(code)))
        program_manifest.update(hashlib.sha256(code).digest())
        for value in record['hint_hex']:
            bytes.fromhex(value)
        hints += len(record['hint_hex'])
        inputs += len(stack_in)
        bytecode_bytes += len(code)
    manifest = program_manifest.hexdigest()
    if expected_program_manifest is not None and manifest != expected_program_manifest:
        raise ValueError('Compiled program manifest differs from the independently supplied pin')
    return {
        'stage_count': expected_stages,
        'matching_boundary_count': links,
        'fixture_continuity_verified': True,
        'program_manifest_sha256': manifest,
        'program_manifest_independently_pinned': expected_program_manifest is not None,
        'hint_stack_items': hints,
        'intermediate_input_items': inputs,
        'compiled_script_bytes': bytecode_bytes,
        'literal_concatenation_initial_items': hints + inputs,
        'initial_stack_limit': 1000,
        'literal_concatenation_fits_initial_stack': hints + inputs <= 1000,
        'terminal_state_commitment': old_output[0].hex(),
        'onchain_stage_continuity_enforced': False,
        'cryptographic_proof_verified_by_this_audit': False,
        'scope': 'Host-side consistency check of exported states. A manifest pin authenticates program order only. Core stage replay and a chained covenant require separate verification.'
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--stages', type=int, default=72)
    parser.add_argument('--program-manifest')
    args = parser.parse_args()
    records = [json.loads(path.read_text()) for path in sorted(args.directory.glob('stage-*.json'))]
    print(json.dumps(audit(records, args.stages, args.program_manifest), indent=2))


if __name__ == '__main__':
    main()
