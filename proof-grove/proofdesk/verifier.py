"""M16 PAY1 binding and process-isolated kan-payment-gate integration.

The 1,292-byte contract comes from Spiral/in-and-out-burger/iob/statement.py.
Parsing is not verification: only the pinned external gate can produce m16-verified.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path

from .domain import Evidence, Refused, hash32, positive

STATEMENT_SIZE = 1292
PROOF_LIMIT = 4 * 1024 * 1024
PIN_NAMES = {"wrap_vk_sha256", "recursion_vk_root", "program_vk_digest", "nova_vk_sha256", "genesis_z0_sha256"}


def read_bounded(path: str | Path, limit: int) -> bytes:
    with open(path, "rb") as handle:
        data = handle.read(limit + 1)
    if not data or len(data) > limit:
        raise Refused("artifact_size", str(limit))
    return data


def _point(raw: bytes) -> tuple[int, str, int]:
    if any(raw[4:32]) or any(raw[48:64]) or any(raw[80:96]):
        raise Refused("statement_state_encoding")
    internal = raw[32:48] + raw[64:80]
    return struct.unpack_from("<I", raw)[0], internal[::-1].hex(), int.from_bytes(raw[96:128], "little")


def parse_statement(raw: bytes, anchor: dict | None = None) -> dict:
    if len(raw) != STATEMENT_SIZE:
        raise Refused("statement_length", "M16 requires exactly 1,292 bytes, including PAY1.")
    network = {b"NHC1": "mainnet", b"NHT4": "testnet4"}.get(raw[:4])
    if network is None:
        raise Refused("wrong_network")
    if struct.unpack_from("<I", raw, 4)[0] != 1:
        raise Refused("wrong_fold_width")
    if raw[1164:1168] != b"PAY1":
        raise Refused("payment_record_magic")
    start_height, start_hash, start_work = _point(raw[12:556])
    tip_height, tip_hash, work = _point(raw[556:1100])
    genesis = {"mainnet": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
               "testnet4": "00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043"}
    if anchor is None:
        if start_height != 0 or start_hash != genesis[network]:raise Refused('wrong_genesis')
    elif start_height!=anchor['height'] or start_hash!=anchor['hash'] or start_work!=int(anchor['chainwork'],16):
        raise Refused('checkpoint_mismatch')
    segments, height = struct.unpack_from("<II", raw, 1168)
    confirmations = struct.unpack_from("<I", raw, 1208)[0]
    vout, value, script_len = struct.unpack_from("<IQI", raw, 1244)
    if segments == 0 or confirmations == 0 or height + confirmations - 1 != tip_height:
        raise Refused("statement_inconsistent")
    if not 0 < script_len <= 10000:
        raise Refused("invalid_script_length")
    return {
        "network": network, "txid": raw[1212:1244][::-1].hex(), "vout": vout,
        "value_sats": value, "script_sha256": raw[1260:1292].hex(),
        "block_hash": raw[1176:1208][::-1].hex(), "block_height": height,
        "tip_hash": tip_hash, "tip_height": tip_height, "tip_chainwork": work,
        "confirmations": confirmations, "statement_sha256": hashlib.sha256(raw).hexdigest(),
    }


def validate_policy(policy: dict) -> None:
    if policy.get("network") not in ("mainnet", "testnet4"):
        raise Refused("wrong_network")
    positive(policy.get("min_confirmations"), "min_confirmations", 100000)
    try:
        work = int(policy["min_tip_chainwork"], 16)
    except (ValueError, TypeError, KeyError):
        raise Refused("invalid_chainwork_floor") from None
    positive(work, "min_tip_chainwork", 2**256 - 1)
    pins = policy.get("pins", {})
    if set(pins) != PIN_NAMES:
        raise Refused("missing_verifier_pins")
    for key, value in pins.items():
        hash32(value, key)
    if 'anchor' in policy:
        anchor=policy['anchor']
        if not isinstance(anchor,dict) or set(anchor)!={'height','hash','chainwork'}:raise Refused('invalid_checkpoint')
        positive(anchor['height'],'checkpoint_height',2**32-1);hash32(anchor['hash'],'checkpoint_hash')
        try:positive(int(anchor['chainwork'],16),'checkpoint_chainwork',2**256-1)
        except (TypeError,ValueError):raise Refused('invalid_checkpoint') from None
    scripts = policy.get("scripts", [])
    if not scripts:
        raise Refused("missing_registered_script")
    for script in scripts:
        hash32(script["script_sha256"], "script_sha256")
        positive(script["min_value_sats"], "min_value_sats")


class M16Gate:
    checkpoint_support=False
    def __init__(self, argv: list[str], binary_sha256: str, policy: dict, timeout: int = 600):
        native = len(argv) == 1
        wsl = len(argv) == 3 and argv[0].lower() == "wsl.exe" and argv[1] == "--exec"
        if not (native or wsl) or not all(isinstance(a, str) and a for a in argv):
            raise Refused("invalid_gate_command", "Use [binary] or [wsl.exe, --exec, /absolute/binary].")
        hash32(binary_sha256, "gate_binary_sha256")
        validate_policy(policy)
        self.argv, self.expected_hash, self.policy, self.timeout = argv, binary_sha256, policy, timeout
        self.wsl = wsl

    def _path(self, path: str) -> str:
        value = str(Path(path).resolve())
        if self.wsl and os.name == "nt" and len(value) > 2 and value[1] == ":":
            return "/mnt/" + value[0].lower() + value[2:].replace("\\", "/")
        return value

    def _check_binary(self) -> None:
        if self.wsl:
            process = subprocess.run(self.argv[:2] + ["sha256sum", self.argv[2]],
                                     stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, check=False)
            actual = process.stdout.split()[0] if process.returncode == 0 and process.stdout.split() else ""
        else:
            h = hashlib.sha256()
            with open(self.argv[0], "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    h.update(chunk)
            actual = h.hexdigest()
        if actual != self.expected_hash:
            raise Refused("verifier_binary_mismatch")

    def check_anchor(self,core):
        anchor=self.policy.get('anchor')
        if anchor:
            if core.rpc('getblockhash',[anchor['height']])!=anchor['hash']:raise Refused('checkpoint_not_active')
            header=core.rpc('getblockheader',[anchor['hash']])
            if int(header['chainwork'],16)!=int(anchor['chainwork'],16):raise Refused('checkpoint_chainwork_mismatch')

    def check_public(self, statement: bytes, proof: bytes) -> dict:
        parsed = parse_statement(statement,self.policy.get('anchor') if self.checkpoint_support else None)
        if not proof or len(proof) > PROOF_LIMIT:
            raise Refused("artifact_size")
        if parsed["network"] != self.policy["network"]:
            raise Refused("wrong_network")
        # Repeat the public policy checks locally; the external verifier binds their bytes.
        if hashlib.sha256(statement[12:556]).hexdigest() != self.policy["pins"]["genesis_z0_sha256"]:
            raise Refused("wrong_genesis_pin")
        if statement[1100:1132].hex() != self.policy["pins"]["nova_vk_sha256"]:
            raise Refused("wrong_nova_key")
        if parsed["confirmations"] < self.policy["min_confirmations"]:
            raise Refused("too_few_confirmations")
        if parsed["tip_chainwork"] < int(self.policy["min_tip_chainwork"], 16):
            raise Refused("chainwork_below_floor")
        if not any(s["script_sha256"] == parsed["script_sha256"] and s["min_value_sats"] <= parsed["value_sats"]
                   for s in self.policy["scripts"]):
            raise Refused("unregistered_payment")
        return parsed

    def verify(self, statement: bytes, proof: bytes) -> Evidence:
        parsed=self.check_public(statement,proof)
        try:
            self._check_binary()
            artifact_root = Path.cwd() / ".runtime" / "verifier"
            artifact_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="proof-grove-", dir=artifact_root) as directory:
                paths = [str(Path(directory) / n) for n in ("statement.bin", "proof.bin", "policy.json")]
                Path(paths[0]).write_bytes(statement)
                Path(paths[1]).write_bytes(proof)
                Path(paths[2]).write_text(json.dumps(self.policy), encoding="utf-8")
                cp = subprocess.run(self.argv + ["check", "--proof", self._path(paths[1]),
                                    "--statement", self._path(paths[0]), "--policy", self._path(paths[2])],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=self.timeout, check=False)
                try:
                    result = json.loads(cp.stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    raise Refused("gate_response_invalid") from None
                if cp.returncode != 0 or result.get("status") != "accepted":
                    raise Refused("proof_rejected", str(result.get("reason", "gate refused"))[:160])
                expected = {key: parsed[key] for key in ("txid", "vout", "value_sats", "script_sha256", "confirmations")}
                if not isinstance(result.get("payment"), dict) or any(
                    type(result["payment"].get(k)) is not type(v) or result["payment"][k] != v for k, v in expected.items()
                ):
                    raise Refused("gate_payment_mismatch")
        except (OSError, subprocess.TimeoutExpired):
            raise Refused("verifier_unavailable") from None
        evidence = Evidence(**parsed, proof_sha256=hashlib.sha256(proof).hexdigest(), kind="m16-verified")
        evidence.validate()
        return evidence


class NativeFinalGate(M16Gate):
    """Pinned m13 final verifier, with explicit M16 policy/checkpoint bindings."""
    checkpoint_support=True

    def verify(self,statement:bytes,proof:bytes)->Evidence:
        parsed=self.check_public(statement,proof)
        expected={key:self.policy['pins'][key] for key in ('wrap_vk_sha256','recursion_vk_root','program_vk_digest')}
        expected.update(committed_values_sha256=parsed['statement_sha256'],exit_code=0,is_complete=1)
        try:
            self._check_binary()
            root=Path.cwd()/'.runtime/verifier';root.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='final-',dir=root) as directory:
                wrap=Path(directory)/'proof.bin';pins=Path(directory)/'expected.json'
                wrap.write_bytes(proof);pins.write_text(json.dumps(expected),encoding='utf-8')
                cp=subprocess.run(self.argv+['verify-v2',self._path(str(wrap)),self._path(str(pins))],
                    stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=self.timeout,check=False)
                if cp.returncode:raise Refused('proof_rejected')
                try:result=json.loads(cp.stdout)
                except ValueError:raise Refused('gate_response_invalid') from None
                if result.get('status')!='verified':raise Refused('proof_rejected')
                if any(result.get('statement',{}).get(key)!=value for key,value in expected.items()):raise Refused('gate_statement_mismatch')
        except (OSError,subprocess.TimeoutExpired):raise Refused('verifier_unavailable') from None
        evidence=Evidence(**parsed,proof_sha256=hashlib.sha256(proof).hexdigest(),kind='m16-verified')
        evidence.validate();return evidence
