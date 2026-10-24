"""Hash-chained receipt ledger for the control module.

The record format is Control-Harness's receipt record, byte for byte: one JSON
object per line with ``index``, ``kind``, ``payload``, ``previous_hash`` and
``hash``, where ``hash`` is the SHA-256 of the sorted-key, compact,
ASCII-escaped JSON of the record without ``hash``, and the first
``previous_hash`` is 64 zeros. Control-Harness's v1 and v2 ledgers therefore
verify here, and its tests check that both sides compute the same digests.

The kind set is Control-Harness's v1 and v2 kinds plus the control kinds (v3).
``grant_issued`` and ``grant_expired`` keep their v2 meaning, principal
authorization grants; control-module leases use the ``lease_*`` kinds. Payloads
may not contain floats. Unlike v1 and v2, a ledger can be reopened, because the
control module must survive a restart and its state is a fold over the ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


GENESIS_HASH = "0" * 64
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECORD_FIELDS = {"index", "kind", "payload", "previous_hash", "hash"}
KINDS_V1 = frozenset({"run_start", "action_proposed", "monitor_decision", "environment_transition", "run_end"})
KINDS_V2 = KINDS_V1 | {"contract_amended", "grant_issued", "grant_expired", "delegation_spawned", "probe"}
CONTROL_KINDS = frozenset(
    {
        "control_decision",
        "lease_issued",
        "lease_consumed",
        "lease_expired",
        "tool_result",
        "escalation",
        "delegation_returned",
        "environment_view",
        "model_turn",
        "context_packet",
        "context_compacted",
        "skill_loaded",
        "phase_entered",
        "bypass_detected",
        "controller_turn",
        "intervention",
    }
)
RECEIPT_KINDS_V3 = KINDS_V2 | CONTROL_KINDS


class ReceiptVerificationError(ValueError):
    """Raised when a receipt stream violates the ledger contract."""


class FloatInPayload(TypeError):
    """Raised when a hashed payload contains a float; amounts must be integers or strings."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def receipt_digest(record_without_hash: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(record_without_hash)).hexdigest()


def reject_floats(value: Any, path: str = "payload") -> None:
    if isinstance(value, float):
        raise FloatInPayload(f"float at {path}; use an integer or a decimal string")
    if isinstance(value, Mapping):
        for key, item in value.items():
            reject_floats(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_floats(item, f"{path}[{index}]")


class ReceiptLedger:
    """Append-only JSONL hash chain. A new ledger refuses an existing path."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.exists():
            raise FileExistsError(f"receipt path already exists: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._index = 0
        self._previous_hash = GENESIS_HASH

    @property
    def record_count(self) -> int:
        return self._index

    @property
    def last_hash(self) -> str:
        return self._previous_hash

    def append(self, kind: str, payload: Mapping[str, Any]) -> str:
        if kind not in RECEIPT_KINDS_V3:
            raise ValueError(f"unsupported receipt kind: {kind}")
        if not isinstance(payload, Mapping):
            raise TypeError("receipt payload must be a mapping")
        reject_floats(payload)
        record: dict[str, Any] = {
            "index": self._index,
            "kind": kind,
            "payload": dict(payload),
            "previous_hash": self._previous_hash,
        }
        record["hash"] = receipt_digest(record)
        with self.path.open("ab") as handle:
            handle.write(canonical_json_bytes(record) + b"\n")
        self._index += 1
        self._previous_hash = str(record["hash"])
        return self._previous_hash

    @classmethod
    def resume(cls, path: str | Path) -> tuple["ReceiptLedger", list[dict[str, Any]]]:
        """Reopen an unclosed ledger after verifying it; return it with its records."""
        records = parse_receipts(path)
        ok, message = verify_receipts(records, require_closed=False)
        if not ok:
            raise ReceiptVerificationError(message)
        if records[-1]["kind"] == "run_end":
            raise ReceiptVerificationError("ledger is closed; a closed run cannot be resumed")
        ledger = cls.__new__(cls)
        ledger.path = Path(path)
        ledger._index = len(records)
        ledger._previous_hash = str(records[-1]["hash"])
        return ledger, records


def parse_receipts(path: str | Path) -> list[dict[str, Any]]:
    ledger_path = Path(path)
    if not ledger_path.is_file():
        raise ReceiptVerificationError(f"receipt file does not exist: {ledger_path}")
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ReceiptVerificationError(f"invalid JSON at line {line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise ReceiptVerificationError(f"record at line {line_number} is not an object")
        records.append(record)
    return records


def verify_receipts(records: Iterable[Mapping[str, Any]], *, require_closed: bool = True) -> tuple[bool, str]:
    previous_hash = GENESIS_HASH
    expected_index = 0
    observed = list(records)
    if not observed:
        return False, "receipt chain is empty"
    for record in observed:
        line = expected_index + 1
        if set(record) != RECORD_FIELDS:
            return False, f"unexpected record fields at line {line}"
        if record.get("index") != expected_index:
            return False, f"unexpected index at line {line}"
        if record.get("kind") not in RECEIPT_KINDS_V3:
            return False, f"unsupported kind at line {line}"
        if not isinstance(record.get("payload"), dict):
            return False, f"payload is not an object at line {line}"
        try:
            reject_floats(record["payload"])
        except FloatInPayload as exc:
            return False, f"{exc} at line {line}"
        if record.get("previous_hash") != previous_hash:
            return False, f"broken previous_hash at line {line}"
        observed_hash = record.get("hash")
        if not isinstance(observed_hash, str) or not SHA256_RE.fullmatch(observed_hash):
            return False, f"invalid hash at line {line}"
        material = dict(record)
        material.pop("hash")
        if receipt_digest(material) != observed_hash:
            return False, f"hash mismatch at line {line}"
        previous_hash = observed_hash
        expected_index += 1
    if observed[0].get("kind") != "run_start":
        return False, "first record is not run_start"
    if require_closed and observed[-1].get("kind") != "run_end":
        return False, "last record is not run_end"
    return True, f"verified {expected_index} records; root={previous_hash}"


def verify_receipt_file(path: str | Path, *, require_closed: bool = True) -> tuple[bool, str]:
    try:
        records = parse_receipts(path)
    except ReceiptVerificationError as exc:
        return False, str(exc)
    return verify_receipts(records, require_closed=require_closed)
