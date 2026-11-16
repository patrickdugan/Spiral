"""A public, redacted receipt bundle, addressed as a CIDv1 raw SHA-256 block.

This prepares bytes for IPFS/Filecoin ingestion. A CID is not a storage deal.
"""
import base64
import hashlib

from .domain import canonical

PUBLIC_FIELDS = {"id", "namespace", "state", "evidence_level", "rail", "network", "amount_sats",
                 "statement_sha256", "proof_sha256", "checked_at", "meaning"}


def bundle(receipts: list[dict]) -> tuple[bytes, dict]:
    data = canonical({"schema": "proof-grove/public-receipts/v1",
                      "receipts": [{k: r[k] for k in sorted(PUBLIC_FIELDS) if k in r} for r in receipts],
                      "storage": "local-only; no Filecoin deal submitted"})
    digest = hashlib.sha256(data).digest()
    cid = "b" + base64.b32encode(b"\x01\x55\x12\x20" + digest).decode().lower().rstrip("=")
    return data, {"cid": cid, "sha256": digest.hex(), "bytes": len(data), "codec": "raw",
                  "storage_state": "local-only", "deal_id": None,
                  "redactions": ["beneficiary", "intent_id", "outpoint", "chain_tip", "Cashu secrets and proofs"]}
