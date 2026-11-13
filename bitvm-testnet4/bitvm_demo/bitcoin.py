"""Bitcoin demo helpers; transaction parsing and point arithmetic stay with iob."""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'in-and-out-burger'))
from iob import btc, ec

spec = importlib.util.spec_from_file_location('bitvm_demo_sighash', ROOT / 'BIPSpace/Keyless-CHECKSIG/reference.py')
reference = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reference
spec.loader.exec_module(reference)

TESTNET4_GENESIS = '00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043'
REGTEST_GENESIS = '0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206'
NUMS_X = bytes.fromhex('50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0')


def fresh_secret() -> int:
    while True:
        value = int.from_bytes(os.urandom(32), 'big')
        if 0 < value < ec.N:
            return value


def xonly(secret: int) -> bytes:
    if not 0 < secret < ec.N:
        raise ValueError('invalid secret scalar')
    return ec.mul(secret)[0].to_bytes(32, 'big')


def sign(message: bytes, secret: int, auxiliary: bytes | None = None) -> bytes:
    """BIP340 signing for a 32-byte Bitcoin sighash; research demo, no key export."""
    if len(message) != 32 or not 0 < secret < ec.N:
        raise ValueError('invalid fixed-size sighash or scalar')
    auxiliary = os.urandom(32) if auxiliary is None else auxiliary
    if len(auxiliary) != 32:
        raise ValueError('auxiliary input must have 32 bytes')
    public = ec.mul(secret)
    adjusted = secret if public[1] % 2 == 0 else ec.N - secret
    masked = bytes(a ^ b for a, b in zip(adjusted.to_bytes(32, 'big'), ec.tagged_hash('BIP0340/aux', auxiliary)))
    nonce = int.from_bytes(ec.tagged_hash('BIP0340/nonce', masked + xonly(secret) + message), 'big') % ec.N
    if nonce == 0:
        raise ValueError('invalid zero nonce')
    commitment = ec.mul(nonce)
    normalized = nonce if commitment[1] % 2 == 0 else ec.N - nonce
    rx = commitment[0].to_bytes(32, 'big')
    challenge = int.from_bytes(ec.tagged_hash('BIP0340/challenge', rx + xonly(secret) + message), 'big') % ec.N
    signature = rx + ((normalized + challenge * adjusted) % ec.N).to_bytes(32, 'big')
    if not verify(message, xonly(secret), signature):
        raise ValueError('signature self-check failed')
    return signature


def verify(message: bytes, public: bytes, signature: bytes) -> bool:
    if len(message) != 32 or len(public) != 32 or len(signature) != 64:
        return False
    try:
        point = ec.parse(b'\x02' + public)
    except ValueError:
        return False
    rx, scalar = int.from_bytes(signature[:32], 'big'), int.from_bytes(signature[32:], 'big')
    if rx >= ec.P or scalar >= ec.N:
        return False
    challenge = int.from_bytes(ec.tagged_hash('BIP0340/challenge', signature[:32] + public + message), 'big') % ec.N
    negative = ec.mul(challenge, point)
    if negative is not None:
        negative = (negative[0], ec.P - negative[1])
    reconstructed = ec.add(ec.mul(scalar), negative)
    return reconstructed is not None and reconstructed[1] % 2 == 0 and reconstructed[0] == rx


def number(value: int) -> bytes:
    if value == 0:
        return b'\x00'
    if 1 <= value <= 16:
        return bytes([0x50 + value])
    raw = value.to_bytes((value.bit_length() + 7) // 8, 'little')
    return btc.push(raw + b'\x00' if raw[-1] & 0x80 else raw)


@dataclass(frozen=True)
class Taproot:
    script_pubkey: bytes
    leaves: tuple[bytes, ...]
    controls: tuple[bytes, ...]


def tree(scripts: list[bytes]) -> Taproot:
    if not scripts:
        raise ValueError('at least one leaf is required')
    paths = {index: [] for index in range(len(scripts))}
    def build(indices):
        if len(indices) == 1:
            return reference.tapleaf(scripts[indices[0]])
        split = len(indices) // 2
        left, right = indices[:split], indices[split:]
        lh, rh = build(left), build(right)
        for index in left: paths[index].append(rh)
        for index in right: paths[index].append(lh)
        return reference.tapbranch(lh, rh)
    root = build(list(range(len(scripts))))
    tweak = int.from_bytes(ec.tagged_hash('TapTweak', NUMS_X + root), 'big')
    if tweak >= ec.N:
        raise ValueError('TapTweak exceeds the group order')
    output = ec.add(ec.parse(b'\x02' + NUMS_X), ec.mul(tweak))
    if output is None:
        raise ValueError('invalid Taproot output')
    prefix = bytes([0xc0 | (output[1] & 1)]) + NUMS_X
    controls = tuple(prefix + b''.join(paths[i]) for i in range(len(scripts)))
    return Taproot(b'\x51\x20' + output[0].to_bytes(32, 'big'), tuple(scripts), controls)


def sighash(tx: btc.Tx, value_sats: int, spent_script: bytes, script: bytes) -> bytes:
    if len(tx.inputs) != 1:
        raise ValueError('the demos require one input')
    item = tx.inputs[0]
    converted = reference.Tx((reference.Input(item.prev_txid, item.prev_vout, value_sats, spent_script, item.sequence),),
                             tuple(reference.Output(out.value, out.script_pubkey) for out in tx.outputs),
                             tx.version, tx.locktime)
    return reference.sighash(converted, 0, leaf=reference.tapleaf(script), key_version=0)


def keypath_sighash(tx: btc.Tx, value_sats: int, spent_script: bytes) -> bytes:
    if len(tx.inputs) != 1:
        raise ValueError('the demos require one input')
    item = tx.inputs[0]
    converted = reference.Tx((reference.Input(item.prev_txid, item.prev_vout, value_sats, spent_script, item.sequence),),
                             tuple(reference.Output(out.value, out.script_pubkey) for out in tx.outputs),
                             tx.version, tx.locktime)
    return reference.sighash(converted, 0, ext_flag=0, key_version=0)
