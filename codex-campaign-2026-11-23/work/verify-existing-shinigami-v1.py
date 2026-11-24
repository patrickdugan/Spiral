import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


work = Path("/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat")
sys.path.insert(0, str(work / "outputs/ark-cashu-proofdesk"))
from proofdesk.domain import Evidence
from proofdesk.shinigami import FIELD_PRIME, ShinigamiGate


runtime = Path("/var/tmp/proof-grove-shinigami-20261123")
report = json.loads((work / "outputs/zk-rusto-no-bitcoino-ark/Ark/results/shinigami-testnet4-tapleaf-verified.json").read_text())
output, chain, stark = report["statement"]["vtxo"], report["chainstate"], report["stark"]
proof = runtime / "tapleaf-independent-verifier.proof.json"
actual_sha256 = hashlib.sha256(proof.read_bytes()).hexdigest()
if actual_sha256 != stark["verifier_json_sha256"]:
    raise ValueError("fixture proof differs from its recorded verifier input")
compiled = json.loads((runtime / "simple_bootloader_compiled.json").read_text())
values = [int(value, 16) % FIELD_PRIME for value in compiled["data"]]
bootloader = hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
payment = Evidence(
    "testnet4", output["txid"], output["vout"], output["amount_sat"],
    hashlib.sha256(bytes.fromhex(output["script_pubkey"])).hexdigest(),
    chain["authenticated_block_hash"], chain["authenticated_block_height"],
    chain["authenticated_block_hash"], chain["authenticated_block_height"],
    1, 1, actual_sha256, actual_sha256, "fixture",
)
with tempfile.TemporaryDirectory(prefix="shinigami-v1-binding-") as directory:
    proof_dir = Path(directory)
    shutil.copyfile(proof, proof_dir / f"{payment.txid}-{payment.vout}.json")
    gate = ShinigamiGate(
        Path("/root/.asdf/installs/scarb/2.19.6/bin/scarb-verify"), proof_dir,
        stark["scarb_verify_binary_sha256"], bootloader, runtime / "prover",
    )
    result = gate.verify(payment)
    print(json.dumps({"verified_existing_historical_proof": result.shinigami_proof_sha256 == actual_sha256,
                      "outpoint": result.outpoint, "amount_sat": result.value_sats,
                      "policy_sha256": result.shinigami_policy_sha256, "issued": False}))
