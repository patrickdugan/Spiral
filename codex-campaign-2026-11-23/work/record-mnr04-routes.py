import hashlib
import json
from pathlib import Path


run = Path("/var/tmp/shz-mnr04-routes.DRDHJbsC")
checkout = Path.cwd()
evidence = checkout / "evidence/mnr04"
artifacts = {
    "routed-regtest-core-archive.json": run / "replay/core-archive.json",
    "routed-regtest-proof.bin": run / "replay/proof/proof.bin",
}
archive, proof = (path.read_bytes() for path in artifacts.values())
summary = json.loads((run / "qualified-benchmark.json").read_bytes())
independent = summary["independent_verification"]
assert summary["core"]["consensus_accepted"] is True
assert independent["native"]["txid"] == "e8abf658eab148d9527c9e622e54298772aa4eebbbf6d15de5e29bba3ad21193"
assert independent["proof_sha256"] == hashlib.sha256(proof).hexdigest()
assert independent["proof_bytes"] == len(proof) == 12576
assert independent["vk_sha256"] == "e92e08dafafd66304914f136910fba8942ad8b16faadf9973c85c064962e606d"
assert independent["routed_netting"]["allocation_sats"] == [55000000, 44000000, 35000000, 55000000, 27498500, 27498500, 330]
assert summary["legacy_key_refused_by_route_profile"] is True
summary["source_commit"] = "a71f82ec00086a47093a2ac5d3400cab14ad21c8"
summary["core_binary_sha256"] = "986e63b3c8770f08d0059820ad3dd085d1ab9e1bea23946c243f858a06888a08"
summary["core_archive_sha256"] = hashlib.sha256(archive).hexdigest()
summary["rustc"] = "1.99.1 (58cf8f9c3 2026-10-13)"
outputs = {
    "routed-regtest-benchmark.json": (json.dumps(summary, indent=2) + "\n").encode("ascii"),
    **dict(zip(artifacts, (archive, proof))),
}
for name, data in outputs.items():
    with (evidence / name).open("xb") as target:
        target.write(data)
print(json.dumps({"timings": summary["phases"], "measurements": summary["prover_measurements"],
                  "verification_seconds": independent["verification_seconds"]}))
