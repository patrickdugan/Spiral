"""The nova-bitvm3 M16 statement: guest A's 1,164-byte chain record plus the 128-byte PAY1
payment record. A byte-for-byte mirror of kan-payment-gate's `statement.rs`; the desk
cross-checks the two whenever the gate binary is available.

    magic "NHC1"|"NHT4" | u32 k | u32 steps | z0 (17 x 32) | zn (17 x 32) | sha256(Nova key)
    | proofs digest | "PAY1" | u32 segments | u32 height_B | hash_B | u32 confirmations
    | txid | u32 vout | u64 value | u32 script length | sha256(script)

Integers are little-endian; hashes and the txid are in internal byte order. A chain state is
17 Pallas scalars: element 0 is the height, elements 1 and 2 hold the low 16 bytes of each half
of the block hash, element 3 is the cumulative chainwork.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .btc import sha256
from .errors import Refusal

STATE_BYTES = 17 * 32
CHAIN_BYTES = 12 + 2 * STATE_BYTES + 64
PAYMENT_BYTES = 128
STATEMENT_BYTES = CHAIN_BYTES + PAYMENT_BYTES

GENESIS_HASH = {
    "mainnet": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
    "testnet4": "00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043",
}
MAGIC = {"mainnet": b"NHC1", "testnet4": b"NHT4"}


@dataclass(frozen=True)
class ChainPoint:
    height: int
    hash_display: str
    chainwork: int


@dataclass(frozen=True)
class Payment:
    segments: int
    block_height: int
    block_hash_display: str
    confirmations: int
    txid_internal: bytes
    vout: int
    value_sats: int
    script_len: int
    script_sha256: bytes

    @property
    def txid_display(self) -> str:
        return self.txid_internal[::-1].hex()

    @property
    def outpoint(self) -> str:
        return f"{self.txid_display}:{self.vout}"


@dataclass(frozen=True)
class Statement:
    raw: bytes
    magic: bytes
    k: int
    steps: int
    z0: bytes
    start: ChainPoint
    tip: ChainPoint
    nova_vk_sha256: bytes
    proofs_sha256: bytes
    payment: Payment

    @property
    def sha256(self) -> str:
        return sha256(self.raw).hex()


def _u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def _point(state: bytes, which: str) -> ChainPoint:
    elem = [state[32 * i : 32 * i + 32] for i in range(4)]
    if any(elem[0][4:]) or any(elem[1][16:]) or any(elem[2][16:]):
        raise Refusal("statement_state_encoding", which)
    internal = elem[1][:16] + elem[2][:16]
    return ChainPoint(_u32(elem[0], 0), internal[::-1].hex(), int.from_bytes(elem[3], "little"))


def parse(raw: bytes) -> Statement:
    if len(raw) == CHAIN_BYTES:
        raise Refusal("no_payment_record", "1,164-byte chain statement")
    if len(raw) != STATEMENT_BYTES:
        raise Refusal("statement_length", f"{len(raw)} bytes, expected {STATEMENT_BYTES}")
    z0 = raw[12 : 12 + STATE_BYTES]
    zn = raw[12 + STATE_BYTES : 12 + 2 * STATE_BYTES]
    tail = raw[12 + 2 * STATE_BYTES : CHAIN_BYTES]
    pay = raw[CHAIN_BYTES:]
    if pay[:4] != b"PAY1":
        raise Refusal("payment_record_magic", pay[:4].hex())
    payment = Payment(
        segments=_u32(pay, 4),
        block_height=_u32(pay, 8),
        block_hash_display=pay[12:44][::-1].hex(),
        confirmations=_u32(pay, 44),
        txid_internal=pay[48:80],
        vout=_u32(pay, 80),
        value_sats=struct.unpack_from("<Q", pay, 84)[0],
        script_len=_u32(pay, 92),
        script_sha256=pay[96:128],
    )
    st = Statement(
        raw=raw,
        magic=raw[:4],
        k=_u32(raw, 4),
        steps=_u32(raw, 8),
        z0=z0,
        start=_point(z0, "z0"),
        tip=_point(zn, "zn"),
        nova_vk_sha256=tail[:32],
        proofs_sha256=tail[32:64],
        payment=payment,
    )
    p = payment
    if p.confirmations == 0 or p.segments == 0 or p.block_height + p.confirmations - 1 != st.tip.height:
        raise Refusal(
            "statement_inconsistent",
            f"block {p.block_height} with {p.confirmations} confirmations under tip {st.tip.height}",
        )
    return st
