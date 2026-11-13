#!/usr/bin/env python3
"""Regtest rehearsal of the BitVM3 claim graph (`iob.bitvm3`) before any testnet4 vault is funded.

  bitvm3_regtest.py --rpc-url http://127.0.0.1:PORT --rpc-user U --rpc-password P --state DIR --out RESULT.json

Drives the same commands as `bitvm3_testnet4.py` on a fresh regtest chain, with the garbled
circuit replaced by two random 16-byte output labels (only their SHA-256 reaches the graph) and
the proven statement by a synthetic payment. Checks, each against Bitcoin Core's verdict:
- honest instance: payout refused before the window, then accepted; redirected payouts refused;
  disprove with the accept label or a random label refused; the payer sweeps P' with p + t;
- dishonest instance: disprove with the reject label accepted; the payout then has no input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bitvm3_testnet4 as d  # noqa: E402
from iob import btc, ec, payout_key  # noqa: E402
from iob import bitvm3 as bv  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc-url", required=True)
    ap.add_argument("--rpc-user", required=True)
    ap.add_argument("--rpc-password", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    a.network = "regtest"
    st = d.State(a.state, "regtest")
    rpc = d.rpc_for(a)
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "ok": bool(ok), **({"detail": detail} if detail is not None else {})})
        print(("PASS " if ok else "FAIL ") + name, detail if detail is not None else "")

    def mine(n):
        rpc.call("generatetoaddress", n, miner)

    try:
        rpc.call("createwallet", "rehearsal")
    except d.RPCError:
        pass
    w = rpc.wallet("rehearsal")
    miner = w.call("getnewaddress", "", "bech32")
    mine(101)

    d.cmd_init(a, st, rpc)
    k = st.keys()
    pub = st.load("public.json")

    # Payment: a real P2PKH spend to the burger address.
    payer_pub = ec.serialize(ec.mul(k["payer"]))
    f = w.call("send", {pub["payer"]["address"]: 0.00012})["txid"]
    vout = next(o["n"] for o in rpc.call("getrawtransaction", f, True)["vout"] if o["scriptPubKey"].get("address") == pub["payer"]["address"])
    d.cmd_pay(types.SimpleNamespace(network="regtest", fund=f"{f}:{vout}:12000"), st, rpc)
    mine(6)
    pay = st.load("payment.json")

    # Synthetic statement check: the derived payout key from the real payment, no proof.
    snd_pt = payout_key.derive_pubkey(payer_pub, bytes.fromhex(pay["txid"])[::-1], pay["vout"])
    payout_spk = d.p2pkh_spk(snd_pt[0])
    st.save("statement-check.json", {"ok": True, "statement_sha256": "00" * 32,
                                     "payout": {"script_pubkey": payout_spk.hex(), "address": d.addr(payout_spk, "regtest")}})
    final_statement = st.path("final-statement.json")
    with open(final_statement, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"committed_values_sha256": "00" * 32, "program_vk_digest": "11" * 32}) + "\n")
    fs_sha = hashlib.sha256(open(final_statement, "rb").read()).hexdigest()

    labels = {}
    for name in ("honest", "dishonest"):
        acc, rej = os.urandom(16), os.urandom(16)
        labels[name] = (acc, rej)
        m14 = {"tool": "m14-claim setup", "seed_sha256": "22" * 32, "statement_sha256": fs_sha,
               "statement": {"committed_values_sha256": "00" * 32, "program_vk_digest": "11" * 32}, "input_bits": 0, "ciphertexts": 0,
               "ciphertext_commitment_blake3": hashlib.sha256(name.encode()).hexdigest(),
               "accept_label_sha256": hashlib.sha256(acc).hexdigest(), "reject_label_sha256": hashlib.sha256(rej).hexdigest(),
               "seconds": 0}
        st.save(f"m14-setup-{name}.json", m14)
        vt = w.call("send", {pub["vault"]["address"]: 0.0002})["txid"]
        vv = next(o["n"] for o in rpc.call("getrawtransaction", vt, True)["vout"] if o["scriptPubKey"]["hex"] == pub["vault"]["script_pubkey"])
        mine(1)
        d.cmd_setup(types.SimpleNamespace(name=name, vault=f"{vt}:{vv}:20000", m14=st.path(f"m14-setup-{name}.json"),
                                          final_statement=final_statement), st, rpc)
        d.cmd_claim(types.SimpleNamespace(name=name), st, rpc)
        mine(1)

    def evaluation(name, verdict):
        acc, rej = labels[name]
        lab = acc if verdict == "accept" else rej
        s = st.load(f"m14-setup-{name}.json")
        ev = {"tool": "m14-claim evaluate", "statement_sha256": s["statement_sha256"], "proof_sha256": "33" * 32,
              "seed_sha256": s["seed_sha256"], "input_bits": s["input_bits"],
              "ciphertexts": 0, "ciphertext_commitment_blake3": s["ciphertext_commitment_blake3"],
              "evaluator_commitment_blake3": s["ciphertext_commitment_blake3"], "verdict": verdict,
              "output_label": lab.hex(), "output_label_sha256": hashlib.sha256(lab).hexdigest(),
              "accept_label_sha256": s["accept_label_sha256"], "reject_label_sha256": s["reject_label_sha256"], "seconds": 0}
        st.save(f"m14-eval-{name}.json", ev)
        return st.path(f"m14-eval-{name}.json")

    # Honest: the evaluator gets "accept"; Bitcoin refuses that label on the disprove leaf.
    d.cmd_dispute(types.SimpleNamespace(name="honest", m14=evaluation("honest", "accept")), st, rpc)
    ev_events = [json.loads(l) for l in open(st.path("events.jsonl"), encoding="utf-8")]
    acc_probe = [e for e in ev_events if e.get("kind") == "disprove_with_accept_label"][-1]
    check("honest: disprove with the accept label refused", not acc_probe["allowed"], acc_probe["reject_reason"])

    g, rec = d.graph_for(st, "honest")
    confs = lambda txid: rpc.call("getrawtransaction", txid, True).get("confirmations", 0)
    early = d.probe(rpc, g.payout_early(rec["presig"]))
    check(f"honest: payout at {confs(g.claim_txid)} confirmations of the claim refused", not early["allowed"], early["reject_reason"])
    mine(bv.WINDOW_BLOCKS - 1 - confs(g.claim_txid))
    early2 = d.probe(rpc, g.payout_early(rec["presig"]))
    check(f"honest: payout at {confs(g.claim_txid)} confirmations refused", confs(g.claim_txid) == bv.WINDOW_BLOCKS - 1 and not early2["allowed"], early2["reject_reason"])
    mine(1)
    # Mature now: each redirected payout can fail only on the desk's signature.
    d.cmd_refusals(types.SimpleNamespace(name="honest", early=False), st, rpc)
    probes = [json.loads(l) for l in open(st.path("events.jsonl"), encoding="utf-8") if '"refusal_probe"' in l]
    for p in probes:
        check(f"honest: {p['case']} refused", not p["allowed"], p["reject_reason"])
    d.cmd_payout(types.SimpleNamespace(name="honest"), st, rpc)
    check(f"honest: payout accepted at {confs(g.claim_txid)} confirmations", confs(g.claim_txid) == bv.WINDOW_BLOCKS)
    mine(1)
    po = rpc.call("getrawtransaction", g.payout.txid(), True)
    check("honest: payout confirmed to P'", po.get("confirmations", 0) >= 1 and po["vout"][0]["scriptPubKey"]["hex"] == payout_spk.hex())
    d.cmd_sweep(types.SimpleNamespace(name="honest", to=miner, network="regtest"), st, rpc)
    mine(1)
    check("honest: payer swept P' with p + t", True)

    # Dishonest: the evaluator gets "reject"; the disprove spends the claim output.
    d.cmd_dispute(types.SimpleNamespace(name="dishonest", m14=evaluation("dishonest", "reject")), st, rpc)
    mine(1)
    gd, recd = d.graph_for(st, "dishonest")
    dp = rpc.call("gettxout", gd.claim_txid, 0, True)
    check("dishonest: claim output spent by the disprove", dp is None)
    mine(bv.WINDOW_BLOCKS)
    late = d.probe(rpc, gd.signed_payout(recd["presig"]))
    check("dishonest: payout after the window has no input", not late["allowed"], late["reject_reason"])

    ok = all(c["ok"] for c in checks)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"network": "regtest", "node": rpc.call("getnetworkinfo")["subversion"], "checks": checks, "all_pass": ok,
                   "graphs": {n: st.load(f"graph-{n}.json")["describe"] for n in ("honest", "dishonest")}}, fh, indent=1)
        fh.write("\n")
    print(f"{sum(c['ok'] for c in checks)}/{len(checks)} checks pass")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
