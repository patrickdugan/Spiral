"""The menu's policy applied to a parsed statement: the same rules, in the same order, as
kan-payment-gate's `policy.rs`. The desk runs this on every order, after the gate when a proof is
present and on its own when the order is unproven."""
from __future__ import annotations

from .btc import sha256
from .errors import Refusal
from .menu import Menu
from .statement import GENESIS_HASH, MAGIC, Statement


def check(menu: Menu, st: Statement) -> None:
    if st.magic != MAGIC[menu.in_network]:
        raise Refusal("wrong_network", st.magic.decode("latin-1"))
    if st.k != 1:
        raise Refusal("wrong_fold_width", str(st.k))
    if (
        sha256(st.z0).hex() != menu.pins["genesis_z0_sha256"]
        or st.start.height != 0
        or st.start.hash_display != GENESIS_HASH[menu.in_network]
    ):
        raise Refusal("wrong_genesis", f"start height {st.start.height} hash {st.start.hash_display}")
    if st.nova_vk_sha256.hex() != menu.pins["nova_vk_sha256"]:
        raise Refusal("wrong_nova_key", st.nova_vk_sha256.hex())
    if st.tip.chainwork < menu.min_tip_chainwork:
        raise Refusal("chainwork_below_floor", f"tip {st.tip.height} chainwork {st.tip.chainwork:x}")
    p = st.payment
    if p.confirmations < menu.min_confirmations:
        raise Refusal("too_few_confirmations", f"{p.confirmations} < {menu.min_confirmations}")
    if p.script_sha256.hex() != menu.in_script_sha256:
        raise Refusal("script_not_registered", p.script_sha256.hex())
    if p.value_sats < menu.min_value_sats:
        raise Refusal("value_below_policy", f"{p.value_sats} < {menu.min_value_sats}")
