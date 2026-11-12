"""Experimental OP_MULADDMOD semantics; no Bitcoin consensus implementation.

Unsigned little-endian residues use the minimal byte width of the modulus.
The draft charges 50 units to the existing BIP342 per-input validation budget.
That proposed charge needs native implementation and adversarial benchmarks.
"""
from __future__ import annotations

MAX_WIDTH = 32
DRAFT_COST = 50


class ScriptError(ValueError):
    """The proposed operation fails script validation."""


def _decode(a: bytes, b: bytes, c: bytes, modulus: bytes) -> tuple[int, int, int, int, int]:
    if any(type(x) is not bytes for x in (a, b, c, modulus)):
        raise ScriptError("stack operands must be byte strings")
    width = len(modulus)
    if not 1 <= width <= MAX_WIDTH:
        raise ScriptError("modulus must occupy 1..32 bytes")
    if modulus[-1] == 0:
        raise ScriptError("modulus is not minimally encoded")
    m = int.from_bytes(modulus, "little")
    if m < 2:
        raise ScriptError("modulus must be at least two")
    if any(len(x) != width for x in (a, b, c)):
        raise ScriptError("residue width differs from modulus width")
    values = tuple(int.from_bytes(x, "little") for x in (a, b, c))
    if any(x >= m for x in values):
        raise ScriptError("noncanonical residue")
    return width, m, values[0], values[1], values[2]


def muladdmod(a: bytes, b: bytes, c: bytes, modulus: bytes) -> bytes:
    """Concise mathematical oracle using Python's arbitrary-precision integers."""
    width, m, av, bv, cv = _decode(a, b, c, modulus)
    return ((av * bv + cv) % m).to_bytes(width, "little")


def muladdmod_bytewise(a: bytes, b: bytes, c: bytes, modulus: bytes) -> bytes:
    """Independent arithmetic path: byte products and binary long reduction.

    Uses no large-integer multiplication, remainder or division for computation.
    The shared decoder validates encodings. Runtime is bounded by a width of 32
    bytes, with a 64-byte product and a 33-byte reduction remainder.
    """
    width, _, _, _, _ = _decode(a, b, c, modulus)
    product = [0] * (2 * width)
    for i in range(width):
        for j in range(width):
            product[i + j] += a[i] * b[j]
        product[i] += c[i]
    for i in range(2 * width - 1):
        product[i + 1] += product[i] >> 8
        product[i] &= 255
    if product[-1] > 255:
        raise AssertionError("512-bit intermediate bound violated")

    remainder = [0] * (width + 1)
    divisor = list(modulus) + [0]
    for digit in reversed(product):
        for bit in range(7, -1, -1):
            carry = (digit >> bit) & 1
            for i in range(width + 1):
                value = (remainder[i] << 1) | carry
                remainder[i] = value & 255
                carry = value >> 8
            assert carry == 0
            if tuple(reversed(remainder)) >= tuple(reversed(divisor)):
                borrow = 0
                for i in range(width + 1):
                    value = remainder[i] - divisor[i] - borrow
                    remainder[i] = value & 255
                    borrow = int(value < 0)
                assert borrow == 0
    assert remainder[-1] == 0
    return bytes(remainder[:-1])


def execute(stack: list[bytes], budget: int, *, bytewise: bool = False) -> int:
    """Consume a,b,c,m and push r. Return remaining shared validation budget.

    Failure is atomic in this model. This routine does not implement Taproot,
    transaction validation, witness serialization or the other Script opcodes.
    """
    if type(budget) is not int or budget < 0:
        raise ScriptError("invalid validation budget")
    if len(stack) < 4:
        raise ScriptError("stack underflow")
    _decode(*stack[-4:])
    if budget < DRAFT_COST:
        raise ScriptError("validation budget exhausted")
    result = (muladdmod_bytewise if bytewise else muladdmod)(*stack[-4:])
    stack[-4:] = [result]
    return budget - DRAFT_COST


def encode_residue(value: int, modulus: int) -> bytes:
    """Helper for construction of model inputs, not part of opcode semantics."""
    if not 2 <= modulus < 1 << 256 or not 0 <= value < modulus:
        raise ValueError("invalid modulus or residue")
    return value.to_bytes((modulus.bit_length() + 7) // 8, "little")


def encode_modulus(modulus: int) -> bytes:
    if not 2 <= modulus < 1 << 256:
        raise ValueError("invalid modulus")
    return modulus.to_bytes((modulus.bit_length() + 7) // 8, "little")
