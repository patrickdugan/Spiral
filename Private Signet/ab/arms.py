"""Matched DLC settlement arms on the same oracle, funding value and payouts.

Arm A (vanilla, stock consensus): funding to a Taproot output whose only
spend path is the leaf <A> CHECKSIGVERIFY <B> CHECKSIG behind the BIP341
NUMS internal key. Before funding, each party gives the other a BIP340
adaptor pre-signature on every settlement transaction (CET), encrypted to
the oracle's attestation point for that outcome. The oracle's attestation
scalar s_m decrypts the counterparty's pre-signature for outcome m only.

Arm B (Keyless-CHECKSIG, experimental consensus): funding to a restricted
P2MR (witness v2) output with one leaf per outcome. Each leaf checks
SHA256(s_m) against the oracle's announced commitment, Merkle-authenticates
the recipient against an allowlist root fixed at funding, rebuilds the
single serialized output and the BIP341 message with OP_CAT, and hands the
digest to the TXCOMMIT key in CHECKSIGVERIFY. No party key authorizes the
spend. Requires TXCOMMIT + OP_CAT + P2MR consensus (patched Core,
-keylessresearch, regtest). On stock consensus any witness-v2 spend is valid.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

import secp
from secp import Oracle, adaptor_complete, adaptor_presign, adaptor_verify, pubkey_xonly, seckey
from txlib import (NUMS, Prevout, Tx, TxIn, TxOut, p2mr_control, p2mr_spk, push, ref,
                   sigmsg_scriptpath, sighash_scriptpath, taproot_output)

OUTCOMES = ("ALICE_WINS", "BOB_WINS")
FUNDING_SATS = 1_000_000
SETTLE_FEE_SATS = 2_000
PAYOUT_SATS = FUNDING_SATS - SETTLE_FEE_SATS

OP_CHECKSIG, OP_CHECKSIGVERIFY, OP_SHA256, OP_EQUALVERIFY = 0xAC, 0xAD, 0xA8, 0x88


def p2tr_key_spk(xonly_key: bytes) -> bytes:
    """Payout output: P2TR to a party's untweaked x-only key (key-path only)."""
    return b"\x51\x20" + xonly_key


@dataclass
class Parties:
    alice: int
    bob: int
    carol: int
    mallory: int
    oracle: Oracle

    @classmethod
    def fixture(cls, label: str = "ab-v1") -> "Parties":
        return cls(seckey(f"{label}/alice"), seckey(f"{label}/bob"), seckey(f"{label}/carol"),
                   seckey(f"{label}/mallory"), Oracle(label))

    def x(self, who: str) -> bytes:
        return pubkey_xonly(getattr(self, who))


# --- Arm A --------------------------------------------------------------------

class ArmA:
    name = "A-vanilla-adaptor-DLC"

    def __init__(self, parties: Parties, payees: dict[str, str] | None = None):
        self.p = parties
        self.leaf = (push(parties.x("alice")) + bytes([OP_CHECKSIGVERIFY]) +
                     push(parties.x("bob")) + bytes([OP_CHECKSIG]))
        self.tree = taproot_output(NUMS, [self.leaf])
        self.payees = payees or {"ALICE_WINS": "alice", "BOB_WINS": "bob"}

    @property
    def funding_spk(self) -> bytes:
        return self.tree["spk"]

    def cet(self, funding_txid: str, vout: int, outcome: str, payee: str | None = None,
            amount: int = PAYOUT_SATS, **tx_fields) -> Tx:
        who = payee or self.payees[outcome]
        return Tx((TxIn(funding_txid, vout, tx_fields.pop("sequence", 0xFFFFFFFD)),),
                  (TxOut(amount, p2tr_key_spk(self.p.x(who))),), **tx_fields)

    def presign_all(self, funding_txid: str, vout: int, payees: dict[str, str] | None = None) -> dict:
        """Both parties' adaptor pre-signatures for every CET (setup phase)."""
        prev = [Prevout(FUNDING_SATS, self.funding_spk)]
        out = {}
        for m in OUTCOMES:
            tx = self.cet(funding_txid, vout, m, (payees or self.payees)[m])
            msg = sighash_scriptpath(tx, 0, prev, self.leaf)
            T = self.p.oracle.attestation_point(m)
            pre = {who: adaptor_presign(getattr(self.p, who), msg, T, f"{m}/{who}")
                   for who in ("alice", "bob")}
            for who, ps in pre.items():
                if not adaptor_verify(self.p.x(who), msg, T, ps):
                    raise AssertionError("counterparty pre-signature does not verify")
            out[m] = {"tx": tx, "msg": msg, "presig": pre}
        return out

    def settle(self, presigned: dict, outcome: str, attestation: int) -> Tx:
        entry = presigned[outcome]
        sigs = {who: adaptor_complete(entry["presig"][who], attestation) for who in ("alice", "bob")}
        for who, sig in sigs.items():
            if not secp.verify(self.p.x(who), entry["msg"], sig):
                raise AssertionError("decrypted signature invalid")
        return entry["tx"].with_witness(0, [sigs["bob"], sigs["alice"], self.leaf,
                                            self.tree["controls"][0]])

    def forge_with_keys(self, funding_txid: str, vout: int, payee_x: bytes) -> Tx:
        """Both funding keys compromised: sign any transaction directly."""
        tx = Tx((TxIn(funding_txid, vout),), (TxOut(PAYOUT_SATS, p2tr_key_spk(payee_x)),))
        msg = sighash_scriptpath(tx, 0, [Prevout(FUNDING_SATS, self.funding_spk)], self.leaf)
        return tx.with_witness(0, [secp.sign(self.p.bob, msg), secp.sign(self.p.alice, msg),
                                   self.leaf, self.tree["controls"][0]])

    setup_keys = 2  # Alice's and Bob's funding keys
    setup_messages = "2 adaptor pre-signatures per outcome per party, exchanged before funding"


# --- Arm B --------------------------------------------------------------------

TOALT, FROMALT, DUP, ROT, SWAP, CAT, IF, ENDIF, TRUE = 0x6B, 0x6C, 0x76, 0x7B, 0x7C, 0x7E, 0x63, 0x68, 0x51


def allowlist_root(keys: tuple[bytes, bytes]) -> bytes:
    return hashlib.sha256(hashlib.sha256(keys[0]).digest() + hashlib.sha256(keys[1]).digest()).digest()


def keyless_leaf(oracle_commitment: bytes | None, keys: tuple[bytes, bytes], amount: int) -> bytes:
    """reference.compiled_script generalized over (allowlist, amount), with an
    oracle preimage gate in front. oracle_commitment=None builds the UNSAFE
    no-oracle fixture.

    Witness, bottom to top: prefix, suffix, xonly_key, sibling_hash,
    direction, oracle_preimage.
    """
    tag = hashlib.sha256(b"TapSighash").digest()
    gate = b"" if oracle_commitment is None else (bytes([OP_SHA256]) + push(oracle_commitment) +
                                                  bytes([OP_EQUALVERIFY]))
    return gate + b"".join((
        bytes([TOALT, TOALT, DUP, OP_SHA256, FROMALT, FROMALT, IF, SWAP, ENDIF, CAT, OP_SHA256]),
        push(allowlist_root(keys)), bytes([OP_EQUALVERIFY]),
        bytes([ROT, TOALT, SWAP, TOALT]),
        push(b"\x51\x20"), bytes([SWAP, CAT]),
        push(struct.pack("<Q", amount) + b"\x22"),
        bytes([SWAP, CAT, OP_SHA256]),
        bytes([FROMALT, FROMALT, ROT, ROT, CAT, CAT]),
        push(tag + tag), bytes([SWAP, CAT, OP_SHA256]),
        push(ref.TXCOMMIT_KEY), bytes([OP_CHECKSIGVERIFY, TRUE]),
    ))


def unconstrained_leaf() -> bytes:
    """UNSAFE: TXCOMMIT on a witness-supplied digest with nothing else.
    Any spender can compute the actual digest of their own transaction."""
    return push(ref.TXCOMMIT_KEY) + bytes([OP_CHECKSIGVERIFY, TRUE])


class ArmB:
    name = "B-keyless-TXCOMMIT"

    def __init__(self, parties: Parties, allow: dict[str, tuple[str, str]] | None = None,
                 *, oracle_gate: bool = True, leaves: dict[str, bytes] | None = None):
        self.p = parties
        self.allow = allow or {"ALICE_WINS": ("alice", "carol"), "BOB_WINS": ("bob", "carol")}
        com = {m: parties.oracle.hash_commitment(m) if oracle_gate else None for m in OUTCOMES}
        self.leaves = leaves or {m: keyless_leaf(com[m], tuple(parties.x(w) for w in self.allow[m]),
                                                 PAYOUT_SATS) for m in OUTCOMES}
        a, b = self.leaves[OUTCOMES[0]], self.leaves[OUTCOMES[1]]
        self.spk = p2mr_spk(a, b)
        self.controls = {OUTCOMES[0]: p2mr_control(b), OUTCOMES[1]: p2mr_control(a)}

    @property
    def funding_spk(self) -> bytes:
        return self.spk

    def settlement(self, funding_txid: str, vout: int, outcome: str, payee: str,
                   attestation: int | None, *, amount: int = PAYOUT_SATS,
                   witness_for: Tx | None = None, **tx_fields) -> Tx:
        """Build the spend; the witness is computed for `witness_for` when
        given (a stale witness replayed onto a mutated transaction)."""
        tx = Tx((TxIn(funding_txid, vout, tx_fields.pop("sequence", 0xFFFFFFFD)),),
                (TxOut(amount, p2tr_key_spk(self.p.x(payee))),), **tx_fields)
        basis = witness_for or tx
        leaf = self.leaves[outcome]
        msg = sigmsg_scriptpath(basis, 0, [Prevout(FUNDING_SATS, self.spk)], leaf, key_version=2)
        if len(msg) != 212:
            raise AssertionError("single-input SIGHASH_DEFAULT script-path message is 212 bytes")
        keys = self.allow[outcome]
        payee_for_proof = self._payee_of(basis)
        if payee_for_proof in keys:
            idx = keys.index(payee_for_proof)
            sibling = hashlib.sha256(self.p.x(keys[1 - idx])).digest()
            direction = b"" if idx == 0 else b"\x01"
        else:   # not allowlisted: present the key with a sibling so the Merkle check runs
            sibling, direction = hashlib.sha256(self.p.x(keys[1])).digest(), b""
        witness = [msg[:138], msg[170:], self.p.x(payee_for_proof), sibling, direction]
        if attestation is not None:
            witness.append(attestation.to_bytes(32, "big"))
        return tx.with_witness(0, witness + [leaf, self.controls[outcome]])

    def _payee_of(self, tx: Tx) -> str:
        key = tx.vout[0].script[2:]
        for who in ("alice", "bob", "carol", "mallory"):
            if self.p.x(who) == key:
                return who
        raise ValueError("unknown payee")

    def spend_with_raw_witness(self, funding_txid: str, vout: int, outcome: str, payee: str,
                               witness: list[bytes]) -> Tx:
        tx = Tx((TxIn(funding_txid, vout),), (TxOut(PAYOUT_SATS, p2tr_key_spk(self.p.x(payee))),))
        return tx.with_witness(0, witness + [self.leaves[outcome], self.controls[outcome]])

    setup_keys = 0
    setup_messages = "oracle announces SHA256(s_m) per outcome; parties agree the allowlists"


class UnsafeUnconstrained:
    """Phase 5 fixture: P2MR tree whose first leaf is a bare TXCOMMIT check."""
    name = "K3-unconstrained-digest"

    def __init__(self):
        self.leaf = unconstrained_leaf()
        self.sibling = bytes([0x6A]) + push(b"unspendable KCS sibling")
        self.spk = p2mr_spk(self.leaf, self.sibling)
        self.control = p2mr_control(self.sibling)

    @property
    def funding_spk(self) -> bytes:
        return self.spk

    def steal(self, funding_txid: str, vout: int, thief_x: bytes) -> Tx:
        tx = Tx((TxIn(funding_txid, vout),), (TxOut(PAYOUT_SATS, p2tr_key_spk(thief_x)),))
        digest = sighash_scriptpath(tx, 0, [Prevout(FUNDING_SATS, self.spk)], self.leaf, key_version=2)
        return tx.with_witness(0, [digest, self.leaf, self.control])


# --- Arm C: CSFS oracle check + owner-assigned recipient + TXCOMMIT ---------

OP_CSFS, OP_OVER, OP_VERIFY = 0xCC, 0x78, 0x69


def contract_id(label: str, outcome: str) -> bytes:
    return hashlib.sha256(f"spiral-armC/{label}/{outcome}".encode()).digest()


def assignment_message(cid: bytes, recipient_x: bytes) -> bytes:
    return hashlib.sha256(cid + recipient_x).digest()


def csfs_leaf(oracle_msg: bytes, oracle_x: bytes, cid: bytes, owner_x: bytes, amount: int) -> bytes:
    """Witness, bottom to top: prefix, suffix, recipient_x, owner_sig, oracle_sig.

    1. The oracle's BIP340 attestation for this outcome (x(R)||s_m) verifies
       under the oracle key; no hash pre-commitment is needed.
    2. The position owner signed SHA256(cid || recipient_x); any recipient,
       chosen after funding, without the counterparty.
    3. The single output pays `amount` to P2TR(recipient_x), bound to the
       actual transaction through TXCOMMIT.
    """
    tag = hashlib.sha256(b"TapSighash").digest()
    return b"".join((
        push(oracle_msg), push(oracle_x), bytes([OP_CSFS, OP_VERIFY]),
        bytes([OP_OVER]), push(cid), bytes([SWAP, CAT, OP_SHA256]), push(owner_x), bytes([OP_CSFS, OP_VERIFY]),
        bytes([ROT, TOALT, SWAP, TOALT]),
        push(b"\x51\x20"), bytes([SWAP, CAT]),
        push(struct.pack("<Q", amount) + b"\x22"),
        bytes([SWAP, CAT, OP_SHA256]),
        bytes([FROMALT, FROMALT, ROT, ROT, CAT, CAT]),
        push(tag + tag), bytes([SWAP, CAT, OP_SHA256]),
        push(ref.TXCOMMIT_KEY), bytes([OP_CHECKSIGVERIFY, TRUE]),
    ))


class ArmC:
    name = "C-CSFS-oracle-owner-assignment"

    def __init__(self, parties: Parties, label: str = "v1",
                 owners: dict[str, str] | None = None):
        self.p, self.label = parties, label
        self.owners = owners or {"ALICE_WINS": "alice", "BOB_WINS": "bob"}
        self.cid = {m: contract_id(label, m) for m in OUTCOMES}
        self.leaves = {m: csfs_leaf(Oracle.message(m), parties.oracle.P, self.cid[m],
                                    parties.x(self.owners[m]), PAYOUT_SATS) for m in OUTCOMES}
        a, b = self.leaves[OUTCOMES[0]], self.leaves[OUTCOMES[1]]
        self.spk = p2mr_spk(a, b)
        self.controls = {OUTCOMES[0]: p2mr_control(b), OUTCOMES[1]: p2mr_control(a)}

    @property
    def funding_spk(self) -> bytes:
        return self.spk

    def oracle_sig(self, outcome: str, attestation: int) -> bytes:
        return self.p.oracle.R + attestation.to_bytes(32, "big")

    def assign(self, outcome: str, recipient: str, signer: str | None = None, cid: bytes | None = None) -> bytes:
        """Owner's off-chain assignment of the payout to `recipient`."""
        who = signer or self.owners[outcome]
        msg = assignment_message(cid or self.cid[outcome], self.p.x(recipient))
        return secp.sign(getattr(self.p, who), msg)

    def settlement(self, funding_txid: str, vout: int, outcome: str, payee: str, oracle_sig: bytes,
                   assignment: bytes, *, proof_payee: str | None = None, amount: int = PAYOUT_SATS,
                   witness_for: Tx | None = None, **tx_fields) -> Tx:
        tx = Tx((TxIn(funding_txid, vout, tx_fields.pop("sequence", 0xFFFFFFFD)),),
                (TxOut(amount, p2tr_key_spk(self.p.x(payee))),), **tx_fields)
        basis = witness_for or tx
        leaf = self.leaves[outcome]
        msg = sigmsg_scriptpath(basis, 0, [Prevout(FUNDING_SATS, self.spk)], leaf, key_version=2)
        recipient = self.p.x(proof_payee or payee)
        witness = [msg[:138], msg[170:], recipient, assignment, oracle_sig]
        return tx.with_witness(0, witness + [leaf, self.controls[outcome]])

    setup_keys = 0
    setup_messages = "standard DLC announcement (oracle key + nonce); owners hold their position keys"


class CsfsProbe:
    """P2TR fixture: leaf `<msg> <key> OP_CHECKSIGFROMSTACK`. On old rules
    0xcc is OP_SUCCESS204, so every spend is valid; on new rules it is a
    BIP340 check whose result is the script's final stack element."""

    def __init__(self, msg: bytes, key: bytes):
        self.msg, self.key = msg, key
        self.leaf = push(msg) + push(key) + bytes([OP_CSFS])
        self.tree = taproot_output(NUMS, [self.leaf])

    @property
    def funding_spk(self) -> bytes:
        return self.tree["spk"]

    def spend(self, funding_txid: str, vout: int, sig: bytes, payee_x: bytes) -> Tx:
        tx = Tx((TxIn(funding_txid, vout),), (TxOut(PAYOUT_SATS, p2tr_key_spk(payee_x)),))
        return tx.with_witness(0, [sig, self.leaf, self.tree["controls"][0]])
