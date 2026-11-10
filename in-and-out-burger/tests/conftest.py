import json
import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from iob import btc, menu, statement  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "m16-mainnet")
MENU_PATH = os.path.join(ROOT, "menus", "m16-mainnet-replay.json")


def read(name, mode="rb"):
    with open(os.path.join(FIX, name), mode) as f:
        return f.read()


@pytest.fixture
def real():
    return {
        "statement": read("statement.bin"),
        "tx_hex": read("payment-tx.hex", "r").strip(),
        "sender_proof": json.loads(read("sender-proof.json", "r")),
    }


def menu_dict(**over):
    with open(MENU_PATH, encoding="utf-8") as f:
        d = json.load(f)
    d["gate"] = {}  # unit tests never start the gate binary
    for path, v in over.items():
        node = d
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = v
    return d


@pytest.fixture
def real_menu():
    return menu.from_dict(menu_dict())


# --- synthetic statements, for orders the real fixture cannot cover --------------------------


def state(height: int, hash_display: str, chainwork: int) -> bytes:
    internal = bytes.fromhex(hash_display)[::-1]
    elems = [
        struct.pack("<I", height) + b"\x00" * 28,
        internal[:16] + b"\x00" * 16,
        internal[16:] + b"\x00" * 16,
        chainwork.to_bytes(32, "little"),
    ] + [b"\x00" * 32] * 13
    return b"".join(elems)


def synthetic_statement(tx: btc.Tx, vout: int, *, block_hash: str, confirmations: int = 6, tip_height: int = 900_005,
                        chainwork: int = 1 << 90, nova_vk: bytes = b"\x11" * 32) -> bytes:
    z0 = state(0, statement.GENESIS_HASH["mainnet"], 0x100010001)
    zn = state(tip_height, "00" * 32, chainwork)
    out = tx.outputs[vout]
    pay = (
        b"PAY1" + struct.pack("<II", 2, tip_height - confirmations + 1) + bytes.fromhex(block_hash)[::-1]
        + struct.pack("<I", confirmations) + tx.txid() + struct.pack("<IQI", vout, out.value, len(out.script_pubkey))
        + btc.sha256(out.script_pubkey)
    )
    raw = b"NHC1" + struct.pack("<II", 1, tip_height) + z0 + zn + nova_vk + b"\x22" * 32 + pay
    assert len(raw) == statement.STATEMENT_BYTES
    return raw


def synthetic_menu(in_spk: bytes, **over) -> menu.Menu:
    z0 = state(0, statement.GENESIS_HASH["mainnet"], 0x100010001)
    d = menu_dict(**over)
    d["in"]["address"] = btc.spk_to_address(in_spk, "mainnet")
    d["in"]["min_tip_chainwork"] = hex(1 << 80)
    d["pins"]["nova_vk_sha256"] = (b"\x11" * 32).hex()
    d["pins"]["genesis_z0_sha256"] = btc.sha256(z0).hex()
    return menu.from_dict(d)
