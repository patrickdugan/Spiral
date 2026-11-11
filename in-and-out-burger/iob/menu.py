"""The menu: the pre-programmed payment address, the pins a proof must match, and the price
list that turns sats in into sats out."""
from __future__ import annotations

import json
from dataclasses import dataclass

from . import btc
from .errors import Refusal

HEX32 = set("0123456789abcdef")


def _hex32(v: str, what: str) -> str:
    if not isinstance(v, str) or len(v) != 64 or set(v) - HEX32:
        raise ValueError(f"{what}: expected 64 lowercase hex characters")
    return v


@dataclass(frozen=True)
class Tier:
    min_value_sats: int
    rate_ppm: int


@dataclass(frozen=True)
class Menu:
    name: str
    in_network: str
    in_address: str
    in_spk: bytes
    min_value_sats: int
    min_confirmations: int
    min_tip_chainwork: int
    out_network: str
    tiers: tuple
    fee_sats: int
    max_payout_sats: int
    fee_rate_sat_vb: float
    link_op_return: bool
    payout_key: str  # "derived": pay P + t*G for a one-key sender; "spent": pay the script they spent
    pins: dict
    gate_argv: tuple
    gate_paths: str

    @property
    def in_script_sha256(self) -> str:
        return btc.sha256(self.in_spk).hex()

    def payout_sats(self, value_sats: int, sender_kind: str) -> tuple[int, Tier]:
        """Sats out for `value_sats` in: the highest tier the payment reaches, at its rate, less
        the flat fee, capped. Refuses below the policy minimum and below dust."""
        if value_sats < self.min_value_sats:
            raise Refusal("value_below_menu", f"{value_sats} < {self.min_value_sats}")
        tier = max((t for t in self.tiers if value_sats >= t.min_value_sats), key=lambda t: t.min_value_sats)
        gross = value_sats * tier.rate_ppm // 1_000_000
        payout = min(gross - self.fee_sats, self.max_payout_sats)
        dust = btc.DUST_SATS[sender_kind]
        if payout < dust:
            raise Refusal("payout_below_dust", f"{payout} sats < {dust} for {sender_kind}")
        return payout, tier

    def gate_policy(self) -> dict:
        """The kan-payment-gate policy this menu implies."""
        return {
            "network": self.in_network,
            "min_confirmations": self.min_confirmations,
            "min_tip_chainwork": f"{self.min_tip_chainwork:064x}",
            "scripts": [{"id": "in-address", "script_sha256": self.in_script_sha256, "min_value_sats": self.min_value_sats}],
            "pins": dict(self.pins),
        }


PIN_NAMES = ("wrap_vk_sha256", "recursion_vk_root", "program_vk_digest", "nova_vk_sha256", "genesis_z0_sha256")


def from_dict(d: dict) -> Menu:
    i, o = d["in"], d["out"]
    in_network = i["network"]
    if in_network not in ("mainnet", "testnet4"):
        raise ValueError("in.network must be mainnet or testnet4 (the networks M16 is pinned for)")
    out_network = o["network"]
    if out_network not in btc.NETWORKS:
        raise ValueError(f"out.network must be one of {sorted(btc.NETWORKS)}")
    spk = btc.address_to_spk(i["address"], in_network)
    tiers = tuple(Tier(int(t["min_value_sats"]), int(t["rate_ppm"])) for t in o["tiers"])
    if not tiers or min(t.min_value_sats for t in tiers) > int(i["min_value_sats"]):
        raise ValueError("out.tiers must include a tier at or below in.min_value_sats")
    if any(t.rate_ppm <= 0 for t in tiers):
        raise ValueError("tier rates must be positive")
    if int(i["min_confirmations"]) < 1:
        raise ValueError("in.min_confirmations must be at least 1")
    chainwork = i["min_tip_chainwork"]
    chainwork = int(chainwork[2:] if chainwork.startswith("0x") else chainwork, 16)
    if chainwork <= 0:
        raise ValueError("in.min_tip_chainwork is required: the proof shows a valid chain, not the heaviest one")
    payout_key = o.get("payout_key", "derived")
    if payout_key not in ("derived", "spent"):
        raise ValueError("out.payout_key must be derived or spent")
    pins = {k: _hex32(d["pins"][k], f"pins.{k}") for k in PIN_NAMES}
    if set(d["pins"]) - set(PIN_NAMES):
        raise ValueError(f"unknown pins: {sorted(set(d['pins']) - set(PIN_NAMES))}")
    gate = d.get("gate", {})
    return Menu(
        name=d.get("name", "In-and-Out-Burger"),
        in_network=in_network,
        in_address=i["address"],
        in_spk=spk,
        min_value_sats=int(i["min_value_sats"]),
        min_confirmations=int(i["min_confirmations"]),
        min_tip_chainwork=chainwork,
        out_network=out_network,
        tiers=tiers,
        fee_sats=int(o["fee_sats"]),
        max_payout_sats=int(o["max_payout_sats"]),
        fee_rate_sat_vb=float(o.get("fee_rate_sat_vb", 1)),
        link_op_return=bool(o.get("link_op_return", True)),
        payout_key=payout_key,
        pins=pins,
        gate_argv=tuple(gate.get("argv", ())),
        gate_paths=gate.get("paths", "native"),
    )


def load(path: str) -> Menu:
    with open(path, encoding="utf-8") as f:
        return from_dict(json.load(f))
