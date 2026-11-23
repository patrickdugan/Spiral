"""SHZ-K1: SatsHedgeZero's numeric inverse DLC settled by script, not keys.

SatsHedgeZero (patrickdugan/SatsHedgeZero @ 5ca390e) funds each trade to a
NUMS P2TR output with a 2-of-2 CET leaf and a CSV-144 refund leaf. Both
parties pre-sign one adaptor CET per dyadic price range (compress_cet_ranges);
the oracle's per-digit BIP340 attestations decrypt the matching CET.
Position transfer (MNR-05) needs the counterparty to re-sign (novation) or a
ClearingGuard.

SHZ-K1 keeps the contract, the oracle and the compression exactly, and moves
enforcement into one P2MR leaf per CET range:

1. For each prefix digit j the leaf rebuilds the oracle signature
   R_j || s_j from the ANNOUNCED nonce R_j (in the script) and the
   attested scalar s_j (in the witness), and checks it with research
   OP_CHECKSIGFROMSTACK on SHZ's own digit message
   tagged_hash("SatsHedgeZero/DLC/DigitOutcome/v0", ...). Pinning R_j keeps
   SHZ's equivocation property: two different bits signed under the same
   nonce reveal the oracle key.
2. Each side's owner (long, short) signs SHA256(cid || recipient_x) once.
   That assignment is valid for every range, so a position can be sold
   to anyone without the counterparty.
3. The two outputs (long payout, short payout) of the range are rebuilt
   with OP_CAT and bound to the spending transaction through TXCOMMIT.

A further keyless refund leaf (CSV, same assignment checks) returns both
margins if the oracle never attests. No party key can move the funds.

Requires the patched Core (TXCOMMIT + OP_CAT + P2MR + research CSFS,
-keylessresearch); on stock rules a witness-v2 spend is anyone-can-spend.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

import secp
from secp import G, N, has_even_y, point_mul, seckey, xonly
from shz_margin import CetRange, InverseContractSpec, compress_cet_ranges, decompose_price_bits, oracle_digit_message
from txlib import Prevout, Tx, TxIn, TxOut, push, ref, sigmsg_scriptpath

OP_CSFS, OP_VERIFY, OP_OVER, OP_SWAP, OP_CAT = 0xCC, 0x69, 0x78, 0x7C, 0x7E
OP_SHA256, OP_TOALT, OP_FROMALT, OP_DROP, OP_CSV = 0xA8, 0x6B, 0x6C, 0x75, 0xB2
OP_CHECKSIGVERIFY, OP_TRUE = 0xAD, 0x51
TAG2 = hashlib.sha256(b"TapSighash").digest() * 2


def p2tr_key_spk(x: bytes) -> bytes:
    return b"\x51\x20" + x


def scriptnum_push(n: int) -> bytes:
    if 1 <= n <= 16:
        return bytes([0x50 + n])
    b = n.to_bytes((n.bit_length() + 8) // 8, "little")
    return push(b)


# --- oracle (SHZ announcement shape: one pre-committed nonce per digit) -----

class DigitOracle:
    """BIP340 oracle over SHZ digit messages with one announced nonce per
    digit, as in shz-dlc OracleAnnouncement. A single key stands in for the
    FROST t-of-n group key; the signature format is the same."""

    def __init__(self, label: str, event_id: str, num_bits: int):
        self.event_id, self.num_bits = event_id, num_bits
        d = seckey(f"shz-oracle/{label}")
        self.d = d if has_even_y(point_mul(G, d)) else N - d
        self.P = xonly(point_mul(G, self.d))
        self.k = []
        for j in range(num_bits):
            k = seckey(f"shz-oracle-nonce/{label}/{event_id}/{j}")
            self.k.append(k if has_even_y(point_mul(G, k)) else N - k)
        self.R = [xonly(point_mul(G, k)) for k in self.k]

    def msg(self, j: int, bit: int) -> bytes:
        return oracle_digit_message(self.event_id, j, bit)

    def attest(self, price: int) -> list[bytes]:
        """s_j for every digit of `price` (MSB first), 32 bytes each."""
        out = []
        for j, bit in enumerate(decompose_price_bits(price, self.num_bits)):
            e = secp.challenge(self.R[j], self.P, self.msg(j, bit))
            out.append(((self.k[j] + e * self.d) % N).to_bytes(32, "big"))
        return out

    def announcement(self) -> dict:
        return {"event_id": self.event_id, "oracle_pubkey_x": self.P.hex(),
                "digit_nonces_x": [r.hex() for r in self.R]}


# --- P2MR tree over many leaves --------------------------------------------

def merkle_tree(leaf_scripts: list[bytes]) -> tuple[bytes, list[list[bytes]]]:
    """BIP341-style tree (sorted TapBranch); returns (root, path per leaf)."""
    hashes = [ref.tapleaf(s) for s in leaf_scripts]
    paths: list[list[bytes]] = [[] for _ in hashes]

    def build(idx: list[int]) -> bytes:
        if len(idx) == 1:
            return hashes[idx[0]]
        mid = len(idx) // 2
        left, right = build(idx[:mid]), build(idx[mid:])
        for i in idx[:mid]:
            paths[i].append(right)
        for i in idx[mid:]:
            paths[i].append(left)
        return ref.tapbranch(left, right)

    if len(hashes) < 2:
        raise ValueError("restricted P2MR needs depth >= 1")
    return build(list(range(len(hashes)))), paths


# --- leaves -----------------------------------------------------------------

def settle_leaf(oracle: DigitOracle, prefix: tuple[int, ...], cid: bytes,
                sides: list[tuple[int, bytes]], csv: int | None = None) -> bytes:
    """`sides` = [(amount, owner_x)] in output order; zero amounts are omitted
    by the caller. Witness, bottom to top: sigmsg prefix (138 B), sigmsg
    suffix, then per side in REVERSE output order (recipient_x, assignment),
    then s_{k-1} .. s_0 (s_0 on top)."""
    parts = []
    if csv is not None:
        parts += [scriptnum_push(csv), bytes([OP_CSV, OP_DROP])]
    for j, bit in enumerate(prefix):
        parts += [push(oracle.R[j]), bytes([OP_SWAP, OP_CAT]), push(oracle.msg(j, bit)), push(oracle.P),
                  bytes([OP_CSFS, OP_VERIFY])]
    for _amount, owner_x in sides:      # first output's side is on top
        parts += [bytes([OP_OVER]), push(cid), bytes([OP_SWAP, OP_CAT, OP_SHA256]), push(owner_x),
                  bytes([OP_CSFS, OP_VERIFY, OP_TOALT])]
    # Altstack now holds recipients with the LAST output's on top.
    for i, (amount, _owner) in enumerate(reversed(sides)):
        parts += [bytes([OP_FROMALT]), push(struct.pack("<Q", amount) + b"\x22\x51\x20"),
                  bytes([OP_SWAP, OP_CAT])]
        if i:
            parts += [bytes([OP_SWAP, OP_CAT])]   # earlier output first
    parts += [bytes([OP_SHA256]),
              bytes([OP_SWAP, OP_TOALT, OP_CAT, OP_FROMALT, OP_CAT]),
              push(TAG2), bytes([OP_SWAP, OP_CAT, OP_SHA256]),
              push(ref.TXCOMMIT_KEY), bytes([OP_CHECKSIGVERIFY, OP_TRUE])]
    return b"".join(parts)


@dataclass
class Leaf:
    kind: str                 # "cet" or "refund"
    script: bytes
    sides: list               # [(role, amount)] in output order
    cet: CetRange | None = None


class K1Contract:
    """One SHZ trade (InverseContractSpec) as a keyless P2MR output."""

    def __init__(self, spec: InverseContractSpec, oracle: DigitOracle, long_owner_x: bytes,
                 short_owner_x: bytes, *, label: str, max_error_sats: int, fee_sats: int,
                 refund_csv: int = 144):
        self.spec, self.oracle, self.fee = spec, oracle, fee_sats
        self.owner = {"long": long_owner_x, "short": short_owner_x}
        self.cid = hashlib.sha256(b"SatsHedgeZero/K1/contract/v0" + label.encode() +
                                  oracle.event_id.encode() + struct.pack(
                                      "<QQQQ", spec.usd_notional, spec.entry_price_usd,
                                      spec.long_margin_sats, spec.short_margin_sats)).digest()
        self.cets = compress_cet_ranges(spec, oracle.num_bits, max_error_sats)
        self.leaves: list[Leaf] = []
        for c in self.cets:
            sides = [(r, a) for r, a in (("long", c.payout.long_sats), ("short", c.payout.short_sats)) if a > 0]
            self.leaves.append(Leaf("cet", self._script(c.prefix_bits, sides), sides, c))
        refund_sides = [("long", spec.long_margin_sats), ("short", spec.short_margin_sats)]
        self.refund_csv = refund_csv
        self.leaves.append(Leaf("refund", self._script((), refund_sides, refund_csv), refund_sides))
        self.root, self.paths = merkle_tree([l.script for l in self.leaves])
        self.spk = b"\x52\x20" + self.root

    def _script(self, prefix, sides, csv=None) -> bytes:
        return settle_leaf(self.oracle, prefix, self.cid,
                           [(a, self.owner[r]) for r, a in sides], csv)

    @property
    def funding_sats(self) -> int:
        return self.spec.total_collateral_sats + self.fee

    def control(self, i: int) -> bytes:
        return b"\xc0" + b"".join(self.paths[i])

    def leaf_for_price(self, price: int) -> int:
        for i, l in enumerate(self.leaves):
            if l.kind == "cet" and l.cet.matches_price(price, self.oracle.num_bits):
                return i
        raise ValueError("no CET covers price")

    def assign(self, owner_secret: int, recipient_x: bytes, cid: bytes | None = None) -> bytes:
        return secp.sign(owner_secret, hashlib.sha256((cid or self.cid) + recipient_x).digest())

    def spend(self, funding_txid: str, vout: int, leaf_index: int, recipients: dict, attest: list[bytes],
              *, amounts: dict | None = None, proof_recipients: dict | None = None,
              witness_for: Tx | None = None, sequence: int | None = None) -> Tx:
        """recipients: {role: (recipient_x, assignment_sig)}. `amounts` and
        `proof_recipients` override what the transaction pays / what the
        witness presents (negative controls)."""
        leaf = self.leaves[leaf_index]
        seq = sequence if sequence is not None else (self.refund_csv if leaf.kind == "refund" else 0xFFFFFFFD)
        outs = tuple(TxOut((amounts or {}).get(r, a), p2tr_key_spk(recipients[r][0])) for r, a in leaf.sides)
        tx = Tx((TxIn(funding_txid, vout, seq),), outs)
        basis = witness_for or tx
        msg = sigmsg_scriptpath(basis, 0, [Prevout(self.funding_sats, self.spk)], leaf.script, key_version=2)
        w = [msg[:138], msg[170:]]
        for r, _a in reversed(leaf.sides):
            x, sig = (proof_recipients or {}).get(r, recipients[r])
            w += [x, sig]
        k = len(leaf.cet.prefix_bits) if leaf.cet else 0
        w += list(reversed(attest[:k]))
        return tx.with_witness(0, w + [leaf.script, self.control(leaf_index)])

    def summary(self) -> dict:
        depths = [len(p) for p in self.paths]
        prefix_lens = [len(l.cet.prefix_bits) for l in self.leaves if l.cet]
        return {"cets": len(self.cets), "leaves": len(self.leaves), "tree_depth_max": max(depths),
                "prefix_len_min": min(prefix_lens), "prefix_len_max": max(prefix_lens),
                "leaf_bytes_max": max(len(l.script) for l in self.leaves), "cid": self.cid.hex(),
                "spk": self.spk.hex(), "funding_sats": self.funding_sats}
