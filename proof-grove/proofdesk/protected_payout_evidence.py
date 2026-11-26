"""Verify a V3 holder exit against a checkpoint pinned outside the receipt.

The observer records the active payout block hash and height from its own
regtest Core node and obtains the original verified reserve bundle ID. Use
those values even when the receipt advertises different ones.

    python -m proofdesk.protected_payout_evidence RECEIPT --bundle-id ID \
        --anchor-height HEIGHT --anchor-hash BLOCK_HASH
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from .cashu import compressed_point
from .domain import digest, hash32, positive
from .protected_reserve import GENESIS, HEX, PLAN_FIELDS, V3_BUNDLE_SCHEMA, V3_PLAN_SCHEMA, _witness_script
from .verifier import read_bounded


CHAIN_SCHEMA = "proof-grove/protected-payout-chain/v1"
MAX_HEADERS = 64
MAX_LEAVES = 256
MAX_TX_BYTES = 64 * 1024
WITNESS_MARKER = bytes.fromhex("6a24aa21a9ed")


def _hash256(value):
    return hashlib.sha256(hashlib.sha256(value).digest()).digest()


def _raw(value, limit, size=None):
    if (not isinstance(value, str) or len(value) > 2 * limit or not HEX.fullmatch(value)
            or (size is not None and len(value) != 2 * size)):
        raise ValueError("invalid Bitcoin evidence hex")
    return bytes.fromhex(value)


class _Reader:
    def __init__(self, raw):
        self.raw, self.offset = raw, 0

    def take(self, size):
        end = self.offset + size
        if end > len(self.raw):
            raise ValueError("truncated Bitcoin transaction")
        data = self.raw[self.offset:end]
        self.offset = end
        return data

    def count(self, limit):
        marker = self.take(1)[0]
        if marker < 253:
            value = marker
        else:
            width = {253: 2, 254: 4, 255: 8}[marker]
            value = int.from_bytes(self.take(width), "little")
            if value < {253: 253, 254: 2**16, 255: 2**32}[marker]:
                raise ValueError("nonminimal Bitcoin CompactSize")
        if value > limit:
            raise ValueError("Bitcoin transaction field exceeds fixture limit")
        return value

    def vector(self):
        return self.take(self.count(MAX_TX_BYTES))


@dataclass(frozen=True)
class _Transaction:
    txid: str
    wtxid: str
    version: bytes
    locktime: bytes
    inputs: list
    outputs: list
    output_bytes: bytes
    witnesses: list


def _transaction(encoded):
    raw = _raw(encoded, MAX_TX_BYTES)
    reader = _Reader(raw)
    version = reader.take(4)
    segregated = raw[4:5] == b"\x00"
    if segregated and reader.take(2) != b"\x00\x01":
        raise ValueError("invalid Bitcoin witness flag")
    base_start = reader.offset
    inputs = [(reader.take(36), reader.vector(), reader.take(4)) for _ in range(reader.count(MAX_LEAVES))]
    output_count = reader.count(MAX_LEAVES)
    output_start = reader.offset
    outputs = [(int.from_bytes(reader.take(8), "little"), reader.vector()) for _ in range(output_count)]
    base_end = reader.offset
    witnesses = [[reader.vector() for _ in range(reader.count(MAX_LEAVES))] for _ in inputs] if segregated else []
    locktime = reader.take(4)
    if not inputs or not outputs or (segregated and not any(witnesses)) or reader.offset != len(raw):
        raise ValueError("invalid Bitcoin transaction framing")
    stripped = version + raw[base_start:base_end] + locktime
    return _Transaction(_hash256(stripped)[::-1].hex(), _hash256(raw)[::-1].hex(), version, locktime,
                        inputs, outputs, raw[output_start:base_end], witnesses)


def _leaves(ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_LEAVES:
        raise ValueError("invalid Bitcoin block transaction count")
    for value in ids:
        hash32(value, "transaction_id")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate Bitcoin block transaction ID")
    return [bytes.fromhex(value)[::-1] for value in ids]


def _merkle_root(leaves):
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves = [*leaves, leaves[-1]]
        leaves = [_hash256(leaves[i] + leaves[i + 1]) for i in range(0, len(leaves), 2)]
    return leaves[0]


def capture(rpc, funding_height, payout_height, funding_block, payout_block):
    """Export the small regtest blocks' ordered leaves while the chain is live."""
    if not 1 <= payout_height - funding_height < MAX_HEADERS:
        raise ValueError("invalid protected payout header interval")
    blocks = [rpc("getblockhash", [height]) for height in range(funding_height, payout_height + 1)]
    if (blocks[0], blocks[-1]) != (funding_block, payout_block):
        raise ValueError("protected payout block left the active chain")
    headers = [rpc("getblockheader", [block, False]) for block in blocks]
    funding = rpc("getblock", [funding_block, 1])
    payout = rpc("getblock", [payout_block, 2])
    payout_txids = [transaction["txid"] for transaction in payout["tx"]]
    payout_wtxids = ["00" * 32] + [transaction["hash"] for transaction in payout["tx"][1:]]
    _leaves(funding["tx"])
    _leaves(payout_txids)
    _leaves(payout_wtxids)
    if (funding.get("hash"), payout.get("hash"), rpc("getblockhash", [payout_height]),
            funding.get("height"), payout.get("height")) != (
            funding_block, payout_block, payout_block, funding_height, payout_height):
        raise ValueError("protected payout chain changed during capture")
    if any(type(block.get("nTx")) is not int or block["nTx"] != len(block["tx"]) for block in (funding, payout)):
        raise ValueError("invalid captured Bitcoin block transaction count")
    return {"schema": CHAIN_SCHEMA, "headers": headers, "funding_txids": funding["tx"],
            "payout_txids": payout_txids, "payout_wtxids": payout_wtxids,
            "payout_coinbase": payout["tx"][0]["hex"]}


def _verify_inclusion(evidence, headers, funding, payout, *, payout_index=-1):
    funding_ids, payout_ids, witness_ids = (evidence[name] for name in ("funding_txids", "payout_txids", "payout_wtxids"))
    funding_leaves, payout_leaves, witness_leaves = map(_leaves, (funding_ids, payout_ids, witness_ids))
    if (funding.txid not in funding_ids[1:] or payout.txid not in payout_ids[1:]
            or _merkle_root(funding_leaves) != headers[0][36:68]
            or _merkle_root(payout_leaves) != headers[payout_index][36:68]):
        raise ValueError("funding or payout txid is outside the pinned headers")
    index = payout_ids.index(payout.txid)
    if (len(witness_ids) != len(payout_ids) or witness_leaves[0] != bytes(32)
            or witness_ids[index] != payout.wtxid):
        raise ValueError("payout witness leaf does not match its transaction index")
    coinbase = _transaction(evidence["payout_coinbase"])
    if (coinbase.txid != payout_ids[0] or len(coinbase.inputs) != 1
            or coinbase.inputs[0][0] != bytes(32) + b"\xff" * 4
            or len(coinbase.witnesses) != 1 or len(coinbase.witnesses[0]) != 1
            or len(coinbase.witnesses[0][0]) != 32):
        raise ValueError("invalid BIP141 coinbase proof")
    commitments = [script[6:38] for _, script in coinbase.outputs if len(script) >= 38 and script.startswith(WITNESS_MARKER)]
    expected = _hash256(_merkle_root(witness_leaves) + coinbase.witnesses[0][0])
    if not commitments or commitments[-1] != expected:
        raise ValueError("payout witness is outside the pinned BIP141 commitment")


def _verify_signature(openssl, pubkey, signature, sighash):
    with tempfile.TemporaryDirectory(prefix="proof-grove-holder-signature-") as directory:
        key, sig, message = [Path(directory) / name for name in ("key.der", "sig.der", "sighash.bin")]
        key.write_bytes(bytes.fromhex("3036301006072a8648ce3d020106052b8104000a032200") + pubkey)
        sig.write_bytes(signature)
        message.write_bytes(sighash)
        result = subprocess.run([openssl, "pkeyutl", "-verify", "-pubin", "-keyform", "DER", "-inkey", str(key),
                                 "-sigfile", str(sig), "-in", str(message), "-pkeyopt", "digest:sha256"],
                                capture_output=True, check=False, timeout=10)
    if result.returncode != 0:
        raise ValueError("holder BIP143 signature verification failed")


def _verify_holder_witness(tx, previous, plan, openssl):
    sequence = positive(plan["delay_blocks"], "delay_blocks", 65535).to_bytes(4, "little")
    reserve = positive(plan["reserve_sats"], "reserve_sats")
    script = _raw(plan["witness_script"], 252)
    if (tx.version != b"\x02\0\0\0" or tx.locktime != bytes(4)
            or tx.inputs != [(previous, b"", sequence)]
            or len(tx.witnesses) != 1 or len(tx.witnesses[0]) != 4):
        raise ValueError("protected holder transaction shape mismatch")
    branch, signature, preimage, witness_script = tx.witnesses[0]
    if branch or signature[-1:] != b"\x01" or preimage.hex() != plan["issuance_preimage"] or witness_script != script:
        raise ValueError("protected payout witness or SIGHASH_ALL mismatch")
    sighash = _hash256(b"".join((tx.version, _hash256(previous), _hash256(sequence), previous,
                                 bytes([len(script)]), script, reserve.to_bytes(8, "little"), sequence,
                                 _hash256(tx.output_bytes), tx.locktime, b"\x01\0\0\0")))
    _verify_signature(openssl, _raw(plan["holder_pubkey"], 33, 33), signature[:-1], sighash)


def _v3_plan(bundle, bundle_id):
    hash32(bundle_id, "bundle_id")
    plan = bundle["plan"]
    if (bundle.get("schema") != V3_BUNDLE_SCHEMA or plan.get("schema") != V3_PLAN_SCHEMA
            or plan.get("network") != "regtest" or plan.get("genesis") != GENESIS
            or bundle.get("bundle_id") != bundle_id
            or digest({k: v for k, v in bundle.items() if k != "bundle_id"}) != bundle_id
            or digest({k: v for k, v in plan.items() if k != "plan_id"}) != plan.get("plan_id")):
        raise ValueError("V3 payout reserve bundle pin mismatch")
    return plan


def _pinned_headers(raw_headers, anchor_height, anchor_hash, minimum):
    hash32(anchor_hash, "anchor_hash")
    positive(anchor_height, "anchor_height", 2**31 - 1)
    if (not isinstance(raw_headers, list) or not minimum <= len(raw_headers) <= MAX_HEADERS
            or anchor_height < len(raw_headers)):
        raise ValueError("invalid protected payout header interval")
    headers = [_raw(header, 80, 80) for header in raw_headers]
    hashes = [_hash256(header) for header in headers]
    if (hashes[-1][::-1].hex() != anchor_hash
            or any(header[4:36] != parent for header, parent in zip(headers[1:], hashes))):
        raise ValueError("protected payout headers differ from the checkpoint")
    return headers, hashes[0][::-1].hex(), anchor_height - len(headers) + 1


def _v3_amounts_and_script(plan, delay):
    reserve = positive(plan["reserve_sats"], "reserve_sats")
    amount = positive(plan["payout_sats"], "payout_sats")
    fee = positive(plan["fee_sats"], "fee_sats")
    destination = _raw(plan["payout_script"], MAX_TX_BYTES)
    if (not compressed_point(plan["holder_pubkey"]) or not compressed_point(plan["mint_pubkey"])
            or plan["holder_pubkey"] == plan["mint_pubkey"]):
        raise ValueError("protected payout requires distinct compressed public keys")
    terms = {k: plan[k] for k in (*PLAN_FIELDS, "network", "genesis", "payout_script")}
    preimage = digest({"schema": "proof-grove/protected-issuance-terms/v3"} | terms)
    commitment = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
    script = _witness_script(plan["holder_pubkey"], plan["mint_pubkey"], delay, commitment)
    funding_script = b"\x00\x20" + hashlib.sha256(script).digest()
    if (funding_script.hex() != plan["funding_script"] or script.hex() != plan["witness_script"]
            or preimage != plan["issuance_preimage"] or commitment != plan["issuance_hash"]
            or reserve - amount != fee or plan["change_sats"] != 0):
        raise ValueError("protected payout differs from the pinned amounts or scripts")
    return reserve, amount, fee, destination, funding_script


def verify(receipt, bundle_id, anchor_height, anchor_hash, *, openssl="openssl"):
    """Verify inclusion and the exact V3 spend under independently obtained pins."""
    bundle = receipt["app_bundle"]
    plan = _v3_plan(bundle, bundle_id)
    if receipt.get("network") != "regtest" or receipt.get("genesis") != GENESIS:
        raise ValueError("V3 payout reserve bundle pin mismatch")
    evidence = receipt["bitcoin_chain_evidence"]
    if evidence.get("schema") != CHAIN_SCHEMA:
        raise ValueError("invalid protected payout header interval")
    headers, funding_block, funding_height = _pinned_headers(evidence["headers"], anchor_height, anchor_hash, 2)
    delay = positive(plan["delay_blocks"], "delay_blocks", 65535)
    outpoint, paid = bundle["funding"], receipt["payout"]
    if (outpoint["block"] != funding_block or paid["block"] != anchor_hash or paid["height"] != anchor_height
            or receipt["mature_holder_check"]["observation"]["funding_height"] != funding_height
            or paid["delay_blocks"] != delay or anchor_height - funding_height < delay):
        raise ValueError("protected payout CSV or height mismatch")
    funding, payout = (_transaction(receipt["public_transactions"][name]) for name in ("funding", "payout"))
    _verify_inclusion(evidence, headers, funding, payout)
    vout = outpoint["vout"]
    reserve, amount, fee, destination, funding_script = _v3_amounts_and_script(plan, delay)
    if (type(vout) is not int or not 0 <= vout < len(funding.outputs) or funding.txid != outpoint["txid"]
            or funding.outputs[vout] != (reserve, funding_script)
            or receipt["reserve"] != outpoint | {"sats": reserve, "script": funding_script.hex()}
            or (paid["txid"], paid["wtxid"], paid["sats"], paid["script"], paid["fee_sats"]) != (
                payout.txid, payout.wtxid, amount, destination.hex(), fee)):
        raise ValueError("protected payout differs from the pinned amounts or scripts")
    previous = bytes.fromhex(funding.txid)[::-1] + vout.to_bytes(4, "little")
    claim_id = hashlib.sha256(b"proof-grove/protected-reserve/v1\0" + bytes.fromhex(GENESIS + funding.txid)
                              + vout.to_bytes(4, "big")).hexdigest()
    if receipt.get("claim_id") != claim_id:
        raise ValueError("protected payout claim differs from the funded outpoint")
    if payout.outputs != [(amount, destination)]:
        raise ValueError("protected payout transaction shape mismatch")
    _verify_holder_witness(payout, previous, plan, openssl)
    return {"schema": "proof-grove/protected-payout-offline-verification/v1", "network": "regtest",
            "bundle_id": bundle_id, "claim_id": claim_id, "anchor_height": anchor_height, "anchor_hash": anchor_hash,
            "funding_txid": funding.txid, "funding_height": funding_height,
            "payout_txid": payout.txid, "payout_wtxid": payout.wtxid, "reserve_sats": reserve,
            "payout_sats": amount, "fee_sats": fee, "relative_delay_blocks": delay,
            "holder_signature_verified": True, "witness_inclusion_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--anchor-height", type=int, required=True)
    parser.add_argument("--anchor-hash", required=True)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args()
    receipt = json.loads(read_bounded(args.receipt, 256 * 1024))
    print(json.dumps(verify(receipt, args.bundle_id, args.anchor_height, args.anchor_hash, openssl=args.openssl), indent=2))


if __name__ == "__main__":
    main()
