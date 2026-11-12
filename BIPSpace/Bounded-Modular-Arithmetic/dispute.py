"""Authenticated straight-line arithmetic traces, evaluated on the host.

Merkle checks here are Python operations, not Bitcoin Script. The model makes
public-input, encoding and gate challenges explicit; it omits funding,
transaction authorization, challenge search, availability and network timing.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import struct
from muladdmod import encode_modulus, encode_residue, muladdmod


def digest(tag: str, payload: bytes) -> bytes:
    t = sha256(tag.encode('ascii')).digest()
    return sha256(t + t + payload).digest()


def u32(n: int) -> bytes:
    if type(n) is not int or not 0 <= n < 2**32:
        raise ValueError('uint32')
    return struct.pack('<I', n)


@dataclass(frozen=True)
class Instruction:
    a: int
    b: int
    c: int


@dataclass(frozen=True)
class Program:
    modulus: int
    inputs: tuple[int, ...]
    gates: tuple[Instruction, ...]
    expected_output: int

    def __post_init__(self) -> None:
        encode_modulus(self.modulus)
        if not self.inputs or not self.gates:
            raise ValueError('need public inputs and gates')
        u32(self.count)
        encode_residue(self.expected_output, self.modulus)
        for v in self.inputs:
            encode_residue(v, self.modulus)
        for k, g in enumerate(self.gates):
            for index in (g.a, g.b, g.c):
                if type(index) is not int or not 0 <= index < len(self.inputs) + k:
                    raise ValueError('source must precede destination')

    @property
    def count(self) -> int:
        return len(self.inputs) + len(self.gates)

    @property
    def width(self) -> int:
        return len(encode_modulus(self.modulus))

    def context(self, instance: bytes) -> bytes:
        if type(instance) is not bytes or len(instance) != 32:
            raise ValueError('32-byte external instance identifier required')
        # The verifier pins this entire context independently of the claimant.
        body = instance + bytes([self.width]) + encode_modulus(self.modulus)
        body += u32(len(self.inputs)) + u32(len(self.gates))
        body += encode_residue(self.expected_output, self.modulus)
        body += b''.join(encode_residue(v, self.modulus) for v in self.inputs)
        body += b''.join(u32(i) for g in self.gates for i in (g.a, g.b, g.c))
        return digest('BMA/context/v1', body)

    def evaluate(self) -> tuple[bytes, ...]:
        values = [encode_residue(v, self.modulus) for v in self.inputs]
        for g in self.gates:
            values.append(muladdmod(values[g.a], values[g.b], values[g.c],
                                    encode_modulus(self.modulus)))
        return tuple(values)


def canonical(value: bytes, program: Program) -> bool:
    return (type(value) is bytes and len(value) == program.width
            and int.from_bytes(value, 'little') < program.modulus)


def leaf(context: bytes, index: int, value: bytes) -> bytes:
    if type(value) is not bytes or len(value) > 520:
        raise ValueError('model leaf must be at most 520 bytes')
    return digest('BMA/leaf/v1', context + u32(index) + u32(len(value)) + value)


@dataclass(frozen=True)
class Opening:
    index: int
    value: bytes
    siblings: tuple[bytes, ...]


class Trace:
    def __init__(self, program: Program, instance: bytes, values: tuple[bytes, ...]):
        if len(values) != program.count:
            raise ValueError('trace length')
        self.context = program.context(instance)
        self.values = tuple(values)
        size = 1 << (program.count - 1).bit_length()
        nodes = [leaf(self.context, i, v) for i, v in enumerate(values)]
        nodes += [digest('BMA/pad/v1', self.context + u32(i))
                  for i in range(program.count, size)]
        self.levels = [nodes]
        while len(nodes) > 1:
            nodes = [digest('BMA/node/v1', self.context + nodes[i] + nodes[i + 1])
                     for i in range(0, len(nodes), 2)]
            self.levels.append(nodes)
        self.root = nodes[0]

    def open(self, index: int) -> Opening:
        if type(index) is not int or not 0 <= index < len(self.values):
            raise ValueError('trace index')
        j, path = index, []
        for nodes in self.levels[:-1]:
            path.append(nodes[j ^ 1])
            j >>= 1
        return Opening(index, self.values[index], tuple(path))


def membership(program: Program, instance: bytes, root: bytes, proof: Opening) -> bool:
    if type(root) is not bytes or len(root) != 32:
        return False
    if type(proof.index) is not int or not 0 <= proof.index < program.count:
        return False
    if len(proof.siblings) != (program.count - 1).bit_length():
        return False
    try:
        context = program.context(instance)
        h = leaf(context, proof.index, proof.value)
    except (TypeError, ValueError):
        return False
    index = proof.index
    for s in proof.siblings:
        if type(s) is not bytes or len(s) != 32:
            return False
        pair = s + h if index & 1 else h + s
        h = digest('BMA/node/v1', context + pair)
        index >>= 1
    return h == root


def input_fraud(p: Program, instance: bytes, root: bytes, proof: Opening) -> bool:
    return (membership(p, instance, root, proof)
            and proof.index < len(p.inputs)
            and proof.value != encode_residue(p.inputs[proof.index], p.modulus))


def encoding_fraud(p: Program, instance: bytes, root: bytes, proof: Opening) -> bool:
    return membership(p, instance, root, proof) and not canonical(proof.value, p)


def output_fraud(p: Program, instance: bytes, root: bytes, proof: Opening) -> bool:
    return (membership(p, instance, root, proof)
            and proof.index == p.count - 1
            and proof.value != encode_residue(p.expected_output, p.modulus))


def arithmetic_fraud(p: Program, instance: bytes, root: bytes, gate: int,
                     proofs: tuple[Opening, ...]) -> bool:
    if type(gate) is not int or not 0 <= gate < len(p.gates) or len(proofs) != 4:
        return False
    g = p.gates[gate]
    required = (g.a, g.b, g.c, len(p.inputs) + gate)
    for index, proof in zip(required, proofs):
        if proof.index != index or not membership(p, instance, root, proof):
            return False
        if not canonical(proof.value, p):
            return False  # The encoding challenge handles this case.
    a, b, c, d = (proof.value for proof in proofs)
    return muladdmod(a, b, c, encode_modulus(p.modulus)) != d


def gate_openings(p: Program, t: Trace, gate: int) -> tuple[Opening, ...]:
    g = p.gates[gate]
    return tuple(t.open(i) for i in (g.a, g.b, g.c, len(p.inputs) + gate))


def find_fraud(p: Program, instance: bytes, t: Trace) -> tuple[str, int] | None:
    """Exhaustive model checker given all trace bytes; not an availability solver."""
    for i in range(p.count):
        proof = t.open(i)
        if input_fraud(p, instance, t.root, proof):
            return ('input', i)
        if encoding_fraud(p, instance, t.root, proof):
            return ('encoding', i)
    if output_fraud(p, instance, t.root, t.open(p.count - 1)):
        return ('output', p.count - 1)
    for k in range(len(p.gates)):
        if arithmetic_fraud(p, instance, t.root, k, gate_openings(p, t, k)):
            return ('arithmetic', k)
    return None
