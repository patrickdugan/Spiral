#!/usr/bin/env python3
"""Build site/data/showcase.json from the committed evidence.

Every number on the showcase page comes from Private Signet/evidence/ or is
recomputed here with the same contract code the trials used (ab/shz_margin.py).

  python3 "Private Signet/site/build_data.py"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
EV = LAB / "evidence"
sys.path.insert(0, str(LAB / "ab"))

from shz_margin import (BookTrade, InverseContractSpec, book_payout_at_price,  # noqa: E402
                        compress_book_ranges, compress_cet_ranges)

REPO = "https://github.com/patrickdugan/Spiral"
TREE = f"{REPO}/blob/main/Private%20Signet"


def latest(folder: str, kind: str) -> dict:
    files = sorted((EV / folder).glob(f"*{kind}.json"))
    return json.loads(files[-1].read_text())


def trials(path: Path, suite: str) -> list[dict]:
    r = json.loads(path.read_text())
    return [{"suite": suite, "arm": t["arm"], "case": t["case"], "vsize": t["vsize"],
             "accepted": t["accepted"], "reasons": {k: v[:90] for k, v in t["reasons"].items()},
             "ok": t["matches_expectation"], "note": t.get("note", "")} for t in r["trials"]]


def main() -> None:
    proto = latest("signet-shz-prototype", "signet-shz-prototype")
    k1sig = latest("signet-shz-k1", "signet-shz-k1")
    k2sig = latest("signet-shz-k2", "signet-shz-k2")
    k1reg = json.loads((EV / "regtest/shz-k1-regtest.json").read_text())
    k2reg = json.loads((EV / "regtest/shz-k2-regtest.json").read_text())

    t1 = InverseContractSpec(1, 80_000, 625, 1_000)
    tri = [BookTrade(t1, "alice", "bob"),
           BookTrade(InverseContractSpec(1, 100_000, 500, 625), "bob", "carol"),
           BookTrade(InverseContractSpec(1, 125_000, 400, 400), "carol", "alice")]
    lo, hi, step = 40_000, 450_000, 1_000
    prices = list(range(lo, hi + 1, step))
    cets = compress_cet_ranges(t1, 20, 1)
    book_ranges = compress_book_ranges(tri, 20, 1)

    def in_view(r):
        return r.max_price_usd >= lo and r.min_price_usd <= hi

    data = {
        "generated_from": "Private Signet/evidence (committed receipts) + ab/shz_margin.py",
        "links": {
            "repo": REPO, "results": f"{TREE}/RESULTS.md", "evidence": f"{REPO}/tree/main/Private%20Signet/evidence",
            "k2_code": f"{TREE}/ab/shz_k2.py", "k1_code": f"{TREE}/ab/shz_k1.py", "frost_code": f"{TREE}/ab/shz_frost.py",
            "margin_code": f"{TREE}/ab/shz_margin.py", "shz_repo": "https://github.com/patrickdugan/SatsHedgeZero",
            "ci": {"prototype_k1": f"{REPO}/actions/runs/45282607416", "k2": f"{REPO}/actions/runs/45326772649"},
        },
        "prototype": {
            "funding_txid": proto["funding_txid"], "clearing_txid": proto["clearing_txid"],
            "clearing_vsize": proto["clearing_vsize"], "block": proto["settlement_block"],
            "versions": proto["versions"], "agreement": proto["agreement"],
            "fundings": [{"label": f["label"], "sats": f["sats"]} for f in proto["shz_receipt"]["funded_dlc_utxos"]],
            "outputs": [{"sats": o["sats"], "unspent_on": o["unspent_on"]} for o in proto["clearing_outputs"]],
            "probes": proto["probes"],
        },
        "trade1": {
            "spec": {"usd_notional": 1, "entry": 80_000, "long_margin": 625, "short_margin": 1_000,
                     "long_liq": t1.long_liquidation_price_usd(), "short_liq": t1.short_liquidation_price_usd()},
            "curve": [[p, t1.payout_at_price(p).long_sats] for p in prices],
            "total": t1.total_collateral_sats,
            "cets_total": len(cets),
            "cets": [[c.min_price_usd, c.max_price_usd, c.payout.long_sats, len(c.prefix_bits),
                      "".join(map(str, c.prefix_bits))] for c in cets if in_view(c)],
        },
        "book": {
            "parties": ["alice", "bob", "carol"],
            "trades": [{"long": t.long_party, "short": t.short_party, "entry": t.spec.entry_price_usd,
                        "long_margin": t.spec.long_margin_sats, "short_margin": t.spec.short_margin_sats} for t in tri],
            "curve": [[p] + [book_payout_at_price(tri, p)[x] for x in ("alice", "bob", "carol")] for p in prices],
            "ranges_total": len(book_ranges),
            "at_125k": book_payout_at_price(tri, 125_000),
        },
        "k1": {"regtest": {"contract": k1reg["contract"], "settle_leaf": k1reg["settle_leaf"],
                           "nodes": {k: v["version"] for k, v in k1reg["nodes"].items()}},
               "signet": {"transfer": {k: k1sig["transfer"][k] for k in ("txid", "vsize", "outputs", "block", "accepted_by_all")},
                          "double_sale": {"txid": k1sig["double_sale"]["txid"],
                                          "verdicts": {n: v["result"] for n, v in k1sig["double_sale"]["verdicts"].items()}},
                          "split": {"txid": k1sig["split"]["txid"], "block": k1sig["split"]["block"],
                                    "status": {n: (c or {}).get("status") for n, c in k1sig["split"]["chaintips"].items()}},
                          "versions": k1sig["versions"]}},
        "k2": {"single": {k: k2reg["single"][k] for k in ("cet_leaves", "leaves", "tree_depth_max", "leaf_bytes_max",
                                                          "transfer_leaf_bytes", "settle_vsize", "transfer_vsize",
                                                          "funding_sats", "settle_floor", "transfer_fee", "refund_csv")},
               "book": {k: k2reg["book"][k] for k in ("cet_leaves", "leaves", "tree_depth_max", "leaf_bytes_max",
                                                      "settle_vsize", "transfer_vsize", "funding_sats")},
               "oracle": {"threshold": k2reg["oracle"]["threshold"], "pubkey": k2reg["oracle"]["oracle_pubkey_x"],
                          "nonces": len(k2reg["oracle"]["digit_nonces_x"])},
               "signet": {
                   "versions": k2sig["versions"], "agreement": k2sig["agreement"],
                   "funding": k2sig["funding"]["txid"],
                   "transfer": {k: k2sig["transfer"][k] for k in ("txid", "vsize", "value", "block", "accepted_by_all")},
                   "mempool": {n: v.get("reject-reason") for n, v in k2sig["transfer_mempool"].items()},
                   "double_sale": {"txid": k2sig["double_sale"]["txid"],
                                   "verdicts": {n: v["result"] for n, v in k2sig["double_sale"]["verdicts"].items()}},
                   "split": {"txid": k2sig["split"]["txid"], "block": k2sig["split"]["block"],
                             "status": {n: (c or {}).get("status") for n, c in k2sig["split"]["chaintips"].items()}},
                   "settle": {k: k2sig["settle"][k] for k in ("txid", "vsize", "outputs", "block", "accepted_by_all")},
                   "book": {k: k2sig["book"][k] for k in ("txid", "vsize", "outputs", "block", "accepted_by_all")},
                   "refund": {k: k2sig["refund"][k] for k in ("txid", "vsize", "outputs", "block", "accepted_by_all")},
                   "refund_early": k2sig["refund_early_mempool"].get("reject-reason"),
               }},
        "sizes": [
            {"label": "SHZ cooperative clearing (3 trades, all parties sign)", "vsize": proto["clearing_vsize"], "kind": "shz"},
            {"label": "K1 settlement (1 trade)", "vsize": k1sig["transfer"]["vsize"], "kind": "k1"},
            {"label": "K2 settlement (1 trade)", "vsize": k2reg["single"]["settle_vsize"], "kind": "k2"},
            {"label": "K2 netted book (3 trades)", "vsize": k2reg["book"]["settle_vsize"], "kind": "k2"},
            {"label": "K2 transfer", "vsize": k2reg["single"]["transfer_vsize"], "kind": "k2"},
            {"label": "K2 refund after CSV", "vsize": next(t["vsize"] for t in k2reg["trials"] if t["case"].startswith("keyless refund")), "kind": "k2"},
        ],
        "trials": trials(EV / "regtest/shz-k1-regtest.json", "SHZ-K1") + trials(EV / "regtest/shz-k2-regtest.json", "SHZ-K2")
                  + trials(EV / "regtest/ab-regtest-csfs.json", "A/B + arm C"),
    }
    out = HERE / "data" / "showcase.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"{out} {out.stat().st_size} bytes, {len(data['trials'])} trials, {len(data['trade1']['cets'])} CETs in view")


if __name__ == "__main__":
    main()
