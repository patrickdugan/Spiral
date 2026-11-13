#!/usr/bin/env python3
"""site/data/demo.json for the In-and-Out-Burger demo page, from the testnet4 run's public state.

  build_site_data.py --state C:\\BitcoinTestnet\\iob-bitvm3 [--gpu-tasks N] [--out site/data/demo.json]

Reads only public files from the state directory (never keys.json or m14-seeds.json), the
committed regtest rehearsal (results/bitvm3-regtest.json) and the M14 self-test record
(results/m14-claim-selftest.json). Graph, claim, evaluation and payout records appear on the
page as soon as the run writes them; rerun this script and push to republish.
"""
from __future__ import annotations

import argparse
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXPLORER = "https://mempool.space/testnet4"
INSTANCES = [
    ("honest", "Honest claim", "The claimant hands over the labels of the real testnet4 proof. The circuit outputs accept, nobody can disprove, and the payout to P' matures after 6 blocks."),
    ("tampered-proof", "Tampered proof", "The same proof with one input bit flipped. The circuit outputs reject; the challenger spends the disprove leaf with that label and the bond goes back to the desk."),
    ("wrong-statement", "Wrong statement", "A valid proof of a different payment (the M16 mainnet one). The circuit pins this order's statement, so it outputs reject and the claim is disproved."),
]


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def events(state):
    p = os.path.join(state, "events.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data", "demo.json"))
    ap.add_argument("--gpu-tasks", type=int, help="tasks the GPU proof run has recorded, while it runs")
    a = ap.parse_args()

    pub = load(os.path.join(a.state, "public.json"))
    pay = load(os.path.join(a.state, "payment.json"))
    sc = load(os.path.join(a.state, "statement-check.json"))
    fs = load(os.path.join(a.state, "tn4-statement.json"))
    ev = events(a.state)
    regtest = load(os.path.join(ROOT, "results", "bitvm3-regtest.json"), {})
    selftest = load(os.path.join(ROOT, "results", "m14-claim-selftest.json"), {})
    wrap = load(os.path.join(a.state, "native-verify.json"), {})

    def last(kind, instance=None, event=None):
        hits = [e for e in ev if e.get("kind") == kind and (instance is None or e.get("instance") == instance)
                and (event is None or e.get("event") == event)]
        return hits[-1] if hits else None

    vault_txid = "7b4a8b64aebc14f82c6c87174652567baaa13c4e2368cbd9729bfee0e989c04e"
    vault_sats = {"honest": 25_000, "tampered-proof": 10_000, "wrong-statement": 10_000}
    vault_vout = {"honest": 0, "tampered-proof": 1, "wrong-statement": 2}
    instances = []
    for name, title, story in INSTANCES:
        g = load(os.path.join(a.state, f"graph-{name}.json"))
        evr = load(os.path.join(a.state, f"m14-eval-{name}.json"))
        d = g["describe"] if g else None
        claim = last("claim", name, "broadcast")
        payout = last("payout", name, "broadcast")
        disprove = last("disprove", name, "broadcast")
        sweep = last("payer_sweep", name, "broadcast")
        if payout or disprove:
            stage = "settled"
        elif claim:
            stage = "claimed"
        elif g:
            stage = "graph_signed"
        else:
            stage = "vault_funded"
        instances.append({
            "name": name, "title": title, "story": story, "stage": stage,
            "vault": {"outpoint": f"{vault_txid}:{vault_vout[name]}", "sats": vault_sats[name]},
            "graph": None if not d else {
                "claim_id": d["claim_id"], "claim_txid": d["claim"]["txid"], "k_sats": d["claim"]["k_sats"],
                "payout_txid": d["payout"]["txid"], "payout_sats": d["payout"]["sats"],
                "disprove_sats": d["disprove"]["sats"], "leaves": d["claim"]["leaves"],
                "ciphertext_commitment": g["m14_setup"]["ciphertext_commitment_blake3"],
                "reject_label_sha256": g["instance"]["reject_label_sha256"],
            },
            "evaluation": None if not evr else {
                "verdict": evr["verdict"], "ciphertexts": evr["ciphertexts"], "seconds": round(evr["seconds"]),
                "flipped_input_bit": evr.get("flipped_input_bit"), "proof_sha256": evr["proof_sha256"],
            },
            "txids": {k: (v or {}).get("txid") for k, v in
                      (("claim", claim), ("payout", payout), ("disprove", disprove), ("sweep", sweep))},
        })

    probes = [e for e in ev if e.get("kind") in ("refusal_probe", "disprove_with_accept_label")]
    gpu_done = wrap.get("status") == "verified" and wrap.get("statement") == fs
    st = sc or {}
    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "network": "testnet4",
        "explorer": EXPLORER,
        "source": "https://github.com/patrickdugan/Spiral/tree/main/in-and-out-burger",
        "addresses": {
            "burger": pub["burger"]["address"],
            "vault": pub["vault"]["address"],
            "payer": pub["payer"]["address"],
            "payout": st.get("payout", {}).get("address"),
        },
        "payment": {
            "txid": pay["txid"], "vout": pay["vout"], "sats": pay["sats"],
            "payer_pubkey": pay["payer_pubkey"],
            "block": st.get("payment", {}).get("block"),
            "confirmations_proven": st.get("payment", {}).get("confirmations"),
        },
        "statement": None if not st else {
            "sha256": st["statement_sha256"], "magic": st["network_magic"], "anchor": st["anchor"], "tip": st["tip"],
            "steps": st["steps"], "checks_passed": sum(1 for v in st["checks"].values() if v), "checks": len(st["checks"]),
            "program_vk_digest": (fs or {}).get("program_vk_digest"),
        },
        "payout_key": None if not st else {
            "tag": "IOB/payout-key", "P": st["payout"]["pubkey"], "t": st["payout"]["tweak"],
            "P_prime": st["payout"]["derived_pubkey"], "script_pubkey": st["payout"]["script_pubkey"],
            "address": st["payout"]["address"], "txid": pay["txid"], "vout": pay["vout"],
        },
        "pipeline": {
            "nova": {"anchor": 160_000, "tip": 161_016, "steps": 1016, "fold_seconds": 1155, "k": 1,
                     "nova_vk": "6894f4903a9ff9713111bb1076b61663ac3592ad3d51b697d58125403fc5c12a"},
            "m16": {"instructions": 21_160_588_597, "elf_sha256": "bb7d51b0352db50512ce4c6485d1a0b255a97dc05c3ebaf10ef7201604584790",
                    "program_vk_digest": "dfc68a5d579b86244a60ba0baee7852348cf0d2a3bb13910ebb95a3e625fcb60",
                    "cpu_execute_seconds": 1279},
            "gpu": {"done": gpu_done, "tasks_recorded": a.gpu_tasks},
            "m14": {"gates": 785_442_492, "input_bits": 8_635_080,
                    "selftest": {k: selftest.get(k) for k in ("verdict", "ciphertexts", "seconds", "peak_rss_gb", "proof", "statement")}},
        },
        "instances": instances,
        "transactions": [{"kind": e["kind"], "instance": e.get("instance"), "txid": e["txid"], "vsize": e.get("vsize"),
                          "note": e.get("note") or e.get("to")} for e in ev if e.get("event") == "broadcast"],
        "probes": probes,
        "regtest": {
            "all_pass": regtest.get("all_pass"), "node": regtest.get("node"),
            "checks": regtest.get("checks", []),
        },
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    print(f"wrote {a.out}: {len(data['transactions'])} transactions, stages "
          + ", ".join(f"{i['name']}={i['stage']}" for i in instances))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
