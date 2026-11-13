"""The order desk: a proven payment in, sats out to whoever sent it.

Order of checks (each refusal has its own reason code):
1. statement parses (`statement.parse`);
2. final proof verified by kan-payment-gate and bound to the statement, or, for a regtest
   payout only, an explicitly unproven order;
3. the menu's policy on the statement (`policy.check`): network, genesis, Nova key, chainwork
   floor, confirmations, the pre-programmed address, minimum value;
4. the payment transaction hashes to the proven txid and its output is the proven one;
5. the sender (`sender.resolve`), with the witness bound to the proven block when needed, and
   for a one-key sender under `payout_key: derived`, the derived payout key (`payout_key.py`);
6. the price (`Menu.payout_sats`);
7. the journal: the outpoint has not been served.
Only then does the desk reserve the outpoint and pay.
"""
from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass
from typing import Protocol

from . import btc, gate, payout_key, policy, sender, statement
from .errors import Refusal
from .ledger import Ledger
from .menu import Menu
from .rpc import RPC, RPCError, btc_amount

LINK_MAGIC = b"IOBP"


@dataclass
class Order:
    statement: bytes
    tx_hex: str
    sender_proof: dict | None = None
    proof_path: str | None = None


def link_data(p: statement.Payment) -> bytes:
    """OP_RETURN payload on the payout: which proven payment it answers."""
    return LINK_MAGIC + p.txid_internal + struct.pack("<I", p.vout)


def _cross_check(st: statement.Statement, rec: dict, where: str) -> None:
    p = st.payment
    want = {
        "txid": p.txid_display,
        "vout": p.vout,
        "value_sats": p.value_sats,
        "script_sha256": p.script_sha256.hex(),
        "confirmations": p.confirmations,
    }
    got = {k: rec.get(k) for k in want}
    if got != want:
        raise Refusal("gate_disagrees", f"{where}: gate {got} vs desk {want}")


def _payment_tx(order: Order, st: statement.Statement) -> btc.Tx:
    try:
        tx = btc.parse_tx(bytes.fromhex(order.tx_hex.strip()))
    except (ValueError, btc.ParseError) as e:
        raise Refusal("tx_malformed", str(e)) from None
    sp = order.sender_proof
    if not tx.has_witness and sp and sp.get("tx"):
        try:
            witnessed = btc.parse_tx(bytes.fromhex(sp["tx"]))
        except (ValueError, btc.ParseError) as e:
            raise Refusal("sender_proof_malformed", f"tx: {e}") from None
        if witnessed.txid() != tx.txid():
            raise Refusal("sender_proof_tx", "sender proof carries a different transaction")
        tx = witnessed
    if tx.txid() != st.payment.txid_internal:
        raise Refusal("txid_mismatch", f"tx {tx.txid()[::-1].hex()} vs proven {st.payment.txid_display}")
    return tx


def _check_output(menu: Menu, st: statement.Statement, tx: btc.Tx) -> None:
    p = st.payment
    if p.vout >= len(tx.outputs):
        raise Refusal("output_mismatch", f"vout {p.vout} out of range")
    out = tx.outputs[p.vout]
    if out.script_pubkey != menu.in_spk or len(out.script_pubkey) != p.script_len or out.value != p.value_sats:
        raise Refusal("output_mismatch", "transaction output differs from the proven one")


def _sender(order: Order, st: statement.Statement, tx: btc.Tx) -> sender.Sender:
    declared = sender.declared_return(tx)
    if declared:
        return declared
    if tx.inputs[0].witness:
        if not order.sender_proof:
            raise Refusal("sender_proof_required", "input 0 is a witness spend")
        sender.verify_proof(order.sender_proof, st.payment.block_hash_display, tx)
    elif not tx.inputs[0].script_sig:
        raise Refusal("sender_unresolvable", "input 0 has an empty scriptSig and no witness: supply a sender proof")
    return sender.from_input(tx.inputs[0])


def evaluate(menu: Menu, order: Order, ledger: Ledger, *, allow_unproven: bool = False) -> dict:
    """Run every check and price the order. Raises Refusal; touches nothing."""
    st = statement.parse(order.statement)
    if order.proof_path:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(order.statement)
            st_path = f.name
        try:
            rec = gate.check(menu, order.proof_path, st_path)
        finally:
            os.unlink(st_path)
        _cross_check(st, rec["payment"], "check")
        proof_state = "verified"
    else:
        if not allow_unproven:
            raise Refusal("proof_required", "no final proof in the order")
        if menu.out_network != "regtest":
            raise Refusal("unproven_needs_regtest", f"payout network is {menu.out_network}")
        proof_state = "absent"
        if gate.available(menu):
            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
                f.write(order.statement)
                st_path = f.name
            try:
                _cross_check(st, gate.inspect(menu, st_path)["payment"], "inspect")
            finally:
                os.unlink(st_path)
    policy.check(menu, st)
    tx = _payment_tx(order, st)
    _check_output(menu, st, tx)
    who = _sender(order, st, tx)
    if menu.payout_key == "derived":
        who = payout_key.derive_sender(who, st.payment.txid_internal, st.payment.vout)
    payout, tier = menu.payout_sats(st.payment.value_sats, who.kind)
    ledger.check_free(st.payment.outpoint)
    p = st.payment
    who_out = {
        "script_pubkey": who.script_pubkey.hex(),
        "kind": who.kind,
        "rule": who.rule,
        "payout_address": btc.spk_to_address(who.script_pubkey, menu.out_network),
    }
    if who.derived_from:
        who_out["derived_from"] = dict(who.derived_from)
    return {
        "status": "accepted",
        "proof": proof_state,
        "statement_sha256": st.sha256,
        "in": {
            "outpoint": p.outpoint,
            "value_sats": p.value_sats,
            "address": menu.in_address,
            "block_height": p.block_height,
            "block_hash": p.block_hash_display,
            "confirmations": p.confirmations,
            "tip_height": st.tip.height,
            "tip_chainwork": f"{st.tip.chainwork:x}",
        },
        "sender": who_out,
        "payout": {"sats": payout, "rate_ppm": tier.rate_ppm, "fee_sats": menu.fee_sats, "network": menu.out_network},
        "_link": link_data(p).hex(),
    }


class PayError(Exception):
    def __init__(self, msg: str, broadcast_attempted: bool):
        super().__init__(msg)
        self.broadcast_attempted = broadcast_attempted


class Payer(Protocol):
    def pay(self, spk: bytes, sats: int, link: bytes | None) -> dict: ...


class CorePayer:
    """Pays from a Bitcoin Core wallet: fund, sign, check the transaction pays exactly what the
    desk priced, test mempool acceptance, then broadcast. Mainnet broadcast needs
    `allow_mainnet`; without `broadcast` it stops at a signed transaction."""

    def __init__(self, rpc: RPC, network: str, fee_rate_sat_vb: float, broadcast: bool = True, allow_mainnet: bool = False):
        self.rpc, self.network, self.fee_rate = rpc, network, fee_rate_sat_vb
        self.broadcast, self.allow_mainnet = broadcast, allow_mainnet

    def pay(self, spk: bytes, sats: int, link: bytes | None) -> dict:
        addr = btc.spk_to_address(spk, self.network)
        outputs = [{addr: btc_amount(sats)}]
        if link:
            outputs.append({"data": link.hex()})
        try:
            funded = self.rpc.call("walletcreatefundedpsbt", [], outputs, 0, {"fee_rate": self.fee_rate, "replaceable": True})
            signed = self.rpc.call("walletprocesspsbt", funded["psbt"], True)
            if not signed.get("complete"):
                raise PayError("wallet could not sign every input", False)
            raw = self.rpc.call("finalizepsbt", signed["psbt"])["hex"]
        except RPCError as e:
            raise PayError(str(e), False) from None
        tx = btc.parse_tx(bytes.fromhex(raw))
        pays = [o for o in tx.outputs if o.script_pubkey == spk]
        if len(pays) != 1 or pays[0].value != sats:
            raise PayError("funded transaction does not pay the priced amount exactly once", False)
        if link and not any(o.script_pubkey == b"\x6a" + btc.push(link) for o in tx.outputs):
            raise PayError("funded transaction lost the link output", False)
        txid = tx.txid()[::-1].hex()
        try:
            acc = self.rpc.call("testmempoolaccept", [raw])[0]
        except RPCError as e:
            raise PayError(str(e), False) from None
        if not acc.get("allowed"):
            raise PayError(f"mempool refuses payout: {acc.get('reject-reason')}", False)
        if not self.broadcast or (self.network == "mainnet" and not self.allow_mainnet):
            return {"txid": txid, "hex": raw, "broadcast": False}
        try:
            sent = self.rpc.call("sendrawtransaction", raw)
        except RPCError as e:
            raise PayError(str(e), True) from None
        return {"txid": sent, "hex": raw, "broadcast": True}


def serve(menu: Menu, order: Order, ledger: Ledger, payer: Payer | None, *, allow_unproven: bool = False) -> dict:
    """evaluate(), then reserve the outpoint and pay. Without a payer, stop at the priced order."""
    try:
        res = evaluate(menu, order, ledger, allow_unproven=allow_unproven)
    except Refusal as r:
        return {"status": "refused", "reason": r.reason, "detail": r.detail}
    link = bytes.fromhex(res.pop("_link")) if menu.link_op_return else None
    res.pop("_link", None)
    if payer is None:
        return res
    outpoint, payout = res["in"]["outpoint"], res["payout"]["sats"]
    spk = bytes.fromhex(res["sender"]["script_pubkey"])
    ledger.reserve(outpoint, payout, spk.hex())
    try:
        paid = payer.pay(spk, payout, link)
    except PayError as e:
        if not e.broadcast_attempted:
            ledger.release(outpoint, str(e))
        return dict(res, status="refused", reason="payout_failed", detail=str(e), reserved=e.broadcast_attempted)
    res["payout"].update(txid=paid["txid"], broadcast=paid["broadcast"])
    if paid["broadcast"]:
        ledger.paid(outpoint, paid["txid"])
        res["status"] = "served"
    else:
        res["payout"]["hex"] = paid["hex"]
        res["status"] = "prepared_not_broadcast" if paid.get("signed") is False else "signed_not_broadcast"
    return res
