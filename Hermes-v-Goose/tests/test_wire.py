"""The JSON Schemas and the hand-written validators describe the same shapes."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import PAY_ALICE, ROOT, proposal  # noqa: E402

from runtime_control.demo import DEMO_REGISTRY  # noqa: E402
from runtime_control.ledger import RECEIPT_KINDS_V3  # noqa: E402
from runtime_control.wire import (  # noqa: E402
    ACTOR_FIELDS,
    OUTCOME_FIELDS,
    PROPOSAL_FIELDS,
    PROVENANCE_FIELDS,
    RUNTIME_FIELDS,
    SURFACES,
    WireError,
    validate_proposal,
    validate_registry,
)


SCHEMAS = ROOT / "schemas"
WIRE = json.loads((SCHEMAS / "runtime-control-wire.v1.schema.json").read_text(encoding="utf-8"))
OPENED = {"contractHash": "c" * 64, "registryHash": "r" * 64, "runId": "run-fixture"}


class WireSchemaTests(unittest.TestCase):
    def test_schemas_are_draft_2020_12_with_closed_roots(self) -> None:
        for path in SCHEMAS.glob("*.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema", path.name)
            self.assertFalse(schema["additionalProperties"], path.name)
            self.assertTrue(schema["required"], path.name)

    def test_receipt_schema_kinds_match_the_ledger(self) -> None:
        receipts = json.loads((SCHEMAS / "receipt-record.v3.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(receipts["properties"]["kind"]["enum"]), set(RECEIPT_KINDS_V3))

    def test_schema_fields_match_validator_fields(self) -> None:
        defs = WIRE["$defs"]
        for name, fields in (("proposal", PROPOSAL_FIELDS), ("provenance", PROVENANCE_FIELDS), ("outcome", OUTCOME_FIELDS), ("actor", ACTOR_FIELDS), ("runtime", RUNTIME_FIELDS)):
            self.assertEqual(set(defs[name]["properties"]), set(fields), name)
            self.assertFalse(defs[name]["additionalProperties"], name)
        self.assertEqual(defs["provenance"]["properties"]["surface"]["enum"], list(SURFACES))

    def test_validator_rejects_unknown_missing_float_and_bad_enum(self) -> None:
        good = proposal(OPENED, PAY_ALICE)
        validate_proposal(good)
        missing = dict(good)
        missing.pop("provenance")
        bad_surface = json.loads(json.dumps(good))
        bad_surface["provenance"]["surface"] = "telepathy"
        for bad in (good | {"extra": 1}, missing, good | {"args": {"amount": 1.5}}, bad_surface):
            with self.assertRaises(WireError):
                validate_proposal(bad)

    def test_registries(self) -> None:
        validate_registry(DEMO_REGISTRY)
        with self.assertRaises(WireError):
            validate_registry({"schema": "control.tool_registry.v1", "tools": {"x": {"effectClass": "harmless"}}})


if __name__ == "__main__":
    unittest.main()
