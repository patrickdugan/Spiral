#!/usr/bin/env python3
"""In-and-Out-Burger refill through a BitVM3 claim graph on testnet4 (or a regtest rehearsal).

A payer pays the burger address on testnet4 from a P2PKH key P. The M16 guest proves that payment
under a Nova proof of the testnet4 header chain from a pinned anchor; M14 is the garbled circuit of that
proof's final verifier. A vault pays P' = P + t*G (the payer's derived key, `iob.payout_key`)
when no reject label of the garbled verifier turns up within the window (`iob.bitvm3`).

  bitvm3_testnet4.py [--network testnet4|regtest] --state DIR init
  ... pay --fund TXID:VOUT:SATS            the payer's payment to the burger address (P2PKH spend)
  ... statement --public PUBLIC.bin --payment-tx TXID --tip-check
  ... setup NAME --vault TXID:VOUT:SATS --m14 SETUP.json
  ... claim NAME | dispute NAME --m14 EVAL.json | payout NAME | refusals NAME | sweep NAME --to ADDR
  ... show

Secrets live in DIR/keys.json (testnet keys, never committed); everything else the commands
write into DIR is public and is what results/ records. Mainnet is refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iob import btc, ec, payout_key, sender, statement  # noqa: E402
from iob import bitvm3 as bv  # noqa: E402
from iob import taproot as tr  # noqa: E402
from iob.rpc import RPC, RPCError  # noqa: E402

NET = {
    "testnet4": {"hrp": "tb", "port": 48332, "cookie": r"C:\BitcoinTestnet\testnet4\.cookie", "p2pkh": 0x6F},
    "regtest": {"hrp": "bcrt", "port": None, "cookie": None, "p2pkh": 0x6F},
}
ROLES = ("desk", "claimant", "watch", "payer", "burger")
PRICE_FEE_SATS = 400  # the payer's payment fee (one P2PKH input, one P2WPKH output: 191 vB)
PIN = {
    # nova-bitvm3/m13/pins.json and m16/README.md: the proven M16 guest and the SP1 wrap pins.
    "program_vk_digest": "dfc68a5d",
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class State:
    def __init__(self, d: str, network: str):
        self.dir, self.network = d, network
        os.makedirs(d, exist_ok=True)

    def path(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def load(self, name: str, default=None):
        p = self.path(name)
        if not os.path.exists(p):
            return default
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def save(self, name: str, obj) -> None:
        with open(self.path(name) + ".tmp", "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=1)
            f.write("\n")
        os.replace(self.path(name) + ".tmp", self.path(name))

    def log(self, event: dict) -> None:
        event = {"at": now(), **event}
        with open(self.path("events.jsonl"), "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(event) + "\n")
        print(json.dumps(event, indent=1))

    # keys -------------------------------------------------------------------------------------
    def keys(self) -> dict:
        k = self.load("keys.json")
        if k is None:
            raise SystemExit("no keys.json: run init")
        return {r: int(k[r], 16) for r in ROLES}

    def parties(self) -> bv.Parties:
        k = self.keys()
        return bv.Parties(desk=k["desk"], claimant=k["claimant"], watch=k["watch"])


def rpc_for(a) -> RPC:
    if a.network == "testnet4":
        r = RPC(f"http://127.0.0.1:{NET['testnet4']['port']}", cookie=NET["testnet4"]["cookie"])
        assert r.call("getblockchaininfo")["chain"] == "testnet4"
        return r
    r = RPC(a.rpc_url, user=a.rpc_user, password=a.rpc_password)
    assert r.call("getblockchaininfo")["chain"] == "regtest"
    return r


def addr(spk: bytes, network: str) -> str:
    return btc.spk_to_address(spk, "testnet4" if network == "testnet4" else "regtest")


def p2pkh_spk(pub: bytes) -> bytes:
    return btc.p2pkh(btc.hash160(pub))


def wpkh_spk(secret: int) -> bytes:
    return btc.p2wpkh(btc.hash160(ec.serialize(ec.mul(secret))))


def burger_spk(k: dict) -> bytes:
    return wpkh_spk(k["burger"])


def refund_spk(k: dict) -> bytes:
    return wpkh_spk(k["desk"])


def broadcast(rpc: RPC, st: State, tx: tr.Tx, kind: str, **extra) -> str:
    acc = rpc.call("testmempoolaccept", [tx.hex()])[0]
    if not acc.get("allowed"):
        st.log({"kind": kind, "event": "refused_before_broadcast", "txid": tx.txid(), "reason": acc.get("reject-reason"), **extra})
        raise SystemExit(f"{kind} refused: {acc.get('reject-reason')}")
    txid = rpc.call("sendrawtransaction", tx.hex())
    assert txid == tx.txid()
    st.log({"kind": kind, "event": "broadcast", "txid": txid, "vsize": tx.vsize(), "hex": tx.hex(), **extra})
    return txid


def probe(rpc: RPC, tx: tr.Tx) -> dict:
    """testmempoolaccept only: the counterexamples are never broadcast."""
    acc = rpc.call("testmempoolaccept", [tx.hex()])[0]
    return {"txid": tx.txid(), "allowed": bool(acc.get("allowed")), "reject_reason": acc.get("reject-reason")}


# --- commands ------------------------------------------------------------------------------------


def cmd_init(a, st: State, rpc: RPC) -> None:
    if st.load("keys.json") is None:
        k = {}
        for r in ROLES:
            while True:
                s = int.from_bytes(os.urandom(32), "big")
                if 0 < s < ec.N:
                    break
            k[r] = f"{s:064x}"
        st.save("keys.json", k)
    k = st.keys()
    payer_pub = ec.serialize(ec.mul(k["payer"]))
    V = bv.vault_output(st.parties())
    pub = {
        "network": a.network,
        "payer": {"pubkey": payer_pub.hex(), "address": addr(p2pkh_spk(payer_pub), a.network)},
        "burger": {"address": addr(burger_spk(k), a.network), "script_pubkey": burger_spk(k).hex()},
        "vault": {"address": addr(V.script_pubkey, a.network), "script_pubkey": V.script_pubkey.hex(),
                  "leaves": [s.hex() for s in V.leaves]},
        "desk_refund": addr(refund_spk(k), a.network),
        "xonly": {"desk": st.parties().D.hex(), "claimant": st.parties().C.hex(), "watch": st.parties().W.hex()},
    }
    st.save("public.json", pub)
    print(json.dumps(pub, indent=1))


def parse_outpoint(s: str):
    txid, vout, sats = s.split(":")
    assert len(bytes.fromhex(txid)) == 32
    return txid, int(vout), int(sats)


def cmd_pay(a, st: State, rpc: RPC) -> None:
    k = st.keys()
    txid, vout, sats = parse_outpoint(a.fund)
    payer_pub = ec.serialize(ec.mul(k["payer"]))
    got = rpc.call("gettxout", txid, vout, True)
    assert got and round(got["value"] * 1e8) == sats and got["scriptPubKey"]["hex"] == p2pkh_spk(payer_pub).hex(), got
    tx = tr.Tx([tr.In(txid, vout, sequence=0xFFFFFFFF)], [tr.Out(sats - PRICE_FEE_SATS, burger_spk(k))], version=2)
    tr.sign_p2pkh(tx, 0, k["payer"])
    txid2 = broadcast(rpc, st, tx, "payment", to=addr(burger_spk(k), a.network), sats=sats - PRICE_FEE_SATS)
    st.save("payment.json", {"txid": txid2, "vout": 0, "sats": sats - PRICE_FEE_SATS, "hex": tx.hex(),
                             "payer_pubkey": payer_pub.hex(), "burger_script_pubkey": burger_spk(k).hex()})


def cmd_statement(a, st: State, rpc: RPC) -> None:
    """The desk's check of the proven statement before it signs any graph, and the payout key."""
    k = st.keys()
    raw = open(a.public, "rb").read()
    s = statement.parse(raw)
    pay = st.load("payment.json")
    p = s.payment
    tx_hex = rpc.call("getrawtransaction", pay["txid"])
    tx = btc.parse_tx(bytes.fromhex(tx_hex))
    checks = {
        "magic_testnet4": s.magic == statement.MAGIC["testnet4"],
        "anchor_height_pinned": s.start.height == a.anchor_height,
        "txid": p.txid_display == pay["txid"],
        "vout": p.vout == pay["vout"],
        "value": p.value_sats == pay["sats"],
        "script": p.script_sha256 == hashlib.sha256(burger_spk(k)).digest() and p.script_len == len(burger_spk(k)),
        "confirmations_at_least_6": p.confirmations >= 6,
        "tx_bytes_hash_to_txid": btc.sha256d(bytes.fromhex(tx_hex))[::-1].hex() == pay["txid"],
    }
    if a.tip_check:
        # The Nova chain starts at z0: genesis, or a checkpoint the desk pins against its own node.
        anchor_hash = rpc.call("getblockhash", s.start.height)
        checks["anchor_hash_equals_node"] = anchor_hash == s.start.hash_display
        checks["anchor_chainwork_equals_node"] = int(rpc.call("getblockheader", anchor_hash)["chainwork"], 16) == s.start.chainwork
        node_hash = rpc.call("getblockhash", s.tip.height)
        checks["tip_hash_equals_node"] = node_hash == s.tip.hash_display
        checks["tip_chainwork_equals_node"] = int(rpc.call("getblockheader", node_hash)["chainwork"], 16) == s.tip.chainwork
        checks["payment_block_equals_node"] = rpc.call("getblockhash", p.block_height) == p.block_hash_display
    snd = sender.resolve(tx)
    derived = payout_key.derive_sender(snd, p.txid_internal, p.vout)
    checks["payer_is_p2pkh_key"] = snd.key_type == "p2pkh" and snd.pubkey.hex() == pay["payer_pubkey"]
    ok = all(checks.values())
    out = {
        "statement_sha256": s.sha256,
        "network_magic": s.magic.decode(),
        "anchor": {"height": s.start.height, "hash": s.start.hash_display, "chainwork": hex(s.start.chainwork)},
        "steps": s.steps,
        "tip": {"height": s.tip.height, "hash": s.tip.hash_display, "chainwork": hex(s.tip.chainwork)},
        "payment": {"outpoint": p.outpoint, "block": p.block_height, "confirmations": p.confirmations, "sats": p.value_sats},
        "payer": {"pubkey": snd.pubkey.hex(), "spent_script_pubkey": snd.script_pubkey.hex()},
        "payout": {**derived.derived_from, "script_pubkey": derived.script_pubkey.hex(),
                   "address": addr(derived.script_pubkey, a.network)},
        "checks": checks,
        "ok": ok,
    }
    st.save("statement-check.json", out)
    print(json.dumps(out, indent=1))
    if not ok:
        raise SystemExit("statement refused")
    if a.final_statement:
        pins = json.load(open(a.pins, encoding="utf-8"))
        fs = {"committed_values_sha256": s.sha256, "exit_code": 0, "is_complete": 1,
              "program_vk_digest": a.program_vk_digest, "recursion_vk_root": pins["recursion_vk_root"],
              "wrap_vk_sha256": pins["wrap_vk_sha256"]}
        ref = json.load(open(a.ref_statement, encoding="utf-8"))
        fs = {kk: fs[kk] for kk in ref}  # same fields and order as the control statement
        with open(a.final_statement, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(fs, indent=2) + "\n")
        print(open(a.final_statement, encoding="utf-8").read())


def graph_for(st: State, name: str) -> tuple[bv.Graph, dict]:
    g = st.load(f"graph-{name}.json")
    if g is None:
        raise SystemExit(f"no graph-{name}.json: run setup")
    inst = bv.Instance(**{**g["instance"], "payout_spk": bytes.fromhex(g["instance"]["payout_spk"])})
    txid, vout, sats = parse_outpoint(g["vault_outpoint"])
    k = st.keys()
    graph = bv.Graph(st.parties(), inst, txid, vout, sats, refund_spk(k))
    assert graph.claim_txid == g["describe"]["claim"]["txid"], "graph does not rebuild to the recorded claim"
    return graph, g


def cmd_setup(a, st: State, rpc: RPC) -> None:
    sc = st.load("statement-check.json")
    if not sc or not sc["ok"]:
        raise SystemExit("run statement first")
    m14 = json.load(open(a.m14, encoding="utf-8"))
    fs = json.load(open(a.final_statement, encoding="utf-8"))
    assert m14["tool"] == "m14-claim setup"
    assert m14["statement_sha256"] == hashlib.sha256(open(a.final_statement, "rb").read()).hexdigest(), "m14 setup was garbled for another statement file"
    assert m14["statement"]["committed_values_sha256"] == sc["statement_sha256"]
    assert m14["statement"] == fs, "m14 setup pins different final-verifier fields"
    txid, vout, sats = parse_outpoint(a.vault)
    got = rpc.call("gettxout", txid, vout, True)
    V = bv.vault_output(st.parties())
    assert got and round(got["value"] * 1e8) == sats and got["scriptPubKey"]["hex"] == V.script_pubkey.hex(), got
    inst = bv.Instance(
        name=a.name,
        statement_committed_sha256=fs["committed_values_sha256"],
        program_vk_digest=fs["program_vk_digest"],
        ciphertext_commitment=m14["ciphertext_commitment_blake3"],
        accept_label_sha256=m14["accept_label_sha256"],
        reject_label_sha256=m14["reject_label_sha256"],
        payout_spk=bytes.fromhex(sc["payout"]["script_pubkey"]),
    )
    graph = bv.Graph(st.parties(), inst, txid, vout, sats, refund_spk(st.keys()))
    presig = graph.presign()
    rec = {
        "instance": {**inst.__dict__, "payout_spk": inst.payout_spk.hex()},
        "vault_outpoint": a.vault,
        "m14_setup": {kk: m14[kk] for kk in ("seed_sha256", "statement_sha256", "input_bits", "ciphertexts",
                                             "ciphertext_commitment_blake3", "accept_label_sha256", "reject_label_sha256", "seconds")},
        "describe": graph.describe(),
        "presig": presig,
        "payout_address": sc["payout"]["address"],
    }
    st.save(f"graph-{a.name}.json", rec)
    st.log({"kind": "setup", "instance": a.name, "claim_id": inst.claim_id().hex(), "claim_txid": graph.claim_txid,
            "payout_txid": graph.payout.txid(), "payout_to": sc["payout"]["address"]})


def cmd_claim(a, st: State, rpc: RPC) -> None:
    graph, g = graph_for(st, a.name)
    tx = graph.signed_claim(g["presig"])
    broadcast(rpc, st, tx, "claim", instance=a.name, claim_id=graph.inst.claim_id().hex())


def cmd_dispute(a, st: State, rpc: RPC) -> None:
    """The challenger: read the claim's commitments back from the chain, check the evaluation is of
    this instance, and spend the disprove leaf iff the evaluator obtained the reject label."""
    graph, g = graph_for(st, a.name)
    ev = json.load(open(a.m14, encoding="utf-8"))
    for _ in range(20):  # txindex can trail a block that just arrived
        try:
            claim_tx = rpc.call("getrawtransaction", graph.claim_txid, True)
            break
        except RPCError:
            time.sleep(0.5)
    else:
        raise SystemExit("claim transaction not found")
    op_return = next(o for o in claim_tx["vout"] if o["scriptPubKey"]["hex"].startswith("6a"))
    on_chain_id = bytes.fromhex(op_return["scriptPubKey"]["hex"])[2:]
    assert on_chain_id == b"IOB3" + graph.inst.claim_id(), "claim on chain commits to another instance"
    s = g["m14_setup"]
    same = (ev["ciphertext_commitment_blake3"] == s["ciphertext_commitment_blake3"] == ev["evaluator_commitment_blake3"]
            and ev["reject_label_sha256"] == graph.inst.reject_label_sha256 and ev["statement_sha256"] == s["statement_sha256"])
    assert same, "evaluation is not of this instance's garbled circuit"
    assert ev["verdict"] in ("accept", "reject"), "evaluator returned neither committed output label"
    for field in ("seed_sha256", "input_bits", "ciphertexts", "accept_label_sha256"):
        assert ev[field] == s[field], f"evaluation differs from setup: {field}"
    label = bytes.fromhex(ev["output_label"])
    assert hashlib.sha256(label).hexdigest() == ev["output_label_sha256"]
    assert ev["output_label_sha256"] == getattr(graph.inst, f"{ev['verdict']}_label_sha256"), "verdict does not match its committed label"
    rec = {"kind": "evaluation", "instance": a.name, "verdict": ev["verdict"], "proof_sha256": ev["proof_sha256"],
           "ciphertexts": ev["ciphertexts"], "seconds": ev["seconds"], "output_label_sha256": ev["output_label_sha256"]}
    st.log(rec)
    if ev["verdict"] == "reject":
        assert hashlib.sha256(label).hexdigest() == graph.inst.reject_label_sha256
        broadcast(rpc, st, graph.signed_disprove(label), "disprove", instance=a.name, label=label.hex())
    else:
        # The accept label opens nothing; show that Bitcoin refuses it on the disprove leaf.
        st.log({"kind": "disprove_with_accept_label", "instance": a.name, **probe(rpc, graph.signed_disprove(label))})


def cmd_payout(a, st: State, rpc: RPC) -> None:
    graph, g = graph_for(st, a.name)
    broadcast(rpc, st, graph.signed_payout(g["presig"]), "payout", instance=a.name, to=g["payout_address"],
              sats=graph.payout_value)


def cmd_refusals(a, st: State, rpc: RPC) -> None:
    """Counterexamples Bitcoin refuses, probed with testmempoolaccept and never broadcast."""
    graph, g = graph_for(st, a.name)
    k = st.keys()
    payer_pub = ec.serialize(ec.mul(k["payer"]))
    out = []
    if a.early:
        out.append({"case": "payout_before_window", **probe(rpc, graph.payout_early(g["presig"]))})
    out.append({"case": "payout_to_payer_old_address", **probe(rpc, graph.payout_redirected(g["presig"], p2pkh_spk(payer_pub)))})
    out.append({"case": "payout_to_claimant", **probe(rpc, graph.payout_redirected(g["presig"], wpkh_spk(k["claimant"])))})
    out.append({"case": "disprove_with_random_label", **probe(rpc, graph.signed_disprove(os.urandom(16)))})
    for r in out:
        st.log({"kind": "refusal_probe", "instance": a.name, **r})


def cmd_probe_early(a, st: State, rpc: RPC) -> None:
    """The presigned payout while the claim has fewer than WINDOW_BLOCKS confirmations."""
    graph, g = graph_for(st, a.name)
    confs = rpc.call("getrawtransaction", graph.claim_txid, True).get("confirmations", 0)
    if confs >= bv.WINDOW_BLOCKS:
        raise SystemExit(f"claim already has {confs} confirmations; the window is over")
    st.log({"kind": "refusal_probe", "instance": a.name, "case": "payout_before_window",
            "claim_confirmations": confs, **probe(rpc, graph.payout_early(g["presig"]))})


def cmd_sweep(a, st: State, rpc: RPC) -> None:
    """The payer recovers p' = p + t and spends the payout: P' is theirs and nobody else's."""
    graph, g = graph_for(st, a.name)
    k = st.keys()
    pay = st.load("payment.json")
    secret = payout_key.derive_private(k["payer"], True, bytes.fromhex(pay["txid"])[::-1], pay["vout"])
    pub = ec.serialize(ec.mul(secret))
    assert p2pkh_spk(pub) == graph.inst.payout_spk, "derived private key does not match the payout"
    txid = graph.payout.txid()
    to = btc.address_to_spk(a.to, "testnet4" if a.network == "testnet4" else "regtest")
    tx = tr.Tx([tr.In(txid, 0, sequence=0xFFFFFFFF)], [tr.Out(graph.payout_value - 400, to)])
    tr.sign_p2pkh(tx, 0, secret)
    broadcast(rpc, st, tx, "payer_sweep", instance=a.name, to=a.to)


SECRET_FILES = {"keys.json", "m14-seeds.json"}


def cmd_record(a, st: State, rpc: RPC) -> None:
    """Copy the public state into a results directory and check every broadcast against the node."""
    import shutil

    os.makedirs(a.out, exist_ok=True)
    copied = []
    for name in sorted(os.listdir(st.dir)):
        if name in SECRET_FILES or not name.endswith((".json", ".jsonl")) or name.endswith(".tmp"):
            continue
        shutil.copyfile(st.path(name), os.path.join(a.out, name))
        copied.append(name)
    events = [json.loads(l) for l in open(st.path("events.jsonl"), encoding="utf-8")]
    txs = []
    for e in events:
        if e.get("event") != "broadcast":
            continue
        t = rpc.call("getrawtransaction", e["txid"], True)
        h = rpc.call("getblockheader", t["blockhash"])["height"] if t.get("blockhash") else None
        txs.append({"kind": e["kind"], "instance": e.get("instance"), "txid": e["txid"], "vsize": e["vsize"],
                    "block_height": h, "confirmations": t.get("confirmations", 0)})
    summary = {
        "network": a.network,
        "recorded_at": now(),
        "node": rpc.call("getnetworkinfo")["subversion"],
        "tip": rpc.call("getblockcount"),
        "transactions": txs,
        "refusal_probes": [e for e in events if e.get("kind") in ("refusal_probe", "disprove_with_accept_label")],
        "evaluations": [e for e in events if e.get("kind") == "evaluation"],
        "files": copied,
    }
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=1)
        f.write("\n")
    print(json.dumps({k: summary[k] for k in ("tip", "transactions")}, indent=1))


def cmd_show(a, st: State, rpc: RPC) -> None:
    print(json.dumps(st.load("public.json"), indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", default="testnet4", choices=["testnet4", "regtest"])
    ap.add_argument("--state", required=True)
    ap.add_argument("--rpc-url")
    ap.add_argument("--rpc-user")
    ap.add_argument("--rpc-password")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("show")
    p = sub.add_parser("pay"); p.add_argument("--fund", required=True)
    p = sub.add_parser("statement")
    p.add_argument("--public", required=True)
    p.add_argument("--tip-check", action="store_true")
    p.add_argument("--anchor-height", type=int, required=True, help="the z0 height the desk accepts (0 = genesis)")
    p.add_argument("--final-statement")
    p.add_argument("--pins")
    p.add_argument("--ref-statement")
    p.add_argument("--program-vk-digest")
    p = sub.add_parser("setup")
    p.add_argument("name"); p.add_argument("--vault", required=True); p.add_argument("--m14", required=True)
    p.add_argument("--final-statement", required=True)
    for c in ("claim", "payout"):
        p = sub.add_parser(c); p.add_argument("name")
    p = sub.add_parser("dispute"); p.add_argument("name"); p.add_argument("--m14", required=True)
    p = sub.add_parser("refusals"); p.add_argument("name"); p.add_argument("--early", action="store_true")
    p = sub.add_parser("sweep"); p.add_argument("name"); p.add_argument("--to", required=True)
    p = sub.add_parser("record"); p.add_argument("--out", required=True)
    p = sub.add_parser("probe-early"); p.add_argument("name")
    a = ap.parse_args()
    st = State(a.state, a.network)
    rpc = rpc_for(a)
    globals()[f"cmd_{a.cmd.replace('-', '_')}"](a, st, rpc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
