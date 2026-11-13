"""Executable specification for a one-shot BitVM sibling-covenant proposal.

This is a transaction/UTXO model, not Bitcoin Script or a BitVM verifier.
Transactions use Bitcoin's non-witness serialization and the annex-absent
BIP 446 template hash. Script identifiers are symbolic 34-byte commitments;
Taproot, signatures, garbling, setup proofs and fraud proofs are NOT implemented.
The Manifest explicitly records the ideal predicates assumed by this model.

The proposed opcode receives one 12-byte descriptor. Its successful stack
effect is to consume that descriptor without pushing a replacement.

The application profile fixes input slots [principal, control]. Every terminal
output is fixed, including a zero-valued anchor. The parent pays zero fees.
A separate child spends that anchor plus an independently owned fee input.
This model says nothing about node relay, package acceptance or miner inclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import struct
from typing import Literal


UINT32_MAX = 2**32 - 1
MAX_MONEY = 21_000_000 * 100_000_000
Branch = Literal["payout", "recovery"]
Role = Literal["principal", "control", "sponsor", "anchor", "terminal"]


class Rejected(ValueError):
    """An invalid opcode invocation, profile or transaction."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Rejected(reason)


def h(data: bytes) -> bytes:
    return sha256(data).digest()


def hash256(data: bytes) -> bytes:
    return h(h(data))


def compact_size(value: int) -> bytes:
    require(0 <= value < 2**64, "CompactSize range")
    if value < 253:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", value)
    if value <= UINT32_MAX:
        return b"\xfe" + struct.pack("<I", value)
    return b"\xff" + struct.pack("<Q", value)


@dataclass(frozen=True)
class OutPoint:
    # txid contains the 32 bytes placed on the wire, not display-order hex.
    txid: bytes
    n: int

    def __post_init__(self) -> None:
        require(len(self.txid) == 32, "outpoint txid length")
        require(0 <= self.n <= UINT32_MAX, "outpoint output index")

    def serialize(self) -> bytes:
        return self.txid + struct.pack("<I", self.n)


@dataclass(frozen=True)
class TxInput:
    prevout: OutPoint
    sequence: int = 0

    def serialize(self) -> bytes:
        require(0 <= self.sequence <= UINT32_MAX, "sequence range")
        # Native SegWit profile: scriptSig is empty.
        return self.prevout.serialize() + b"\x00" + struct.pack("<I", self.sequence)


@dataclass(frozen=True)
class TxOutput:
    value: int
    script: bytes

    def serialize(self) -> bytes:
        require(0 <= self.value <= MAX_MONEY, "output amount range")
        return struct.pack("<Q", self.value) + compact_size(len(self.script)) + self.script


@dataclass(frozen=True)
class Transaction:
    inputs: tuple[TxInput, ...]
    outputs: tuple[TxOutput, ...]
    version: int = 2
    locktime: int = 0

    def serialize(self) -> bytes:
        require(-(2**31) <= self.version < 2**31, "version range")
        require(0 <= self.locktime <= UINT32_MAX, "locktime range")
        return (
            struct.pack("<i", self.version)
            + compact_size(len(self.inputs))
            + b"".join(item.serialize() for item in self.inputs)
            + compact_size(len(self.outputs))
            + b"".join(item.serialize() for item in self.outputs)
            + struct.pack("<I", self.locktime)
        )

    def txid(self) -> bytes:
        return hash256(self.serialize())


def template_hash(tx: Transaction, input_index: int, annex: bytes | None = None) -> bytes:
    """BIP 446's annex-absent TemplateHash; unsupported annexes fail closed.

    Sequences and serialized CTxOuts receive single SHA256, as in BIP 341.
    The final hash is tagged SHA256, with tag exactly b"TemplateHash".
    Input outpoints and input values are intentionally absent from this hash.
    """
    require(annex is None, "this profile supports no annex")
    require(0 <= input_index < len(tx.inputs), "current input index")
    # Force transaction field-range checks even though prevouts are not hashed.
    tx.serialize()
    payload = (
        struct.pack("<iI", tx.version, tx.locktime)
        + h(b"".join(struct.pack("<I", item.sequence) for item in tx.inputs))
        + h(b"".join(item.serialize() for item in tx.outputs))
        + b"\x00"
        + struct.pack("<I", input_index)
    )
    tag_hash = h(b"TemplateHash")
    return h(tag_hash + tag_hash + payload)


def descriptor(own_parent_vout: int, peer_input_index: int, peer_parent_vout: int) -> bytes:
    require(all(0 <= n <= UINT32_MAX for n in (own_parent_vout, peer_input_index, peer_parent_vout)),
            "descriptor field range")
    return struct.pack("<III", own_parent_vout, peer_input_index, peer_parent_vout)


def check_sibling_verify(stack: list[bytes], tx: Transaction, current_input: int) -> None:
    """Proposed opcode semantics. Only input outpoints are inspected."""
    require(bool(stack), "empty stack")
    operand = stack[-1]
    require(len(operand) == 12, "descriptor must be exactly 12 bytes")
    own_vout, peer_input, peer_vout = struct.unpack("<III", operand)
    require(0 <= current_input < len(tx.inputs), "current input out of bounds")
    require(peer_input < len(tx.inputs), "peer input out of bounds")
    require(peer_input != current_input, "peer equals current input")
    require(own_vout != peer_vout, "equal output roles")
    own = tx.inputs[current_input].prevout
    peer = tx.inputs[peer_input].prevout
    require(own.n == own_vout, "current output role mismatch")
    require(peer.n == peer_vout, "peer output role mismatch")
    require(own.txid == peer.txid, "different funding transactions")
    stack.pop()


@dataclass(frozen=True)
class Manifest:
    graph_id: bytes
    statement_hash: bytes
    setup_id: bytes
    principal_value: int = 1_000_000
    control_value: int = 10_000
    anchor_value: int = 0
    delay: int = 20
    payout_script: bytes = b"operator-reimbursement"
    recovery_script: bytes = b"terminal-safe-recovery"
    bond_return_script: bytes = b"operator-bond-return"
    bond_recovery_script: bytes = b"fixed-bond-recovery"
    keypath_disabled: bool = True
    complete_tree_checked: bool = True
    setup_verified: bool = True
    assert_encoding_valid: bool = True
    claim_is_false: bool = True
    one_shot: bool = True

    def check_admission(self) -> None:
        """Pre-funding audit requirements, NOT new consensus checks."""
        require(all(len(x) == 32 for x in (self.graph_id, self.statement_hash, self.setup_id)),
                "manifest identifier length")
        require(self.keypath_disabled, "a usable key path bypasses the covenant")
        require(self.complete_tree_checked, "hidden or unaudited script leaves")
        require(self.setup_verified, "setup correctness has not been established")
        require(self.assert_encoding_valid, "assert encoding is invalid")
        require(self.one_shot, "model supports one-shot instances only")
        require(1 <= self.delay <= 0xFFFF, "block-based CSV delay range")
        require(self.anchor_value == 0 and self.control_value > 0, "profile requires zero anchor and positive control")
        require(self.principal_value > 0, "invalid principal")
        require(self.principal_value + self.control_value <= MAX_MONEY, "protected amount range")
        require(self.payout_script != self.recovery_script, "terminal branches must differ")

    def terminal_outputs(self, branch: Branch) -> tuple[TxOutput, ...]:
        require(branch in ("payout", "recovery"), "unknown branch")
        if branch == "payout":
            first, second = self.payout_script, self.bond_return_script
        else:
            first, second = self.recovery_script, self.bond_recovery_script
        return (
            TxOutput(self.principal_value, first),
            TxOutput(self.control_value - self.anchor_value, second),
            TxOutput(self.anchor_value, b"anyone-can-spend-anchor"),
        )

    def template(self, branch: Branch, role: Role) -> bytes:
        own_index = 0 if role == "principal" else 1
        dummy = OutPoint(bytes(32), 0)
        sequence = self.delay if branch == "payout" else 0
        skeleton = Transaction(
            (TxInput(dummy, sequence), TxInput(dummy, sequence)),
            self.terminal_outputs(branch),
        )
        return template_hash(skeleton, own_index)

    def symbolic_script(self, role: Role) -> bytes:
        require(role in ("principal", "control"), "unsupported protected role")
        # A commitment-shaped identifier, NOT an actual Taproot output key.
        return b"\x51\x20" + h(
            b"symbolic-sibling-profile-v1\x00" + role.encode() + self.graph_id
            + self.statement_hash + self.setup_id
            + self.template("payout", role) + self.template("recovery", role)
        )


@dataclass(frozen=True)
class FraudEvidence:
    graph_id: bytes
    statement_hash: bytes
    setup_id: bytes
    valid_under_ideal_verifier: bool = True

    def verifies(self, manifest: Manifest) -> bool:
        # Explicit ideal predicate. This provides NO cryptographic implementation.
        return (
            self.valid_under_ideal_verifier
            and manifest.claim_is_false
            and self.graph_id == manifest.graph_id
            and self.statement_hash == manifest.statement_hash
            and self.setup_id == manifest.setup_id
        )


@dataclass(frozen=True)
class Witness:
    branch: Branch
    operand: bytes
    evidence: FraudEvidence | None = None
    operator_signature_valid: bool = False
    keypath: bool = False
    annex: bytes | None = None


@dataclass(frozen=True)
class Coin:
    output: TxOutput
    height: int
    role: Role
    manifest: Manifest | None = None


@dataclass
class Ledger:
    coins: dict[OutPoint, Coin]

    def copy(self) -> "Ledger":
        return Ledger(dict(self.coins))

    def values_and_uniqueness(self, tx: Transaction) -> list[Coin]:
        require(bool(tx.inputs), "no inputs")
        points = [item.prevout for item in tx.inputs]
        require(len(set(points)) == len(points), "duplicate transaction input")
        require(all(point in self.coins for point in points), "missing or spent input")
        coins = [self.coins[point] for point in points]
        tx.serialize()
        require(sum(x.output.value for x in coins) >= sum(x.value for x in tx.outputs), "value inflation")
        require(sum(x.value for x in tx.outputs) <= MAX_MONEY, "output total range")
        return coins

    def validate_pair(self, tx: Transaction, witnesses: tuple[Witness, Witness], height: int) -> int:
        coins = self.values_and_uniqueness(tx)
        require(len(tx.inputs) == 2, "profile requires exactly two protected inputs")
        require(len(witnesses) == 2, "two protected witnesses required")
        require(coins[0].role == "principal" and coins[1].role == "control", "fixed input role layout")
        for i, role in ((0, "principal"), (1, "control")):
            coin, witness = coins[i], witnesses[i]
            manifest = coin.manifest
            require(manifest is not None, "missing manifest")
            manifest.check_admission()
            require(coin.output.script == manifest.symbolic_script(role), "manifest/script mismatch")
            expected_amount = manifest.principal_value if i == 0 else manifest.control_value
            require(coin.output.value == expected_amount, "protected coin denomination mismatch")
            require(not witness.keypath, "key path disabled by the admitted profile")
            require(witness.annex is None, "annex outside profile")
            expected_operand = descriptor(i, 1 - i, 1 - i)
            require(witness.operand == expected_operand, "descriptor differs from script literal")
            stack = [witness.operand]
            check_sibling_verify(stack, tx, i)
            require(not stack, "unexpected opcode stack result")
            require(template_hash(tx, i, witness.annex) == manifest.template(witness.branch, role),
                    "branch template mismatch")
            require(height >= coin.height, "settlement before assertion block")
            if i == 1 and witness.branch == "payout":
                require(tx.version >= 2, "CSV transaction version")
                require(tx.inputs[i].sequence == manifest.delay, "CSV sequence")
                require(height >= coin.height + manifest.delay, "relative timelock not mature")
                require(witness.operator_signature_valid, "invalid ideal operator signature")
            if i == 1 and witness.branch == "recovery":
                require(witness.evidence is not None and witness.evidence.verifies(manifest),
                        "invalid ideal fraud evidence")
        protected = coins[0].output.value + coins[1].output.value
        require(sum(x.value for x in tx.outputs) == protected, "protected value changed")
        return 0

    def apply_pair(self, tx: Transaction, witnesses: tuple[Witness, Witness], height: int) -> bytes:
        self.validate_pair(tx, witnesses, height)
        txid = tx.txid()
        require(all(OutPoint(txid, i) not in self.coins for i in range(len(tx.outputs))), "duplicate outputs")
        for item in tx.inputs:
            del self.coins[item.prevout]
        for i, output in enumerate(tx.outputs):
            role: Role = "anchor" if i == 2 else "terminal"
            self.coins[OutPoint(txid, i)] = Coin(output, height, role)
        return txid

    def apply_anchor_child(self, tx: Transaction, height: int, sponsor_signature_valid: bool = True) -> bytes:
        coins = self.values_and_uniqueness(tx)
        require(len(coins) == 2 and coins[0].role == "anchor" and coins[1].role == "sponsor",
                "child must spend one profile anchor and a fee sponsor")
        require(sponsor_signature_valid, "invalid ideal sponsor signature")
        require(coins[1].height < height, "fee sponsor must already be confirmed in this profile")
        require(height >= coins[0].height, "child before parent")
        txid = tx.txid()
        for item in tx.inputs:
            del self.coins[item.prevout]
        for i, output in enumerate(tx.outputs):
            self.coins[OutPoint(txid, i)] = Coin(output, height, "terminal")
        return txid


@dataclass(frozen=True)
class Instance:
    manifest: Manifest
    assertion: Transaction
    principal: OutPoint
    control: OutPoint
    sponsor: OutPoint

    def evidence(self) -> FraudEvidence:
        m = self.manifest
        return FraudEvidence(m.graph_id, m.statement_hash, m.setup_id)

    def spending(self, branch: Branch, evidence: FraudEvidence | None = None) -> tuple[Transaction, tuple[Witness, Witness]]:
        m = self.manifest
        sequence = m.delay if branch == "payout" else 0
        tx = Transaction(
            (TxInput(self.principal, sequence), TxInput(self.control, sequence)),
            m.terminal_outputs(branch),
        )
        witnesses = (
            Witness(branch, descriptor(0, 1, 1)),
            Witness(branch, descriptor(1, 0, 0),
                    self.evidence() if evidence is None and branch == "recovery" else evidence,
                    operator_signature_valid=branch == "payout"),
        )
        return tx, witnesses


def make_instance(number: int = 0, *, ledger: Ledger | None = None, height: int = 100,
                  claim_is_false: bool = True, manifest: Manifest | None = None) -> tuple[Ledger, Instance]:
    """Admit an assertion under ideal setup/encoding predicates.

    Its funding transaction is outside this model. The assertion consumes a
    distinct synthetic existing outpoint; the resulting txid is calculated from
    the serialized transaction. Callers must not interpret this as verification
    of a complete Bitcoin deposit or bridge protocol.
    """
    ledger = Ledger({}) if ledger is None else ledger
    seed = str(number).encode()
    if manifest is None:
        manifest = Manifest(h(b"graph" + seed), h(b"statement" + seed), h(b"setup" + seed),
                            claim_is_false=claim_is_false)
    manifest.check_admission()
    assertion = Transaction(
        (TxInput(OutPoint(h(b"assert-funding" + seed), 0)),),
        (TxOutput(manifest.principal_value, manifest.symbolic_script("principal")),
         TxOutput(manifest.control_value, manifest.symbolic_script("control"))),
    )
    parent = assertion.txid()
    principal, control = OutPoint(parent, 0), OutPoint(parent, 1)
    sponsor = OutPoint(h(b"fee-funding" + seed), 0)
    require(principal not in ledger.coins and control not in ledger.coins, "instance already exists")
    ledger.coins[principal] = Coin(assertion.outputs[0], height, "principal", manifest)
    ledger.coins[control] = Coin(assertion.outputs[1], height, "control", manifest)
    ledger.coins[sponsor] = Coin(TxOutput(3_000, b"fee-sponsor"), height - 1, "sponsor")
    return ledger, Instance(manifest, assertion, principal, control, sponsor)


def replace_input(tx: Transaction, index: int, prevout: OutPoint) -> Transaction:
    inputs = list(tx.inputs)
    inputs[index] = replace(inputs[index], prevout=prevout)
    return replace(tx, inputs=tuple(inputs))
