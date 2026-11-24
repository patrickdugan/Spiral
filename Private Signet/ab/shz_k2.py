"""SHZ-K2: keyless SatsHedgeZero contracts with exclusive on-chain transfer and
netted multi-trade (book) settlement.

K1 (shz_k1.py) moved settlement into script but left transfer as an
off-chain owner signature, so an owner could sell one position twice. K2
puts the owners into the output itself:

    spk  = P2MR root = TapBranch(C, TapLeaf(state))
    state = OP_RETURN <K_1> ... <K_n>        (never executed)
    C     = Merkle root of the contract leaves; none of them contains a key

Every contract leaf takes K_1..K_n, C and the branch order from the
witness, recomputes the spk, and puts SHA256(0x22 || spk) into the
TXCOMMIT message as sha_scriptpubkeys. A wrong owner list gives a wrong
spk, so a spend that names anyone but the current owners fails.

Leaves in C:
- one CET leaf per price range: per-digit oracle signatures checked with
  CSFS under the announced nonces (as K1), then the range's payouts to the
  owners in the state, bound by TXCOMMIT;
- a keyless refund after a CSV delay paying the margins to the owners;
- one transfer leaf per party p: the current owner K_p signs the spending
  transaction (BIP342 CHECKSIG); the single output must be the same C with
  K_p replaced by a new key, holding the input amount minus a fixed transfer
  fee (4-byte script arithmetic, so amounts stay below 2^31 sats) and no less
  than a floor that keeps settlement funded.

Transfer is an on-chain step the counterparty cannot block and is not
needed for. Once it confirms, the old owner's key is gone from the state,
so a second sale spends a coin that no longer exists.

A K2 output can carry one trade (parties long/short) or a book of trades
on one oracle event (parties alice/bob/carol): leaves then pay each party
its netted total, like SHZ's collated clearing, without signatures.

Requires TXCOMMIT + OP_CAT + P2MR + research CSFS (-keylessresearch).
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

import secp
from shz_k1 import merkle_tree
from shz_margin import (BookTrade, InverseContractSpec, compress_book_ranges, compress_cet_ranges)
from txlib import Prevout, Tx, TxIn, TxOut, push, ref, sighash_scriptpath, sigmsg_scriptpath

OP = dict(N0=0x00, IF=0x63, ELSE=0x67, ENDIF=0x68, VERIFY=0x69, RETURN=0x6A, TOALT=0x6B, FROMALT=0x6C,
          DROP=0x75, DUP=0x76, NIP=0x77, OVER=0x78, PICK=0x79, ROLL=0x7A, ROT=0x7B, SWAP=0x7C, CAT=0x7E,
          SIZE=0x82, EQUAL=0x87, EQUALVERIFY=0x88, SUB=0x94, GTE=0xA2, SHA256=0xA8, CHECKSIGVERIFY=0xAD,
          CSV=0xB2, CSFS=0xCC, TRUE=0x51)


def op(*names: str) -> bytes:
    return bytes(OP[n] for n in names)


def num(n: int) -> bytes:
    """Minimal push of a non-negative script number."""
    if n == 0:
        return b"\x00"
    if 1 <= n <= 16:
        return bytes([0x50 + n])
    return push(enc_num(n))


def enc_num(n: int) -> bytes:
    if n == 0:
        return b""
    b = n.to_bytes((n.bit_length() + 7) // 8, "little")
    return b + b"\x00" if b[-1] & 0x80 else b


TAG2 = hashlib.sha256(b"TapSighash").digest() * 2
TL2 = hashlib.sha256(b"TapLeaf").digest() * 2
TB2 = hashlib.sha256(b"TapBranch").digest() * 2


def state_script(keys: list[bytes]) -> bytes:
    return bytes([OP["RETURN"]]) + b"".join(push(k) for k in keys)


def state_prefix(n: int) -> bytes:
    """TapLeaf tag || leaf version || compact size || OP_RETURN."""
    return TL2 + b"\xc0" + bytes([1 + 33 * n]) + bytes([OP["RETURN"]])


def p2tr_key_spk(x: bytes) -> bytes:
    return b"\x51\x20" + x


# --- script fragments ------------------------------------------------------

def frag_num8() -> bytes:
    """Top: positive script number < 2^31 -> its 8-byte little-endian form."""
    z = lambda k: push(bytes(k))  # noqa: E731
    return b"".join((op("SIZE", "DUP"), num(1), op("EQUAL", "IF", "DROP"), z(7), op("CAT", "ELSE", "DUP"), num(2),
                     op("EQUAL", "IF", "DROP"), z(6), op("CAT", "ELSE", "DUP"), num(3), op("EQUAL", "IF", "DROP"),
                     z(5), op("CAT", "ELSE"), num(4), op("EQUALVERIFY"), z(4), op("CAT", "ENDIF", "ENDIF", "ENDIF")))


def frag_digits(oracle, prefix) -> bytes:
    out = b""
    for j, bit in enumerate(prefix):
        out += push(oracle.R[j]) + op("SWAP", "CAT") + push(oracle.msg(j, bit)) + push(oracle.P) + op("CSFS", "VERIFY")
    return out


def frag_state_copy(n: int, replace: int | None = None) -> bytes:
    """Keys K_1..K_n on top (K_n topmost). Leaves them and pushes
    TapLeaf(state). With `replace`=p, K_p is taken from the altstack."""
    out, have = b"", False
    for j in range(1, n + 1):
        depth = n - j + (1 if have else 0)
        item = op("FROMALT") if j == replace else num(depth) + op("PICK")
        out += item + push(b"\x20") + op("SWAP", "CAT")
        if have:
            out += op("CAT")
        have = True
    return out + push(state_prefix(n)) + op("SWAP", "CAT", "SHA256")


def frag_state_consume(n: int) -> bytes:
    """Consumes K_1..K_n (K_n topmost); pushes TapLeaf(state)."""
    out = push(b"\x20") + op("SWAP", "CAT")
    for _ in range(n - 1):
        out += op("SWAP") + push(b"\x20") + op("SWAP", "CAT", "SWAP", "CAT")
    return out + push(state_prefix(n)) + op("SWAP", "CAT", "SHA256")


def frag_branch_spk_hash() -> bytes:
    """[a b] -> SHA256(0x22 || 0x52 0x20 || TapBranch(a||b)) (= sha_scriptpubkeys)."""
    return op("CAT") + push(TB2) + op("SWAP", "CAT", "SHA256") + push(b"\x22\x52\x20") + op("SWAP", "CAT", "SHA256")


def frag_outputs_consume(amounts: list[int]) -> bytes:
    """Consumes K_1..K_n (K_n topmost); pushes SHA256 of the outputs paying
    amounts[j] to P2TR(K_j), in key order, zero amounts omitted."""
    out, have = b"", False
    for j in range(len(amounts) - 1, -1, -1):
        hdr = push(struct.pack("<Q", amounts[j]) + b"\x22\x51\x20")
        if not have:
            out += (hdr + op("SWAP", "CAT")) if amounts[j] else op("DROP")
            have = have or amounts[j] > 0
        else:
            out += (op("SWAP") + hdr + op("SWAP", "CAT", "SWAP", "CAT")) if amounts[j] else op("NIP")
    if not have:
        raise ValueError("no positive output")
    return out + op("SHA256")


def frag_txcommit() -> bytes:
    return push(TAG2) + op("SWAP", "CAT", "SHA256") + push(ref.TXCOMMIT_KEY) + op("CHECKSIGVERIFY", "TRUE")


def payout_leaf(oracle, prefix, amounts: list[int], csv: int | None = None) -> bytes:
    """Witness, bottom to top: msg[:74], msg[106:138], msg[170:], C, dir,
    K_1..K_n, s_{k-1}..s_0. dir = 1 iff C < TapLeaf(state)."""
    n = len(amounts)
    s = b""
    if csv is not None:
        s += num(csv) + op("CSV", "DROP")
    s += frag_digits(oracle, prefix)
    s += frag_state_copy(n)                                   # .. C dir K.. H
    s += num(n + 1) + op("ROLL") + num(n + 2) + op("ROLL")    # .. K.. H dir C
    s += op("SWAP", "IF", "SWAP", "ENDIF") + frag_branch_spk_hash() + op("TOALT")
    s += frag_outputs_consume(amounts)                        # pre mid suf sha_out
    s += op("SWAP", "CAT", "CAT", "FROMALT", "SWAP", "CAT", "CAT")
    return s + frag_txcommit()


def transfer_leaf(n: int, p: int, fee: int, floor: int) -> bytes:
    """Witness, bottom to top: msg[:42], msg[106:138], msg[170:], amount_in
    (script number), C, dir_new, dir_old, K_1..K_n, new_key, owner_sig.
    dir_old = 1 iff C < H_old; dir_new = 1 iff H_new < C. p is 1-based."""
    s = num(2 + n - p) + op("PICK", "CHECKSIGVERIFY", "TOALT")   # owner K_p signed this tx
    s += frag_state_copy(n, replace=p) + op("TOALT")             # alt: H_new
    s += frag_state_consume(n)                                    # .. amt C dn do H_old
    s += num(3) + op("PICK", "ROT", "IF", "SWAP", "ENDIF") + frag_branch_spk_hash()   # sha_spk(old)
    s += op("FROMALT", "SWAP", "TOALT")                           # .. amt C dn H_new ; alt sha_spk
    s += op("SWAP", "IF", "SWAP", "ENDIF", "CAT") + push(TB2) + op("SWAP", "CAT", "SHA256")   # root_new
    s += op("SWAP", "DUP") + num(fee) + op("SUB", "DUP") + num(floor) + op("GTE", "VERIFY")
    s += frag_num8() + push(b"\x22\x52\x20") + op("CAT", "ROT", "CAT", "SHA256")           # amt sha_out
    s += op("SWAP") + frag_num8() + op("SHA256", "TOALT")         # pre mid suf sha_out ; alt sha_spk sha_amt
    s += op("SWAP", "CAT", "CAT", "FROMALT", "FROMALT", "CAT", "SWAP", "CAT", "CAT")
    return s + frag_txcommit()


# --- contract --------------------------------------------------------------

@dataclass
class Leaf:
    kind: str                  # cet | refund | transfer
    script: bytes
    amounts: list | None = None
    rng: object = None
    party: int | None = None


@dataclass
class Coin:
    txid: str
    vout: int
    value: int
    keys: list


class K2Contract:
    def __init__(self, oracle, parties: list[str], ranges: list, refund_amounts: list[int], *,
                 refund_csv: int = 144, transfer_fee: int = 500, settle_floor: int):
        """ranges: objects with prefix_bits, min/max_price_usd and payouts
        (dict party -> sats)."""
        self.oracle, self.parties, self.n = oracle, parties, len(parties)
        self.refund_csv, self.transfer_fee = refund_csv, transfer_fee
        self.settle_floor = settle_floor
        self.leaves: list[Leaf] = []
        for r in ranges:
            amts = [r.payouts.get(p, 0) for p in parties]
            self.leaves.append(Leaf("cet", payout_leaf(oracle, r.prefix_bits, amts), amts, r))
        self.leaves.append(Leaf("refund", payout_leaf(oracle, (), refund_amounts, refund_csv), list(refund_amounts)))
        for i in range(self.n):
            self.leaves.append(Leaf("transfer", transfer_leaf(self.n, i + 1, transfer_fee, settle_floor), party=i))
        self.C, self.paths = merkle_tree([l.script for l in self.leaves])

    # state / addresses
    def h_state(self, keys) -> bytes:
        return ref.tapleaf(state_script(keys))

    def spk(self, keys) -> bytes:
        return b"\x52\x20" + ref.tapbranch(self.C, self.h_state(keys))

    def control(self, i: int, keys) -> bytes:
        return b"\xc0" + b"".join(self.paths[i]) + self.h_state(keys)

    def index(self, kind: str, *, price: int | None = None, party: str | None = None) -> int:
        for i, l in enumerate(self.leaves):
            if l.kind != kind:
                continue
            if kind == "cet" and l.rng.matches_price(price, self.oracle.num_bits):
                return i
            if kind == "refund":
                return i
            if kind == "transfer" and self.parties[l.party] == party:
                return i
        raise ValueError(f"no {kind} leaf")

    def _dir(self, h: bytes) -> bytes:
        return b"\x01" if self.C < h else b""

    # spends
    def payout(self, coin: Coin, leaf_index: int, attest: list[bytes], *, claimed_keys=None, pay_keys=None,
               amounts=None, witness_for: Tx | None = None) -> Tx:
        """Settle (CET) or refund. claimed_keys: owner list presented in the
        witness (default: the coin's real state); pay_keys / amounts:
        what the transaction actually pays (negative controls)."""
        leaf = self.leaves[leaf_index]
        claimed = claimed_keys or coin.keys
        payees = pay_keys or claimed
        amts = amounts or leaf.amounts
        seq = self.refund_csv if leaf.kind == "refund" else 0xFFFFFFFD
        outs = tuple(TxOut(a, p2tr_key_spk(k)) for a, k in zip(amts, payees) if a > 0)
        tx = Tx((TxIn(coin.txid, coin.vout, seq),), outs)
        basis = witness_for or tx
        msg = sigmsg_scriptpath(basis, 0, [Prevout(coin.value, self.spk(coin.keys))], leaf.script, key_version=2)
        w = [msg[:74], msg[106:138], msg[170:], self.C, self._dir(self.h_state(claimed))] + list(claimed)
        k = len(leaf.rng.prefix_bits) if leaf.kind == "cet" else 0
        w += list(reversed(attest[:k]))
        return tx.with_witness(0, w + [leaf.script, self.control(leaf_index, coin.keys)])

    def transfer(self, coin: Coin, party: str, new_key: bytes, signer_secret: int, *, claimed_keys=None,
                 out_keys=None, out_value: int | None = None) -> tuple[Tx, Coin]:
        """Move `party`'s position to new_key. out_keys / out_value override
        the actual output (negative controls)."""
        i = self.index("transfer", party=party)
        leaf = self.leaves[i]
        p = self.parties.index(party)
        claimed = claimed_keys or coin.keys
        new_keys = list(claimed)
        new_keys[p] = new_key
        value = out_value if out_value is not None else coin.value - self.transfer_fee
        tx = Tx((TxIn(coin.txid, coin.vout),), (TxOut(value, self.spk(out_keys or new_keys)),))
        prev = [Prevout(coin.value, self.spk(coin.keys))]
        msg = sigmsg_scriptpath(tx, 0, prev, leaf.script, key_version=2)
        sig = secp.sign(signer_secret, sighash_scriptpath(tx, 0, prev, leaf.script, key_version=0))
        h_new, h_old = self.h_state(new_keys), self.h_state(claimed)
        w = [msg[:42], msg[106:138], msg[170:], enc_num(coin.value), self.C,
             b"\x01" if h_new < self.C else b"", self._dir(h_old)] + list(claimed) + [new_key, sig]
        tx = tx.with_witness(0, w + [leaf.script, self.control(i, coin.keys)])
        return tx, Coin(tx.txid, 0, value, out_keys or new_keys)

    def summary(self) -> dict:
        cets = [l for l in self.leaves if l.kind == "cet"]
        return {"parties": self.parties, "cet_leaves": len(cets), "leaves": len(self.leaves),
                "tree_depth_max": max(len(p) for p in self.paths) + 1, "C": self.C.hex(),
                "leaf_bytes_max": max(len(l.script) for l in self.leaves),
                "transfer_leaf_bytes": len(self.leaves[-1].script), "refund_csv": self.refund_csv,
                "transfer_fee": self.transfer_fee, "settle_floor": self.settle_floor}


# --- constructors ----------------------------------------------------------

@dataclass(frozen=True)
class _Range:
    prefix_bits: tuple
    min_price_usd: int
    max_price_usd: int
    payouts: dict

    def matches_price(self, price: int, num_bits: int) -> bool:
        p = min(price, (1 << num_bits) - 1)
        return self.min_price_usd <= p <= self.max_price_usd


def single_trade(oracle, spec: InverseContractSpec, *, max_error_sats: int, settle_fee: int, **kw) -> K2Contract:
    ranges = [_Range(c.prefix_bits, c.min_price_usd, c.max_price_usd,
                     {"long": c.payout.long_sats, "short": c.payout.short_sats})
              for c in compress_cet_ranges(spec, oracle.num_bits, max_error_sats)]
    return K2Contract(oracle, ["long", "short"], ranges, [spec.long_margin_sats, spec.short_margin_sats],
                      settle_floor=spec.total_collateral_sats + settle_fee, **kw)


def book(oracle, trades: list[BookTrade], parties: list[str], *, max_error_sats: int, settle_fee: int,
         **kw) -> K2Contract:
    ranges = compress_book_ranges(trades, oracle.num_bits, max_error_sats)
    refund = {p: 0 for p in parties}
    for t in trades:
        refund[t.long_party] += t.spec.long_margin_sats
        refund[t.short_party] += t.spec.short_margin_sats
    total = sum(t.spec.total_collateral_sats for t in trades)
    return K2Contract(oracle, parties, ranges, [refund[p] for p in parties], settle_floor=total + settle_fee, **kw)
