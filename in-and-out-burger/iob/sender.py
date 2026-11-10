"""Who sent the payment, so the burger knows where to send the sats back.

Bitcoin has no sender field. The desk uses two rules, in this order:

1. **Declared return script.** An output `OP_RETURN "IOB1" || scriptPubKey` in the payment
   transaction names the payout script. It is covered by the txid, which the M16 proof places
   in a block, so no extra data is needed. Exactly one such output is allowed.
2. **The script input 0 spent.** Reconstructed from what the spend reveals: P2PKH (signature and
   key in scriptSig), P2SH (redeem script), P2SH-wrapped and native P2WPKH and P2WSH (witness).
   Taproot spends are refused: a key-path spend reveals no key, and script-path spends are not
   implemented. Bare P2PK and bare multisig are refused: their spends do not reveal the script.

A witness is not covered by the txid. For rule 2 on a segwit input the order carries a
*sender proof*: header B, the coinbase with its Merkle branch, and the payment transaction's
txid and wtxid branches. The desk checks that header B hashes to the block hash in the proven
statement, that both transactions are in that block, and that the payment's wtxid is under the
coinbase's BIP141 witness commitment. Every byte the desk reads is then bound to the proof.

A spender who builds an unusual script can make rule 2 name a script other than the one they
spent (for example a P2WSH whose witness script looks like a public key). That only redirects
their own payout: the payment transaction, and so the reconstruction, is theirs alone.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import btc
from .errors import Refusal

RETURN_MAGIC = b"IOB1"
COMMITMENT_PREFIX = bytes.fromhex("6a24aa21a9ed")


@dataclass(frozen=True)
class Sender:
    script_pubkey: bytes
    kind: str
    rule: str  # "declared" or "input0:<how>"


def declared_return(tx: btc.Tx):
    found = []
    for o in tx.outputs:
        spk = o.script_pubkey
        if spk[:1] != b"\x6a":
            continue
        items = btc.parse_pushes(spk[1:])
        if items and len(items) == 1 and items[0].startswith(RETURN_MAGIC):
            found.append(items[0][len(RETURN_MAGIC) :])
    if not found:
        return None
    if len(found) > 1:
        raise Refusal("ambiguous_return_script", f"{len(found)} IOB1 outputs")
    spk = found[0]
    kind = btc.script_kind(spk)
    if kind is None:
        raise Refusal("return_script_nonstandard", spk.hex())
    return Sender(spk, kind, "declared")


def _strip_annex(witness: list) -> list:
    if len(witness) >= 2 and witness[-1][:1] == b"\x50":
        return witness[:-1]
    return witness


def _looks_taproot(witness: list) -> str | None:
    w = _strip_annex(witness)
    if len(w) == 1 and len(w[0]) in (64, 65):
        return "taproot_key_path"
    # A witness v0 script starting 0xc0/0xc1 cannot execute (those opcodes are invalid outside
    # tapscript), so a last item shaped like a control block is a taproot script-path spend.
    if len(w) >= 2:
        cb = w[-1]
        if len(cb) >= 33 and (len(cb) - 33) % 32 == 0 and cb[0] & 0xFE == 0xC0:
            return "taproot_script_path"
    return None


def from_input(txin: btc.TxIn) -> Sender:
    pushes = btc.parse_pushes(txin.script_sig)
    if pushes is None:
        raise Refusal("sender_unresolvable", "scriptSig is not push-only")
    wit = txin.witness

    if not wit:
        if not pushes:
            raise Refusal("sender_unresolvable", "empty scriptSig and no witness")
        if len(pushes) == 2 and btc.is_der_signature(pushes[0]) and btc.is_pubkey(pushes[1]):
            return Sender(btc.p2pkh(btc.hash160(pushes[1])), "p2pkh", "input0:p2pkh")
        redeem = pushes[-1]
        if not redeem or btc.is_der_signature(redeem):
            raise Refusal("sender_unresolvable", "bare P2PK or multisig spend does not reveal its script")
        return Sender(btc.p2sh(btc.hash160(redeem)), "p2sh", "input0:p2sh")

    tap = _looks_taproot(wit)
    if tap and not txin.script_sig:
        raise Refusal("sender_unresolvable", f"{tap}: use an IOB1 return output")

    if len(wit) == 2 and btc.is_der_signature(wit[0]) and btc.is_compressed_pubkey(wit[1]):
        program = b"\x00\x14" + btc.hash160(wit[1])
        how = "p2wpkh"
    else:
        program = b"\x00\x20" + btc.sha256(wit[-1])
        how = "p2wsh"

    if not txin.script_sig:
        return Sender(program, how, f"input0:{how}")

    # Nested segwit: scriptSig is exactly one push of the witness program, and the program must
    # match what the witness reveals.
    if len(pushes) != 1 or btc.script_kind(pushes[0]) not in ("p2wpkh", "p2wsh"):
        raise Refusal("sender_unresolvable", "witness spend with a scriptSig that is not one witness program")
    if pushes[0] != program:
        raise Refusal("sender_unresolvable", "P2SH witness program does not match the witness")
    return Sender(btc.p2sh(btc.hash160(pushes[0])), "p2sh", f"input0:p2sh-{how}")


def resolve(tx: btc.Tx) -> Sender:
    declared = declared_return(tx)
    if declared:
        return declared
    return from_input(tx.inputs[0])


# --- sender proof -----------------------------------------------------------------------------

PROOF_VERSION = "IOB-SP1"


def build_proof(block: bytes, txid_display: str) -> dict:
    """Cut a sender proof for one transaction out of a full block."""
    header, txs = btc.parse_block(block)
    txids = [t.txid() for t in txs]
    want = bytes.fromhex(txid_display)[::-1]
    if want not in txids:
        raise ValueError(f"{txid_display} is not in this block")
    index = txids.index(want)
    if index == 0:
        raise ValueError("the coinbase cannot be a payment")
    wtxids = [b"\x00" * 32] + [t.wtxid() for t in txs[1:]]
    return {
        "version": PROOF_VERSION,
        "header": header.hex(),
        "coinbase": txs[0].serialize().hex(),
        "coinbase_branch": [h.hex() for h in btc.merkle_branch(txids, 0)],
        "index": index,
        "tx": txs[index].serialize().hex(),
        "tx_branch": [h.hex() for h in btc.merkle_branch(txids, index)],
        "wtx_branch": [h.hex() for h in btc.merkle_branch(wtxids, index)],
    }


def _hexlist(xs) -> list:
    out = []
    for x in xs:
        b = bytes.fromhex(x)
        if len(b) != 32:
            raise Refusal("sender_proof_malformed", "branch node is not 32 bytes")
        out.append(b)
    return out


def verify_proof(sp: dict, block_hash_display: str, tx: btc.Tx) -> None:
    """Bind `tx`'s witness to the proven block. Raises Refusal on any mismatch."""
    try:
        if sp.get("version") != PROOF_VERSION:
            raise Refusal("sender_proof_malformed", f"version {sp.get('version')!r}")
        header = bytes.fromhex(sp["header"])
        coinbase_raw = bytes.fromhex(sp["coinbase"])
        cb_branch = _hexlist(sp["coinbase_branch"])
        tx_branch = _hexlist(sp["tx_branch"])
        wtx_branch = _hexlist(sp["wtx_branch"])
        index = int(sp["index"])
    except (KeyError, TypeError, ValueError) as e:
        raise Refusal("sender_proof_malformed", str(e)) from None
    if len(header) != 80:
        raise Refusal("sender_proof_malformed", "header is not 80 bytes")
    if btc.sha256d(header)[::-1].hex() != block_hash_display:
        raise Refusal("sender_proof_header", "header does not hash to the proven block")
    if not (len(cb_branch) == len(tx_branch) == len(wtx_branch)):
        raise Refusal("sender_proof_malformed", "branches differ in depth")
    if index <= 0:
        raise Refusal("sender_proof_malformed", "payment index must be above 0")

    try:
        cb = btc.parse_tx(coinbase_raw)
    except btc.ParseError as e:
        raise Refusal("sender_proof_coinbase", f"unparseable: {e}") from None
    cbin = cb.inputs[0]
    if len(cb.inputs) != 1 or cbin.prev_txid != b"\x00" * 32 or cbin.prev_vout != 0xFFFFFFFF:
        raise Refusal("sender_proof_coinbase", "not a coinbase")
    # A 64-byte transaction can pose as an inner Merkle node; refuse the shape outright.
    if len(cb.stripped()) == 64 or len(tx.stripped()) == 64 or len(tx.serialize()) == 64:
        raise Refusal("sender_proof_coinbase", "64-byte transaction")

    root = header[36:68]
    try:
        if btc.root_from_branch(cb.txid(), cb_branch, 0) != root:
            raise Refusal("sender_proof_coinbase", "coinbase is not in the proven block")
        if btc.root_from_branch(tx.txid(), tx_branch, index) != root:
            raise Refusal("sender_proof_tx", "payment txid is not at that index in the proven block")
        witness_root = btc.root_from_branch(tx.wtxid(), wtx_branch, index)
    except btc.ParseError as e:
        raise Refusal("sender_proof_malformed", str(e)) from None

    if len(cbin.witness) != 1 or len(cbin.witness[0]) != 32:
        raise Refusal("sender_proof_witness", "coinbase witness reserved value missing")
    commitments = [o.script_pubkey for o in cb.outputs if len(o.script_pubkey) >= 38 and o.script_pubkey[:6] == COMMITMENT_PREFIX]
    if not commitments:
        raise Refusal("sender_proof_witness", "block has no witness commitment")
    # BIP141: the commitment is the matching output with the highest index.
    if commitments[-1][6:38] != btc.sha256d(witness_root + cbin.witness[0]):
        raise Refusal("sender_proof_witness", "payment wtxid is not under the block's witness commitment")
