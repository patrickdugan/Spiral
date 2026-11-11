"""The derived payout key: pay the sender at a fresh key, not at the script they spent from.

A sender that revealed one public key P (P2PKH, P2WPKH, or P2WPKH in P2SH) is paid at the same
script type over

    P' = P + t*G,   t = int(tagged_hash("IOB/payout-key", in_txid || in_vout || P)) mod n

where in_txid is the payment's txid in internal byte order, in_vout is a little-endian u32, and
P is serialized exactly as the spend revealed it (33 or 65 bytes). Its private key is p + t mod n.

Every input to t is public and fixed by the proof (the txid and vout are proven; P is bound by
the txid or by the sender proof), so:
- the payer needs no address of their own in the payment, and no address is paid twice: each
  payment gets its own P';
- anyone can recompute P' from the chain, including a later proof of the payout leg;
- the payer recovers the key with `python -m iob payout-key` and imports it into any wallet that
  takes a WIF descriptor.

Senders that revealed a script rather than one key (P2SH, P2WSH) are paid at that script, and
a declared return script (`IOB1`) is always paid as declared.
"""
from __future__ import annotations

import dataclasses
import struct

from . import btc, ec
from .errors import Refusal

TAG = "IOB/payout-key"
TYPES = ("p2pkh", "p2wpkh", "p2sh-p2wpkh")
WIF_VERSION = {"mainnet": 0x80, "testnet4": 0xEF, "signet": 0xEF, "regtest": 0xEF}
DESCRIPTOR = {"p2pkh": "pkh({})", "p2wpkh": "wpkh({})", "p2sh-p2wpkh": "sh(wpkh({}))"}


def tweak(pubkey: bytes, txid_internal: bytes, vout: int) -> int:
    if len(txid_internal) != 32:
        raise ValueError("txid must be 32 bytes")
    t = int.from_bytes(ec.tagged_hash(TAG, txid_internal + struct.pack("<I", vout) + pubkey), "big")
    if t == 0 or t >= ec.N:
        raise Refusal("derived_key_invalid", "tweak is not a valid scalar")
    return t


def derive_pubkey(pubkey: bytes, txid_internal: bytes, vout: int) -> tuple[bytes, int]:
    """P' and t for a revealed key P. P' keeps P's serialization (compressed or not)."""
    try:
        pt = ec.parse(pubkey)
    except ValueError as e:
        raise Refusal("sender_key_invalid", str(e)) from None
    t = tweak(pubkey, txid_internal, vout)
    out = ec.add(pt, ec.mul(t))
    if out is None:
        raise Refusal("derived_key_invalid", "tweaked key is the point at infinity")
    return ec.serialize(out, compressed=len(pubkey) == 33), t


def script_for(pubkey: bytes, key_type: str) -> bytes:
    h = btc.hash160(pubkey)
    if key_type == "p2pkh":
        return btc.p2pkh(h)
    if key_type == "p2wpkh":
        return btc.p2wpkh(h)
    if key_type == "p2sh-p2wpkh":
        return btc.p2sh(btc.hash160(btc.p2wpkh(h)))
    raise ValueError(f"unknown key type {key_type!r}")


def derive_sender(s, txid_internal: bytes, vout: int):
    """The sender with its payout moved to P'. A declared return or a script sender is returned
    unchanged."""
    if s.pubkey is None:
        return s
    new_pk, t = derive_pubkey(s.pubkey, txid_internal, vout)
    return dataclasses.replace(
        s,
        script_pubkey=script_for(new_pk, s.key_type),
        rule=s.rule + ":derived",
        derived_from={
            "pubkey": s.pubkey.hex(),
            "tweak": f"{t:064x}",
            "derived_pubkey": new_pk.hex(),
            "spent_script_pubkey": s.script_pubkey.hex(),
        },
    )


# --- the payer's side --------------------------------------------------------------------------


def wif_encode(secret: int, network: str, compressed: bool = True) -> str:
    if not 0 < secret < ec.N:
        raise ValueError("private key out of range")
    return btc.base58check_encode(bytes([WIF_VERSION[network]]) + secret.to_bytes(32, "big") + (b"\x01" if compressed else b""))


def wif_decode(wif: str) -> tuple[int, bool, int]:
    """(secret, compressed, version byte)."""
    raw = btc.base58check_decode(wif.strip())
    if raw is None or raw[0] not in (0x80, 0xEF) or len(raw) not in (33, 34) or (len(raw) == 34 and raw[33] != 1):
        raise ValueError("not a WIF private key")
    secret = int.from_bytes(raw[1:33], "big")
    if not 0 < secret < ec.N:
        raise ValueError("private key out of range")
    return secret, len(raw) == 34, raw[0]


def derive_private(secret: int, compressed: bool, txid_internal: bytes, vout: int) -> int:
    """p + t mod n, where t is computed from the public key p*G as the spend revealed it."""
    pub = ec.serialize(ec.mul(secret), compressed)
    return (secret + tweak(pub, txid_internal, vout)) % ec.N


def parse_outpoint(s: str) -> tuple[bytes, int]:
    txid, _, vout = s.partition(":")
    raw = bytes.fromhex(txid)
    if len(raw) != 32 or not vout.isdigit():
        raise ValueError("outpoint must be TXID:VOUT")
    return raw[::-1], int(vout)
