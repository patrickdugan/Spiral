"""Export a paired benchmark receipt after checking the exact returned artifacts."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def records(path):
    decoder = json.JSONDecoder()
    raw = path.read_text(encoding="utf-8")
    return {entry["status"]: entry for position in range(len(raw))
            if raw[position] == "{" and (position == 0 or raw[position - 1] == "\n")
            for entry in [decoder.raw_decode(raw[position:])[0]] if "status" in entry}


def fixture_path(value):
    assert value.startswith("/mnt/c/"), "fixture must be from the configured local Core/CDK test"
    return Path("C:/" + value.removeprefix("/mnt/c/"))


def cloud_and_local_match(name, cloud, proof, audit):
    assert cloud["status"] == "fresh_proof_independently_verified" and cloud["case"] == name
    assert cloud["case"] == audit["case"]
    assert cloud["statement"] == audit["statement"]
    assert cloud["source"] == audit["source"]
    assert cloud["input_sha256"] == audit["input_sha256"]
    assert cloud["verifier_input_sha256"] == audit["verifier_input_sha256"] == digest(proof)
    for phase, code in {"verify": 0, "reject_changed_anchor_amount": 1, "reject_changed_commitment": 1}.items():
        assert cloud["phases"][phase]["exit_code"] == audit["phases"][phase]["exit_code"] == code


def report(run):
    state = json.loads((run / "state.json").read_text())
    assert state["stage"] == "paired_issuance_and_redemption_verified" and state["cleanup"] == "vm_deleted"
    journal = records(run / "fixture.log")
    issuance = journal["passed"]
    payout = journal["confirmed_regtest_holder_reserve_redemption"]
    accepted = journal["redemption_proof_independently_verified_on_regtest"]
    first = json.loads((run / "benchmark.json").read_text())
    second = json.loads((run / "redemption-benchmark.json").read_text())
    issuance_proof = fixture_path(journal["waiting_for_shinigami_proof"]["proof_target"])
    payout_proof = fixture_path(journal["waiting_for_redemption_proof"]["proof_target"])
    audit = json.loads(payout_proof.with_name("redemption-proof-audit.json").read_text())
    reserve = json.loads(payout_proof.with_name("funded-refusal-state.json").read_text())
    assert issuance["network"] == payout["network"] == "regtest"
    assert issuance["amount_sats"] == 25000 and issuance["shinigami_source"] == "external"
    assert issuance["shinigami_verified"] and issuance["dleq_verified"] and issuance["no_second_issuance"]
    assert first["status"] == "fresh_proof_independently_verified" and first["case"] == "fresh_cashu_regtest"
    assert digest(issuance_proof) == first["verifier_input_sha256"] == issuance["shinigami_proof_sha256"]
    assert first["phases"]["verify"]["exit_code"] == 0
    assert all(first["phases"][label]["exit_code"] == 1 for label in
               ("reject_changed_anchor_amount", "reject_changed_commitment"))
    assert audit["status"] == "existing_proof_audited"
    cloud_and_local_match("fresh_cashu_redemption", second, payout_proof, audit)
    assert accepted["proof_sha256"] == second["verifier_input_sha256"]
    assert accepted["confirmed_spend"] == payout["confirmed_spend"]
    assert reserve["token_sha256"] == issuance["token_sha256"]
    assert reserve["reserve"] == payout["reserve"] and reserve["claim_commitment"] == payout["cashu_claim_commitment"]
    assert payout["payout_sat"] == 24750 and payout["payout_fee_sat"] == 250 and payout["timeout_blocks"] == 6
    assert payout["mint_offline"] and payout["early_spend_refused"] and payout["cooperative_conflict_refused"]
    assert second["public_words_matched"] == 24

    def metrics(trial, path):
        return {"case": trial["case"], "proof_sha256": trial["verifier_input_sha256"],
                "proof_bytes": path.stat().st_size, "source": trial["source"],
                "input_pins": trial["input_sha256"], "started_at": trial["started_at"],
                "finished_at": trial["finished_at"], "phases": trial["phases"]}

    return {
        "schema": "proofdesk/paired-shinigami-cloud-benchmark/v1", "network": "regtest",
        "status": "issuance_and_funded_refusal_proofs_verified",
        "worker": {"provider": "Hyperstack", "region": "CANADA-1", "flavor": state["flavor"],
                   "prover_backend": "cpu", "cpu": second["cpu_model"],
                   "vcpus": second["available_logical_cpus"], "prover_threads": second["rayon_threads"],
                   "rate_usd_per_hour_with_ip": round(state["rate_usd_per_hour"], 6)},
        "issuance": {**metrics(first, issuance_proof), "amount_sats": issuance["amount_sats"],
                     "exact_live_quote_verified": True, "cdk_dleq_verified": True, "single_issuance": True},
        "funded_refusal": {**metrics(second, payout_proof), "payout_sats": payout["payout_sat"],
                           "payout_fee_sats": payout["payout_fee_sat"], "timeout_blocks": payout["timeout_blocks"],
                           "mint_offline": True, "early_spend_refused": True, "competing_reserve_spend_refused": True,
                           "independent_local_verifier_and_live_core_checks": True,
                           "public_output_words_matched": second["public_words_matched"]},
        "scope": "Both fresh proofs use one isolated Core/CDK run. The linked holder reserve is funded separately. Ordinary Cashu melts and the holder reserve do not share a single-spend rule. This is Shinigami regtest evidence, separate from the Ark SP1 and Nova/BitVM3 campaigns.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(report(args.run), indent=2) + "\n"
    with args.output.open("x", encoding="utf-8") as file:
        file.write(encoded)
