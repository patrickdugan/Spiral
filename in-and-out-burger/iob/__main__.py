"""In-and-Out-Burger command line.

  python -m iob order --menu M --statement S --tx T [--sender-proof SP] [--proof P]
                      [--ledger L] [--allow-unproven]
                      [--pay --rpc-url U (--rpc-cookie F | --rpc-user U --rpc-password P) --wallet W
                       [--no-broadcast] [--allow-mainnet]]
  python -m iob sender-proof --block BLOCK.bin --txid TXID      (prints the sender proof JSON)
  python -m iob tx --block BLOCK.bin --txid TXID                 (prints the transaction hex)
  python -m iob policy --menu M                                  (prints the gate policy JSON)
  python -m iob inspect --statement S                            (prints the parsed statement)

`order` prints one JSON line and exits 0 when the order is accepted or served, 1 when refused.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import btc, desk, menu as menu_mod, sender, statement
from .errors import Refusal
from .ledger import Ledger
from .rpc import RPC


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def cmd_order(a) -> int:
    m = menu_mod.load(a.menu)
    sp = json.loads(_read(a.sender_proof)) if a.sender_proof else None
    order = desk.Order(statement=_read(a.statement), tx_hex=_read(a.tx).decode().strip(), sender_proof=sp, proof_path=a.proof)
    payer = None
    if a.pay:
        rpc = RPC(a.rpc_url, cookie=a.rpc_cookie, user=a.rpc_user, password=a.rpc_password, wallet=a.wallet)
        payer = desk.CorePayer(rpc, m.out_network, m.fee_rate_sat_vb, broadcast=not a.no_broadcast, allow_mainnet=a.allow_mainnet)
    res = desk.serve(m, order, Ledger(a.ledger), payer, allow_unproven=a.allow_unproven)
    print(json.dumps(res, sort_keys=True))
    return 0 if res["status"] in ("accepted", "served", "signed_not_broadcast") else 1


def cmd_sender_proof(a) -> int:
    print(json.dumps(sender.build_proof(_read(a.block), a.txid), indent=1))
    return 0


def cmd_tx(a) -> int:
    _, txs = btc.parse_block(_read(a.block))
    want = bytes.fromhex(a.txid)[::-1]
    for t in txs:
        if t.txid() == want:
            print(t.serialize().hex())
            return 0
    print(f"{a.txid} not in block", file=sys.stderr)
    return 1


def cmd_policy(a) -> int:
    print(json.dumps(menu_mod.load(a.menu).gate_policy(), indent=1))
    return 0


def cmd_inspect(a) -> int:
    try:
        st = statement.parse(_read(a.statement))
    except Refusal as r:
        print(json.dumps({"status": "refused", "reason": r.reason, "detail": r.detail}))
        return 1
    p = st.payment
    print(json.dumps({
        "network": st.magic.decode("latin-1"), "k": st.k, "steps": st.steps,
        "tip": {"height": st.tip.height, "hash": st.tip.hash_display, "chainwork": f"{st.tip.chainwork:x}"},
        "z0_sha256": btc.sha256(st.z0).hex(), "nova_vk_sha256": st.nova_vk_sha256.hex(),
        "payment": {"outpoint": p.outpoint, "block_height": p.block_height, "block_hash": p.block_hash_display,
                    "confirmations": p.confirmations, "value_sats": p.value_sats, "script_bytes": p.script_len,
                    "script_sha256": p.script_sha256.hex()},
        "statement_sha256": st.sha256,
    }, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="iob", description="In-and-Out-Burger: proven payment in, sats out to the sender")
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("order")
    o.add_argument("--menu", required=True)
    o.add_argument("--statement", required=True, help="the 1,292-byte M16 statement")
    o.add_argument("--tx", required=True, help="payment transaction, hex (with or without witness)")
    o.add_argument("--sender-proof")
    o.add_argument("--proof", help="M16 final proof (BLAKE3 wrap v2) for kan-payment-gate")
    o.add_argument("--ledger", help="served-outpoint journal (JSON lines)")
    o.add_argument("--allow-unproven", action="store_true", help="accept an order with no proof; regtest payouts only")
    o.add_argument("--pay", action="store_true")
    o.add_argument("--rpc-url")
    o.add_argument("--rpc-cookie")
    o.add_argument("--rpc-user")
    o.add_argument("--rpc-password")
    o.add_argument("--wallet")
    o.add_argument("--no-broadcast", action="store_true")
    o.add_argument("--allow-mainnet", action="store_true")
    o.set_defaults(fn=cmd_order)

    s = sub.add_parser("sender-proof")
    s.add_argument("--block", required=True)
    s.add_argument("--txid", required=True)
    s.set_defaults(fn=cmd_sender_proof)

    t = sub.add_parser("tx")
    t.add_argument("--block", required=True)
    t.add_argument("--txid", required=True)
    t.set_defaults(fn=cmd_tx)

    p = sub.add_parser("policy")
    p.add_argument("--menu", required=True)
    p.set_defaults(fn=cmd_policy)

    i = sub.add_parser("inspect")
    i.add_argument("--statement", required=True)
    i.set_defaults(fn=cmd_inspect)

    a = ap.parse_args(argv)
    if a.cmd == "order" and a.pay and not a.rpc_url:
        ap.error("--pay needs --rpc-url")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
