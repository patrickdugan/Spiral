"""Process-isolated Cairo/Shinigami (Stwo) and Nova (ArkTransitionV1) verification gates.

These gates complement Proof Grove's M16 payment verifier and Bark wallet observations:
- VtxoExitStarkGate verifies Cairo/Shinigami (`taproot-provable`) Stwo exit-chain proofs
  (proving Taproot key-path/script-path spend validity from an anchor output to a VTXO).
  Stwo proofs are NOT zero-knowledge; raw proof blobs must never be published in public
  CIDv1 archives — only redacted hashes and public anchor/VTXO commitments.
- ArkTransitionNovaGate verifies `ark-transition-nova` (Nova 0.76 Pallas/Vesta Spartan-IPA)
  round proofs (proving per-tx value conservation, fee bounds, and global single-use
  `spend_id` uniqueness across commitment, NestedMuSig2 tree, and forfeit txs).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .domain import Refused, hash32, positive

SHINIGAMI_PROGRAM_HASH = "0x4f57fcf7291f51140672bbefbaf92a509df7caecef6effab0e99bf24bf9c8b4"
ARK_NOVA_VK_DIGEST = "22ad3282b71196a227d95b2216921a78e8d362d96702a3377347c0d085dfcdad"
ARK_NOVA_PROOF_LIMIT = 256 * 1024
STWO_PROOF_LIMIT = 32 * 1024 * 1024
MAX_MONEY = 21_000_000 * 100_000_000


def _wsl_path(path: str | Path, use_wsl: bool) -> str:
    value = str(Path(path).resolve())
    if use_wsl and os.name == "nt" and len(value) > 2 and value[1] == ":":
        return "/mnt/" + value[0].lower() + value[2:].replace("\\", "/")
    return value


def _check_pinned_binary(argv: list[str], expected_sha256: str) -> None:
    hash32(expected_sha256, "gate_binary_sha256")
    use_wsl = len(argv) >= 3 and argv[0].lower() == "wsl.exe" and argv[1] == "--exec"
    if use_wsl:
        cp = subprocess.run(
            argv[:2] + ["sha256sum", argv[2]],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        actual = cp.stdout.split()[0] if cp.returncode == 0 and cp.stdout.split() else ""
    else:
        h = hashlib.sha256()
        with open(argv[0], "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        actual = h.hexdigest()
    if actual != expected_sha256:
        raise Refused("verifier_binary_mismatch")


def _validate_hex_prefixed(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("0x") or len(value) < 4:
        raise Refused(f"invalid_{name}")
    body = value[2:]
    if len(body) > 64 or any(c not in "0123456789abcdef" for c in body.lower()):
        raise Refused(f"invalid_{name}")
    return "0x" + body.lower()


def validate_exit_statement(stmt: Any) -> dict[str, Any]:
    """Validate public statement fields of a Cairo/Shinigami `vtxo-exit-proof`."""
    if not isinstance(stmt, dict):
        raise Refused("invalid_exit_statement")
    program_hash = _validate_hex_prefixed(stmt.get("program_hash", ""), "program_hash")
    if program_hash != SHINIGAMI_PROGRAM_HASH:
        raise Refused("shinigami_program_hash_mismatch")

    anchor = stmt.get("anchor")
    vtxo = stmt.get("vtxo")
    if not isinstance(anchor, dict) or not isinstance(vtxo, dict):
        raise Refused("invalid_exit_statement")

    anchor_txid = hash32(anchor.get("txid", ""), "anchor_txid")
    anchor_vout = anchor.get("vout")
    if type(anchor_vout) is not int or not (0 <= anchor_vout <= 0xFFFFFFFF):
        raise Refused("invalid_anchor_vout")
    anchor_amount = positive(anchor.get("amount"), "anchor_amount", MAX_MONEY)

    vtxo_txid = hash32(vtxo.get("txid", ""), "vtxo_txid")
    vtxo_vout = vtxo.get("vout")
    if type(vtxo_vout) is not int or not (0 <= vtxo_vout <= 0xFFFFFFFF):
        raise Refused("invalid_vtxo_vout")
    vtxo_amount = positive(vtxo.get("amount"), "vtxo_amount", MAX_MONEY)
    if vtxo_amount > anchor_amount:
        raise Refused("exit_value_inflation")

    tx_count = positive(stmt.get("transaction_count"), "transaction_count", 64)
    return {
        "program_hash": program_hash,
        "anchor": {
            "txid": anchor_txid,
            "vout": anchor_vout,
            "amount": anchor_amount,
            "script_pubkey": str(anchor.get("script_pubkey", "")),
        },
        "vtxo": {
            "txid": vtxo_txid,
            "vout": vtxo_vout,
            "amount": vtxo_amount,
            "script_pubkey": str(vtxo.get("script_pubkey", "")),
        },
        "transaction_count": tx_count,
    }


def validate_ark_nova_public(pub: Any) -> dict[str, Any]:
    """Validate an `ark-transition-nova-public-v1` statement envelope."""
    if not isinstance(pub, dict):
        raise Refused("invalid_nova_public")
    if pub.get("schema") != "ark-transition-nova-public-v1":
        raise Refused("wrong_nova_schema")
    vk_digest = hash32(pub.get("vk_digest", ""), "vk_digest")
    if vk_digest != ARK_NOVA_VK_DIGEST:
        raise Refused("ark_nova_vk_mismatch")
    statement_digest = hash32(pub.get("statement_digest", ""), "statement_digest")
    r1 = hash32(pub.get("r1", ""), "r1")
    gamma = hash32(pub.get("gamma", ""), "gamma")
    steps = positive(pub.get("steps"), "steps", 1_000_000)
    fee_bound = pub.get("fee_bound_sat")
    if type(fee_bound) is not int or not (0 <= fee_bound <= MAX_MONEY):
        raise Refused("invalid_fee_bound")
    expect = pub.get("expect")
    if not isinstance(expect, dict):
        raise Refused("invalid_nova_expect")
    n_tx = positive(expect.get("n_tx"), "n_tx", 100_000)
    n_in = positive(expect.get("n_in"), "n_in", 100_000)
    sum_in = positive(expect.get("sum_in"), "sum_in", MAX_MONEY)
    sum_out = positive(expect.get("sum_out"), "sum_out", MAX_MONEY)
    sum_fee = expect.get("sum_fee")
    if type(sum_fee) is not int or not (0 <= sum_fee <= MAX_MONEY):
        raise Refused("invalid_sum_fee")
    if sum_out + sum_fee != sum_in:
        raise Refused("nova_conservation_mismatch")
    return {
        "schema": "ark-transition-nova-public-v1",
        "vk_digest": vk_digest,
        "statement_digest": statement_digest,
        "r1": r1,
        "gamma": gamma,
        "steps": steps,
        "fee_bound_sat": fee_bound,
        "expect": {
            "n_tx": n_tx,
            "n_in": n_in,
            "sum_in": sum_in,
            "sum_out": sum_out,
            "sum_fee": sum_fee,
        },
    }


class VtxoExitStarkGate:
    """Process-isolated Cairo/Shinigami Stwo exit-chain proof verifier."""

    def __init__(self, argv: list[str] | None = None, binary_sha256: str | None = None, timeout: int = 120):
        self.argv = argv
        self.expected_hash = binary_sha256
        self.timeout = timeout
        self.wsl = bool(argv and len(argv) >= 3 and argv[0].lower() == "wsl.exe" and argv[1] == "--exec")

    def verify(self, statement: dict[str, Any], proof_bytes: bytes | None = None, core=None) -> dict[str, Any]:
        parsed = validate_exit_statement(statement)
        proof_sha256 = None
        cryptographically_verified = False

        if proof_bytes is not None:
            if not proof_bytes or len(proof_bytes) > STWO_PROOF_LIMIT:
                raise Refused("artifact_size", str(STWO_PROOF_LIMIT))
            proof_sha256 = hashlib.sha256(proof_bytes).hexdigest()
            if not self.argv or not self.expected_hash:
                raise Refused("shinigami_verifier_not_configured")
            _check_pinned_binary(self.argv, self.expected_hash)
            artifact_root = Path.cwd() / ".runtime" / "verifier"
            artifact_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="pg-stwo-", dir=artifact_root) as tmpdir:
                proof_path = Path(tmpdir) / "proof.json"
                proof_path.write_bytes(proof_bytes)
                cp = subprocess.run(
                    self.argv + ["verify", "--proof-file", _wsl_path(proof_path, self.wsl)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
                if cp.returncode != 0:
                    raise Refused("stwo_proof_rejected", (cp.stderr or cp.stdout or "scarb verify failed")[:160])
                cryptographically_verified = True
        else:
            raise Refused("missing_proof_artifact", "Provide proof_base64 for cryptographic verification.")

        anchor_observation = None
        anchor_error = None
        if core is not None:
            try:
                txo = core.rpc("gettxout", [parsed["anchor"]["txid"], parsed["anchor"]["vout"], False])
                if not isinstance(txo, dict):
                    anchor_error = "anchor_spent_or_missing"
                else:
                    sats = round(float(txo.get("value", 0.0)) * 100_000_000)
                    if sats != parsed["anchor"]["amount"]:
                        anchor_error = "anchor_amount_mismatch"
                    else:
                        anchor_observation = {
                            "unspent": True,
                            "confirmations": int(txo.get("confirmations", 0)),
                            "value_sats": sats,
                        }
            except Refused as exc:
                anchor_error = exc.code
        else:
            anchor_error = "core_not_configured"

        return {
            "schema": "proof-grove/ark-vtxo-exit-check/v1",
            "proof_verified": cryptographically_verified,
            "evidence_level": "stwo-shinigami-exit-verified",
            "zero_knowledge": False,
            "archive_privacy": "redacted-hash-only",
            "proof_sha256": proof_sha256,
            "statement": parsed,
            "anchor_observation": anchor_observation,
            "anchor_error": anchor_error,
            "coverage": {
                "cairo_stwo_proved": [
                    "Taproot key-path and script-path consensus validation (shinigami@19cb9fa, 4,977 Core vectors)",
                    "Double-SHA256 txid chaining from anchor outpoint to VTXO output",
                    "Per-tx non-inflation and canonical transaction bounds",
                ],
                "external_required": [
                    "Anchor UTXO on-chain existence and unspentness (Bitcoin Core / M18 UTXO IMT)",
                    "No competing off-chain spend along intermediate exit hops",
                ],
            },
        }


class ArkTransitionNovaGate:
    """Process-isolated `ark-transition-nova` (Nova 0.76 Spartan-IPA) verifier."""

    def __init__(self, argv: list[str] | None = None, binary_sha256: str | None = None, timeout: int = 120):
        self.argv = argv
        self.expected_hash = binary_sha256
        self.timeout = timeout
        self.wsl = bool(argv and len(argv) >= 3 and argv[0].lower() == "wsl.exe" and argv[1] == "--exec")

    def verify(self, public_doc: dict[str, Any], proof_bytes: bytes | None = None) -> dict[str, Any]:
        parsed = validate_ark_nova_public(public_doc)
        if proof_bytes is None or not proof_bytes or len(proof_bytes) > ARK_NOVA_PROOF_LIMIT:
            raise Refused("artifact_size", str(ARK_NOVA_PROOF_LIMIT))
        proof_sha256 = hashlib.sha256(proof_bytes).hexdigest()

        if not self.argv or not self.expected_hash:
            raise Refused("ark_nova_verifier_not_configured")
        _check_pinned_binary(self.argv, self.expected_hash)

        artifact_root = Path.cwd() / ".runtime" / "verifier"
        artifact_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="pg-ark-nova-", dir=artifact_root) as tmpdir:
            pub_path = Path(tmpdir) / "public.json"
            proof_path = Path(tmpdir) / "proof.bin"
            pub_path.write_text(json.dumps(public_doc), encoding="utf-8")
            proof_path.write_bytes(proof_bytes)
            cp = subprocess.run(
                self.argv + ["verify", "--public", _wsl_path(pub_path, self.wsl), "--proof", _wsl_path(proof_path, self.wsl)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            if cp.returncode != 0:
                raise Refused("ark_nova_proof_rejected", (cp.stderr or cp.stdout or "ark-nova verify failed")[:160])

        return {
            "schema": "proof-grove/ark-round-nova-check/v1",
            "proof_verified": True,
            "evidence_level": "ark-transition-nova-verified",
            "zero_knowledge": True,
            "proof_bytes": len(proof_bytes),
            "proof_sha256": proof_sha256,
            "public": parsed,
            "coverage": {
                "nova_proved": [
                    "Per-transaction exact value conservation: sum(inputs) = sum(outputs) + fee",
                    "Per-transaction fee bound: 0 <= fee <= fee_bound_sat (64-bit range-checked)",
                    "Global single-use spend_id uniqueness across commitment, tree, and forfeit graph (Poseidon grand product)",
                    "Binding to 32-byte statement_digest and Poseidon record chain r1",
                ],
                "external_required": [
                    "Taproot key-path (NestedMuSig2) and tapscript signature validity (shinigami / bitcoin-rs-script)",
                    "On-chain funding UTXO confirmation and unspentness (Bitcoin Core / M16 + M18)",
                ],
            },
        }


def decode_base64_bounded(raw_b64: Any, limit: int) -> bytes:
    if not isinstance(raw_b64, str) or not raw_b64:
        raise Refused("invalid_artifact_encoding")
    try:
        data = base64.b64decode(raw_b64, validate=True)
    except (ValueError, TypeError, binascii.Error):
        raise Refused("invalid_artifact_encoding") from None
    if not data or len(data) > limit:
        raise Refused("artifact_size", str(limit))
    return data


def recorded_ark_proof_catalog(
    stwo_configured: bool = False,
    nova_configured: bool = False,
) -> dict[str, Any]:
    """Return pinned provenance metadata for Proof Grove's Cairo/Shinigami and Nova Ark proof gates."""
    return {
        "schema": "proof-grove/ark-zk-catalog/v1",
        "gates": {
            "shinigami_stwo_exit": {
                "configured": stwo_configured,
                "engine": "patrickdugan/shinigami (taproot-provable + feat/ark-multi-input-hardening)",
                "prover": "vtxo-exit-proof (Scarb 2.19.6 / Stwo Blake2s Circle STARK)",
                "program_hash": SHINIGAMI_PROGRAM_HASH,
                "core_consensus_vectors": "4,977 / 4,977 passed (plus 2-input Ark forfeit & CSV exit)",
                "zero_knowledge": False,
                "archive_policy": "Redacted proof_sha256 & statement commitments only (raw ~15 MB Stwo proofs stay private)",
                "measured_benchmarks": [
                    {"chain": "board (1 tx)", "steps": 797232, "prove_s": 158, "verify_s": 0.25, "proof_mb": 15.1},
                    {"chain": "round1 (4 txs)", "steps": 3444619, "prove_s": 208, "verify_s": 0.25, "proof_mb": 15.2},
                    {"chain": "arkoor3 (5 txs)", "steps": 5034769, "prove_s": 269, "verify_s": 0.25, "proof_mb": 15.2},
                ],
            },
            "ark_transition_nova": {
                "configured": nova_configured,
                "engine": "zk-rusto-no-bitcoino/integrations/ark-transition-nova (Nova 0.76 Pallas/Vesta Spartan-IPA)",
                "l1_harness": "patrickdugan/bitcoin-rs/tools/ark-nested-musig2 (Arkade-compatible NestedMuSig2)",
                "vk_digest": ARK_NOVA_VK_DIGEST,
                "constraints_per_step": 1050,
                "proof_bytes": 11104,
                "negative_controls": "22 / 22 mutations rejected",
                "zero_knowledge": True,
                "measured_benchmarks": [
                    {"graph": "ark-nm2 nested-4", "steps": 28, "fold_s": 6.38, "compress_s": 7.73, "verify_s": 0.21, "peak_rss_mib": 178},
                    {"graph": "ark-nm2 nested-16", "steps": 112, "fold_s": 28.49, "compress_s": 6.11, "verify_s": 0.17, "peak_rss_mib": 178},
                    {"graph": "ark-nm2 nested-64", "steps": 448, "fold_s": 100.21, "compress_s": 5.69, "verify_s": 0.21, "peak_rss_mib": 185},
                    {"graph": "synthetic 256", "steps": 1792, "fold_s": 464.02, "compress_s": 6.25, "verify_s": 0.18, "peak_rss_mib": 176},
                ],
            },
        },
        "boundary_note": (
            "Cairo/Shinigami proves Taproot exit script validity; Nova proves round conservation, "
            "fee bounds, and single-use spend_id uniqueness; Bitcoin Core / M16+M18 observes on-chain anchor finality."
        ),
    }
