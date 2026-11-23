"""Stock-consensus on-chain DLC ownership rollover.

A confirmed transaction consumes Alice/Bob's original funding outpoint and
creates a fresh Carol/Bob Taproot contract. Old Alice-bound CETs remain valid
signatures of an *already spent input*, so they cannot confirm on that chain.

The transfer is cooperative (Alice and Bob both sign) and on-chain. It is
not Lightning-style off-chain transfer or keyless covenant enforcement.
All private keys here are deterministic, valueless Signet fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass

import secp
from arms import ArmA, FUNDING_SATS, OUTCOMES, Parties, SETTLE_FEE_SATS, p2tr_key_spk
from secp import adaptor_complete, adaptor_presign, adaptor_verify
from txlib import NUMS, Prevout, Tx, TxIn, TxOut, push, sighash_scriptpath, taproot_output


ROLLOVER_FEE_SATS = 1_000


@dataclass
class RolledDLC:
    """DLC with a replacement holder key and freshly signed adaptor CETs."""

    parties: Parties
    holder: str = "carol"
    counterparty: str = "bob"
    funding_sats: int = FUNDING_SATS - ROLLOVER_FEE_SATS
    settlement_fee_sats: int = SETTLE_FEE_SATS

    def __post_init__(self):
        if self.holder == self.counterparty:
            raise ValueError("holder and counterparty need independent keys")
        if self.funding_sats <= self.settlement_fee_sats:
            raise ValueError("contract must fund a positive payout")
        self.signers = (self.holder, self.counterparty)
        self.leaf = (push(self.parties.x(self.holder)) + b"\xad" +
                     push(self.parties.x(self.counterparty)) + b"\xac")
        self.tree = taproot_output(NUMS, [self.leaf])

    @property
    def funding_spk(self) -> bytes:
        return self.tree["spk"]

    @property
    def payout_sats(self) -> int:
        return self.funding_sats - self.settlement_fee_sats

    def cet(self, funding_txid: str, vout: int, outcome: str) -> Tx:
        if outcome not in OUTCOMES:
            raise ValueError("unrecognized oracle outcome")
        payee = self.holder if outcome == "ALICE_WINS" else self.counterparty
        return Tx((TxIn(funding_txid, vout),),
                  (TxOut(self.payout_sats, p2tr_key_spk(self.parties.x(payee))),))

    def presign_all(self, funding_txid: str, vout: int) -> dict:
        """Buyer and counterparty prepare CETs before broadcast of rollover."""
        out = {}
        for outcome in OUTCOMES:
            tx = self.cet(funding_txid, vout, outcome)
            msg = sighash_scriptpath(tx, 0, [Prevout(self.funding_sats, self.funding_spk)],
                                     self.leaf)
            T = self.parties.oracle.attestation_point(outcome)
            presig = {
                name: adaptor_presign(getattr(self.parties, name), msg, T,
                                      f"rolled/{funding_txid}/{outcome}/{name}")
                for name in self.signers
            }
            if not all(adaptor_verify(self.parties.x(name), msg, T, presig[name])
                       for name in self.signers):
                raise AssertionError("rollover presignature verification failed")
            out[outcome] = {"tx": tx, "msg": msg, "presig": presig}
        return out

    def settle(self, presigned: dict, outcome: str, attestation: int) -> Tx:
        entry = presigned[outcome]
        signatures = {
            name: adaptor_complete(entry["presig"][name], attestation)
            for name in self.signers
        }
        for name in self.signers:
            if not secp.verify(self.parties.x(name), entry["msg"], signatures[name]):
                raise AssertionError("rollover settlement signature invalid")
        return entry["tx"].with_witness(
            0,
            [signatures[self.counterparty], signatures[self.holder],
             self.leaf, self.tree["controls"][0]],
        )


def make_rollover(old_contract: ArmA, parties: Parties, funding_txid: str, vout: int,
                  successor: RolledDLC, *, fee_sats: int = ROLLOVER_FEE_SATS) -> Tx:
    """Alice and Bob sign an actual transfer spend into Carol/Bob's contract.

    Both signatures commit to the new output. The old funding input is
    consumed once the transfer confirms. The successor's CETs bind to the
    newly created outpoint and need fresh buyer/counterparty pre-signatures.
    """
    if not 0 < fee_sats < FUNDING_SATS:
        raise ValueError("invalid rollover fee")
    if successor.funding_sats != FUNDING_SATS - fee_sats:
        raise ValueError("successor amount must match rollover output")
    if successor.holder == "alice":
        raise ValueError("rollover must change holder")
    tx = Tx((TxIn(funding_txid, vout),), (TxOut(successor.funding_sats,
                                                successor.funding_spk),))
    msg = sighash_scriptpath(tx, 0, [Prevout(FUNDING_SATS, old_contract.funding_spk)],
                             old_contract.leaf)
    return tx.with_witness(
        0, [secp.sign(parties.bob, msg), secp.sign(parties.alice, msg),
            old_contract.leaf, old_contract.tree["controls"][0]]
    )


def former_holder_attack(successor: RolledDLC, funding_txid: str,
                         vout: int) -> Tx:
    """Negative fixture: Alice+Bob try to sign where Carol+Bob are required."""
    tx = successor.cet(funding_txid, vout, "ALICE_WINS")
    msg = sighash_scriptpath(tx, 0,
                             [Prevout(successor.funding_sats, successor.funding_spk)],
                             successor.leaf)
    return tx.with_witness(
        0, [secp.sign(successor.parties.bob, msg),
            secp.sign(successor.parties.alice, msg),
            successor.leaf, successor.tree["controls"][0]]
    )
