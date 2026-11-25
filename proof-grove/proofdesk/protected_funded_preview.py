"""Expose pinned recipient verification and funded evidence in the local recovery demo."""

from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat

from .domain import Refused, hash32, positive
from .verifier import read_bounded


ARCHIVE_LIMIT = 256 * 1024 * 1024
ARTIFACT = re.compile(r"[a-z0-9][a-z0-9.-]{0,126}\.(?:zip|json)")


def local_artifact(manifest, name, suffix):
    if not isinstance(name, str) or not ARTIFACT.fullmatch(name) or not name.endswith(suffix):
        raise Refused("funded_preview_invalid_artifact")
    path = manifest.with_name(name)
    if path.resolve().parent != manifest.parent:
        raise Refused("funded_preview_invalid_artifact")
    return path


@contextmanager
def verified_archive(manifest):
    """Yield the checked file and receipt once the operator's atomic publication arrives."""
    if manifest is None:
        raise Refused("funded_preview_not_configured")
    try:
        publication = json.loads(read_bounded(manifest, 4096))
    except FileNotFoundError:
        yield None
        return
    except (OSError, ValueError) as exc:
        raise Refused("funded_preview_invalid_publication") from exc

    try:
        if publication["schema"] != "proof-grove/funded-preview/v1":
            raise Refused("funded_preview_invalid_publication")
        archive_pin = hash32(publication["archive_sha256"], "archive")
        receipt_pin = hash32(publication["verification_sha256"], "verification receipt")
        statement_pin = hash32(publication["statement_sha256"], "withdrawal statement")
        receipt_path = local_artifact(manifest, publication["verification"], ".json")
        receipt_raw = read_bounded(receipt_path, 128 * 1024)
        if hashlib.sha256(receipt_raw).hexdigest() != receipt_pin:
            raise Refused("funded_preview_verification_changed")
        receipt = json.loads(receipt_raw)
        proof, m14, chain = receipt["m13"], receipt["m14"], receipt["bitcoin"]
        if (receipt["schema"] != "proof-grove/m14/independent-funded-cashu-verification/v1"
                or receipt["archive_sha256"] != archive_pin or proof["statement_sha256"] != statement_pin
                or proof["status"] != "verified" or m14["status"] != "accept_opening_matches_pinned_setup"
                or chain["schema"] != "proof-grove/protected-regtest-block-replay/v1"
                or chain["network"] != "regtest" or type(chain["wallets_loaded"]) is not int
                or chain["wallets_loaded"] != 0):
            raise Refused("funded_preview_unverified")
        hash32(proof["proof_sha256"], "M13 proof")
        hash32(proof["verifier_sha256"], "M13 verifier")
        hash32(m14["setup_sha256"], "M14 setup")
        result = {
            "status": "verified", "network": "regtest", "archive_sha256": archive_pin,
            "statement_sha256": statement_pin, "verification_sha256": receipt_pin,
            "txid": hash32(chain["txid"], "transaction"), "wtxid": hash32(chain["wtxid"], "witness transaction"),
            "height": positive(chain["height"], "height", 4096),
            **{field: positive(receipt[field], field) for field in ("holder_sats", "refund_sats", "fee_sats")},
        }
        source = local_artifact(manifest, publication["archive"], ".zip").open("rb")
    except (OSError, TypeError, KeyError, ValueError, AttributeError) as exc:
        if isinstance(exc, Refused):
            raise
        raise Refused("funded_preview_invalid_publication") from exc

    with source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= ARCHIVE_LIMIT
                or hashlib.file_digest(source, "sha256").hexdigest() != archive_pin):
            raise Refused("funded_preview_archive_changed")
        after = os.fstat(source.fileno())
        if (after.st_size, after.st_mtime_ns) != (info.st_size, info.st_mtime_ns):
            raise Refused("funded_preview_archive_changed")
        source.seek(0)
        yield result, receipt_raw, source, info.st_size
