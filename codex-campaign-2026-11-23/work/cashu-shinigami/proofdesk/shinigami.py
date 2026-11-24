"""Pinned Shinigami exit-chain verification for an already authenticated payment."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from .domain import Evidence, MAX_SATS, Refused, canonical, hash32
from .verifier import read_bounded


PROOF_LIMIT = 32 * 1024 * 1024
FIELD_PRIME = 2**251 + 17 * 2**192 + 1
EXIT_PROGRAM_HASH = int("4f57fcf7291f51140672bbefbaf92a509df7caecef6effab0e99bf24bf9c8b4", 16)
PROOF_PROFILE = {
    "pow_bits": 26,
    "fri_config": {"log_last_layer_degree_bound": 0, "log_blowup_factor": 1, "n_queries": 70, "fold_step": 1},
    "lifting_log_size": 26,
}


def _public_values(rows, limit):
    if not isinstance(rows, list) or not 0 < len(rows) <= limit:
        raise ValueError("invalid public memory segment length")
    values = []
    for row in rows:
        value_id, limbs = row
        if (type(value_id) is not int or not 0 <= value_id < 2**32
                or not isinstance(limbs, list) or len(limbs) != 8
                or any(type(limb) is not int or not 0 <= limb < 2**32 for limb in limbs)):
            raise ValueError("invalid public memory cell")
        value = sum(limb << (32 * index) for index, limb in enumerate(limbs))
        if value >= FIELD_PRIME:
            raise ValueError("noncanonical field element")
        values.append(value)
    return values


def _read_output(values):
    lo, hi, vout, amount, words = (next(values) for _ in range(5))
    if not (lo < 2**128 and hi < 2**128 and vout < 2**32 and 0 < amount <= MAX_SATS and words <= 322):
        raise ValueError("invalid Bitcoin output")
    script = b"".join(next(values).to_bytes(31, "big") for _ in range(words))
    pending, count = next(values), next(values)
    if count >= 31:
        raise ValueError("invalid script remainder")
    script += pending.to_bytes(count, "big")
    if not 0 < len(script) <= 10000:
        raise ValueError("invalid Bitcoin script length")
    txid = (lo | hi << 128).to_bytes(32, "little").hex()
    return txid, vout, amount, script


def paid_output(raw: bytes, bootloader_sha256: str) -> tuple[str, int, int, str]:
    """Decode the exact public layout of the pinned one-transaction program."""
    try:
        document = json.loads(raw)
        if (document["stark_proof"]["config"] != PROOF_PROFILE or document["channel_salt"] != 0
                or document["preprocessed_trace_variant"] != "canonical_without_pedersen"):
            raise Refused("shinigami_profile_mismatch")
        memory = document["claim"]["public_data"]["public_memory"]
        encoded = json.dumps(_public_values(memory["program"], 65536), separators=(",", ":")).encode()
        if hashlib.sha256(encoded).hexdigest() != bootloader_sha256:
            raise Refused("shinigami_bootloader_mismatch")
        output = _public_values(memory["output"], 680)
        if output[:3] != [1, len(output) - 1, EXIT_PROGRAM_HASH]:
            raise Refused("shinigami_program_mismatch")
        values = iter(output[3:])
        _read_output(values)  # anchor; the existing payment verifier supplies the chain view
        txid, vout, amount, script = _read_output(values)
        if next(values) != 1 or next(values, None) is not None:
            raise ValueError("invalid transaction count or output length")
    except Refused:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, StopIteration, RecursionError):
        raise Refused("shinigami_output_invalid") from None
    return txid, vout, amount, hashlib.sha256(script).hexdigest()


class ShinigamiGate:
    def __init__(self, verifier: Path, proof_dir: Path, binary_sha256: str, bootloader_sha256: str,
                 manifest_dir: Path | None = None):
        hash32(binary_sha256, "shinigami_binary_sha256")
        hash32(bootloader_sha256, "shinigami_bootloader_sha256")
        if not verifier.is_absolute():
            raise Refused("shinigami_verifier_path")
        self.verifier, self.proof_dir, self.manifest_dir = verifier, proof_dir, manifest_dir
        self.binary_sha256, self.bootloader_sha256 = binary_sha256, bootloader_sha256
        self.policy_sha256 = hashlib.sha256(canonical({
            "program_hash": hex(EXIT_PROGRAM_HASH), "bootloader_sha256": bootloader_sha256,
            "verifier_sha256": binary_sha256, "profile": PROOF_PROFILE,
        })).hexdigest()

    def verify(self, payment: Evidence) -> Evidence:
        payment.validate()
        try:
            with self.verifier.open("rb") as executable:
                digest = hashlib.sha256()
                for chunk in iter(lambda: executable.read(1 << 20), b""):
                    digest.update(chunk)
            if digest.hexdigest() != self.binary_sha256:
                raise Refused("shinigami_verifier_binary_mismatch")
            raw = read_bounded(self.proof_dir / f"{payment.txid}-{payment.vout}.json", PROOF_LIMIT)
            expected = (payment.txid, payment.vout, payment.value_sats, payment.script_sha256)
            if paid_output(raw, self.bootloader_sha256) != expected:
                raise Refused("shinigami_payment_mismatch")
            with tempfile.TemporaryDirectory(prefix="proofdesk-shinigami-") as directory:
                proof = Path(directory) / "proof.json"
                proof.write_bytes(raw)
                result = subprocess.run([str(self.verifier), "--proof-file", str(proof)],
                                        cwd=self.manifest_dir, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        timeout=60, check=False)
        except FileNotFoundError:
            raise Refused("shinigami_proof_or_verifier_missing") from None
        except (OSError, subprocess.TimeoutExpired):
            raise Refused("shinigami_verifier_unavailable") from None
        if result.returncode:
            raise Refused("shinigami_proof_rejected")
        return replace(payment, shinigami_proof_sha256=hashlib.sha256(raw).hexdigest(),
                       shinigami_policy_sha256=self.policy_sha256)
