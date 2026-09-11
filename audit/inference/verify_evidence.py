"""Validate and bind the final audit bundle; no network or original writes."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

root=Path(__file__).resolve().parent
read=lambda name:json.loads((root/name).read_text(encoding="utf-8"))
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
results=read("results.json")
receipt=read("receipt.json")
one,two=read("hash_seed_1.json"),read("hash_seed_2.json")
assert results["pythonhashseed"]=="1"
assert receipt["script_sha256"]==sha(root/"run_audit.py")
assert receipt["results_sha256"]==sha(root/"results.json")
for path,digest in receipt["inputs"].items():
    assert sha(path)==digest,path
assert one["sample_id"]==two["sample_id"]
assert one["canonical_edges_sha256"]==two["canonical_edges_sha256"]
assert one["canonical_public_metadata_sha256"]==two["canonical_public_metadata_sha256"]
assert one["synthetic_state_sha256"]!=two["synthetic_state_sha256"]
assert one["catalogue_sha256"]!=two["catalogue_sha256"]
assert one["canonical_order_reference"]==two["canonical_order_reference"]
assert all(c["trajectory_identical"] for c in results["budget_replay"]["matched_budget_trajectory_checks"])
assert results["integrity"]["duplicate_condition_keys"]==0
assert all(c["unmatched_left"]==c["unmatched_right"]==0 for c in results["integrity"]["pair_counts"].values())
files=("run_audit.py","results.json","receipt.json","hash_order_witness.py","hash_seed_1.json",
       "hash_seed_2.json","test_audit.py","report.md","verify_evidence.py")
bundle={"created_utc":datetime.now(timezone.utc).isoformat(),"status":"all_bundle_assertions_passed",
        "files":{name:sha(root/name) for name in files},
        "matched_trajectory_checks":len(results["budget_replay"]["matched_budget_trajectory_checks"]),
        "original_reproduction_checks_exact":sum(c["exact"] for c in results["budget_replay"]["original_reproduction_checks"]),
        "hashseed_witness":"same_sample_and_public_graph_different_original_state_equal_canonical_reference",
        "scope":"offline, post-hoc diagnostics; no testnet4 LN execution or wallet activity"}
(root/"bundle_receipt.json").write_text(json.dumps(bundle,indent=2),encoding="utf-8")
print(json.dumps(bundle,indent=2))
