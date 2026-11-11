"""P2PROOF semantic model. No cryptographic proof system or Bitcoin integration.

The receipt backend defaults to rejection. Values and spent scripts represent
trusted UTXO-view data. Test profile 0 and witness version 2 are placeholders.
Public-key arithmetic below is for public-data tests, never secret-key handling.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256, new as new_hash
from struct import pack
from typing import Callable, Mapping

MAX_MONEY = 21_000_000 * 100_000_000
ZERO = bytes(32)
PROOF_PREFIX = b"\x52\x20"  # illustrative unallocated witness version
MODEL_PROFILE = 0
MAX_PROOF_BYTES = 4096  # test fixture limits, not deployment parameters
MAX_JOURNAL_BYTES = 4096
MAX_IO = 16
NO_OUTPUT = 0xFFFFFFFF


class Reject(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Reject(reason)


def h(tag: str, data: bytes) -> bytes:
    t = sha256(tag.encode("ascii")).digest()
    return sha256(t + t + data).digest()


def sized(data: bytes) -> bytes:
    return pack("<I", len(data)) + data


def fixed32(data: bytes) -> bytes:
    need(isinstance(data, bytes) and len(data) == 32, "field_length")
    return data


@dataclass(frozen=True)
class Outpoint:
    txid: bytes  # internal byte order
    index: int

    def encode(self) -> bytes:
        need(0 <= self.index <= 0xFFFFFFFF, "outpoint_index")
        return fixed32(self.txid) + pack("<I", self.index)


@dataclass(frozen=True)
class Descriptor:
    program: bytes
    policy: bytes
    origin: bytes
    state: bytes
    profile: int = MODEL_PROFILE

    def encode(self) -> bytes:
        need(self.profile == MODEL_PROFILE, "unsupported_profile")
        return bytes((1, self.profile)) + b"".join(
            fixed32(x) for x in (self.program, self.policy, self.origin, self.state)
        )

    def immutable(self) -> tuple:
        return self.profile, self.program, self.policy, self.origin

    def script(self) -> bytes:
        return PROOF_PREFIX + h("ProvenSpend/descriptor", self.encode())


@dataclass(frozen=True)
class Input:
    prevout: Outpoint
    amount: int
    script: bytes
    sequence: int = 0xFFFFFFFD

    def encode(self) -> bytes:
        need(0 <= self.amount <= MAX_MONEY, "input_amount")
        need(0 <= self.sequence <= 0xFFFFFFFF, "sequence")
        return self.prevout.encode() + pack("<Q", self.amount) + sized(self.script) + pack("<I", self.sequence)


@dataclass(frozen=True)
class Output:
    amount: int
    script: bytes

    def encode(self) -> bytes:
        need(0 <= self.amount <= MAX_MONEY, "output_amount")
        return pack("<Q", self.amount) + sized(self.script)


@dataclass(frozen=True)
class Tx:
    inputs: tuple[Input, ...]
    outputs: tuple[Output, ...]
    version: int = 2
    locktime: int = 0

    def encode(self) -> bytes:
        need(-(1 << 31) <= self.version < (1 << 31), "version")
        need(0 <= self.locktime <= 0xFFFFFFFF, "locktime")
        return (pack("<iI", self.version, self.locktime)
                + pack("<I", len(self.inputs)) + b"".join(x.encode() for x in self.inputs)
                + pack("<I", len(self.outputs)) + b"".join(x.encode() for x in self.outputs))


@dataclass(frozen=True)
class Envelope:
    phase: str
    old: Descriptor | None
    new: Descriptor | None
    output_index: int
    anchor_height: int
    anchor_hash: bytes
    nonce: bytes = ZERO
    journal: bytes = b""
    proof: bytes = b""

    def header(self) -> bytes:
        need(self.phase in ("INIT", "STEP"), "phase")
        need(0 <= self.output_index <= NO_OUTPUT, "output_index")
        need(0 <= self.anchor_height <= NO_OUTPUT, "anchor_height")
        return ((b"\x00" if self.phase == "INIT" else b"\x01")
                + pack("<II", self.output_index, self.anchor_height)
                + fixed32(self.anchor_hash) + fixed32(self.nonce)
                + sized(self.old.encode() if self.old else b"")
                + sized(self.new.encode() if self.new else b"")
                + sized(self.journal))


def origin_id(chain: bytes, seed: Outpoint, index: int, program: bytes,
              policy: bytes, nonce: bytes) -> bytes:
    return h("ProvenSpend/origin", fixed32(chain) + seed.encode() + pack("<I", index)
             + fixed32(program) + fixed32(policy) + fixed32(nonce))


def ordinary_native_witness(script: bytes) -> bool:
    return ((len(script) == 22 and script[:2] == b"\x00\x14")
            or (len(script) == 34 and script[:2] in (b"\x00\x20", b"\x51\x20")))


def message(chain: bytes, tx: Tx, env: Envelope) -> bytes:
    """Economic transaction binding. All witnesses/signatures are excluded."""
    return h("ProvenSpend/context-v1", fixed32(chain) + tx.encode() + env.header())


def precheck(chain: bytes, tx: Tx, env: Envelope, ancestors: Mapping[int, bytes]) -> bytes:
    need(0 < len(tx.inputs) <= MAX_IO and 0 < len(tx.outputs) <= MAX_IO, "io_count")
    need(len({i.prevout for i in tx.inputs}) == len(tx.inputs), "duplicate_input")
    tx.encode()  # range validation before computing totals
    need(sum(i.amount for i in tx.inputs) <= MAX_MONEY, "input_total")
    need(sum(o.amount for o in tx.outputs) <= sum(i.amount for i in tx.inputs), "value_creation")
    need(0 < len(env.proof) <= MAX_PROOF_BYTES, "proof_size")
    need(len(env.journal) <= MAX_JOURNAL_BYTES, "journal_size")
    need(ancestors.get(env.anchor_height) == env.anchor_hash, "noncanonical_anchor")
    env.header()
    ins = [j for j, i in enumerate(tx.inputs) if i.script.startswith(PROOF_PREFIX)]
    outs = [j for j, o in enumerate(tx.outputs) if o.script.startswith(PROOF_PREFIX)]
    if env.phase == "INIT":
        need(not ins and env.old is None and env.new is not None, "init_shape")
        need(len(tx.inputs[0].script) == 34 and tx.inputs[0].script[:2] == b"\x51\x20", "init_carrier")
        d = env.new
        need(d.origin == origin_id(chain, tx.inputs[0].prevout, env.output_index,
                                   d.program, d.policy, env.nonce), "origin_binding")
        need(outs == [env.output_index], "init_output")
    else:
        need(ins == [0] and env.old is not None, "step_shape")
        need(tx.inputs[0].script == env.old.script(), "old_commitment")
        need(env.nonce == ZERO, "step_nonce")
        if env.new is None:
            need(not outs and env.output_index == NO_OUTPUT, "close_shape")
        else:
            need(outs == [env.output_index], "successor_count")
            need(env.new.immutable() == env.old.immutable(), "program_or_origin_changed")
    for j, i in enumerate(tx.inputs):
        if not (env.phase == "STEP" and j == 0):
            need(ordinary_native_witness(i.script), "unsupported_input")
    if env.new is not None:
        need(0 <= env.output_index < len(tx.outputs), "successor_index")
        need(tx.outputs[env.output_index].script == env.new.script(), "new_commitment")
    return message(chain, tx, env)


Verifier = Callable[[bytes, str, bytes, bytes], bool]


def validate(chain: bytes, tx: Tx, env: Envelope, ancestors: Mapping[int, bytes],
             verifier: Verifier | None = None) -> bytes:
    digest = precheck(chain, tx, env, ancestors)
    need(verifier is not None, "no_cryptographic_backend")
    d = env.old if env.old else env.new
    assert d is not None
    need(verifier(d.program, env.phase, digest, env.proof), "receipt_rejected")
    return digest


def validate_block(items: list[tuple[bytes, Tx, Envelope]], ancestors: Mapping[int, bytes],
                   verifier: Verifier, budget: int) -> None:
    """One fixed test cost per receipt, including INIT; precharge the whole block."""
    need(len(items) <= budget, "block_proof_budget")
    for chain, tx, env in items:
        validate(chain, tx, env, ancestors, verifier)


# Public secp256k1 arithmetic for the dynamic P2WPKH target example.
FIELD = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x, y = a
    u, v = b
    if x == u and (y + v) % FIELD == 0:
        return None
    slope = ((3 * x * x) * pow(2 * y, -1, FIELD) if a == b
             else (v - y) * pow(u - x, -1, FIELD)) % FIELD
    q = (slope * slope - x - u) % FIELD
    return q, (slope * (x - q) - y) % FIELD


def mul(k: int, point=G):
    need(0 <= k < ORDER, "scalar")
    result = None
    while k:
        if k & 1:
            result = add(result, point)
        point = add(point, point)
        k >>= 1
    return result


def compressed(point) -> bytes:
    need(point is not None, "infinity")
    return bytes((2 + (point[1] & 1),)) + point[0].to_bytes(32, "big")


def dynamic_target(pubkey: bytes, payment: Outpoint) -> bytes:
    need(len(pubkey) == 33 and pubkey[0] in (2, 3), "pubkey_format")
    x = int.from_bytes(pubkey[1:], "big")
    need(x < FIELD, "pubkey_range")
    y = pow((x * x * x + 7) % FIELD, (FIELD + 1) // 4, FIELD)
    need((y * y - x * x * x - 7) % FIELD == 0, "pubkey_curve")
    if (y & 1) != (pubkey[0] & 1):
        y = FIELD - y
    t = int.from_bytes(h("IOB/payout-key", payment.encode() + pubkey), "big")
    # Matches current Spiral implementation: exceptional hashes are rejected.
    need(0 < t < ORDER, "tweak_range")
    q = compressed(add((x, y), mul(t)))
    return b"\x00\x14" + new_hash("ripemd160", sha256(q).digest()).digest()


def state_root(claims: frozenset[bytes]) -> bytes:
    """Toy sorted-set commitment. Production needs an authenticated accumulator."""
    return h("ProvenSpend/test-state", pack("<I", len(claims)) + b"".join(sorted(fixed32(c) for c in claims)))


@dataclass(frozen=True)
class Menu:
    rate_ppm: int = 1_010_000
    flat_fee: int = 1000
    payout_cap: int = 2_000_000
    miner_fee_cap: int = 2000

    def digest(self) -> bytes:
        return h("ProvenSpend/test-menu", pack("<QQQQ", self.rate_ppm, self.flat_fee,
                                             self.payout_cap, self.miner_fee_cap))


@dataclass(frozen=True)
class AuthenticatedPayment:
    """Ideal authenticated evidence for tests; M16/SPV authentication is absent."""
    prevout: Outpoint
    amount: int
    pubkey: bytes
    origin: bytes
    anchor: bytes

    def nullifier(self) -> bytes:
        return h("ProvenSpend/claim", self.origin + self.prevout.encode())


def iob_relation(tx: Tx, env: Envelope, menu: Menu, claims: frozenset[bytes],
                 payment: AuthenticatedPayment | None = None) -> None:
    """Test application relation, evaluated OFF CHAIN by the ideal test issuer."""
    d = env.old if env.old else env.new
    need(d is not None and d.policy == menu.digest(), "menu_binding")
    if env.phase == "INIT":
        need(env.new is not None and env.new.state == state_root(frozenset()), "initial_state")
        need(not claims and not env.journal, "initial_history")
        return
    need(env.old is not None and env.new is not None and payment is not None, "iob_shape")
    need(len(tx.inputs) == 1 and len(tx.outputs) == 2 and env.output_index == 1, "iob_layout")
    need(payment.origin == env.old.origin, "payment_domain")
    need(payment.anchor == env.anchor_hash, "payment_anchor")
    need(env.old.state == state_root(claims), "history_root")
    n = payment.nullifier()
    need(n not in claims, "already_paid")
    need(env.new.state == state_root(claims | {n}) and env.journal == n, "history_update")
    payout = min(payment.amount * menu.rate_ppm // 1_000_000 - menu.flat_fee, menu.payout_cap)
    need(payout > 0, "payout_nonpositive")
    need(tx.outputs[0] == Output(payout, dynamic_target(payment.pubkey, payment.prevout)), "dynamic_payout")
    fee = sum(x.amount for x in tx.inputs) - sum(x.amount for x in tx.outputs)
    need(0 <= fee <= menu.miner_fee_cap, "fee_cap")
    need(tx.outputs[1].amount > 0, "reserve_exhausted")
