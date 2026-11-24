"""Publish the allowlisted proof and attach its checked receipt to the Ark branch."""
import json
import os
from pathlib import Path
import runpy
import subprocess


WORK = Path(__file__).resolve().parent
REPO = Path(r"C:\Users\patri\Documents\Codex\2026-11-15\new-chat\outputs\zk-rusto-no-bitcoino-ark")
BRANCH = "ark/asp-management"
common = runpy.run_path(str(WORK / "publish-ark-held-delta.py"))


def read_json(path):
    return json.loads(path.read_bytes())


def git(*args):
    result = subprocess.run(["git", "-C", str(REPO), *map(str, args)], text=True, capture_output=True,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
    if result.returncode:
        raise RuntimeError(f"Ark git {args[0]} failed with exit {result.returncode}")
    return result.stdout.strip()


def publish_verified(pilot, proof_dir, compressed_sha256):
    required = ("independent-sdk-m13-passed", "independent-m14-passed")
    if any(not (proof_dir / marker).is_file() for marker in required):
        raise ValueError("the complete verification markers are missing")
    sdk = read_json(proof_dir / "sdk-verification.json")
    nova = read_json(proof_dir / "m13-verification.json")
    policy = read_json(proof_dir / "policy-verification.json")
    m14 = read_json(proof_dir / "m14-claim-v1.json")
    statement = read_json(proof_dir / "expected-statement.json")
    negative = m14["full_circuit_negative"]
    compressed = proof_dir / "compressed.bin"
    wrap = proof_dir / "m13" / "wrap-v2.bin"
    wrap_sha = common["sha256"](wrap)
    if not (
        sdk["status"] == "compressed_proof_verified"
        and sdk["public_sha256"] == statement["committed_values_sha256"]
        and sdk["program_vk_digest"] == statement["program_vk_digest"]
        and common["sha256"](compressed) == compressed_sha256
        and nova["status"] == policy["status"] == "verified"
        and nova["statement"] == policy["statement"] == m14["statement"] == negative["statement"] == statement
        and policy["ark_policy_final_proof_verified"] is True
        and m14["status"] == "verified_offchain_claim" and m14["bindings_match"] is True
        and m14["proof_sha256"] == negative["proof_sha256"] == wrap_sha
        and negative["verdict"] == "reject" and negative["flipped_input_bit"] == 0
        and negative["input_bits"] == 8635080 and negative["ciphertexts"] == 785442492
        and negative["ciphertext_commitment_blake3"] == negative["evaluator_commitment_blake3"]
    ):
        raise ValueError("Ark verification receipts disagree with the proof or expected statement")
    expected_repo = common["helpers"]["REPO"]
    if (git("branch", "--show-current") != BRANCH
            or git("remote", "get-url", "--push", "origin") != f"https://github.com/{expected_repo}.git"):
        raise ValueError("Ark branch or push remote differs from the authorized destination")

    release_dir = proof_dir / "public-release"
    if release_dir.resolve() != release_dir:
        raise ValueError("unexpected public proof staging path")
    release_dir.mkdir(exist_ok=True)
    for source in (compressed, wrap, proof_dir / "expected-statement.json"):
        link = release_dir / source.name
        if link.exists():
            if not link.samefile(source):
                raise ValueError("proof staging contains a conflicting file")
        else:
            os.link(source, link)
    assets = [common["part_metadata"](release_dir / name) for name in
              ("compressed.bin", "wrap-v2.bin", "expected-statement.json")]
    suffix = pilot.name[-10:]
    tag = "ark-679-offchain-" + suffix
    url = f"https://github.com/{expected_repo}/releases/tag/{tag}"
    receipt = {
        "schema": "ark-679-offchain-proof-chain/v1", "chain": "regtest", "height": 679,
        "vtxos": 4, "policy_sats": 79440, "statement": statement, "release": url, "artifacts": assets,
        "sdk_compressed_proof_verified": True, "m13_statement_verified": True,
        "offchain_m14_honest_evaluation_verified": True,
        "negative_controls": {"compressed_proof_bit_flip": "normal_refusal", "m13_proof_bit_flip": "normal_refusal",
                              "m13_wrong_statement": "normal_refusal", "m14_full_circuit_bit_flip": "reject"},
        "m14": {key: m14[key] for key in ("manifest_sha256", "release_sha256", "proof_sha256", "output_label_sha256")},
        "full_circuit_negative": {key: negative[key] for key in
                                  ("verdict", "flipped_input_bit", "input_bits", "ciphertexts", "ciphertext_commitment_blake3")},
        "funded_bitvm_claim_verified": False, "private_state_published": False,
    }
    receipt_path = release_dir / "verification.json"
    wire = json.dumps(receipt, indent=2) + "\n"
    receipt_path.write_text(wire, encoding="ascii")
    assets.append(common["part_metadata"](receipt_path))
    sums = release_dir / "SHA256SUMS"
    sums.write_text("".join(f"{item['sha256']}  {item['name']}\n" for item in assets), encoding="ascii")
    assets.append(common["part_metadata"](sums))
    body = ("SP1 SDK verification, exact M13 statement verification, honest BitVM3 off-chain evaluation, and "
            "full-circuit bit-flip rejection passed for the four-VTXO Ark regtest policy at height 679. "
            "The verification receipt records the binding digests and proof scope. Funded on-chain claims were outside this run.")
    observed = common["complete_release"](tag, "Ark height-679 verified off-chain proof", common["helpers"]["TARGET"],
                                          body, release_dir, assets)
    if observed["html_url"] != url:
        raise ValueError("published Ark proof release identifies an unexpected destination")
    if git("branch", "--show-current") != BRANCH:
        raise ValueError("the Ark checkout switched branches during publication")

    destination = Path("Ark") / "results" / f"ark-679-full-offchain-{suffix}.json"
    report = REPO / destination
    if report.exists() and report.read_text(encoding="ascii") != wire:
        raise ValueError("Ark proof receipt conflicts with an existing tracked result")
    if not report.exists():
        report.write_text(wire, encoding="ascii")
    git("add", "--", destination)
    if git("diff", "--cached", "--name-only", "--", destination):
        git("commit", "--only", "-m", "Record verified Ark SP1, M13 and BitVM3 proof chain", "--", destination)
    head = git("rev-parse", "HEAD")
    if git("rev-parse", BRANCH) != head:
        raise ValueError("the new Ark result is not on the authorized branch")
    git("push", "origin", f"{head}:refs/heads/{BRANCH}")
    remote = git("ls-remote", "origin", f"refs/heads/{BRANCH}").split()
    if not remote or remote[0] != head:
        raise ValueError("Ark branch push could not be verified")
    pilot.note(verified_proof_release=url, ark_pushed_commit=head)

    for staged in (release_dir / item["name"] for item in assets):
        if staged.is_symlink() or staged.resolve(strict=True).parent != release_dir:
            raise ValueError("public proof cleanup path escaped its staging directory")
        staged.unlink()
    for staged in (compressed, wrap, proof_dir / "wrong-compressed.bin", proof_dir / "wrong-wrap.bin"):
        if staged.is_symlink() or not staged.resolve().is_relative_to(proof_dir):
            raise ValueError("proof cleanup path escaped its staging directory")
        staged.unlink(missing_ok=True)
