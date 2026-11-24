import hashlib
import json
from pathlib import Path


run = Path("/var/tmp/shz-mnr04-signed.uPrrf59F")
evidence = Path("evidence/mnr04")
archive = (run / "replay/core-archive.json").read_bytes()
proof = (run / "replay/proof/proof.bin").read_bytes()
report = json.loads((run / "qualified-benchmark.json").read_bytes())
verified = report["independent_verification"]
accepted = report["core"]
route = verified["routed_netting"]
assert accepted["consensus_accepted"]
assert all(verified["native"][name] == accepted["native"][name] for name in ("txid", "wtxid"))
assert route["signed_origination"] == accepted["signed_origination"]
assert len(set(route["signed_origination"]["participant_xonly_keys"])) == 3
assert route["signed_origination"]["native_signatures_verified"]
assert route["changed_origination_context_refused"]
assert verified["vk_sha256"] == "e92e08dafafd66304914f136910fba8942ad8b16faadf9973c85c064962e606d"
assert verified["proof_sha256"] == hashlib.sha256(proof).hexdigest()
assert verified["proof_bytes"] == len(proof)
assert report["core_archive_sha256"] == hashlib.sha256(archive).hexdigest()
assert all(control["exit_code"] == 1 for control in report["origination_negative_controls"])
assert len(report["origination_negative_controls"]) == 4
report["source_commit"] = "d27ff72490bd629ae4208f745ef6dd4f92fb4054"
report["rustc"] = "1.99.1 (58cf8f9c3 2026-10-13)"
files = {
    "signed-regtest-benchmark.json": (json.dumps(report, indent=2) + "\n").encode("ascii"),
    "signed-regtest-core-archive.json": archive,
    "signed-regtest-proof.bin": proof,
}
for name, data in files.items():
    with (evidence / name).open("xb") as target:
        target.write(data)
print(json.dumps({
    "txid": verified["native"]["txid"], "proof_bytes": verified["proof_bytes"],
    "prove_seconds": report["phases"]["prove"]["elapsed_seconds"],
    "verify_seconds": report["phases"]["verify"]["elapsed_seconds"],
    "peak_rss_kib": report["phases"]["prove"]["peak_rss_kib"],
}))
