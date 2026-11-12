"""Witness serialization and conservative resource bounds; no script VM."""
from muladdmod import DRAFT_COST


def compact_size(n: int) -> bytes:
    if type(n) is not int or not 0 <= n < 2**64:
        raise ValueError('CompactSize range')
    if n < 253:
        return bytes([n])
    for marker, width in ((253, 2), (254, 4), (255, 8)):
        if n < 1 << (8 * width):
            return bytes([marker]) + n.to_bytes(width, 'little')
    raise AssertionError('unreachable')


def witness_size(items: tuple[bytes, ...]) -> int:
    if any(type(x) is not bytes for x in items):
        raise ValueError('witness byte strings required')
    return len(compact_size(len(items))) + sum(len(compact_size(len(x))) + len(x) for x in items)


def initial_budget(items: tuple[bytes, ...]) -> int:
    """Supply the whole witness, including script, control block and any annex."""
    return 50 + witness_size(items)


def call_ceiling(weight: int, spending_inputs: int = 1) -> int:
    """Conservative ceiling for 50-unit arithmetic + charged signature calls.

    Weight >= sum(witness_bytes) + 164 * spending_inputs. Input bonuses add
    only 50 * spending_inputs, leaving >=114 units of overhead per input.
    Other transaction/block bytes make the actual ceiling smaller.
    """
    if type(weight) is not int or type(spending_inputs) is not int:
        raise ValueError('integer inputs required')
    if spending_inputs < 1 or weight < 164 * spending_inputs:
        raise ValueError('insufficient weight for input count')
    return max(0, (weight - 114 * spending_inputs) // DRAFT_COST)
