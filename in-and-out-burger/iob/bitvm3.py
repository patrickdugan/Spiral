"""The BitVM3 claim graph for a vault refill: a garbled M14 verifier decides, Bitcoin enforces.

One graph per claim. The vault pays the payer's derived key P' if nobody holds the circuit's
reject label within a window after the claim:

    vault V   NUMS + { claim:   <D> CHECKSIGVERIFY <C> CHECKSIG
                       reclaim: <RECLAIM> CSV DROP <D> CHECKSIG }
       |  claim tx (D presigns at setup, the claimant C signs to start the window)
       v
    claim K   NUMS + { payout:   <WINDOW> CSV DROP <D> CHECKSIG     -> P'   (D presigns at setup)
                       disprove: SHA256 <H(reject)> EQUALVERIFY <W> CHECKSIG -> desk }
              + OP_RETURN "IOB3" || claim_id

claim_id commits to the statement the circuit was garbled for, the garbler's ciphertext
commitment, both output-label hashes, the payout script and the instance name. The claimant
garbles M14 with the statement as a circuit constant and hands the challenger the input labels
of its proof's bits; the challenger evaluates. A valid proof of that statement yields the accept
label, which opens nothing, and the presigned payout matures. Any other proof yields the reject
label, the preimage the disprove leaf asks for.

What Bitcoin enforces: who may start a claim; the claim's commitments; the window; that only the
reject label of this instance stops the payout; that the payout goes to P' and nowhere else.
What it does not (the trust assumptions T1-T3 of FlatCheck FC03): that the tables are a correct
garbling of M14 for that statement (T1, cut-and-choose is not run); that the claimant hands over
the input labels (T2); and the presigned graph standing in for a covenant (T3).
"""
from __future__ import annotations

import dataclasses
import hashlib
import struct

from . import btc, taproot as tr
from .taproot import In, Out, Tx

RECLAIM_BLOCKS = 144
WINDOW_BLOCKS = 6
FEE_SAT_VB = 2
TAG = b"IOB/bitvm3-claim/v1"


def frame(b: bytes) -> bytes:
    return struct.pack(">I", len(b)) + b


@dataclasses.dataclass(frozen=True)
class Parties:
    desk: int       # vault owner and committee of one: presigns claim and payout
    claimant: int   # starts the claim
    watch: int      # challenger: spends the disprove leaf

    @property
    def D(self) -> bytes:
        return tr.xonly(self.desk)

    @property
    def C(self) -> bytes:
        return tr.xonly(self.claimant)

    @property
    def W(self) -> bytes:
        return tr.xonly(self.watch)


def vault_output(p: Parties) -> tr.TapOutput:
    claim = btc.push(p.D) + bytes([tr.OP_CHECKSIGVERIFY]) + btc.push(p.C) + bytes([tr.OP_CHECKSIG])
    reclaim = tr.num(RECLAIM_BLOCKS) + bytes([tr.OP_CSV, tr.OP_DROP]) + btc.push(p.D) + bytes([tr.OP_CHECKSIG])
    return tr.TapOutput((claim, reclaim))


def claim_output(p: Parties, reject_label_sha256: bytes) -> tr.TapOutput:
    assert len(reject_label_sha256) == 32
    payout = tr.num(WINDOW_BLOCKS) + bytes([tr.OP_CSV, tr.OP_DROP]) + btc.push(p.D) + bytes([tr.OP_CHECKSIG])
    disprove = bytes([tr.OP_SHA256]) + btc.push(reject_label_sha256) + bytes([tr.OP_EQUALVERIFY]) + btc.push(p.W) + bytes([tr.OP_CHECKSIG])
    return tr.TapOutput((payout, disprove))


@dataclasses.dataclass(frozen=True)
class Instance:
    """One garbled M14 instance (from `m14-claim setup`) bound to one payout."""
    name: str
    statement_committed_sha256: str   # committed_values_sha256 the circuit pins
    program_vk_digest: str
    ciphertext_commitment: str        # BLAKE3 of the garbler's ciphertext stream
    accept_label_sha256: str
    reject_label_sha256: str
    payout_spk: bytes

    def claim_id(self) -> bytes:
        h = hashlib.sha256(frame(TAG))
        for part in (
            self.name.encode(),
            bytes.fromhex(self.statement_committed_sha256),
            bytes.fromhex(self.program_vk_digest),
            bytes.fromhex(self.ciphertext_commitment),
            bytes.fromhex(self.accept_label_sha256),
            bytes.fromhex(self.reject_label_sha256),
            self.payout_spk,
        ):
            h.update(frame(part))
        return h.digest()


def _fee(vbytes: int) -> int:
    return FEE_SAT_VB * vbytes


# Witness sizes are fixed (Schnorr signatures are 64 bytes), so fees are known before signing.
def _dummy_vsize(tx: Tx, witnesses: list) -> int:
    t = dataclasses.replace(tx, ins=[dataclasses.replace(i, witness=w) for i, w in zip(tx.ins, witnesses)])
    return t.vsize()


@dataclasses.dataclass
class Graph:
    parties: Parties
    inst: Instance
    vault_txid: str
    vault_vout: int
    vault_value: int
    refund_spk: bytes   # where a disprove sends the bond back (the desk's)

    def __post_init__(self):
        self.V = vault_output(self.parties)
        self.K = claim_output(self.parties, bytes.fromhex(self.inst.reject_label_sha256))
        sig, leaf_v, leaf_k = bytes(64), self.V.leaves[0], self.K.leaves[0]
        claim = self._claim_tx(0)
        k_value = self.vault_value - _fee(_dummy_vsize(claim, [[sig, sig, leaf_v, self.V.control_block(0)]]))
        self.claim_fee = self.vault_value - k_value
        self.k_value = k_value
        self.claim = self._claim_tx(k_value)
        pay = self._payout_tx(0)
        self.payout_value = k_value - _fee(_dummy_vsize(pay, [[sig, leaf_k, self.K.control_block(0)]]))
        self.payout = self._payout_tx(self.payout_value)
        dis = self._disprove_tx(0)
        self.disprove_value = k_value - _fee(_dummy_vsize(dis, [[sig, bytes(16), self.K.leaves[1], self.K.control_block(1)]]))
        assert self.payout_value > 330 and self.disprove_value > 330, "vault too small for the presigned fees"

    # --- transactions --------------------------------------------------------------------

    def _claim_tx(self, k_value: int) -> Tx:
        return Tx([In(self.vault_txid, self.vault_vout, sequence=0xFFFFFFFF)],
                  [Out(k_value, self.K.script_pubkey), Out(0, tr.op_return(b"IOB3" + self.inst.claim_id()))])

    def _payout_tx(self, value: int) -> Tx:
        return Tx([In(self.claim_txid if hasattr(self, "claim") else "00" * 32, 0, sequence=WINDOW_BLOCKS)],
                  [Out(value, self.inst.payout_spk)])

    def _disprove_tx(self, value: int) -> Tx:
        return Tx([In(self.claim_txid if hasattr(self, "claim") else "00" * 32, 0, sequence=0xFFFFFFFD)],
                  [Out(value, self.refund_spk)])

    @property
    def claim_txid(self) -> str:
        return self.claim.txid()

    # --- signatures ----------------------------------------------------------------------

    def _vault_spent(self):
        return [(self.vault_value, self.V.script_pubkey)]

    def _k_spent(self):
        return [(self.k_value, self.K.script_pubkey)]

    def presign(self) -> dict:
        """The desk's signatures, made at setup: the claim (its half) and the payout to P'."""
        m_claim = tr.sighash_script_path(self.claim, 0, self._vault_spent(), self.V.leaves[0])
        m_pay = tr.sighash_script_path(self.payout, 0, self._k_spent(), self.K.leaves[0])
        return {"claim_desk": tr.schnorr_sign(m_claim, self.parties.desk).hex(),
                "payout_desk": tr.schnorr_sign(m_pay, self.parties.desk).hex()}

    def signed_claim(self, presig: dict) -> Tx:
        m = tr.sighash_script_path(self.claim, 0, self._vault_spent(), self.V.leaves[0])
        sig_c = tr.schnorr_sign(m, self.parties.claimant)
        sig_d = bytes.fromhex(presig["claim_desk"])
        assert tr.schnorr_verify(m, self.parties.D, sig_d), "desk presignature does not match the claim"
        tx = dataclasses.replace(self.claim)
        tx.ins = [dataclasses.replace(self.claim.ins[0], witness=[sig_c, sig_d, self.V.leaves[0], self.V.control_block(0)])]
        assert tx.txid() == self.claim_txid
        return tx

    def signed_payout(self, presig: dict) -> Tx:
        sig_d = bytes.fromhex(presig["payout_desk"])
        tx = dataclasses.replace(self.payout)
        tx.ins = [dataclasses.replace(self.payout.ins[0], witness=[sig_d, self.K.leaves[0], self.K.control_block(0)])]
        return tx

    def signed_disprove(self, label: bytes) -> Tx:
        """The challenger's spend with an output label it evaluated. Bitcoin accepts it only with
        the reject label."""
        m = tr.sighash_script_path(self.disprove_unsigned, 0, self._k_spent(), self.K.leaves[1])
        sig_w = tr.schnorr_sign(m, self.parties.watch)
        tx = dataclasses.replace(self.disprove_unsigned)
        tx.ins = [dataclasses.replace(self.disprove_unsigned.ins[0], witness=[sig_w, label, self.K.leaves[1], self.K.control_block(1)])]
        return tx

    @property
    def disprove_unsigned(self) -> Tx:
        return self._disprove_tx(self.disprove_value)

    # --- counterexample transactions ----------------------------------------------------

    def payout_redirected(self, presig: dict, spk: bytes) -> Tx:
        """The presigned payout with its output moved elsewhere: the desk's signature no longer
        matches."""
        tx = self.signed_payout(presig)
        tx.outs = [Out(self.payout_value, spk)]
        return tx

    def payout_early(self, presig: dict) -> Tx:
        """The presigned payout itself, sent before WINDOW_BLOCKS confirmations of the claim."""
        return self.signed_payout(presig)

    def describe(self) -> dict:
        return {
            "instance": self.inst.name,
            "claim_id": self.inst.claim_id().hex(),
            "vault": {"outpoint": f"{self.vault_txid}:{self.vault_vout}", "sats": self.vault_value,
                      "script_pubkey": self.V.script_pubkey.hex(),
                      "leaves": [s.hex() for s in self.V.leaves]},
            "claim": {"txid": self.claim_txid, "fee": self.claim_fee, "k_sats": self.k_value,
                      "k_script_pubkey": self.K.script_pubkey.hex(),
                      "leaves": [s.hex() for s in self.K.leaves]},
            "payout": {"txid": self.payout.txid(), "sats": self.payout_value, "to_script_pubkey": self.inst.payout_spk.hex(),
                       "sequence": WINDOW_BLOCKS},
            "disprove": {"sats": self.disprove_value, "to_script_pubkey": self.refund_spk.hex()},
            "window_blocks": WINDOW_BLOCKS,
            "reclaim_blocks": RECLAIM_BLOCKS,
            "fee_sat_vb": FEE_SAT_VB,
        }
