"""Pure Python reference for the proposed 12-byte sibling descriptor.

This is a symbolic rule, NOT Bitcoin script execution.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class Outpoint:
    txid: bytes
    vout: int

    def __post_init__(self):
        if len(self.txid) != 32 or not 0 <= self.vout <= 0xFFFFFFFF:
            raise ValueError("invalid outpoint")


def descriptor(own_vout: int, peer_input: int, peer_vout: int) -> bytes:
    return struct.pack("<III", own_vout, peer_input, peer_vout)


def sibling_verify(inputs: tuple[Outpoint, ...], current_input: int, raw: bytes) -> bool:
    if len(raw) != 12 or not 0 <= current_input < len(inputs):
        return False
    own_vout, peer_input, peer_vout = struct.unpack("<III", raw)
    if peer_input == current_input or peer_input >= len(inputs):
        return False
    if own_vout == peer_vout:
        return False
    own, peer = inputs[current_input], inputs[peer_input]
    return own.vout == own_vout and peer.vout == peer_vout and own.txid == peer.txid
