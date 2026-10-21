"""Read-only Core decoding of already captured signed virtual transactions."""
import hashlib
import json
from attest import DEST, save
from bootstrap import core

records = {}
for label in ["failure-resolved", "failure-captured-resolved"]:
    snapshot = json.loads((DEST / f"{label}.json").read_text())
    for row in snapshot["database"]["virtual_transactions"]:
        if row["signed_tx"] and row["txid"] not in records:
            tx = core("decoderawtransaction", row["signed_tx"])
            assert tx["txid"] == row["txid"]
            records[row["txid"]] = {"raw_sha256": hashlib.sha256(bytes.fromhex(row["signed_tx"])).hexdigest(),
                "source_snapshot": label, "transaction": tx}
save("failure-virtual-transactions.json", {"evidence_class": "decoded_captured_virtual_transactions", "transactions": records,
     "interpretation": "These virtual claim transactions are not independently counted economic assets and were not broadcast by this decoder."})
print(json.dumps({"decoded_transactions": len(records), "broadcast": False}))
